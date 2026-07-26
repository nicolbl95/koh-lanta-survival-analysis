"""Unit tests — MUSCULAR_ATHLETIC_BINARY_V2."""

import pytest
import pandas as pd
import os
import json
import hashlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv")
METADATA_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1_metadata.json")
PHYSICAL_QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_physical_research_queue.csv")


class TestFrozenDescriptiveData:
    def test_frozen_csv_exists(self):
        assert os.path.exists(FROZEN_CSV)
    def test_frozen_csv_has_21_candidates(self):
        df = pd.read_csv(FROZEN_CSV); assert len(df) == 21
    def test_frozen_csv_physical_scores_empty(self):
        df = pd.read_csv(FROZEN_CSV); assert df["physical_score"].isna().all()


class TestMetadata:
    def test_metadata_sha256_matches_frozen_file(self):
        with open(FROZEN_CSV, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        with open(METADATA_JSON, "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["sha256"] == actual_hash


class TestQueueStructure:
    def test_has_v2_columns(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        for col in ("physical_positive_reason", "documented_muscular_build",
                     "muscularity_evidence_text", "manual_evidence_added_by"):
            assert col in df.columns

    def test_definition_version_v2(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        assert (df["physical_score_definition_version"] == "MUSCULAR_ATHLETIC_BINARY_V2").all()


class TestBinaryScore:
    def test_scores_only_0_1_or_null(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        scores = df["physical_score"].dropna()
        for s in scores:
            assert float(s) in (0, 1)

    def test_no_score_2_or_3(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        scores = df["physical_score"].dropna()
        assert not scores.isin([2, 3]).any()

    def test_all_score_1_have_positive_reason(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        for _, r in df[df["physical_score"].dropna() == 1.0].iterrows():
            assert str(r["physical_positive_reason"]) != ""

    def test_all_score_0_have_zero_reason(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        for _, r in df[df["physical_score"] == 0.0].iterrows():
            assert str(r["physical_zero_reason"]) != ""


# ─── Manual decisions ──────────────────────────────────────────────────────

class TestManualDecisionsV2:
    def test_laurence_corbellotti_score_0(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        row = df[df["candidate_name"] == "Laurence Corbellotti"]
        assert float(row["physical_score"].values[0]) == 0
        assert row["documented_muscular_build"].values[0] == False

    def test_romain_score_1_muscular(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        row = df[df["candidate_name"] == "Romain Palazzetti"]
        assert float(row["physical_score"].values[0]) == 1
        assert row["physical_positive_reason"].values[0] == "MUSCULAR_BUILD"
        assert row["documented_muscular_build"].values[0] == True

    def test_nicolas_score_1_muscular(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        row = df[df["candidate_name"] == "Nicolas Rouyé"]
        assert float(row["physical_score"].values[0]) == 1
        assert row["physical_positive_reason"].values[0] == "MUSCULAR_BUILD"
        assert row["documented_muscular_build"].values[0] == True

    def test_romain_nicolas_have_manual_excerpt(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        for name in ("Romain Palazzetti", "Nicolas Rouyé"):
            row = df[df["candidate_name"] == name]
            assert str(row["manual_evidence_exact_excerpt"].values[0]) != ""
            assert str(row["manual_evidence_added_by"].values[0]) == "USER"


class TestPositiveReasons:
    def test_valid_positive_reasons(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        valid = {"MUSCULAR_BUILD", "STRENGTH_OR_COMBAT_SPORT", "HIGH_PHYSICAL_TRAINING",
                 "ENDURANCE_TRAINING", "DIRECT_PHYSICAL_PROFESSION",
                 "MULTIPLE_QUALIFYING_INDICATORS", "", "nan"}
        for v in df["physical_positive_reason"].unique():
            assert str(v) in valid, f"Invalid positive_reason: {v}"


class TestNoImageAnalysis:
    def test_muscular_scores_not_from_image(self):
        df = pd.read_csv(PHYSICAL_QUEUE_CSV)
        muscular = df[df["physical_positive_reason"] == "MUSCULAR_BUILD"]
        for _, r in muscular.iterrows():
            assert "image" not in str(r["muscularity_evidence_text"]).lower()
            assert "photo" not in str(r["muscularity_evidence_text"]).lower()


class TestFrozenFileImmutability:
    def test_frozen_file_not_modified_by_test(self):
        with open(FROZEN_CSV, "rb") as f:
            original_hash = hashlib.sha256(f.read()).hexdigest()
        with open(FROZEN_CSV, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()
        assert current_hash == original_hash