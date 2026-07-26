"""Fix KL03 Bocas del Toro candidate list corruption.

The enrichment CSV, external research queue, and batch 001 all contain
15 incorrect/incomplete candidate names for KL03.  This script replaces
the 18 KL03 rows with the canonical candidate list.

CANONICAL KL03 CANDIDATES (18):
  1. Alexandra Denikine
  2. Candice Cohen
  3. Michel Jeandel
  4. Sophie Guilloix
  5. Julie Bourdon
  6. Linda Delamarre
  7. Philippe Huquet
  8. Alexandre Bérard
  9. Richard Lecourt
 10. Sylvie Rivoal
 11. Sébastien Loew
 12. Valérie Dot
 13. Hélène Patry
 14. Moundir Zoughari
 15. Antoine Sanchez
 16. Moussa Niangane
 17. Delphine Bano
 18. Isabelle Seguin
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

ENRICHMENT_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_local_enrichment_v1.csv")
QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_external_research_queue_v1.csv")
BATCH_DIR = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_batches")
BATCH_001 = os.path.join(BATCH_DIR, "external_research_batch_001.csv")
RESULT_TMPL = os.path.join(BATCH_DIR, "external_research_batch_001_results_template.csv")

# Canonical KL03 candidates in Wikipedia episode table order
KL03_CANONICAL = [
    "Alexandra Denikine",
    "Candice Cohen",
    "Michel Jeandel",
    "Sophie Guilloix",
    "Julie Bourdon",
    "Linda Delamarre",
    "Philippe Huquet",
    "Alexandre Bérard",
    "Richard Lecourt",
    "Sylvie Rivoal",
    "Sébastien Loew",
    "Valérie Dot",
    "Hélène Patry",
    "Moundir Zoughari",
    "Antoine Sanchez",
    "Moussa Niangane",
    "Delphine Bano",
    "Isabelle Seguin",
]

# Keepers from current batch that are correct (for verification)
KL03_CORRECT_IN_CORRUPT = {"Isabelle Seguin", "Delphine Bano", "Moundir Zoughari"}
KL03_WRONG_IN_CORRUPT = {
    "Pascal Salviani", "Valérie", "Jean-Marc", "Cindy", "Marie-Laure",
    "Raphaël", "Patricia", "Richard", "Sylvie", "Odile", "Jean-Pierre",
    "Christine", "Philippe", "Nicolas", "Ludovic",
}


def make_canonical_key(name: str) -> str:
    """Produce candidate_season_key like KL03::alexandra denikine."""
    return f"KL03::{name.lower()}"


def make_search_query(name: str, query_type: str) -> str:
    """Generate search queries matching the existing format."""
    sn = "Koh-Lanta : Bocas del Toro"
    if query_type == "identity":
        return f'"""{name}"" ""Koh-Lanta"" {sn} 2003'
    elif query_type == "gender":
        return f'"""{name}"" ""Koh-Lanta"" candidat candidate homme femme'
    elif query_type == "profession":
        return f'"""{name}"" ""Koh-Lanta"" 2003 portrait métier profession'
    elif query_type == "physical":
        return f'"""{name}"" ""Koh-Lanta"" sport entrainement musclé athlétique'
    return ""


def fix_enrichment_csv():
    """Replace KL03 rows in the local enrichment CSV."""
    print("\n" + "=" * 60)
    print("FIXING: koh_lanta_global_local_enrichment_v1.csv")
    print("=" * 60)

    df = pd.read_csv(ENRICHMENT_CSV)

    # Identify KL03 rows (first 18 rows after header are KL03)
    kl03_mask = df["season_id"] == "KL03"
    kl03_count = kl03_mask.sum()
    print(f"  Found {kl03_count} KL03 rows")

    kl03_indices = df[kl03_mask].index.tolist()

    if len(kl03_indices) != 18:
        print(f"  ERROR: Expected 18 KL03 rows, found {len(kl03_indices)}")
        return False

    current_names = df.loc[kl03_indices, "candidate_name"].tolist()
    print(f"  Current names: {current_names}")
    print(f"  Expected:      {KL03_CANONICAL}")

    match_count = sum(1 for n in current_names if n in set(KL03_CANONICAL))
    print(f"  Matches: {match_count}/18")

    # Replace names
    for idx, name in zip(kl03_indices, KL03_CANONICAL):
        df.at[idx, "candidate_name"] = name
        df.at[idx, "candidate_name_normalized"] = name.lower()
        df.at[idx, "candidate_season_key"] = make_canonical_key(name)

    df.to_csv(ENRICHMENT_CSV, index=False, encoding="utf-8")

    # Verify
    df2 = pd.read_csv(ENRICHMENT_CSV)
    updated_names = df2[df2["season_id"] == "KL03"]["candidate_name"].tolist()
    if updated_names == KL03_CANONICAL:
        print(f"  [OK] Enrichment CSV fixed successfully")
        return True
    else:
        print(f"  ❌ Verification failed")
        print(f"     Got: {updated_names}")
        return False


