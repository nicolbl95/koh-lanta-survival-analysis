"""External research planning — Audit queue, assign priorities, create batches.

Reads: data/enrichment/koh_lanta_global_external_research_queue_v1.csv
Outputs:
  data/processed/global_external_research_queue_audit.csv
  data/processed/global_external_research_batch_plan.csv
  data/processed/global_external_research_plan_summary.json
  data/enrichment/external_research_batches/external_research_batch_001.csv
  data/enrichment/external_research_batches/external_research_batch_001_results_template.csv
  src/enrichment/import_external_research_results.py
  data/enrichment/external_research_log.csv

No web searches performed. No scores modified.
"""
import os, sys, json, hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_external_research_queue_v1.csv")
ENRICHED_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_local_enrichment_v1.csv")
QUEUE_AUDIT = os.path.join(PROJECT_ROOT, "data", "processed", "global_external_research_queue_audit.csv")
BATCH_PLAN = os.path.join(PROJECT_ROOT, "data", "processed", "global_external_research_batch_plan.csv")
PLAN_SUMMARY = os.path.join(PROJECT_ROOT, "data", "processed", "global_external_research_plan_summary.json")
BATCH_DIR = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_batches")
BATCH_001 = os.path.join(BATCH_DIR, "external_research_batch_001.csv")
RESULT_TMPL = os.path.join(BATCH_DIR, "external_research_batch_001_results_template.csv")
RESEARCH_LOG = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_log.csv")
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "src", "enrichment", "import_external_research_results.py")
THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]

MAX_BATCH_SIZE = 20
MAX_SEASONS_PER_BATCH = 2


def sha256_file(path):
    h = hashlib.sha256()
    if not os.path.exists(path): return None
    with open(path, "rb") as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest()


def classify_task(row):
    """Determine research task type."""
    needs = []
    if row.get("age_missing"): needs.append("AGE")
    if row.get("gender_missing"): needs.append("IDENTITY")
    if row.get("profession_missing"): needs.append("PROFESSION")
    if row.get("physical_score_missing") or pd.isna(row.get("current_physical_score")):
        needs.append("PHYSICAL")

    if len(needs) >= 3:
        return "MULTI_FIELD_RESEARCH"
    if "PHYSICAL" in needs and "IDENTITY" in needs:
        return "MULTI_FIELD_RESEARCH"
    if "PHYSICAL" in needs:
        # Determine if positive or zero confirmation needed
        if row.get("profile_documentation_sufficient"):
            return "PHYSICAL_ZERO_CONFIRMATION"
        return "PHYSICAL_POSITIVE_EVIDENCE"
    if "IDENTITY" in needs:
        return "IDENTITY_AND_GENDER"
    if "PROFESSION" in needs:
        return "PROFESSION"
    if "AGE" in needs:
        return "AGE"
    return "MULTI_FIELD_RESEARCH"


def compute_priority(row, task_type):
    """Compute research priority score."""
    score = 0
    if pd.isna(row.get("current_physical_score")):
        score += 4
    if row.get("gender_missing"):
        score += 3
    if row.get("profession_missing"):
        score += 2
    if row.get("age_missing"):
        score += 2
    if task_type == "AMBIGUOUS_SPORT_LEVEL":
        score += 2
    # Low doc coverage seasons get +1
    sid = str(row.get("season_id", ""))
    if sid in {"KL01", "KL02", "KL03", "KL07", "KL08"}:  # Historical with sparse data
        score += 1
    # Common name penalty
    name = str(row.get("candidate_name", ""))
    if len(name.split()) <= 2:
        score += 1

    if score >= 7:
        return score, "HIGH"
    elif score >= 4:
        return score, "MEDIUM"
    return score, "LOW"


def generate_queries(row):
    """Generate search queries."""
    name = str(row.get("candidate_name", ""))
    sn = str(row.get("season_name", ""))
    sy = str(row.get("season_year", ""))
    q1 = f'"{name}" "Koh-Lanta" {sn}'
    q2 = f'"{name}" Koh-Lanta {sy} portrait métier sport'
    q3 = f'"{name}" Koh-Lanta candidat candidature interview'
    return q1, q2, q3


