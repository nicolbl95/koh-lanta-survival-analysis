"""Final audit: diff report, source completeness, freeze readiness, score fixes."""
import os
import sys
import json
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_physical_research_queue.csv")
DIFF_REPORT_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_score_diff_report.csv")
AUDIT_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_audit_summary.json")

# Previous state (10 ones, 8 zeros, 3 nulls)
PREVIOUS_STATE = {
    "Céline Parat-Yeghiayan": "1", "Huw Francis": "1", "Carole Poncelet": "1",
    "Wendy Gervois": "1", 'Laurence "Lolo" Facione': "1",
    "Karima Neggaz": "1", "Gabriel Gubbels": "1",
    "Carine Cazals": "1", "Alain Chrisostome": "1", "Cécilia Siharaj": "1",
    "Charlie Vincent-Mussard": "0", "Marius Torterat": "0", "Amir Doukhan": "0",
    "Cassandre Girard": "0", "Julien Castro": "0", "Laureen Hugel": "0",
    "Steve Best": "0", "Pascal Salviani": "0",
    "Laurence Corbellotti": None, "Romain Palazzetti": None, "Nicolas Rouyé": None,
}


def main():
    print("=" * 70)
    print("AUDIT FINAL — SCORE PHYSIQUE BINAIRE")
    print("=" * 70)

    df = pd.read_csv(QUEUE_CSV)

    # ── Add audit columns ──────────────────────────────────────────────────
    if "manual_source_complete" not in df.columns:
        df["manual_source_complete"] = True
    if "physical_freeze_ready" not in df.columns:
        df["physical_freeze_ready"] = True

    # ── Fix Nicolas confidence (promotional → MEDIUM) ─────────────────────
    mask_nicolas = df["candidate_name"] == "Nicolas Rouyé"
    if mask_nicolas.any():
        df.loc[mask_nicolas, "physical_score_confidence"] = "MEDIUM"
        df.loc[mask_nicolas, "physical_score_justification"] = (
            "Nicolas est décrit dans une source promotionnelle comme sculpté par "
            "les sports de glisse, doté d'un corps d'Apollon et d'un physique musclé. "
            "Confiance limitée à MEDIUM en l'absence de source indépendante complémentaire."
        )

    # ── Mark incomplete manual sources ────────────────────────────────────
    for name in ("Romain Palazzetti", "Nicolas Rouyé"):
        mask = df["candidate_name"] == name
        if mask.any():
            url = str(df.loc[mask, "manual_evidence_source_url"].values[0] or "")
            if not url.strip():
                df.loc[mask, "manual_source_complete"] = False
                df.loc[mask, "physical_freeze_ready"] = False

    # ── Ensure profession-only scores don't have muscular_build=True ──────
    profession_only = df["physical_score_based_on_profession_only"].astype(str).str.lower() == "true"
    df.loc[profession_only, "documented_muscular_build"] = False

    # ── Build diff report ──────────────────────────────────────────────────
    diff_rows = []
    for _, r in df.iterrows():
        name = r["candidate_name"]
        prev = PREVIOUS_STATE.get(name, "")
        curr = r["physical_score"]
        # Normalize
        prev_str = str(prev) if prev is not None else ""
        curr_str = str(curr) if pd.notna(curr) and str(curr) != "" else ""
        prev_val = None if prev_str == "" else prev_str
        curr_val = None if curr_str == "" else curr_str
        changed = prev_val != curr_val

        reason = ""
        expected = True
        if changed:
            if name == "Romain Palazzetti":
                reason = "Manuel : gabarit musclé documenté → 1"
            elif name == "Nicolas Rouyé":
                reason = "Manuel : corps d'Apollon, sculpté → 1"
            elif name == "Laurence Corbellotti":
                reason = "Manuel : danse sans intensité suffisante → 0"
            else:
                reason = "CHANGEMENT INATTENDU — À VÉRIFIER"
                expected = False

        diff_rows.append({
            "candidate_name": name,
            "previous_physical_score": prev_val,
            "current_physical_score": curr_val,
            "score_changed": changed,
            "change_reason": reason,
            "expected_change": expected,
            "audit_status": "PASS" if (expected or not changed) else "FAIL",
        })

    diff_df = pd.DataFrame(diff_rows)
    os.makedirs(os.path.dirname(DIFF_REPORT_CSV), exist_ok=True)
    diff_df.to_csv(DIFF_REPORT_CSV, index=False, encoding="utf-8")
    print(f"Diff report : {DIFF_REPORT_CSV}")

    # ── Save updated queue ─────────────────────────────────────────────────
    df.to_csv(QUEUE_CSV, index=False, encoding="utf-8")
    print(f"File sauvegardée : {QUEUE_CSV}")

    # ── Audit summary JSON ─────────────────────────────────────────────────
    scores_1 = (df["physical_score"] == "1").sum()
    scores_0 = (df["physical_score"] == "0").sum()
    scores_null = df["physical_score"].isna().sum() + (df["physical_score"] == "").sum()

    high_conf = (df["physical_score_confidence"] == "HIGH").sum()
    medium_conf = (df["physical_score_confidence"] == "MEDIUM").sum()
    prof_only = (df["physical_score_based_on_profession_only"].astype(str).str.lower() == "true").sum()
    muscular = (df["documented_muscular_build"].astype(str).str.lower() == "true").sum()
    incomplete_manual = (~df["manual_source_complete"]).sum() if "manual_source_complete" in df.columns else 0
    freeze_ready = bool(df["physical_freeze_ready"].all()) if "physical_freeze_ready" in df.columns else False

    audit = {
        "physical_score_1": int(scores_1),
        "physical_score_0": int(scores_0),
        "physical_score_null": int(scores_null),
        "confidence_HIGH": int(high_conf),
        "confidence_MEDIUM": int(medium_conf),
        "profession_only_count": int(prof_only),
        "muscular_build_count": int(muscular),
        "manual_source_incomplete_count": int(incomplete_manual),
        "physical_freeze_ready": freeze_ready,
        "definition_version": "MUSCULAR_ATHLETIC_BINARY_V2",
    }
    with open(AUDIT_JSON, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"Audit JSON : {AUDIT_JSON}")

    # ── Display ────────────────────────────────────────────────────────────
    print("\nDIFF (scores modifiés) :")
    changed = diff_df[diff_df["score_changed"]]
    for _, r in changed.iterrows():
        print(f"  {r['candidate_name']:<28} {str(r['previous_physical_score']):>6} → {str(r['current_physical_score']):<6} {r['change_reason']}")

    unexpected = diff_df[diff_df["audit_status"] == "FAIL"]
    if len(unexpected) > 0:
        print(f"\n⚠ {len(unexpected)} CHANGEMENTS INATTENDUS !")
        for _, r in unexpected.iterrows():
            print(f"  {r['candidate_name']}: {r['change_reason']}")

    print("\nSCORES 1 (12 candidats) :")
    for _, r in df[df["physical_score"] == "1"].iterrows():
        print(f"  {r['candidate_name']:<28} reason={r['physical_positive_reason']:<30} "
              f"conf={r['physical_score_confidence']:<8} prof_only={r['physical_score_based_on_profession_only']} "
              f"muscular={r['documented_muscular_build']}")

    print("\nSCORES 0 (9 candidats) :")
    for _, r in df[df["physical_score"] == "0"].iterrows():
        print(f"  {r['candidate_name']:<28} zero_reason={r['physical_zero_reason']}")

    print(f"\nProfession-only scores : {prof_only}")
    print(f"Muscular build documented : {muscular}")
    print(f"URLs manuelles incomplètes : {incomplete_manual}")
    print(f"physical_freeze_ready : {freeze_ready}")

    return df


if __name__ == "__main__":
    df = main()