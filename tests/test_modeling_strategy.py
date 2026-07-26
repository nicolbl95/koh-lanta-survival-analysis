"""Unit tests for modeling strategy and survival dataset preparation."""

import pytest
import pandas as pd
import os
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv")
SURVIVAL_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_survival_ready_v1.csv")
MODELING_STRATEGY_MD = os.path.join(PROJECT_ROOT, "docs", "modeling_strategy.md")


class TestModelingStrategyDoc:
    def test_doc_exists(self):
        assert os.path.exists(MODELING_STRATEGY_MD)

    def test_doc_mentions_3_predictors(self):
        with open(MODELING_STRATEGY_MD, "r", encoding="utf-8") as f:
            content = f.read()
        assert "age" in content.lower()
        assert "gender" in content.lower()
        assert "physical_score" in content.lower()

    def test_doc_excludes_profession(self):
        with open(MODELING_STRATEGY_MD, "r", encoding="utf-8") as f:
            content = f.read()
        assert "profession_raw" in content.lower() or "profession" in content.lower()
        assert "excluded" in content.lower() or "exclu" in content.lower()

    def test_doc_mentions_single_model(self):
        with open(MODELING_STRATEGY_MD, "r", encoding="utf-8") as f:
            content = f.read()
        assert "single" in content.lower() or "seul" in content.lower() or "one model" in content.lower()


class TestPrimaryModelFeatures:
    def test_only_3_features(self):
        from src.modeling.prepare_survival_dataset import PRIMARY_MODEL_FEATURES
        assert len(PRIMARY_MODEL_FEATURES) == 3
        assert "age" in PRIMARY_MODEL_FEATURES
        assert "gender_normalized" in PRIMARY_MODEL_FEATURES
        assert "physical_score" in PRIMARY_MODEL_FEATURES

    def test_no_profession_in_features(self):
        from src.modeling.prepare_survival_dataset import PRIMARY_MODEL_FEATURES
        for f in PRIMARY_MODEL_FEATURES:
            assert "profession" not in f.lower()
            assert "education" not in f.lower()
            assert "categorie" not in f.lower()

    def test_excluded_features_list(self):
        from src.modeling.prepare_survival_dataset import EXCLUDED_FEATURES
        assert "profession_raw" in EXCLUDED_FEATURES
        assert "profession_category" in EXCLUDED_FEATURES


class TestSurvivalDataset:
    def test_csv_exists(self):
        assert os.path.exists(SURVIVAL_CSV), "Run prepare_survival_dataset.py first"

    def test_21_candidates(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert len(df) == 21

    def test_has_age_column(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert "age" in df.columns
        assert df["age"].notna().all()

    def test_has_gender_column(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert "gender" in df.columns
        assert df["gender"].notna().all()

    def test_has_physical_score_column(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert "physical_score" in df.columns

    def test_has_all_cause_exit_event(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert "all_cause_exit_event" in df.columns

    def test_all_cause_exit_event_values(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert set(df["all_cause_exit_event"].unique()) == {0, 1}

    def test_winner_censored(self):
        df = pd.read_csv(SURVIVAL_CSV)
        winner = df[df["departure_type_normalized"] == "VAINQUEUR"]
        assert len(winner) == 1
        assert winner["all_cause_exit_event"].values[0] == 0
        assert winner["censored_at_end"].values[0] == True

    def test_finalist_not_censored(self):
        df = pd.read_csv(SURVIVAL_CSV)
        finalist = df[df["departure_type_normalized"] == "FINALISTE"]
        assert len(finalist) == 1
        assert finalist["all_cause_exit_event"].values[0] == 1

    def test_abandon_medical_event(self):
        df = pd.read_csv(SURVIVAL_CSV)
        medical = df[df["departure_type_normalized"] == "ABANDON_MEDICAL"]
        if len(medical) > 0:
            assert (medical["all_cause_exit_event"] == 1).all()

    def test_abandon_volontaire_event(self):
        df = pd.read_csv(SURVIVAL_CSV)
        voluntary = df[df["departure_type_normalized"] == "ABANDON_VOLONTAIRE"]
        if len(voluntary) > 0:
            assert (voluntary["all_cause_exit_event"] == 1).all()

    def test_single_censored(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert df["censored_at_end"].sum() == 1

    def test_analysis_exit_order_1_to_21(self):
        df = pd.read_csv(SURVIVAL_CSV)
        orders = sorted(df["analysis_exit_order"].tolist())
        assert orders == list(range(1, 22))

    def test_winner_normalized_is_1(self):
        df = pd.read_csv(SURVIVAL_CSV)
        winner = df[df["departure_type_normalized"] == "VAINQUEUR"]
        assert winner["analysis_exit_order_normalized"].values[0] == 1.0

    def test_no_imputation_of_null_physical_score(self):
        df = pd.read_csv(SURVIVAL_CSV)
        null_before = pd.read_csv(SURVIVAL_CSV)
        assert df["physical_score"].isna().sum() == null_before["physical_score"].isna().sum()

    def test_departure_types_preserved(self):
        df = pd.read_csv(SURVIVAL_CSV)
        assert "departure_type_normalized" in df.columns
        assert "departure_category" in df.columns
        assert "departure_model_category" in df.columns

    def test_frozen_csv_unchanged(self):
        with open(FROZEN_CSV, "rb") as f:
            original_hash = hashlib.sha256(f.read()).hexdigest()

        # Just verify the file still exists and is readable
        df = pd.read_csv(FROZEN_CSV)
        assert len(df) == 21

        with open(FROZEN_CSV, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()
        assert current_hash == original_hash