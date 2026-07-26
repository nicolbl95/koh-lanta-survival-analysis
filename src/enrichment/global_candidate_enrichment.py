"""Global candidate enrichment pipeline — Local pass + Pilot mode.

--pilot: 20 diverse candidates for testing
--local-pass-all: Process ALL 320 non-Thailand candidates using local data only.
  No external web search. Strict rules: insufficient data → null.

Outputs:
  data/enrichment/koh_lanta_global_local_enrichment_v1.csv (341 rows)
  data/enrichment/koh_lanta_global_external_research_queue_v1.csv
  data/processed/global_local_enrichment_coverage_report.csv
  data/processed/global_local_enrichment_summary.json
  data/processed/global_local_physical_score_audit.csv
"""
import os, re, sys, json, hashlib, argparse
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

GLOBAL_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_global_audit_candidate_dataset.csv")
LOCAL_OUT = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_local_enrichment_v1.csv")
EXT_QUEUE = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_external_research_queue_v1.csv")
COV_REPORT = os.path.join(PROJECT_ROOT, "data", "processed", "global_local_enrichment_coverage_report.csv")
ENRICH_SUMMARY = os.path.join(PROJECT_ROOT, "data", "processed", "global_local_enrichment_summary.json")
PHYS_AUDIT = os.path.join(PROJECT_ROOT, "data", "processed", "global_local_physical_score_audit.csv")
THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]

# Also pilot files
PILOT_OUT = os.path.join(PROJECT_ROOT, "data", "enrichment", "global_enrichment_pilot_20.csv")
PILOT_QUEUE = os.path.join(PROJECT_ROOT, "data", "enrichment", "global_enrichment_pilot_research_queue.csv")
PILOT_REPORT = os.path.join(PROJECT_ROOT, "data", "processed", "global_enrichment_pilot_report.csv")
PILOT_SELECTION = os.path.join(PROJECT_ROOT, "data", "processed", "global_enrichment_pilot_selection.csv")
ZERO_AUDIT = os.path.join(PROJECT_ROOT, "data", "processed", "global_enrichment_pilot_zero_score_audit.csv")