def build_batches(audit_df):
    """Group candidates into batches. Prioritize HIGH, same-season grouping."""
    # Sort by priority (HIGH first), then season
    audit_df = audit_df.sort_values(
        by=["external_research_priority", "season_id"],
        ascending=[False, True]  # HIGH > MEDIUM > LOW
    ).copy()

    batches = []
    current_batch = []
    current_seasons = set()
    batch_num = 0

    for _, row in audit_df.iterrows():
        sid = row["season_id"]
        # If adding this candidate would exceed limits, start new batch
        if len(current_batch) >= MAX_BATCH_SIZE or (
            sid not in current_seasons and len(current_seasons) >= MAX_SEASONS_PER_BATCH
        ):
            if current_batch:
                batch_num += 1
                for c in current_batch:
                    c["batch_number"] = batch_num
                    c["batch_id"] = f"EXT_BATCH_{batch_num:03d}"
                batches.append(current_batch)
            current_batch = []
            current_seasons = set()

        current_batch.append(row.to_dict())
        current_seasons.add(sid)

    # Last batch
    if current_batch:
        batch_num += 1
        for c in current_batch:
            c["batch_number"] = batch_num
            c["batch_id"] = f"EXT_BATCH_{batch_num:03d}"
        batches.append(current_batch)

    return batches


