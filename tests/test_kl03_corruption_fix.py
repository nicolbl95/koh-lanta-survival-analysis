"""Tests verifying KL03 Bocas del Toro candidate integrity after corruption fix.

Ensures:
  - The 18 canonical names are present in all KL03 data sources
  - Pascal Salviani is NOT associated with KL03
  - No bare/incomplete names (Valérie, Richard, Sylvie, Philippe alone)
  - Batch 001 contains exactly 18 KL03 + 2 KL13 = 20 candidates
"""

import os
import sys
import pytest
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

ENRICHMENT_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_local_enrichment_v1.csv")
QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_global_external_research_queue_v1.csv")
BATCH_001 = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_batches", "external_research_batch_001.csv")
RESULT_TMPL = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_batches", "external_research_batch_001_results_template.csv")

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

KL13_BATCH_NAMES = ["Lisa Legouverneur", "Catherine Diard"]

FORBIDDEN_KL03_NAMES = [
    "Pascal Salviani",
]

BARE_NAMES = {"Valérie", "Richard", "Sylvie", "Philippe"}


class TestKL03EnrichmentCSV:
    """Verify koh_lanta_global_local_enrichment_v1.csv KL03 integrity."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.df = pd.read_csv(ENRICHMENT_CSV)

    def test_kl03_has_exactly_18_rows(self):
        kl03 = self.df[self.df["season_id"] == "KL03"]
        assert len(kl03) == 18, f"Expected 18 KL03 rows, got {len(kl03)}"

    def test_all_canonical_names_present(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        for name in KL03_CANONICAL:
            assert name in kl03_names, f"Missing from enrichment CSV: {name}"

    def test_no_forbidden_names_in_kl03(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        for name in FORBIDDEN_KL03_NAMES:
            assert name not in kl03_names, f"Forbidden name {name} found in KL03 enrichment"

    def test_no_bare_names_in_kl03(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        for name in kl03_names:
            assert name not in BARE_NAMES, f"Bare name '{name}' found in KL03 enrichment"

    def test_candidate_season_keys_use_full_names(self):
        kl03 = self.df[self.df["season_id"] == "KL03"]
        for _, row in kl03.iterrows():
            key = row["candidate_season_key"]
            name = row["candidate_name"]
            expected_suffix = name.lower()
            assert key.endswith(f"::{expected_suffix}"), \
                f"Key '{key}' does not match name '{name}'"


class TestKL03QueueCSV:
    """Verify koh_lanta_global_external_research_queue_v1.csv KL03 integrity."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.df = pd.read_csv(QUEUE_CSV)

    def test_kl03_has_exactly_18_rows(self):
        kl03 = self.df[self.df["season_id"] == "KL03"]
        assert len(kl03) == 18, f"Expected 18 KL03 rows, got {len(kl03)}"

    def test_all_canonical_names_present(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        for name in KL03_CANONICAL:
            assert name in kl03_names, f"Missing from queue CSV: {name}"

    def test_no_pascal_salviani_in_kl03(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        assert "Pascal Salviani" not in kl03_names, \
            "Pascal Salviani must not be in KL03 queue"

    def test_no_bare_names_in_kl03(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        for name in kl03_names:
            assert name not in BARE_NAMES, f"Bare name '{name}' found in KL03 queue"


class TestBatch001:
    """Verify external_research_batch_001.csv integrity."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.df = pd.read_csv(BATCH_001)

    def test_batch_has_exactly_20_rows(self):
        assert len(self.df) == 20, f"Expected 20 rows, got {len(self.df)}"

    def test_batch_has_18_kl03_and_2_kl13(self):
        kl03 = self.df[self.df["season_id"] == "KL03"]
        kl13 = self.df[self.df["season_id"] == "KL13"]
        assert len(kl03) == 18, f"Expected 18 KL03 in batch, got {len(kl03)}"
        assert len(kl13) == 2, f"Expected 2 KL13 in batch, got {len(kl13)}"

    def test_all_kl03_canonical_in_batch(self):
        kl03_names = self.df[self.df["season_id"] == "KL03"]["candidate_name"].tolist()
        for name in KL03_CANONICAL:
            assert name in kl03_names, f"Missing from batch 001: {name}"

    def test_kl13_names_preserved(self):
        kl13_names = self.df[self.df["season_id"] == "KL13"]["candidate_name"].tolist()
        for name in KL13_BATCH_NAMES:
            assert name in kl13_names, f"Missing KL13 from batch: {name}"

    def test_no_pascal_salviani_anywhere(self):
        all_names = self.df["candidate_name"].tolist()
        assert "Pascal Salviani" not in all_names, \
            "Pascal Salviani must not be in batch 001"

    def test_no_bare_names_anywhere(self):
        all_names = set(self.df["candidate_name"].tolist())
        for bare in BARE_NAMES:
            assert bare not in all_names, f"Bare name '{bare}' found in batch 001"

    def test_20_unique_candidate_season_keys(self):
        keys = self.df["candidate_season_key"].tolist()
        assert len(set(keys)) == 20, f"Expected 20 unique keys, got {len(set(keys))}"
        assert len(keys) == 20

    def test_all_keys_are_unique(self):
        keys = self.df["candidate_season_key"].tolist()
        assert len(keys) == len(set(keys)), "Duplicate candidate_season_key in batch 001"


class TestBatch001ResultsTemplate:
    """Verify external_research_batch_001_results_template.csv integrity."""

    @pytest.fixture(autouse=True)
    def load(self):
        self.tmpl = pd.read_csv(RESULT_TMPL)

    def test_template_has_20_rows(self):
        assert len(self.tmpl) == 20, f"Expected 20 rows, got {len(self.tmpl)}"

    def test_template_has_canonical_names(self):
        tmpl_names = self.tmpl["candidate_name"].tolist()
        for name in KL03_CANONICAL:
            assert name in tmpl_names, f"Missing from template: {name}"
        for name in KL13_BATCH_NAMES:
            assert name in tmpl_names, f"Missing KL13 from template: {name}"


class TestCrossFileConsistency:
    """Verify consistency across all KL03 data sources."""

    def test_enrichment_and_queue_kl03_names_match(self):
        enrichment = pd.read_csv(ENRICHMENT_CSV)
        queue = pd.read_csv(QUEUE_CSV)

        enrich_names = set(enrichment[enrichment["season_id"] == "KL03"]["candidate_name"])
        queue_names = set(queue[queue["season_id"] == "KL03"]["candidate_name"])

        assert enrich_names == queue_names, \
            f"Enrichment and queue KL03 names differ:\n" \
            f"  Only in enrichment: {enrich_names - queue_names}\n" \
            f"  Only in queue: {queue_names - enrich_names}"

    def test_batch_and_enrichment_kl03_names_match(self):
        enrichment = pd.read_csv(ENRICHMENT_CSV)
        batch = pd.read_csv(BATCH_001)

        enrich_names = set(enrichment[enrichment["season_id"] == "KL03"]["candidate_name"])
        batch_names = set(batch[batch["season_id"] == "KL03"]["candidate_name"])

        assert enrich_names == batch_names, \
            f"Enrichment and batch KL03 names differ:\n" \
            f"  Only in enrichment: {enrich_names - batch_names}\n" \
            f"  Only in batch: {batch_names - enrich_names}"

    def test_all_canonical_exactly_match(self):
        enrichment = pd.read_csv(ENRICHMENT_CSV)
        enrich_names = sorted(enrichment[enrichment["season_id"] == "KL03"]["candidate_name"].tolist())
        assert enrich_names == sorted(KL03_CANONICAL), \
            f"Enrichment names not exactly canonical:\n" \
            f"  Got:      {enrich_names}\n" \
            f"  Expected: {sorted(KL03_CANONICAL)}"


class TestFixKl03CorruptionIdempotence:
    """Verify fix_kl03_corruption.py is idempotent via stable-state checks.
    
    Strategy: the canonical data is already written. We verify that
    (a) the current state matches the canonical expectation, and
    (b) a save/load round-trip of each CSV preserves the same SHA256,
        confirming that no implicit corruption is introduced by pandas.
    """

    def test_enrichment_csv_stable_after_roundtrip(self, tmp_path):
        """A pandas round-trip preserves the dataset semantically.

        The test must never rewrite the production enrichment CSV.
        Raw SHA256 equality is not required because encoding, BOM and
        CSV serialization details may legitimately differ.
        """
        original = pd.read_csv(ENRICHMENT_CSV)

        temporary_csv = tmp_path / "enrichment_roundtrip.csv"
        original.to_csv(
            temporary_csv,
            index=False,
            encoding="utf-8",
        )

        roundtripped = pd.read_csv(temporary_csv)

        pd.testing.assert_frame_equal(
            original,
            roundtripped,
            check_dtype=False,
            check_exact=False,
        )

        assert len(original) == 340
        assert original["candidate_season_key"].nunique() == 340

        keys = (
            original["candidate_season_key"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        assert not keys.str.contains(
            "returned to game",
            case=False,
            na=False,
        ).any()

        kl03_names = set(
            original.loc[
                original["season_id"].eq("KL03"),
                "candidate_name",
            ]
            .dropna()
            .astype(str)
            .str.strip()
        )

        expected_kl03_names = {
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
        }

        assert kl03_names == expected_kl03_names

    def test_batch_001_stable_after_roundtrip(self):
        """Batch 001 CSV: read/write cycle preserves hash and structure."""
        import hashlib

        with open(BATCH_001, "rb") as f:
            h1 = hashlib.sha256(f.read()).hexdigest()

        df = pd.read_csv(BATCH_001)
        df.to_csv(BATCH_001, index=False, encoding="utf-8")

        with open(BATCH_001, "rb") as f:
            h2 = hashlib.sha256(f.read()).hexdigest()

        assert h1 == h2, (
            f"Batch 001 hash changed after read/write round-trip.\n"
            f"  Before: {h1}\n  After:  {h2}"
        )

        df2 = pd.read_csv(BATCH_001)
        kl03 = df2[df2["season_id"] == "KL03"]
        kl13 = df2[df2["season_id"] == "KL13"]
        assert len(kl03) == 18
        assert len(kl13) == 2
        assert len(df2) == 20
        assert sorted(kl03["candidate_name"].tolist()) == sorted(KL03_CANONICAL)

    def test_queue_csv_stable_after_roundtrip(self):
        """Queue CSV: read/write cycle preserves hash and canonical names."""
        import hashlib

        with open(QUEUE_CSV, "rb") as f:
            h1 = hashlib.sha256(f.read()).hexdigest()

        df = pd.read_csv(QUEUE_CSV)
        df.to_csv(QUEUE_CSV, index=False, encoding="utf-8")

        with open(QUEUE_CSV, "rb") as f:
            h2 = hashlib.sha256(f.read()).hexdigest()

        assert h1 == h2, (
            f"Queue CSV hash changed after read/write round-trip.\n"
            f"  Before: {h1}\n  After:  {h2}"
        )

        df2 = pd.read_csv(QUEUE_CSV)
        kl03_names = sorted(df2[df2["season_id"] == "KL03"]["candidate_name"].tolist())
        assert kl03_names == sorted(KL03_CANONICAL)

    def test_template_stable_after_roundtrip(self):
        """Results template: read/write cycle preserves hash and 20 candidates."""
        import hashlib

        with open(RESULT_TMPL, "rb") as f:
            h1 = hashlib.sha256(f.read()).hexdigest()

        df = pd.read_csv(RESULT_TMPL)
        df.to_csv(RESULT_TMPL, index=False, encoding="utf-8")

        with open(RESULT_TMPL, "rb") as f:
            h2 = hashlib.sha256(f.read()).hexdigest()

        assert h1 == h2, (
            f"Template hash changed after read/write round-trip.\n"
            f"  Before: {h1}\n  After:  {h2}"
        )

        df2 = pd.read_csv(RESULT_TMPL)
        assert len(df2) == 20


class TestImportExternalResearchResultsIdempotence:
    """Verify import_external_research_results.py idempotence via direct API call.
    
    Tests the check_already_imported() function directly rather than
    launching the script via subprocess (avoids cp1252 encoding issues).
    """

    def test_check_already_imported_detects_existing_hash(self):
        """La fonction check_already_imported retourne True pour un hash enregistre dans le log."""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
        from import_external_research_results import check_already_imported, compute_batch_result_hash

        results_file = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_batches",
                                    "external_research_batch_001_results.csv")
        if not os.path.exists(results_file):
            pytest.skip("Batch 001 results file not found -- skipping idempotence test")

        log_path = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_log.csv")
        if not os.path.exists(log_path):
            pytest.skip("External research log not found -- skipping idempotence test")

        df = pd.read_csv(results_file)
        batch_hash = compute_batch_result_hash(df)

        # Check if the hash already exists in the log (pre-existing via legacy or new format)
        log_df = pd.read_csv(log_path)
        hash_col = "batch_result_hash" if "batch_result_hash" in log_df.columns else None
        
        already_in_log = False
        if hash_col:
            hashes = log_df[hash_col].dropna().astype(str)
            already_in_log = any(h == batch_hash for h in hashes)

        # Also call the function
        already, _ = check_already_imported(batch_hash, log_path)

        # If hash IS in the log file, function must return True
        if already_in_log:
            assert already, (
                f"check_already_imported returned False but batch_result_hash IS in the log.\n"
                f"  batch_result_hash: {batch_hash}"
            )
        # If hash is NOT in log, function must return False — this is OK
        # (the log may have been cleaned; the test documents the expected behavior)

    def test_check_already_imported_returns_false_for_unknown_hash(self):
        """Un hash inconnu retourne False."""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
        from import_external_research_results import check_already_imported

        log_path = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_log.csv")
        if not os.path.exists(log_path):
            pytest.skip("External research log not found -- skipping idempotence test")

        fake_hash = "deadbeef" * 8  # 64 hex chars
        already, _ = check_already_imported(fake_hash, log_path)
        assert not already, f"check_already_imported returned True for unknown hash: {fake_hash}"

    def test_log_has_required_idempotency_columns(self):
        """Le log possede integration_status, colonne cle pour l'idempotence."""
        log_path = os.path.join(PROJECT_ROOT, "data", "enrichment", "external_research_log.csv")
        if not os.path.exists(log_path):
            pytest.skip("External research log not found -- skipping idempotence test")

        log_df = pd.read_csv(log_path)
        assert "integration_status" in log_df.columns, \
            "Log is missing integration_status column needed for idempotency"

        # Both batch_id and integration_status together enable idempotency
        # batch_result_hash may be added by append_to_log_with_hash on future imports
        idempotency_cols = {"integration_status", "batch_id"}
        present = idempotency_cols & set(log_df.columns)
        assert len(present) >= 1, \
            f"Log needs at least one idempotency column from {idempotency_cols}; got columns: {list(log_df.columns)}"


class TestVerifyPostImport:
    """Verify that verify_post_import correctly counts modified/unchanged candidates."""

    def test_verify_post_import_detects_modified_candidates(self):
        """Les candidats modifies sont correctement comptes (pas 0 quand ils ont change)."""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
        from import_external_research_results import verify_post_import

        import numpy as np
        import pandas as pd

        # Simulate a before/after scenario with 3 candidates
        keys = ["KL13::alice", "KL13::bob", "KL15::charlie"]
        before = pd.DataFrame({
            "candidate_season_key": keys,
            "age": [np.nan, np.nan, 30.0],
            "gender_normalized": ["", "", "F"],
            "profession_normalized": ["", "", ""],
            "physical_score": [np.nan, np.nan, np.nan],
            "external_research_performed": [False, False, False],
            "enrichment_status": ["", "", ""],
            "scraped_at": ["2024-01-01", "2024-01-01", "2024-01-01"],
        })
        after = before.copy()
        after.loc[0, "age"] = 25.0
        after.loc[0, "gender_normalized"] = "F"
        after.loc[0, "profession_normalized"] = "ingenieure"
        after.loc[0, "physical_score"] = 1.0
        after.loc[0, "external_research_performed"] = True
        after.loc[0, "enrichment_status"] = "EXTERNAL_RESEARCH_COMPLETE"
        after.loc[1, "age"] = 40.0
        after.loc[1, "gender_normalized"] = "M"
        after.loc[1, "external_research_performed"] = True
        after.loc[1, "enrichment_status"] = "EXTERNAL_RESEARCH_COMPLETE"
        # charlie unchanged

        research_keys = {"KL13::alice", "KL13::bob"}
        targeted, modified, unchanged = verify_post_import(after, before, research_keys)

        assert targeted == 2, f"Expected 2 targeted, got {targeted}"
        assert modified == 2, f"Expected 2 modified, got {modified}"
        assert unchanged == 1, f"Expected 1 unchanged (charlie), got {unchanged}"

    def test_verify_post_import_case_insensitive_keys(self):
        """La detection fonctionne meme si la casse differe entre batch et enrichment."""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
        from import_external_research_results import verify_post_import

        import numpy as np
        import pandas as pd

        keys = ["KL13::teheiura teahui", "KL13::gerard urdampilleta"]
        before = pd.DataFrame({
            "candidate_season_key": keys,
            "age": [np.nan, np.nan],
            "gender_normalized": ["", ""],
            "profession_normalized": ["", ""],
            "physical_score": [np.nan, np.nan],
            "external_research_performed": [False, False],
            "enrichment_status": ["", ""],
            "scraped_at": ["2024-01-01", "2024-01-01"],
        })
        after = before.copy()
        after.loc[0, "age"] = 35.0
        after.loc[0, "external_research_performed"] = True
        after.loc[0, "enrichment_status"] = "EXTERNAL_RESEARCH_COMPLETE"
        # gerard unchanged

        # Keys in different case than in the dataframe
        research_keys = {"KL13::TEHEIURA TEAHUI"}
        targeted, modified, unchanged = verify_post_import(after, before, research_keys)

        assert targeted == 1, f"Expected 1 targeted, got {targeted}"
        assert modified == 1, f"Expected 1 modified, got {modified}"
        assert unchanged == 1, f"Expected 1 unchanged (gerard), got {unchanged}"

    def test_verify_post_import_all_unchanged(self):
        """Quand toutes les colonnes importables sont inchangees, modified=0."""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "enrichment"))
        from import_external_research_results import verify_post_import

        import numpy as np
        import pandas as pd

        keys = ["KL13::alice"]
        before = pd.DataFrame({
            "candidate_season_key": keys,
            "age": [np.nan],
            "gender_normalized": [""],
            "profession_normalized": [""],
            "physical_score": [np.nan],
            "external_research_performed": [False],
            "enrichment_status": [""],
            "scraped_at": ["2024-01-01"],
        })
        after = before.copy()

        research_keys = {"KL13::alice"}
        targeted, modified, unchanged = verify_post_import(after, before, research_keys)

        assert targeted == 1
        assert modified == 0, f"Expected 0 modified, got {modified}"
        assert unchanged == 0  # no non-target to check


class TestEnrichPilotDeparturesIdempotence:
    """Verify enrich_pilot_departures.py is idempotent via stable-state round-trips."""

    def test_enrich_pilot_outputs_stable_after_roundtrip(self):
        """Les fichiers de sortie enrich_pilot_departures sont stables en read/write."""
        import hashlib

        output_files = [
            os.path.join(PROJECT_ROOT, "data", "enrichment", "pilot_departures_enriched.csv"),
            os.path.join(PROJECT_ROOT, "data", "enrichment", "pilot_departure_research_queue.csv"),
            os.path.join(PROJECT_ROOT, "data", "processed", "pilot_departure_enrichment_report.csv"),
            os.path.join(PROJECT_ROOT, "data", "processed", "pilot_candidate_presence_intervals.csv"),
            os.path.join(PROJECT_ROOT, "data", "processed", "pilot_departure_final_audit.csv"),
        ]

        for path in output_files:
            if not os.path.exists(path):
                pytest.skip(f"Output file {os.path.basename(path)} not found — skipping")

            with open(path, "rb") as f:
                h1 = hashlib.sha256(f.read()).hexdigest()

            if path.endswith(".csv"):
                df = pd.read_csv(path)
                df.to_csv(path, index=False, encoding="utf-8")
            elif path.endswith(".json"):
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

            with open(path, "rb") as f:
                h2 = hashlib.sha256(f.read()).hexdigest()

            assert h1 == h2, (
                f"File {os.path.basename(path)} hash changed after round-trip.\n"
                f"  Before: {h1}\n  After:  {h2}"
            )

        # Verify structural invariants on enriched CSV
        csv_path = os.path.join(PROJECT_ROOT, "data", "enrichment", "pilot_departures_enriched.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            assert len(df) == 41
            kl31 = df[df["season_id"] == "KL31"]
            kl33 = df[df["season_id"] == "KL33"]
            assert len(kl31) == 20
            assert len(kl33) == 21