PILOT_SIZE = 20
DIRECT_PHYSICAL_JOBS = {
    "pompier", "militaire", "soldat", "sergent", "gendarme", "policier",
    "boxeur", "boxeuse", "coach sportif", "sportif professionnel",
    "maître-nageur", "maitre-nageur", "préparateur physique",
    "combattant", "champion",
}
INTENSIVE_SPORTS = {
    "boxe", "mma", "judo", "karaté", "karate", "lutte", "escrime",
    "rugby", "football", "basket", "handball", "volley",
    "natation", "athlétisme", "crossfit", "musculation",
    "trail", "marathon", "triathlon", "escalade", "haltéro",
}
LIGHT_SPORTS = {"ping-pong", "tennis de table", "pétanque", "bowling", "fléchettes", "darts"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest()


def select_pilot(df):
    """Select 20 diverse candidates from ≥ 5 seasons."""
    non_thai = df[df["season_id"] != "KL18"].copy()
    selected = []
    for sid in ["KL33", "KL26"]:
        selected.append(non_thai[non_thai["season_id"] == sid].head(3))
    selected.append(non_thai[non_thai["season_id"] == "KL29"].head(3))
    selected.append(non_thai[non_thai["season_id"] == "KL15"].head(2))
    selected.append(non_thai[non_thai["season_id"] == "KL03"].head(2))
    selected.append(non_thai[non_thai["season_id"] == "KL01"].head(2))
    used = pd.concat(selected).index
    remaining = non_thai[~non_thai.index.isin(used)]
    needed = max(0, 20 - len(pd.concat(selected)))
    selected.append(remaining[remaining["season_year"].astype(int) >= 2020].head(needed))
    result = pd.concat(selected).drop_duplicates().head(PILOT_SIZE)
    if len(result["season_id"].unique()) < 5:
        raise ValueError(f"Need ≥ 5 seasons, got {len(result['season_id'].unique())}")
    return result


def enrich_one(r):
    """Enrich one candidate row dict using local data only."""
    r["local_enrichment_performed"] = True
    r["external_research_performed"] = False

    # --- Age ---
    r["age"] = None
    r["age_source_type"] = "NOT_AVAILABLE"
    r["age_review_status"] = "NOT_FOUND"
    raw_age = str(r.get("age_raw", "")) if pd.notna(r.get("age_raw")) else ""
    if raw_age.strip() and raw_age.lower() not in ("nan", "none", ""):
        try:
            val = int(re.findall(r'\d+', raw_age)[0])
            if 18 <= val <= 80:
                r["age"] = val
                r["age_source_type"] = "RAW_SEASON_TABLE"
                r["age_confidence"] = "HIGH"
                r["age_review_status"] = "VALIDATED"
        except (IndexError, ValueError):
            pass

    # --- Gender ---
    r["gender_normalized"] = "UNKNOWN"
    r["gender_local_evidence"] = ""
    r["gender_confidence"] = "UNKNOWN"
    r["gender_review_status"] = "NOT_FOUND"
    gr = str(r.get("gender_raw", "")).strip().upper() if pd.notna(r.get("gender_raw")) else ""
    if gr in ("F", "FEMALE"):
        r["gender_normalized"] = "FEMALE"; r["gender_confidence"] = "HIGH"; r["gender_review_status"] = "VALIDATED"
    elif gr in ("M", "MALE"):
        r["gender_normalized"] = "MALE"; r["gender_confidence"] = "HIGH"; r["gender_review_status"] = "VALIDATED"

    # --- Profession ---
    r["profession_normalized"] = None
    r["profession_local_evidence"] = ""
    r["profession_confidence"] = "UNKNOWN"
    r["profession_review_status"] = "NOT_FOUND"
    prof = str(r.get("profession_raw", "")) if pd.notna(r.get("profession_raw")) else ""
    if prof.strip() and prof.lower() not in ("nan", "none", ""):
        r["profession_normalized"] = prof.strip()
        r["profession_confidence"] = "MEDIUM"
        r["profession_review_status"] = "VALIDATED"
        r["profession_local_evidence"] = f"Source: {r.get('season_url', '')}"

    # --- Profile documentation assessment ---
    has_age = r["age"] is not None
    has_gender = r["gender_normalized"] in ("MALE", "FEMALE")
    has_prof = r["profession_normalized"] is not None
    r["profile_documentation_sufficient"] = bool(has_prof or (has_age and has_gender))
    r["local_evidence_fields_reviewed"] = "age_raw, gender_raw, profession_raw"

    # --- Physical score ---
    pl = r["profession_normalized"].lower() if r["profession_normalized"] else ""
    is_direct = any(kw in pl for kw in DIRECT_PHYSICAL_JOBS)
    has_intensive = any(kw in pl for kw in INTENSIVE_SPORTS)
    has_light = any(kw in pl for kw in LIGHT_SPORTS)

    if is_direct:
        r["physical_score"] = 1
        r["physical_score_confidence"] = "MEDIUM"
        r["physical_score_reviewer_status"] = "A_REVOIR"
        r["physical_score_justification"] = f"Profession physique directe: {r['profession_normalized']}"
        r["physical_positive_reason"] = "DIRECT_PHYSICAL_PROFESSION"
        r["physical_score_based_on_profession_only"] = True
        r["external_research_required"] = False
    elif has_intensive and not has_light:
        r["physical_score"] = 1
        r["physical_score_confidence"] = "MEDIUM"
        r["physical_score_reviewer_status"] = "A_REVOIR"
        r["physical_score_justification"] = f"Sport exigeant documenté: {r['profession_normalized']}"
        r["physical_positive_reason"] = "STRENGTH_OR_COMBAT_SPORT"
        r["physical_score_based_on_profession_only"] = False
        r["external_research_required"] = False
    elif r["profile_documentation_sufficient"] and not is_direct and not has_intensive:
        r["physical_score"] = 0
        r["physical_score_confidence"] = "MEDIUM"
        r["physical_score_reviewer_status"] = "VALIDATED"
        r["physical_score_justification"] = "Profil documenté, aucun indicateur physique qualifiant"
        r["physical_zero_reason"] = "COMPLETE_PROFILE_NO_QUALIFYING_INDICATOR"
        r["external_research_required"] = False
    else:
        r["physical_score"] = None
        r["physical_score_confidence"] = "UNKNOWN"
        r["physical_score_reviewer_status"] = "INSUFFICIENT_EVIDENCE"
        r["physical_score_justification"] = "Données locales insuffisantes pour le score physique"
        r["external_research_required"] = True

    # Enrichment status
    has_all = r["age"] is not None and r["gender_normalized"] in ("MALE", "FEMALE") and r["profession_normalized"] is not None
    r["enrichment_status"] = "LOCALLY_COMPLETE" if has_all else ("LOCALLY_PARTIAL" if has_prof or has_age else "EXTERNAL_RESEARCH_REQUIRED")
    r["enrichment_notes"] = "Passe locale uniquement, recherche externe non effectuée" if r.get("external_research_required") else "Données locales suffisantes"

    return r


def build_ext_queue(enriched_df, season_map):
    """Build external research queue."""
    ext = enriched_df[enriched_df["external_research_required"] == True].copy()
    rows = []
    for _, r in ext.iterrows():
        name = str(r["candidate_name"])
        sn = str(r.get("season_name", ""))
        sy = str(r.get("season_year", ""))
        rows.append({
            "candidate_season_key": r.get("candidate_season_key", ""),
            "season_id": r["season_id"], "season_name": sn, "season_year": sy,
            "candidate_name": name,
            "age_missing": r["age"] is None,
            "gender_missing": r["gender_normalized"] == "UNKNOWN",
            "profession_missing": r["profession_normalized"] is None,
            "physical_score_missing": pd.isna(r.get("physical_score")),
            "current_age": r["age"],
            "current_gender": r["gender_normalized"],
            "current_profession": str(r.get("profession_normalized", ""))[:80],
            "current_physical_score": r.get("physical_score"),
            "search_query_identity": f'"{name}" "Koh-Lanta" {sn} {sy}',
            "search_query_gender": f'"{name}" "Koh-Lanta" candidat candidate homme femme',
            "search_query_profession": f'"{name}" "Koh-Lanta" {sy} portrait métier profession',
            "search_query_physical_1": f'"{name}" "Koh-Lanta" sport entrainement musclé athlétique',
            "external_research_priority": "HIGH" if pd.isna(r.get("physical_score")) else "MEDIUM",
            "external_research_request": f"Rechercher: profession exacte, pratique sportive, intensité, musculature pour {name} ({sn}, {sy})",
            "research_status": "NOT_STARTED", "review_status": "A_REVOIR",
        })
    return pd.DataFrame(rows)


def coverage_report(enriched_df):
    """Generate per-season coverage report."""
    rows = []
    for sid in sorted(enriched_df["season_id"].unique()):
        df = enriched_df[enriched_df["season_id"] == sid]
        n = len(df)
        age_ok = int(df["age_review_status"].value_counts().get("VALIDATED", 0))
        gen_ok = int((df["gender_normalized"].isin(["MALE", "FEMALE"])).sum())
        prof_ok = int(df["profession_normalized"].notna().sum())
        ps1 = int((df["physical_score"] == 1).sum())
        ps0 = int((df["physical_score"] == 0).sum())
        psn = int(df["physical_score"].isna().sum())
        ext_n = int(df["external_research_required"].sum())
        rows.append({
            "season_name": df["season_name"].iloc[0], "candidate_count": n,
            "age_validated_count": age_ok, "gender_validated_count": gen_ok,
            "profession_validated_count": prof_ok,
            "physical_score_1_count": ps1, "physical_score_0_count": ps0,
            "physical_score_null_count": psn,
            "external_research_required_count": ext_n,
            "age_coverage": round(age_ok/n, 4) if n>0 else 0,
            "gender_coverage": round(gen_ok/n, 4) if n>0 else 0,
            "profession_coverage": round(prof_ok/n, 4) if n>0 else 0,
            "physical_score_non_null_coverage": round((ps1+ps0)/n, 4) if n>0 else 0,
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true", help="Pilot mode: 20 candidates")
    parser.add_argument("--local-pass-all", action="store_true", help="Process all 320 non-Thailand candidates")
    args = parser.parse_args()

    if not args.pilot and not args.local_pass_all:
        parser.print_help()
        return

    thai_hashes = {p: sha256_file(p) if os.path.exists(p) else None for p in THAILANDE_FILES}
    df = pd.read_csv(GLOBAL_CSV)
    config = json.load(open(os.path.join(PROJECT_ROOT, "config", "seasons.json"), encoding="utf-8"))
    season_map = {s["season_id"]: s for s in config["seasons"]}

    if args.pilot:
        return run_pilot(df, thai_hashes)

    # --- Local pass all ---
    print("=" * 70)
    print("ENRICHISSEMENT LOCAL — 320 CANDIDATS (PASSE COMPLÈTE)")
    print("=" * 70)

    # Backup stats
    before_age = int(df["age_raw"].notna().sum())
    before_gen = int(df["gender_raw"].notna().sum())
    phys_col = "physical_score"
    before_phys = int(df[phys_col].notna().sum()) if phys_col in df.columns else 0

    # Load Thailand frozen files for authoritative data
    thai_desc = pd.read_csv(os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"))
    thai_phys = pd.read_csv(os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"))
    thai_phys["name_key"] = thai_phys["candidate_name"].str.strip().str.lower()
    
    # Process each row
    rows = []
    thai_ages_restored = 0
    thai_phys_restored = 0
    for _, row in df.iterrows():
        r = row.to_dict()
        sid = str(r["season_id"])
        if sid == "KL18":
            # Preserve Thailand frozen data — use frozen files as authoritative source
            r["local_enrichment_performed"] = False
            r["external_research_performed"] = False
            r["enrichment_status"] = "VALIDATED_FROZEN"
            r["enrichment_notes"] = "Données gelées Thaïlande — inchangées"
            r["profile_documentation_sufficient"] = True
            r["age_review_status"] = "VALIDATED"
            
            # Restore age from frozen descriptive file
            name_key = str(r.get("candidate_name", "")).strip().lower()
            desc_match = thai_desc[thai_desc["candidate_name"].str.strip().str.lower() == name_key]
            phys_match = thai_phys[thai_phys["name_key"] == name_key]
            
            if len(desc_match) > 0:
                desc_row = desc_match.iloc[0]
                # Restore gender
                if pd.notna(desc_row.get("gender_normalized")):
                    r["gender_normalized"] = desc_row["gender_normalized"]
                    r["gender_confidence"] = "HIGH"
                    r["gender_review_status"] = "VALIDATED"
                # Restore age from age_raw
                age_raw_val = desc_row.get("age_raw") if pd.notna(desc_row.get("age_raw")) else r.get("age_raw")
                if pd.notna(age_raw_val) and str(age_raw_val).strip():
                    try:
                        val = int(re.findall(r'\d+', str(age_raw_val))[0])
                        if 18 <= val <= 80:
                            r["age"] = val
                            r["age_source_type"] = "FROZEN_DESCRIPTIVE"
                            r["age_confidence"] = "HIGH"
                            r["age_review_status"] = "VALIDATED"
                            thai_ages_restored += 1
                    except (IndexError, ValueError):
                        pass
            
            if len(phys_match) > 0:
                phys_row = phys_match.iloc[0]
                r["physical_score"] = phys_row.get("physical_score")
                r["physical_score_confidence"] = phys_row.get("physical_score_confidence", "HIGH")
                r["physical_score_reviewer_status"] = "VALIDATED"
                r["physical_score_justification"] = phys_row.get("physical_score_justification", "")
                r["physical_positive_reason"] = phys_row.get("physical_positive_reason", "")
                r["physical_zero_reason"] = phys_row.get("physical_zero_reason", "")
                r["external_research_required"] = False
                thai_phys_restored += 1
            
            rows.append(r)
        else:
            enriched = enrich_one(r)
            rows.append(enriched)
    
    print(f"Thailand: {thai_ages_restored} ages restored, {thai_phys_restored} physical scores restored")

    enriched_df = pd.DataFrame(rows)

    # Compute new stats
    after_age = int(enriched_df["age"].notna().sum()) if "age" in enriched_df.columns else 0
    after_gen = int(enriched_df["gender_normalized"].isin(["MALE", "FEMALE"]).sum())
    after_phys = int(enriched_df[phys_col].notna().sum()) if phys_col in enriched_df.columns else 0
    ps1 = int((enriched_df["physical_score"] == 1).sum())
    ps0 = int((enriched_df["physical_score"] == 0).sum())
    psn = int(enriched_df["physical_score"].isna().sum())
    ext_n = int(enriched_df["external_research_required"].sum())

    # Save
    os.makedirs(os.path.dirname(LOCAL_OUT), exist_ok=True)
    enriched_df.to_csv(LOCAL_OUT, index=False, encoding="utf-8")
    print(f"\nEnriched: {LOCAL_OUT} ({len(enriched_df)} candidates)")

    # External queue
    queue = build_ext_queue(enriched_df, season_map)
    queue.to_csv(EXT_QUEUE, index=False, encoding="utf-8")
    print(f"External queue: {EXT_QUEUE} ({len(queue)} candidates)")

    # Coverage report
    cov = coverage_report(enriched_df)
    cov.to_csv(COV_REPORT, index=False, encoding="utf-8")
    print(f"Coverage: {COV_REPORT}")

    # Physical score audit
    audit_rows = []
    for _, r in enriched_df.iterrows():
        ps = r.get("physical_score")
        audit_rows.append({
            "season_name": r.get("season_name", ""),
            "candidate_name": r.get("candidate_name", ""),
            "profession_normalized": str(r.get("profession_normalized", ""))[:80],
            "profile_documentation_sufficient": r.get("profile_documentation_sufficient", False),
            "physical_score": ps,
            "physical_positive_reason": r.get("physical_positive_reason", ""),
            "physical_zero_reason": r.get("physical_zero_reason", ""),
            "physical_score_justification": str(r.get("physical_score_justification", ""))[:120],
            "external_research_required": r.get("external_research_required", False),
            "audit_status": "PASS" if ps is not None or r.get("external_research_required") else "A_REVOIR",
            "audit_warning": "",
        })
    pd.DataFrame(audit_rows).to_csv(PHYS_AUDIT, index=False, encoding="utf-8")
    print(f"Audit: {PHYS_AUDIT}")

    # Summary JSON
    summary = {
        "candidate_count": 341, "thailand_frozen_count": 21,
        "new_candidates_processed": 320,
        "age_count_before": before_age, "age_count_after": after_age,
        "gender_count_before": before_gen, "gender_count_after": after_gen,
        "physical_score_count_before": before_phys, "physical_score_count_after": after_phys,
        "physical_score_1_count": ps1, "physical_score_0_count": ps0,
        "physical_score_null_count": psn,
        "external_research_queue_count": len(queue),
    }
    with open(ENRICH_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary: {ENRICH_SUMMARY}")

    # Verify integrity
    df2 = pd.read_csv(GLOBAL_CSV)
    assert len(df2) == 341
    for path, h in thai_hashes.items():
        if h and os.path.exists(path):
            assert sha256_file(path) == h, f"Modified: {os.path.basename(path)}"

    print(f"\n{'─'*70}")
    print(f"Stats: age {before_age}→{after_age}, gender {before_gen}→{after_gen}, phys {before_phys}→{after_phys}")
    print(f"Scores: 1={ps1}, 0={ps0}, null={psn}, external_queue={len(queue)}")
    print(f"Thailand: 21 frozen | Source: intact ✅")
    return enriched_df


def run_pilot(df, thai_hashes):
    """Original pilot mode."""
    pilot = select_pilot(df)
    rows = [enrich_one(row.to_dict()) for _, row in pilot.iterrows()]
    edf = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(PILOT_OUT), exist_ok=True)
    edf.to_csv(PILOT_OUT, index=False, encoding="utf-8")
    q = edf[edf["external_research_required"]==True]
    q[["season_id","season_name","candidate_name","gender_normalized","profession_normalized","physical_score"]].to_csv(PILOT_QUEUE, index=False, encoding="utf-8")
    print(f"Pilot: {len(edf)} candidates, queue={len(q)}")
    return edf


if __name__ == "__main__":
    main()