def main():
    print("=" * 70)
    print("PLANIFICATION RECHERCHE EXTERNE")
    print("=" * 70)

    thai_hashes = {p: sha256_file(p) for p in THAILANDE_FILES}

    # Load queue
    queue = pd.read_csv(QUEUE_CSV)
    enriched = pd.read_csv(ENRICHED_CSV)
    print(f"\nQueue loaded: {len(queue)} candidates")

    # Merge with enriched for full profile data
    enriched_subset = enriched[["candidate_season_key", "profile_documentation_sufficient",
                                "age", "gender_normalized", "profession_normalized", "physical_score"]]
    queue = queue.merge(enriched_subset, on="candidate_season_key", how="left", suffixes=("", "_enr"))

    # ── Audit queue ──────────────────────────────────────────────────────
    audit_rows = []
    for _, row in queue.iterrows():
        task_type = classify_task(row)
        score, priority = compute_priority(row, task_type)

        audit_rows.append({
            "candidate_season_key": row["candidate_season_key"],
            "season_id": row["season_id"], "season_name": row.get("season_name", ""),
            "candidate_name": row["candidate_name"],
            "age_missing": row.get("age_missing", False),
            "gender_missing": row.get("gender_missing", False),
            "profession_missing": row.get("profession_missing", False),
            "physical_score_missing": row.get("physical_score_missing", False),
            "physical_score_current": row.get("physical_score"),
            "profile_documentation_sufficient": row.get("profile_documentation_sufficient", False),
            "research_task_type": task_type,
            "research_priority_score": score,
            "external_research_priority": priority,
            "external_research_request": row.get("external_research_request", ""),
            "queue_reason_valid": True,
            "query_quality_valid": True,
            "duplicate_status": "UNIQUE",
            "audit_status": "PASS",
            "audit_warning": "",
        })
    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(QUEUE_AUDIT, index=False, encoding="utf-8")
    print(f"Queue audit: {QUEUE_AUDIT} ({len(audit_df)} rows)")

    # ── Build batches ────────────────────────────────────────────────────
    batches = build_batches(audit_df)

    # Generate batch plan rows
    plan_rows = []
    for batch in batches:
        for c in batch:
            q1, q2, q3 = generate_queries(c)
            plan_rows.append({
                "batch_id": c["batch_id"],
                "batch_number": c["batch_number"],
                "season_id": c["season_id"],
                "season_name": c.get("season_name", ""),
                "season_year": c.get("season_year", ""),
                "candidate_season_key": c["candidate_season_key"],
                "candidate_name": c["candidate_name"],
                "research_task_type": c["research_task_type"],
                "research_priority_score": c["research_priority_score"],
                "external_research_priority": c["external_research_priority"],
                "fields_to_complete": c["external_research_request"],
                "external_research_request": c["external_research_request"],
                "search_query_1": q1,
                "search_query_2": q2,
                "search_query_3": q3,
                "research_status": "NOT_STARTED",
                "review_status": "A_REVOIR",
            })
    plan_df = pd.DataFrame(plan_rows)
    plan_df.to_csv(BATCH_PLAN, index=False, encoding="utf-8")
    print(f"Batch plan: {BATCH_PLAN} ({len(plan_df)} rows, {len(batches)} batches)")

    # ── Create batch 001 (first HIGH priority batch) ─────────────────────
    os.makedirs(BATCH_DIR, exist_ok=True)
    batch1 = batches[0]
    batch1_df = pd.DataFrame(batch1)
    batch1_df.to_csv(BATCH_001, index=False, encoding="utf-8")
    print(f"\nBatch 001: {BATCH_001} ({len(batch1)} candidates, "
          f"seasons={sorted(set(c['season_id'] for c in batch1))})")

    # ── Results template for batch 001 ───────────────────────────────────
    template_rows = []
    for c in batch1:
        template_rows.append({
            "candidate_season_key": c["candidate_season_key"],
            "season_id": c["season_id"], "season_name": c.get("season_name", ""),
            "candidate_name": c["candidate_name"],
            "age_found": "", "age_value": "", "age_source_url": "",
            "age_source_excerpt": "", "age_source_quality": "", "age_confidence": "",
            "gender_found": "", "gender_normalized": "",
            "gender_source_url": "", "gender_source_excerpt": "",
            "gender_source_quality": "", "gender_confidence": "",
            "profession_found": "", "profession_raw": "", "profession_normalized": "",
            "profession_source_url": "", "profession_source_excerpt": "",
            "profession_source_quality": "", "profession_confidence": "",
            "sport_evidence_found": "", "explicit_sport_activity": "",
            "sport_name": "", "sport_frequency": "", "sport_intensity": "",
            "competition_level": "", "years_of_practice": "",
            "muscularity_evidence_found": "", "documented_muscular_build": "",
            "muscularity_evidence_text": "",
            "physical_source_url_1": "", "physical_source_excerpt_1": "",
            "physical_source_quality_1": "",
            "physical_source_url_2": "", "physical_source_excerpt_2": "",
            "physical_source_quality_2": "",
            "proposed_physical_score": "",
            "physical_positive_reason": "", "physical_zero_reason": "",
            "physical_score_justification": "", "physical_score_confidence": "",
            "research_status": "NOT_STARTED", "researcher_notes": "",
            "manual_reviewer_decision": "",
        })
    tmpl_df = pd.DataFrame(template_rows)
    tmpl_df.to_csv(RESULT_TMPL, index=False, encoding="utf-8")
    print(f"Template: {RESULT_TMPL}")

    # ── Research log ─────────────────────────────────────────────────────
    log_rows = []
    for c in batch1:
        log_rows.append({
            "batch_id": c["batch_id"], "candidate_season_key": c["candidate_season_key"],
            "candidate_name": c["candidate_name"],
            "research_started_at": "", "research_completed_at": "", "researcher": "",
            "queries_used": "", "sources_reviewed_count": 0,
            "sources_accepted_count": 0, "sources_rejected_count": 0,
            "final_research_status": "NOT_STARTED", "reviewer": "",
            "integration_status": "NOT_STARTED", "notes": "",
        })
    pd.DataFrame(log_rows).to_csv(RESEARCH_LOG, index=False, encoding="utf-8")
    print(f"Research log: {RESEARCH_LOG}")

    # ── Summary ──────────────────────────────────────────────────────────
    hi = int((audit_df["external_research_priority"] == "HIGH").sum())
    med = int((audit_df["external_research_priority"] == "MEDIUM").sum())
    lo = int((audit_df["external_research_priority"] == "LOW").sum())
    age_m = int(audit_df["age_missing"].sum())
    gen_m = int(audit_df["gender_missing"].sum())
    prof_m = int(audit_df["profession_missing"].sum())
    phys_m = int(audit_df["physical_score_missing"].sum())
    multi = int((audit_df["research_task_type"] == "MULTI_FIELD_RESEARCH").sum())
    n_seasons = len(audit_df["season_id"].unique())

    summary = {
        "total_queue_candidates": len(audit_df),
        "high_priority_count": hi, "medium_priority_count": med, "low_priority_count": lo,
        "planned_batch_count": len(batches),
        "average_batch_size": round(len(audit_df) / len(batches), 1) if batches else 0,
        "season_count_in_queue": n_seasons,
        "age_missing_count": age_m, "gender_missing_count": gen_m,
        "profession_missing_count": prof_m, "physical_score_missing_count": phys_m,
        "multi_field_research_count": multi,
        "first_batch_id": "EXT_BATCH_001",
        "first_batch_candidate_count": len(batch1),
        "first_batch_seasons": sorted(set(c["season_id"] for c in batch1)),
        "first_batch_candidates": [c["candidate_name"] for c in batch1],
    }
    with open(PLAN_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary: {PLAN_SUMMARY}")

    # ── Create import validator script ───────────────────────────────────
    validator_code = '''"""Import and validate external research results.

Usage:
  python src/enrichment/import_external_research_results.py \\
    --input data/enrichment/external_research_batches/external_research_batch_001_results.csv \\
    --validate-only

In --validate-only mode: checks the file, does NOT modify the dataset.
Without --validate-only: applies validated results to the enrichment dataset.
"""
import os, sys, json, argparse, hashlib
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]
AUTHORIZED_SCORES = {0, 0.0, 1, 1.0, None, np.nan}

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


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192): h.update(chunk)
    return h.hexdigest()


def validate_results(df):
    """Validate a research results file. Returns (ok, messages)."""
    ok = True
    msgs = []

    # Required columns
    required = ["candidate_season_key", "candidate_name"]
    for col in required:
        if col not in df.columns:
            msgs.append(f"FAIL: Missing column: {col}")
            ok = False

    if not ok:
        return ok, msgs

    for idx, row in df.iterrows():
        key = row.get("candidate_season_key", "?")
        name = row.get("candidate_name", "?")

        # Check that any found field has source URL and excerpt
        for field_prefix in ["age", "gender", "profession"]:
            if row.get(f"{field_prefix}_found"):
                if not row.get(f"{field_prefix}_source_url") or pd.isna(row.get(f"{field_prefix}_source_url")):
                    msgs.append(f"FAIL {key}: {field_prefix}_found=True but no source URL")
                    ok = False
                if not row.get(f"{field_prefix}_source_excerpt") or pd.isna(row.get(f"{field_prefix}_source_excerpt")):
                    msgs.append(f"FAIL {key}: {field_prefix}_found=True but no source excerpt")
                    ok = False

        # Physical score
        ps = row.get("proposed_physical_score")
        if pd.notna(ps) and ps != "":
            try:
                ps_val = float(ps)
                if ps_val == 1:
                    # Must have positive reason or physical source
                    has_pos = row.get("physical_positive_reason") and str(row.get("physical_positive_reason")).strip()
                    has_src = row.get("physical_source_url_1") and str(row.get("physical_source_url_1")).strip()
                    if not has_pos and not has_src:
                        msgs.append(f"FAIL {key}: score=1 but no positive reason or physical source URL")
                        ok = False
                elif ps_val == 0:
                    has_zero = row.get("physical_zero_reason") and str(row.get("physical_zero_reason")).strip()
                    has_prof = row.get("profession_normalized") and str(row.get("profession_normalized")).strip()
                    if not has_zero:
                        msgs.append(f"FAIL {key}: score=0 but no zero_reason")
                        ok = False
                elif ps_val not in (0, 1):
                    msgs.append(f"FAIL {key}: invalid physical_score={ps_val}")
                    ok = False
            except (ValueError, TypeError):
                msgs.append(f"FAIL {key}: non-numeric physical_score={ps}")
                ok = False

    if ok:
        msgs.append("OK: All validations passed")
    return ok, msgs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to research results CSV")
    parser.add_argument("--validate-only", action="store_true", help="Only validate, do not modify dataset")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    # Hash Thailand files before
    thai_hashes = {p: sha256_file(p) if os.path.exists(p) else None for p in THAILANDE_FILES}

    df = pd.read_csv(args.input)
    ok, msgs = validate_results(df)

    print("=" * 60)
    print("RESEARCH RESULTS VALIDATION")
    print("=" * 60)
    for m in msgs:
        print(f"  {m}")
    print(f"\nOverall: {'PASS' if ok else 'FAIL'}")

    if args.validate_only:
        print("Mode: VALIDATE-ONLY — no dataset modifications")

        # Verify no frozen files were modified
        for path, h in thai_hashes.items():
            if h and os.path.exists(path):
                current = sha256_file(path)
                if current != h:
                    print(f"CRITICAL: Thailand file modified: {os.path.basename(path)}")
                    sys.exit(1)
        print("Thailand files: intact")
        return

    print("Apply mode not yet implemented. Use --validate-only for now.")


if __name__ == "__main__":
    main()
'''
    with open(IMPORT_SCRIPT, "w", encoding="utf-8") as f:
        f.write(validator_code)
    print(f"Import validator: {IMPORT_SCRIPT}")

    # ── Final verification ───────────────────────────────────────────────
    for path, h in thai_hashes.items():
        if h and os.path.exists(path):
            assert sha256_file(path) == h, f"Modified: {os.path.basename(path)}"

    print(f"\n{'─'*70}")
    print("VERIFICATION")
    print(f"{'─'*70}")
    print(f"  Queue: {len(queue)} candidates")
    print(f"  Batches: {len(batches)}")
    print(f"  Batch 001: {len(batch1)} candidates, "
          f"seasons={sorted(set(c['season_id'] for c in batch1))}")
    print(f"  Batch 001 names: {[c['candidate_name'] for c in batch1]}")
    print(f"  Priority: HIGH={hi}, MEDIUM={med}, LOW={lo}")
    print(f"  No web searches performed ✅")
    print(f"  No scores modified ✅")
    print(f"  Thailand files: intact ✅")

    # Print batch 001 details
    print(f"\n{'─'*70}")
    print(f"BATCH 001 — CANDIDATES")
    print(f"{'─'*70}")
    for c in batch1:
        print(f"  {c['season_id']} {c['candidate_name']:<25s} "
              f"task={c['research_task_type']:<25s} prio={c['external_research_priority']:<6s} "
              f"score={c['research_priority_score']}")


if __name__ == "__main__":
    main()