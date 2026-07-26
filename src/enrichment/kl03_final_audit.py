"""Final anti-regression audit for KL03 corruption fix.

Steps 1-5: Audit all KL03 sources, identify authoritative source,
verify keys, regenerate batch plan, audit incomplete names globally.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

KL03_CANONICAL = [
    "Alexandra Denikine", "Candice Cohen", "Michel Jeandel",
    "Sophie Guilloix", "Julie Bourdon", "Linda Delamarre",
    "Philippe Huquet", "Alexandre Bérard", "Richard Lecourt",
    "Sylvie Rivoal", "Sébastien Loew", "Valérie Dot",
    "Hélène Patry", "Moundir Zoughari", "Antoine Sanchez",
    "Moussa Niangane", "Delphine Bano", "Isabelle Seguin",
]

SET_CANONICAL = set(KL03_CANONICAL)
BARE_NAMES_RISK = {"Valérie", "Richard", "Sylvie", "Philippe"}

FILES_TO_AUDIT = [
    ("data/processed/koh_lanta_global_audit_candidate_dataset.csv", "audit_dataset"),
    ("data/enrichment/koh_lanta_global_local_enrichment_v1.csv", "enrichment"),
    ("data/enrichment/koh_lanta_global_external_research_queue_v1.csv", "queue"),
    ("data/processed/global_external_research_batch_plan.csv", "batch_plan"),
    ("data/enrichment/external_research_batches/external_research_batch_001.csv", "batch_001"),
    ("data/enrichment/external_research_batches/external_research_batch_001_results_template.csv", "template"),
]


def resolve_path(rel):
    return os.path.join(PROJECT_ROOT, rel)


def audit_kl03_in_file(rel_path, label):
    """Audit KL03 names in a single file."""
    path = resolve_path(rel_path)
    if not os.path.exists(path):
        return {
            "source_file": rel_path,
            "label": label,
            "row_count": 0,
            "kl03_row_count": 0,
            "canonical_name_count": 0,
            "unexpected_names": [],
            "missing_names": [],
            "status": "FILE_NOT_FOUND",
            "warnings": [],
        }

    df = pd.read_csv(path)
    kl03 = df[df["season_id"] == "KL03"] if "season_id" in df.columns else pd.DataFrame()
    kl03_count = len(kl03)
    kl03_names = set(kl03["candidate_name"].tolist()) if kl03_count > 0 else set()

    canonical_found = kl03_names & SET_CANONICAL
    unexpected = kl03_names - SET_CANONICAL
    missing = SET_CANONICAL - kl03_names

    warnings = []
    for name in kl03_names:
        if name in BARE_NAMES_RISK:
            warnings.append(f"Bare name in KL03: '{name}'")
    if "Pascal Salviani" in kl03_names:
        warnings.append("Pascal Salviani incorrectly in KL03")

    status = "PASS"
    if kl03_count != 18:
        status = "FAIL"
        warnings.append(f"Expected 18 KL03 rows, got {kl03_count}")
    if unexpected:
        status = "FAIL"
    if missing:
        status = "FAIL"

    return {
        "source_file": rel_path,
        "label": label,
        "total_rows": len(df),
        "kl03_row_count": kl03_count,
        "canonical_name_count": len(canonical_found),
        "unexpected_names": sorted(unexpected),
        "missing_names": sorted(missing),
        "status": status,
        "warnings": warnings,
    }


def verify_keys():
    """Verify KL03 candidate_season_keys are well-formed."""
    print("\n" + "=" * 60)
    print("STEP 3: KEY VERIFICATION")
    print("=" * 60)

    issues = []

    for rel_path, label in FILES_TO_AUDIT:
        path = resolve_path(rel_path)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path)
        if "season_id" not in df.columns or "candidate_season_key" not in df.columns:
            continue

        kl03 = df[df["season_id"] == "KL03"]
        if len(kl03) == 0:
            continue

        keys = kl03["candidate_season_key"].tolist()
        names = kl03["candidate_name"].tolist()

        # Check 18 unique keys
        if len(set(keys)) != 18:
            issues.append(f"{label}: Expected 18 unique keys, got {len(set(keys))}")

        # Check no single-name keys
        for key, name in zip(keys, names):
            key_suffix = key.split("::")[-1] if "::" in key else key
            if len(key_suffix.split()) <= 1:
                issues.append(f"{label}: Single-name key '{key}' for '{name}'")

            # Check key matches name
            expected_suffix = name.lower()
            if not key.endswith(f"::{expected_suffix}"):
                issues.append(f"{label}: Key mismatch: '{key}' vs expected suffix '{expected_suffix}'")

    if issues:
        print("  ❌ Key issues found:")
        for i in issues:
            print(f"     - {i}")
    else:
        print("  ✅ All KL03 keys verified: 18 unique, full names, no collisions")

    return issues


def regenerate_batch_plan():
    """Regenerate global_external_research_batch_plan.csv."""
    print("\n" + "=" * 60)
    print("STEP 4: REGENERATING BATCH PLAN")
    print("=" * 60)

    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
    import plan_external_research as planner
    planner.main()

    plan_path = resolve_path("data/processed/global_external_research_batch_plan.csv")
    df = pd.read_csv(plan_path)

    # Verify
    total = len(df)
    unique_candidates = df["candidate_season_key"].nunique()
    unique_batch_per_candidate = df.groupby("candidate_season_key")["batch_id"].nunique()

    print(f"  Total rows in plan: {total}")
    print(f"  Unique candidates: {unique_candidates}")
    print(f"  Candidates with >1 batch: {(unique_batch_per_candidate > 1).sum()}")

    # Batch 001 check
    b1 = df[df["batch_id"] == "EXT_BATCH_001"]
    b1_kl03 = b1[b1["season_id"] == "KL03"]
    b1_kl13 = b1[b1["season_id"] == "KL13"]
    print(f"  Batch 001: {len(b1)} total, KL03={len(b1_kl03)}, KL13={len(b1_kl13)}")

    # Check no bad KL03 lines
    kl03_all = df[df["season_id"] == "KL03"]
    kl03_bad = kl03_all[~kl03_all["candidate_name"].isin(SET_CANONICAL)]
    if len(kl03_bad) > 0:
        print(f"  ❌ Bad KL03 names in plan: {kl03_bad['candidate_name'].tolist()}")
        return False

    # Distribution check: 190 unique keys?
    print(f"  Season distribution: {df['season_id'].value_counts().to_dict()}")

    if unique_candidates != total:
        print(f"  ❌ {total - unique_candidates} duplicate candidate entries in plan")
        return False

    if len(b1) != 20 or len(b1_kl03) != 18 or len(b1_kl13) != 2:
        print(f"  ❌ Batch 001 composition incorrect")
        return False

    print("  ✅ Batch plan regenerated successfully")
    return True


def audit_incomplete_names():
    """Global audit of incomplete candidate names."""
    print("\n" + "=" * 60)
    print("STEP 5: GLOBAL INCOMPLETE NAME AUDIT")
    print("=" * 60)

    enrich_path = resolve_path("data/enrichment/koh_lanta_global_local_enrichment_v1.csv")
    df = pd.read_csv(enrich_path)

    audit_rows = []
    manual_review = []

    for _, row in df.iterrows():
        sid = row["season_id"]
        name = str(row["candidate_name"])
        key = row.get("candidate_season_key", "")
        words = name.split()

        classification = "OK"
        warnings = []

        # Single-word names
        if len(words) == 1:
            # Check if name looks like a note/artifact
            if "[" in name or "†" in name:
                classification = "REFERENCE_ARTIFACT"
                warnings.append(f"Reference artifact in name: {name}")
            elif name.isdigit() or name.replace(".", "").isdigit():
                classification = "REFERENCE_ARTIFACT"
                warnings.append(f"Numeric name: {name}")
            else:
                classification = "POSSIBLY_INCOMPLETE"
                warnings.append(f"Single-word name: {name}")

        # Check for Wikipedia note suffixes
        if "[ n " in name.lower() or "[n " in name.lower():
            classification = "REFERENCE_ARTIFACT"
            warnings.append(f"Wikipedia note suffix in name")
        if "†" in name:
            if classification == "OK":
                classification = "REFERENCE_ARTIFACT"
            warnings.append(f"Dagger/annotation in name")

        # Check for key using only line number
        key_suffix = key.split("::")[-1] if "::" in key else key
        if key_suffix.replace(" ", "").isdigit():
            if classification == "OK":
                classification = "REFERENCE_ARTIFACT"
            warnings.append(f"Key appears to use numeric disambiguation")

        audit_rows.append({
            "candidate_season_key": key,
            "season_id": sid,
            "candidate_name": name,
            "word_count": len(words),
            "classification": classification,
            "warnings": "; ".join(warnings) if warnings else "",
            "needs_review": classification != "OK",
        })

        if classification != "OK":
            manual_review.append({
                "season_id": sid,
                "candidate_name": name,
                "candidate_season_key": key,
                "classification": classification,
                "warnings": "; ".join(warnings),
            })

    audit_df = pd.DataFrame(audit_rows)
    out_path = resolve_path("data/processed/global_incomplete_candidate_names_audit.csv")
    audit_df.to_csv(out_path, index=False, encoding="utf-8")

    # Distribution
    dist = audit_df["classification"].value_counts()
    print(f"  Classification distribution:")
    for cls, cnt in dist.items():
        print(f"    {cls}: {cnt}")

    print(f"\n  🔍 Candidates needing review ({len(manual_review)}):")
    for item in manual_review:
        print(f"    [{item['classification']}] {item['season_id']} {item['candidate_name']}")
        if item["warnings"]:
            print(f"      → {item['warnings']}")

    # Duplicate detection within seasons
    print(f"\n  🔍 Duplicate names within same season:")
    for sid in sorted(df["season_id"].unique()):
        season_names = df[df["season_id"] == sid]["candidate_name"].tolist()
        name_counts = Counter(season_names)
        dupes = {n: c for n, c in name_counts.items() if c > 1}
        if dupes:
            print(f"    {sid}: {dupes}")

    print(f"\n  Audit saved: {out_path}")
    return manual_review


def find_authoritative_source():
    """Identify authoritative KL03 candidate source."""
    print("\n" + "=" * 60)
    print("STEP 2: AUTHORITATIVE SOURCE IDENTIFICATION")
    print("=" * 60)

    # The enrichment CSV is the root, but we need to check what feeds it
    # The scraper is the true authoritative source
    scraper_config = resolve_path("config/seasons.json")
    with open(scraper_config, "r", encoding="utf-8") as f:
        config = json.load(f)

    kl03_config = config.get("KL03", {})
    print(f"  KL03 Wikipedia URL: {kl03_config.get('url', 'N/A')}")
    print(f"  KL03 season name: {kl03_config.get('name', 'N/A')}")
    print(f"  KL03 year: {kl03_config.get('year', 'N/A')}")

    # The enrichment CSV is the authoritative processed source
    enrich_path = resolve_path("data/enrichment/koh_lanta_global_local_enrichment_v1.csv")
    enrich_df = pd.read_csv(enrich_path)
    kl03_enrich = enrich_df[enrich_df["season_id"] == "KL03"]
    enrich_names = set(kl03_enrich["candidate_name"].tolist())

    # Also check raw data
    raw_path = resolve_path("data/raw")
    raw_files = [f for f in os.listdir(raw_path) if os.path.isfile(os.path.join(raw_path, f)) and "kl03" in f.lower() or "bocas" in f.lower()]

    print(f"\n  KL03 raw files found: {raw_files}")

    # Create authoritative source audit
    audit_rows = []
    for rel_path, label in FILES_TO_AUDIT:
        result = audit_kl03_in_file(rel_path, label)
        audit_rows.append({
            "source_file": rel_path,
            "row_count": result["total_rows"],
            "canonical_name_count": result["canonical_name_count"],
            "unexpected_name_count": len(result["unexpected_names"]),
            "missing_name_count": len(result["missing_names"]),
            "is_authoritative": label == "enrichment",
            "audit_status": result["status"],
            "warnings": "; ".join(result["warnings"]),
        })

    # The enrichment file is authoritative
    audit_rows.append({
        "source_file": "config/seasons.json (KL03 entry)",
        "row_count": 1,
        "canonical_name_count": 18,
        "unexpected_name_count": 0,
        "missing_name_count": 0,
        "is_authoritative": False,
        "audit_status": "CONFIG_REFERENCE",
        "warnings": "Wikipedia URL used as seed for scraping",
    })

    audit_df = pd.DataFrame(audit_rows)
    out_path = resolve_path("data/processed/kl03_authoritative_source_audit.csv")
    audit_df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n  Authoritative source audit saved: {out_path}")
    print(f"  Authoritative source: koh_lanta_global_local_enrichment_v1.csv")

    if enrich_names != SET_CANONICAL:
        missing = SET_CANONICAL - enrich_names
        extra = enrich_names - SET_CANONICAL
        print(f"  ❌ Authoritative source NOT canonical!")
        if missing:
            print(f"     Missing: {sorted(missing)}")
        if extra:
            print(f"     Extra: {sorted(extra)}")
    else:
        print(f"  ✅ Authoritative source contains exactly the 18 canonical names")

    return audit_df


def main():
    print("=" * 70)
    print("KL03 FINAL ANTI-REGRESSION AUDIT")
    print("=" * 70)

    # Step 1: Audit all KL03 sources
    print("\n" + "=" * 60)
    print("STEP 1: KL03 AUDIT ACROSS ALL FILES")
    print("=" * 60)

    all_pass = True
    for rel_path, label in FILES_TO_AUDIT:
        result = audit_kl03_in_file(rel_path, label)
        print(f"\n  📄 {label} ({rel_path})")
        print(f"     Status: {result['status']}")
        print(f"     KL03 rows: {result['kl03_row_count']}")
        print(f"     Canonical matches: {result['canonical_name_count']}/18")
        if result["unexpected_names"]:
            print(f"     ❌ Unexpected: {result['unexpected_names']}")
        if result["missing_names"]:
            print(f"     ❌ Missing: {result['missing_names']}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"     ⚠ {w}")
        if result["status"] != "PASS":
            all_pass = False

    if all_pass:
        print(f"\n  ✅ ALL 6 FILES PASS KL03 AUDIT")
    else:
        print(f"\n  ❌ SOME FILES FAILED KL03 AUDIT")

    # Step 2: Find authoritative source
    authoritative_audit = find_authoritative_source()

    # Step 3: Verify keys
    key_issues = verify_keys()

    # Step 4: Regenerate batch plan
    plan_ok = regenerate_batch_plan()

    # Step 5: Audit incomplete names globally
    incomplete_review = audit_incomplete_names()

    # Overall status
    print("\n" + "=" * 70)
    print("AUDIT SUMMARY")
    print("=" * 70)
    print(f"  KL03 file audit: {'PASS' if all_pass else 'FAIL'}")
    print(f"  Key verification: {'PASS' if not key_issues else 'FAIL'}")
    print(f"  Batch plan: {'PASS' if plan_ok else 'FAIL'}")
    print(f"  Incomplete names flagged: {len(incomplete_review)}")
    print(f"\n  KL03 Canonical names (18):")
    for i, name in enumerate(KL03_CANONICAL, 1):
        print(f"    {i:2d}. {name}")


if __name__ == "__main__":
    main()