def fix_queue_csv():
    """Replace KL03 rows in the external research queue CSV."""
    print("\n" + "=" * 60)
    print("FIXING: koh_lanta_global_external_research_queue_v1.csv")
    print("=" * 60)

    df = pd.read_csv(QUEUE_CSV)

    kl03_mask = df["season_id"] == "KL03"
    kl03_count = kl03_mask.sum()
    print(f"  Found {kl03_count} KL03 rows")

    kl03_indices = df[kl03_mask].index.tolist()

    if len(kl03_indices) != 18:
        print(f"  ERROR: Expected 18 KL03 rows, found {len(kl03_indices)}")
        return False

    for idx, name in zip(kl03_indices, KL03_CANONICAL):
        key = make_canonical_key(name)
        df.at[idx, "candidate_season_key"] = key
        df.at[idx, "candidate_name"] = name
        df.at[idx, "search_query_identity"] = make_search_query(name, "identity")
        df.at[idx, "search_query_gender"] = make_search_query(name, "gender")
        df.at[idx, "search_query_profession"] = make_search_query(name, "profession")
        df.at[idx, "search_query_physical_1"] = make_search_query(name, "physical")
        df.at[idx, "external_research_request"] = (
            f"Rechercher: profession exacte, pratique sportive, intensité, "
            f"musculature pour {name} (Koh-Lanta : Bocas del Toro, 2003)"
        )

    df.to_csv(QUEUE_CSV, index=False, encoding="utf-8")

    # Verify
    df2 = pd.read_csv(QUEUE_CSV)
    updated_names = df2[df2["season_id"] == "KL03"]["candidate_name"].tolist()
    if updated_names == KL03_CANONICAL:
        print(f"  [OK] Queue CSV fixed successfully")
        return True
    else:
        print(f"  ❌ Verification failed")
        return False


def regenerate_batch_001():
    """Re-run plan_external_research.py to regenerate batch files."""
    print("\n" + "=" * 60)
    print("REGENERATING: Batch 001 files")
    print("=" * 60)

    # Import and run plan_external_research main
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
    import plan_external_research as planner
    planner.main()

    # Verify batch 001
    df = pd.read_csv(BATCH_001)
    kl03_in_batch = df[df["season_id"] == "KL03"]
    kl13_in_batch = df[df["season_id"] == "KL13"]

    print(f"\n  Batch 001 KL03 candidates: {len(kl03_in_batch)}")
    print(f"  Batch 001 KL13 candidates: {len(kl13_in_batch)}")
    print(f"  Total: {len(df)}")

    kl03_names = kl03_in_batch["candidate_name"].tolist()
    print(f"  KL03 names: {kl03_names}")

    kl13_names = kl13_in_batch["candidate_name"].tolist()
    print(f"  KL13 names: {kl13_names}")

    errors = []

    if len(kl03_in_batch) != 18:
        errors.append(f"Expected 18 KL03, got {len(kl03_in_batch)}")
    if len(kl13_in_batch) != 2:
        errors.append(f"Expected 2 KL13, got {len(kl13_in_batch)}")
    if len(df) != 20:
        errors.append(f"Expected 20 total, got {len(df)}")

    # Check canonical names
    for name in KL03_CANONICAL:
        if name not in kl03_names:
            errors.append(f"Missing from batch: {name}")

    # Check that Pascal Salviani is NOT present
    if "Pascal Salviani" in kl03_names:
        errors.append("Pascal Salviani should NOT be in KL03 batch")

    # Check no bare names
    bad_bare = {"Valérie", "Richard", "Sylvie", "Philippe"}
    for name in kl03_names:
        if name in bad_bare:
            errors.append(f"Bare name in batch: {name}")

    if errors:
        print(f"\n  ❌ ERRORS:")
        for e in errors:
            print(f"     - {e}")
        return False
    else:
        print(f"\n  [OK] Batch 001 regenerated successfully")
        return True


def main():
    print("=" * 70)
    print("KL03 CORRUPTION FIX — Bocas del Toro")
    print("=" * 70)

    # Step 1: Fix enrichment CSV (root source)
    if not fix_enrichment_csv():
        print("\n❌ Failed at enrichment CSV fix. Aborting.")
        sys.exit(1)

    # Step 2: Fix queue CSV
    if not fix_queue_csv():
        print("\n❌ Failed at queue CSV fix. Aborting.")
        sys.exit(1)

    # Step 3: Regenerate batch 001
    if not regenerate_batch_001():
        print("\n❌ Failed at batch regeneration. Aborting.")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("[OK] ALL KL03 CORRUPTIONS FIXED SUCCESSFULLY")
    print("=" * 70)
    print(f"  - {ENRICHMENT_CSV}")
    print(f"  - {QUEUE_CSV}")
    print(f"  - {BATCH_001}")
    print(f"  - {RESULT_TMPL}")


if __name__ == "__main__":
    main()