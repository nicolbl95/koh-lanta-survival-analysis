"""Global dataset audit V2 — 17 primary seasons, proper source selection."""
import os, re, sys, json, hashlib, glob
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]

EXPECTED_SEASONS = 17
INCLUDED_SIDS = {
    "KL01","KL02","KL03","KL07","KL08","KL13","KL15","KL17",
    "KL18","KL31","KL22","KL32","KL33","KL25","KL26","KL27","KL29"
}

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest()

def normalize_name(name):
    return str(name).strip().lower()

def main():
    thai_hashes = {p: sha256_file(p) if os.path.exists(p) else None for p in THAILANDE_FILES}
    all_dfs = []

    # Load all standard season CSVs
    files = sorted(glob.glob(os.path.join(PROJECT_ROOT, "data", "raw", "seasons", "*_raw.csv")))
    for f in files:
        basename = os.path.basename(f)
        df = pd.read_csv(f)
        if "season_id" not in df.columns:
            if "koh_lanta_thailande" in basename:
                df["season_id"] = "KL18"
            else:
                continue
        sid = str(df["season_id"].iloc[0])
        if sid not in INCLUDED_SIDS:
            continue

        # For KL18, enrich with frozen physical scores and descriptive data
        if sid == "KL18":
            phys_path = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv")
            desc_path = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv")

            if os.path.exists(phys_path):
                phys = pd.read_csv(phys_path)
                phys["name_key"] = phys["candidate_name"].apply(normalize_name)
                df["name_key"] = df["candidate_name"].apply(normalize_name)

                # Copy physical_score column
                for col in ["physical_score", "physical_score_justification", "physical_score_sources"]:
                    if col in phys.columns:
                        phys_map = phys.set_index("name_key")[col].dropna().to_dict()
                        df[col] = df["name_key"].map(phys_map)
                        # Fill remaining with None
                        df[col] = df[col].where(pd.notna(df[col]), None)

            if os.path.exists(desc_path):
                desc = pd.read_csv(desc_path)
                desc["name_key"] = desc["candidate_name"].apply(normalize_name)
                # Copy validated descriptive columns (only string-type columns)
                string_cols = [c for c in desc.columns if c not in ("name_key", "candidate_name")
                               and desc[c].dtype == object]
                for col in string_cols:
                    if col in df.columns:
                        desc_map = desc.set_index("name_key")[col].dropna().to_dict()
                        mapped = df["name_key"].map(desc_map)
                        # Only override if the mapped value is not None
                        df[col] = mapped.combine_first(df[col])

            df.drop(columns=["name_key"], inplace=True, errors="ignore")

            # Ensure all_cause_exit_event and censored_at_end are computed
            if "all_cause_exit_event" not in df.columns or df["all_cause_exit_event"].isna().all():
                df["all_cause_exit_event"] = df["departure_type_normalized"].apply(
                    lambda t: 0 if t in ("VAINQUEUR", "CO_VAINQUEUR") else 1)
            if "censored_at_end" not in df.columns or df["censored_at_end"].isna().all():
                df["censored_at_end"] = df["departure_type_normalized"].apply(
                    lambda t: True if t in ("VAINQUEUR", "CO_VAINQUEUR") else False)

        # Normalize names and create unique key
        df["candidate_name_normalized"] = df["candidate_name"].apply(normalize_name)
        df["candidate_season_key"] = df["season_id"] + "::" + df["candidate_name_normalized"]

        # Deduplicate: if two rows share the same normalized name, disambiguate
        dupes = df[df.duplicated(subset=["candidate_season_key"], keep=False)]
        if len(dupes) > 0:
            for idx in dupes.index:
                old_key = df.at[idx, "candidate_season_key"]
                df.at[idx, "candidate_season_key"] = f"{old_key}#row{int(df.at[idx, 'source_row_number'])}"

        all_dfs.append(df)

    global_df = pd.concat(all_dfs, ignore_index=True)
    n = len(global_df)
    sids = sorted(global_df["season_id"].unique())
    unique_keys = global_df["candidate_season_key"].nunique()

    print(f"{'='*70}")
    print(f"GLOBAL DATASET AUDIT V2")
    print(f"{'='*70}")
    print(f"\nSeasons: {len(sids)} (expected {EXPECTED_SEASONS})")
    print(f"Candidates: {n}")
    print(f"Unique keys: {unique_keys}")

    ok = True
    msgs = []

    if len(sids) == EXPECTED_SEASONS:
        msgs.append(f"OK 1: {EXPECTED_SEASONS} seasons")
    else:
        msgs.append(f"FAIL 1: {len(sids)} != {EXPECTED_SEASONS}"); ok = False

    if unique_keys == n:
        msgs.append(f"OK 2: {n} rows, {unique_keys} unique keys")
    else:
        msgs.append(f"FAIL 2: {n} rows, {unique_keys} unique keys"); ok = False

    excluded_present = set(sids) - INCLUDED_SIDS
    if not excluded_present:
        msgs.append("OK 3: No excluded seasons")
    else:
        msgs.append(f"FAIL 3: {excluded_present}"); ok = False

    missing = INCLUDED_SIDS - set(sids)
    if not missing:
        msgs.append("OK 4: No missing included seasons")
    else:
        msgs.append(f"FAIL 4: {missing}"); ok = False

    # Winners and censoring
    winners = global_df[global_df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
    non_winners = global_df[~global_df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
    w_ok = (winners["censored_at_end"] == True).all() and (winners["all_cause_exit_event"] == 0).all()
    nw_ok = (non_winners["all_cause_exit_event"] == 1).all()

    for sid in sids:
        df_s = global_df[global_df["season_id"] == sid]
        wc = len(df_s[df_s["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])])
        cc = int(df_s["censored_at_end"].sum())
        if not (wc >= 1 and wc == cc):
            msgs.append(f"FAIL 5 {sid}: winners={wc}, censored={cc}"); ok = False

    if w_ok and nw_ok:
        msgs.append("OK 5: Winners censored, non-winners event=1")
    else:
        msgs.append(f"FAIL 5: Censoring error (w_ok={w_ok}, nw_ok={nw_ok})"); ok = False

    # Thailand specific: Wendy
    kl18 = global_df[global_df["season_id"] == "KL18"]
    wendy = kl18[kl18["candidate_name"].str.contains("Wendy", na=False)]
    if len(wendy) > 0:
        w_cens = wendy["censored_at_end"].values[0]
        w_event = wendy["all_cause_exit_event"].values[0]
        if w_cens == True and w_event == 0:
            msgs.append("OK 6: Wendy censored correctly")
        else:
            msgs.append(f"FAIL 6: Wendy censored={w_cens}, event={w_event}"); ok = False

    # Coverage
    age_cov = int(global_df["age_raw"].notna().sum())
    gender_cov = int(global_df["gender_raw"].notna().sum())
    ps_col = "physical_score"
    phys_cov = int(global_df[ps_col].notna().sum()) if ps_col in global_df.columns else 0
    definitive = global_df[global_df["all_cause_exit_event"] == 1]
    indet_n = int((global_df["departure_type_normalized"] == "INDETERMINE").sum())
    known = definitive.shape[0] - int((definitive["departure_type_normalized"] == "INDETERMINE").sum())
    coverage = round(known / definitive.shape[0], 4) if definitive.shape[0] > 0 else 0.0

    # Thailand intact
    for path, orig_h in thai_hashes.items():
        if orig_h and os.path.exists(path) and sha256_file(path) != orig_h:
            msgs.append(f"FAIL: Thailand file modified: {os.path.basename(path)}"); ok = False
    if ok:
        msgs.append(f"OK 7: Thailand files intact")

    # Season inventory
    inv_rows = []
    for sid in sorted(set(sids) & INCLUDED_SIDS):
        df_s = global_df[global_df["season_id"] == sid]
        w_df = df_s[df_s["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        f_df = df_s[df_s["departure_type_normalized"] == "FINALISTE"]
        indet_s = int((df_s["departure_type_normalized"] == "INDETERMINE").sum())
        def_s = df_s[df_s["all_cause_exit_event"] == 1]
        known_s = int(def_s.shape[0]) - int((def_s["departure_type_normalized"] == "INDETERMINE").sum())
        cov_s = round(known_s / def_s.shape[0], 4) if def_s.shape[0] > 0 else 0.0
        returns_s = int(df_s["returned_to_game"].sum())

        if cov_s >= 0.90: desc = "READY"
        elif cov_s >= 0.75: desc = "READY_WITH_WARNING"
        else: desc = "INSUFFICIENT"

        inv_rows.append({
            "season_id": sid, "season_name": df_s["season_name"].iloc[0],
            "candidate_count": len(df_s), "winner_count": len(w_df),
            "winner_names": "; ".join(w_df["candidate_name"].tolist()),
            "finalist_names": "; ".join(f_df["candidate_name"].tolist()) if len(f_df) > 0 else "",
            "departure_mechanism_coverage": cov_s,
            "indeterminate_departure_count": indet_s,
            "return_case_count": returns_s,
            "ready_for_all_cause_model": len(w_df) >= 1,
            "ready_for_descriptive_departure_statistics": desc,
            "audit_status": "PASS" if len(w_df) >= 1 else "FAIL",
        })

    proc_dir = os.path.join(PROJECT_ROOT, "data", "processed")
    os.makedirs(proc_dir, exist_ok=True)
    pd.DataFrame(inv_rows).to_csv(os.path.join(proc_dir, "global_season_inventory.csv"), index=False, encoding="utf-8")
    global_df.to_csv(os.path.join(proc_dir, "koh_lanta_global_audit_candidate_dataset.csv"), index=False, encoding="utf-8")

    summary = {
        "configuration_version": "CLASSIC_SEASONS_V5",
        "season_count": len(sids), "candidate_count": n,
        "unique_candidate_season_key_count": unique_keys,
        "event_count": int(global_df["all_cause_exit_event"].sum()),
        "censored_count": int(global_df["censored_at_end"].sum()),
        "winner_count_total": int(len(winners)),
        "return_case_count": int(global_df["returned_to_game"].sum()),
        "indeterminate_departure_count": indet_n,
        "overall_departure_mechanism_coverage": coverage,
        "age_coverage": age_cov, "gender_coverage": gender_cov,
        "physical_score_coverage": phys_cov,
        "ready_for_global_enrichment": ok and len(sids) == EXPECTED_SEASONS and unique_keys == n,
        "ready_for_survival_model_after_enrichment": False,
        "audit_warnings": [m for m in msgs if "FAIL" in m or "WARN" in m],
    }
    with open(os.path.join(proc_dir, "global_dataset_audit_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'─'*70}")
    for m in msgs: print(f"  {m}")
    print(f"\n  Age: {age_cov}/{n}  Gender: {gender_cov}/{n}  Physical: {phys_cov}/{n}")
    print(f"  Departure mechanism coverage: {coverage:.1%}")
    print(f"  ready_for_global_enrichment: {summary['ready_for_global_enrichment']}")
    print(f"  ready_for_survival_model_after_enrichment: {False}")
    print(f"\nSeason breakdown:")
    for _, r in pd.DataFrame(inv_rows).iterrows():
        print(f"  {r['season_id']}: {r['candidate_count']:>2} cand, winners={r['winner_names'][:40]}, mech_cov={r['departure_mechanism_coverage']:.0%}")

    return global_df, summary

if __name__ == "__main__":
    main()