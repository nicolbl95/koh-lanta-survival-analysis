"""Import and validate external research results.

Usage:
  python src/enrichment/import_external_research_results.py \
    --input data/enrichment/external_research_batches/external_research_batch_001_results.csv \
    --validate-only

In --validate-only mode: checks the file, does NOT modify the dataset.
Without --validate-only: applies validated results to the enrichment dataset.
"""
import os, sys, json, argparse, hashlib, shutil, time
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]
AUTHORIZED_SCORES = {0, 0.0, 1, 1.0, None, np.nan}

GLOBAL_ENRICHMENT_PATH = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_local_enrichment_v1.csv")
EXTERNAL_RESEARCH_QUEUE_PATH = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_external_research_queue_v1.csv")
EXTERNAL_RESEARCH_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_log.csv")

DIRECT_PHYSICAL_JOBS = {
    "pompier", "militaire", "soldat", "sergent", "gendarme", "policier",
    "boxeur", "boxeuse", "coach sportif", "sportif professionnel",
    "maitre-nageur", "maitre-nageur", "preparateur physique",
    "combattant", "champion",
}
INTENSIVE_SPORTS = {
    "boxe", "mma", "judo", "karate", "karate", "lutte", "escrime",
    "rugby", "football", "basket", "handball", "volley",
    "natation", "athletisme", "crossfit", "musculation",
    "trail", "marathon", "triathlon", "escalade", "haltero",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def compute_batch_result_hash(df):
    """Compute a stable SHA256 hash from the results dataframe content.
    
    The hash covers: candidate_season_key and the result columns
    (age_found, gender_found, profession_found, proposed_physical_score,
    manual_reviewer_decision, research_status).
    This allows detecting if the same results are being re-imported.
    """
    key_cols = [
        "candidate_season_key",
        "age_found", "age_value", "gender_found", "gender_normalized",
        "profession_found", "profession_normalized",
        "proposed_physical_score", "manual_reviewer_decision", "research_status",
    ]
    available_cols = [c for c in key_cols if c in df.columns]
    sorted_df = df[available_cols].sort_values("candidate_season_key").reset_index(drop=True)
    content = sorted_df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def check_already_imported(batch_result_hash, log_path):
    """Check if this batch result hash already exists in the import log.
    
    Returns (already_imported, conflicting_hash) tuple.
    - already_imported: True if this exact result was previously imported
    - conflicting_hash: the previous hash if batch_id matches but content differs
    
    Checks both rows with integration_status == "IMPORTED" and legacy rows
    where action == "IMPORT" and batch_result_hash is present (integration_status
    may be NaN in older entries).
    """
    if not os.path.exists(log_path):
        return False, None
    
    try:
        existing = pd.read_csv(log_path)
    except Exception:
        return False, None
    
    if "batch_result_hash" not in existing.columns:
        return False, None
    
    # Check rows with integration_status == "IMPORTED" (new format)
    if "integration_status" in existing.columns:
        imported_new = existing[existing["integration_status"] == "IMPORTED"]
        for _, row in imported_new.iterrows():
            existing_hash = str(row.get("batch_result_hash", ""))
            if existing_hash == batch_result_hash:
                return True, None
    
    # Also check legacy rows where action == "IMPORT" and batch_result_hash is filled
    if "action" in existing.columns:
        imported_legacy = existing[
            (existing["action"] == "IMPORT") &
            existing["batch_result_hash"].notna() &
            (existing["batch_result_hash"] != "") &
            (existing["batch_result_hash"] != "nan")
        ]
        for _, row in imported_legacy.iterrows():
            existing_hash = str(row.get("batch_result_hash", ""))
            if existing_hash == batch_result_hash:
                return True, None
    
    # No exact match found
    return False, None


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
                    has_pos = row.get("physical_positive_reason") and str(row.get("physical_positive_reason")).strip()
                    has_src = row.get("physical_source_url_1") and str(row.get("physical_source_url_1")).strip()
                    if not has_pos and not has_src:
                        msgs.append(f"FAIL {key}: score=1 but no positive reason or physical source URL")
                        ok = False
                elif ps_val == 0:
                    has_zero = row.get("physical_zero_reason") and str(row.get("physical_zero_reason")).strip()
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


def apply_results(research_df, enrichment_df):
    """Apply validated research results to the enrichment dataframe.
    Returns (enrichment_df, stats_dict)."""
    stats = {
        "ages_added": 0,
        "genders_added": 0,
        "professions_added": 0,
        "scores_1_added": 0,
        "scores_0_added": 0,
        "scores_null": 0,
        "candidates_updated": 0,
    }

    # Ensure string-target columns are object dtype to avoid LossySetitemError
    string_columns = [
        "gender_local_evidence", "gender_confidence", "gender_review_status",
        "profession_local_evidence", "profession_confidence", "profession_review_status",
        "age_source_type", "age_confidence", "age_review_status",
        "physical_score_justification", "physical_score_confidence",
        "physical_score_reviewer_status", "physical_score_sources",
        "physical_positive_reason", "physical_zero_reason",
        "enrichment_status", "enrichment_notes",
        "gender_normalized", "profession_normalized",
    ]
    for col in string_columns:
        if col in enrichment_df.columns:
            enrichment_df[col] = enrichment_df[col].astype(object)

    # Index enrichment by candidate_season_key (lowercased for case-insensitive matching)
    enrichment_df_lower = enrichment_df.copy()
    enrichment_df_lower["_key_lower"] = enrichment_df_lower["candidate_season_key"].str.strip().str.lower()
    enrichment_indexed = enrichment_df_lower.set_index("_key_lower", drop=False)

    research_keys = set(research_df["candidate_season_key"].str.strip().str.lower())
    enrichment_keys = set(enrichment_df["candidate_season_key"].str.strip().str.lower())

    not_found = research_keys - enrichment_keys
    if not_found:
        print(f"WARNING: {len(not_found)} candidates in research results not found in enrichment dataset:")
        for k in sorted(not_found):
            print(f"  - {k}")

    timestamp = pd.Timestamp.now().isoformat()

    for idx, row in research_df.iterrows():
        key_raw = str(row["candidate_season_key"]).strip()
        key = key_raw.lower()

        if key not in enrichment_indexed.index:
            continue

        stats["candidates_updated"] += 1
        enrichment_idx = enrichment_indexed.index.get_loc(key)

        # --- Age ---
        if row.get("age_found") and pd.notna(row.get("age_value")):
            enrichment_df.at[enrichment_idx, "age"] = float(row["age_value"])
            enrichment_df.at[enrichment_idx, "age_source_type"] = str(row.get("age_source_url", ""))
            enrichment_df.at[enrichment_idx, "age_confidence"] = str(row.get("age_confidence", "HIGH"))
            enrichment_df.at[enrichment_idx, "age_review_status"] = "EXTERNAL_RESEARCH_VALIDATED"
            stats["ages_added"] += 1

        # --- Gender ---
        if row.get("gender_found") and pd.notna(row.get("gender_normalized")):
            enrichment_df.at[enrichment_idx, "gender_normalized"] = str(row["gender_normalized"]).strip().upper()
            enrichment_df.at[enrichment_idx, "gender_local_evidence"] = str(row.get("gender_source_excerpt", ""))
            enrichment_df.at[enrichment_idx, "gender_confidence"] = str(row.get("gender_confidence", "HIGH"))
            enrichment_df.at[enrichment_idx, "gender_review_status"] = "EXTERNAL_RESEARCH_VALIDATED"
            stats["genders_added"] += 1

        # --- Profession ---
        if row.get("profession_found") and pd.notna(row.get("profession_normalized")):
            enrichment_df.at[enrichment_idx, "profession_normalized"] = str(row["profession_normalized"]).strip()
            enrichment_df.at[enrichment_idx, "profession_local_evidence"] = str(row.get("profession_source_excerpt", ""))
            enrichment_df.at[enrichment_idx, "profession_confidence"] = str(row.get("profession_confidence", "HIGH"))
            enrichment_df.at[enrichment_idx, "profession_review_status"] = "EXTERNAL_RESEARCH_VALIDATED"
            stats["professions_added"] += 1

        # --- Physical Score ---
        ps = row.get("proposed_physical_score")
        if pd.notna(ps) and str(ps).strip() != "":
            ps_val = int(float(ps))
            enrichment_df.at[enrichment_idx, "physical_score"] = ps_val
            enrichment_df.at[enrichment_idx, "physical_score_justification"] = str(row.get("physical_score_justification", ""))
            enrichment_df.at[enrichment_idx, "physical_score_confidence"] = str(row.get("physical_score_confidence", "MEDIUM"))
            enrichment_df.at[enrichment_idx, "physical_score_reviewer_status"] = "EXTERNAL_RESEARCH_VALIDATED"

            # Build physical_score_sources from URLs
            sources = []
            for i in range(1, 3):
                url_col = f"physical_source_url_{i}"
                excerpt_col = f"physical_source_excerpt_{i}"
                if pd.notna(row.get(url_col)) and str(row.get(url_col)).strip():
                    sources.append(f"{row[url_col]} | {row.get(excerpt_col, '')}")
            enrichment_df.at[enrichment_idx, "physical_score_sources"] = " || ".join(sources)

            if ps_val == 1:
                enrichment_df.at[enrichment_idx, "physical_positive_reason"] = str(row.get("physical_positive_reason", ""))
                stats["scores_1_added"] += 1
            elif ps_val == 0:
                enrichment_df.at[enrichment_idx, "physical_zero_reason"] = str(row.get("physical_zero_reason", ""))
                stats["scores_0_added"] += 1
        else:
            # Score remains null / undetermined
            stats["scores_null"] += 1
            enrichment_df.at[enrichment_idx, "physical_score_reviewer_status"] = "INSUFFICIENT_EVIDENCE_EXTERNAL"

        # --- Global enrichment status ---
        enrichment_df.at[enrichment_idx, "external_research_performed"] = True

        # Determine enrichment_status based on manual_reviewer_decision
        decision = row.get("manual_reviewer_decision", "")
        research_status = row.get("research_status", "")

        if decision == "ACCEPT_PROPOSAL":
            enrichment_df.at[enrichment_idx, "enrichment_status"] = "EXTERNAL_RESEARCH_COMPLETE"
        elif decision == "NEEDS_MORE_RESEARCH":
            enrichment_df.at[enrichment_idx, "enrichment_status"] = "EXTERNAL_RESEARCH_PARTIAL"
            enrichment_df.at[enrichment_idx, "external_research_required"] = True
        else:
            enrichment_df.at[enrichment_idx, "enrichment_status"] = "EXTERNAL_RESEARCH_COMPLETE"

        enrichment_df.at[enrichment_idx, "enrichment_notes"] = str(row.get("researcher_notes", ""))

        # profile_documentation_sufficient
        if row.get("profile_documentation_sufficient"):
            enrichment_df.at[enrichment_idx, "profile_documentation_sufficient"] = True

    return enrichment_df, stats


def update_external_research_queue(research_df, queue_path):
    """Update the external research queue with the results."""
    if not os.path.exists(queue_path):
        print(f"WARNING: External research queue not found at {queue_path}")
        return

    queue_df = pd.read_csv(queue_path)
    queue_indexed = queue_df.set_index("candidate_season_key", drop=False)
    timestamp = pd.Timestamp.now().isoformat()

    updated = 0
    for idx, row in research_df.iterrows():
        key_raw = str(row["candidate_season_key"]).strip()
        key = key_raw.lower()

        if key not in queue_indexed.index:
            continue

        queue_idx = queue_indexed.index.get_loc(key)

        decision = row.get("manual_reviewer_decision", "")
        if decision == "ACCEPT_PROPOSAL":
            queue_df.at[queue_idx, "research_status"] = "COMPLETE"
            queue_df.at[queue_idx, "review_status"] = "VALIDATED"
        elif decision == "NEEDS_MORE_RESEARCH":
            queue_df.at[queue_idx, "research_status"] = "PARTIAL"
            queue_df.at[queue_idx, "review_status"] = "NEEDS_REVIEW"
        else:
            queue_df.at[queue_idx, "research_status"] = "PENDING_REVIEW"
            queue_df.at[queue_idx, "review_status"] = "A_REVOIR"

        # Update current values in queue
        if row.get("age_found") and pd.notna(row.get("age_value")):
            queue_df.at[queue_idx, "age_missing"] = False
        if row.get("gender_found"):
            queue_df.at[queue_idx, "gender_missing"] = False
        if row.get("profession_found"):
            queue_df.at[queue_idx, "profession_missing"] = False

        ps = row.get("proposed_physical_score")
        if pd.notna(ps) and str(ps).strip() != "":
            queue_df.at[queue_idx, "physical_score_missing"] = True
        else:
            queue_df.at[queue_idx, "physical_score_missing"] = True  # still missing if null

        updated += 1

    if updated > 0:
        queue_df.to_csv(queue_path, index=False)
        print(f"External research queue updated: {updated} candidates in {queue_path}")

    return updated


def append_to_log(research_df, log_path):
    """Append import event to the external research log (legacy, without hash/status)."""
    timestamp = pd.Timestamp.now().isoformat()
    log_entries = []
    for idx, row in research_df.iterrows():
        log_entries.append({
            "timestamp": timestamp,
            "candidate_season_key": row["candidate_season_key"],
            "candidate_name": row["candidate_name"],
            "action": "IMPORT",
            "age_imported": bool(row.get("age_found")),
            "gender_imported": bool(row.get("gender_found")),
            "profession_imported": bool(row.get("profession_found")),
            "physical_score": row.get("proposed_physical_score"),
            "decision": row.get("manual_reviewer_decision", ""),
        })

    log_df = pd.DataFrame(log_entries)
    if os.path.exists(log_path):
        existing = pd.read_csv(log_path)
        log_df = pd.concat([existing, log_df], ignore_index=True)
    log_df.to_csv(log_path, index=False)
    print(f"Log updated: {len(log_entries)} entries in {log_path}")


def append_to_log_with_hash(research_df, log_path, batch_result_hash, batch_id):
    """Append import event to the log with batch_result_hash and integration_status.
    
    This version includes idempotency fields that prevent duplicate imports.
    """
    timestamp = pd.Timestamp.now().isoformat()
    log_entries = []
    for idx, row in research_df.iterrows():
        log_entries.append({
            "timestamp": timestamp,
            "candidate_season_key": row["candidate_season_key"],
            "candidate_name": row["candidate_name"],
            "action": "IMPORT",
            "age_imported": bool(row.get("age_found")),
            "gender_imported": bool(row.get("gender_found")),
            "profession_imported": bool(row.get("profession_found")),
            "physical_score": row.get("proposed_physical_score"),
            "decision": row.get("manual_reviewer_decision", ""),
            "batch_id": batch_id,
            "batch_result_hash": batch_result_hash,
            "integration_status": "IMPORTED",
            "duplicate_import_attempt_count": "0",
        })

    log_df = pd.DataFrame(log_entries)
    if os.path.exists(log_path):
        existing = pd.read_csv(log_path)
        # Align columns
        for col in log_df.columns:
            if col not in existing.columns:
                existing[col] = ""
        for col in existing.columns:
            if col not in log_df.columns:
                log_df[col] = ""
        log_df = pd.concat([existing, log_df], ignore_index=True)
    log_df.to_csv(log_path, index=False)
    print(f"Log updated: {len(log_entries)} entries in {log_path}")


def verify_thailand_files(thai_hashes_before):
    """Verify frozen Thailand files are intact."""
    all_intact = True
    for path, h in thai_hashes_before.items():
        if h and os.path.exists(path):
            current = sha256_file(path)
            if current != h:
                print(f"CRITICAL: Thailand file modified: {os.path.basename(path)}")
                all_intact = False
    if all_intact:
        print("Thailand files: intact (verified)")
    else:
        print("CRITICAL: One or more Thailand files were modified!")
    return all_intact


def verify_post_import(enrichment_df_after, enrichment_df_before, research_keys):
    """Verify post-import integrity.

    The enrichment DataFrames are indexed by a lowercase-normalized version
    of candidate_season_key so that lookups match the lowercased research_keys
    (which come from the batch CSV where keys may differ in case).
    """
    print("\n" + "=" * 60)
    print("POST-IMPORT VERIFICATION")
    print("=" * 60)

    # Build lowercase-normalized index for case-insensitive lookup
    after_copy = enrichment_df_after.copy()
    after_copy["_key_lower"] = after_copy["candidate_season_key"].str.strip().str.lower()
    after_indexed = after_copy.set_index("_key_lower", drop=False)

    before_copy = enrichment_df_before.copy()
    before_copy["_key_lower"] = before_copy["candidate_season_key"].str.strip().str.lower()
    before_indexed = before_copy.set_index("_key_lower", drop=False)

    research_keys_lower = set(k.strip().lower() for k in research_keys)

    # Check which candidates changed
    changed_keys = []
    for key_lower in research_keys_lower:
        if key_lower in after_indexed.index and key_lower in before_indexed.index:
            before_row = before_indexed.loc[key_lower]
            after_row = after_indexed.loc[key_lower]
            # Compare key columns — a candidate is "modified" if at least one
            # importable column changed
            for col in ["age", "gender_normalized", "profession_normalized",
                         "physical_score", "external_research_performed",
                         "enrichment_status"]:
                bv = before_row[col] if col in before_row.index else None
                av = after_row[col] if col in after_row.index else None
                if pd.isna(bv) and pd.isna(av):
                    continue
                # Compare as strings to handle numeric/None/NaN uniformly
                bv_str = "" if pd.isna(bv) else str(bv).strip()
                av_str = "" if pd.isna(av) else str(av).strip()
                if bv_str != av_str:
                    changed_keys.append(key_lower)
                    break

    print(f"Candidates targeted by batch: {len(research_keys_lower)}")
    print(f"Candidates actually modified: {len(set(changed_keys))}")

    # Verify other candidates unchanged
    all_keys = set(enrichment_df_before["candidate_season_key"].str.strip().str.lower())
    non_research_keys = all_keys - research_keys_lower

    unchanged_count = 0
    changed_unexpected = []
    for key_lower in non_research_keys:
        if key_lower in after_indexed.index and key_lower in before_indexed.index:
            before_row = before_indexed.loc[key_lower]
            after_row = after_indexed.loc[key_lower]
            cols_to_compare = [c for c in enrichment_df_before.columns
                              if c not in ("scraped_at",)]
            is_same = True
            for col in cols_to_compare:
                if col not in before_row.index or col not in after_row.index:
                    continue
                bv = before_row[col]
                av = after_row[col]
                if pd.isna(bv) and pd.isna(av):
                    continue
                try:
                    bv_str = "" if pd.isna(bv) else str(bv).strip()
                    av_str = "" if pd.isna(av) else str(av).strip()
                    if bv_str != av_str:
                        is_same = False
                        changed_unexpected.append((key_lower, col, str(bv), str(av)))
                        break
                except (TypeError, AttributeError):
                    if bv != av:
                        is_same = False
                        changed_unexpected.append((key_lower, col, str(bv), str(av)))
                        break
            if is_same:
                unchanged_count += 1

    print(f"Non-target candidates unchanged: {unchanged_count}/{len(non_research_keys)}")
    if changed_unexpected:
        print(f"WARNING: {len(changed_unexpected)} unexpected changes detected:")
        for cu in changed_unexpected[:10]:
            print(f"  - {cu[0]}: {cu[1]} changed from '{cu[2]}' to '{cu[3]}'")
    else:
        print("All non-target candidates: unchanged")

    return len(research_keys_lower), len(set(changed_keys)), unchanged_count


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
    overall_msg = "\nOverall: {}".format("PASS" if ok else "FAIL")
    print(overall_msg)

    if args.validate_only:
        print("Mode: VALIDATE-ONLY -- no dataset modifications")
        verify_thailand_files(thai_hashes)
        return

    if not ok:
        print("Validation failed. Cannot proceed with import.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("IMPORT MODE")
    print("=" * 60)

    # --- Pre-import: backup global enrichment file ---
    if not os.path.exists(GLOBAL_ENRICHMENT_PATH):
        print(f"ERROR: Global enrichment file not found: {GLOBAL_ENRICHMENT_PATH}")
        sys.exit(1)

    backup_path = GLOBAL_ENRICHMENT_PATH + f".backup_{int(time.time())}"
    shutil.copy2(GLOBAL_ENRICHMENT_PATH, backup_path)
    print(f"Backup created: {backup_path}")

    # Calculate hash of the enrichment file before import
    hash_before = sha256_file(GLOBAL_ENRICHMENT_PATH)
    print(f"Pre-import SHA256: {hash_before}")

    # Verify Thailand files
    print(f"\nPre-import Thailand verification:")
    if not verify_thailand_files(thai_hashes):
        print("Aborting import.")
        sys.exit(1)

    # Read enrichment dataset
    enrichment_df_before = pd.read_csv(GLOBAL_ENRICHMENT_PATH)
    print(f"Enrichment dataset loaded: {len(enrichment_df_before)} candidates")

    # Verify batch candidates exist in enrichment
    research_keys = set(df["candidate_season_key"].str.strip().str.lower())
    enrichment_keys_before = set(enrichment_df_before["candidate_season_key"].str.strip().str.lower())
    missing = research_keys - enrichment_keys_before
    if missing:
        print(f"ERROR: {len(missing)} candidates from batch not found in enrichment dataset:")
        for k in sorted(missing):
            print(f"  - {k}")
        print("Aborting import.")
        sys.exit(1)

    print(f"All {len(research_keys)} batch candidates found in enrichment dataset.")

    # --- Idempotency check: compute batch result hash ---
    batch_result_hash = compute_batch_result_hash(df)
    print(f"Batch result hash: {batch_result_hash}")

    # Extract batch_id from results file (first row, if present)
    batch_id = str(df.iloc[0].get("batch_id", "UNKNOWN")) if "batch_id" in df.columns else "UNKNOWN"

    already_imported, _ = check_already_imported(batch_result_hash, EXTERNAL_RESEARCH_LOG_PATH)
    if already_imported:
        print("\n" + "=" * 60)
        print("IMPORT STATUS: ALREADY_IMPORTED")
        print("=" * 60)
        print(f"  batch_id: {batch_id}")
        print(f"  batch_result_hash: {batch_result_hash}")
        print(f"  integration_status = ALREADY_IMPORTED")
        print(f"  data_changed = False")
        print(f"  log_changed = False")
        print("\nThis exact batch has already been imported. No changes made.")
        verify_thailand_files(thai_hashes)
        return

    # --- Apply results ---
    enrichment_df_after, stats = apply_results(df, enrichment_df_before.copy())
    print(f"\n--- Apply Summary ---")
    print(f"  Candidates processed: {stats['candidates_updated']}")
    print(f"  Ages added:           {stats['ages_added']}")
    print(f"  Genders added:        {stats['genders_added']}")
    print(f"  Professions added:    {stats['professions_added']}")
    print(f"  Scores = 1 added:     {stats['scores_1_added']}")
    print(f"  Scores = 0 added:     {stats['scores_0_added']}")
    print(f"  Scores remaining null:{stats['scores_null']}")

    # --- Post-import verification ---
    verify_post_import(enrichment_df_after, enrichment_df_before, research_keys)

    # --- Verify Thailand files still intact ---
    print(f"\nPost-import Thailand verification:")
    thailand_ok = verify_thailand_files(thai_hashes)
    if not thailand_ok:
        print("RESTORING BACKUP due to Thailand file integrity issue.")
        shutil.copy2(backup_path, GLOBAL_ENRICHMENT_PATH)
        print(f"Backup restored from {backup_path}")
        sys.exit(1)

    # --- Write enriched dataset ---
    enrichment_df_after.to_csv(GLOBAL_ENRICHMENT_PATH, index=False)
    hash_after = sha256_file(GLOBAL_ENRICHMENT_PATH)
    print(f"\nPost-import SHA256: {hash_after}")
    print(f"Enrichment dataset saved: {GLOBAL_ENRICHMENT_PATH}")

    # --- Update external research queue ---
    update_external_research_queue(df, EXTERNAL_RESEARCH_QUEUE_PATH)

    # --- Append to log with batch_result_hash and integration_status ---
    append_to_log_with_hash(df, EXTERNAL_RESEARCH_LOG_PATH, batch_result_hash, batch_id)

    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()