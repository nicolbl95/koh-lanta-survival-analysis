"""Unit tests for multi-season configuration and dry-run."""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "seasons.json")
FROZEN_THAILANDE = os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv")
FROZEN_DESCRIPTIVE = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv")
FROZEN_PHYSICAL = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv")


class TestSeasonsConfig:
    def test_config_exists(self):
        assert os.path.exists(CONFIG_PATH)

    def test_config_is_valid_json(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "seasons" in data

    def test_config_has_seasons(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["seasons"]) >= 1

    def test_thailande_is_included(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        thai = [s for s in data["seasons"] if "Thaïlande" in s["season_name"]]
        assert len(thai) == 1
        assert thai[0]["include_in_primary_dataset"] is True

    def test_excluded_seasons_are_16(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        excluded = [s for s in data["seasons"] if not s["include_in_primary_dataset"]]
        assert len(excluded) == 16

    def test_included_seasons_are_17(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        included = [s for s in data["seasons"] if s["include_in_primary_dataset"]]
        assert len(included) == 17

    def test_fidji_is_excluded(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        fidji = [s for s in data["seasons"] if "Fidji" in s["season_name"]]
        assert len(fidji) == 1
        assert not fidji[0]["include_in_primary_dataset"]

    def test_panama_excluded_gender(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        panama = [s for s in data["seasons"] if "Panama" in s["season_name"]]
        assert not panama[0]["include_in_primary_dataset"]
        assert panama[0]["exclusion_reason_code"] == "TEAMS_STRUCTURED_BY_GENDER"

    def test_pacifique_excluded_age(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        pacifique = [s for s in data["seasons"] if "Pacifique" in s["season_name"]]
        assert not pacifique[0]["include_in_primary_dataset"]
        assert pacifique[0]["exclusion_reason_code"] == "TEAMS_STRUCTURED_BY_AGE"

    def test_tribu_maudite_excluded(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        tribu = [s for s in data["seasons"] if "Tribu maudite" in s["season_name"]]
        assert not tribu[0]["include_in_primary_dataset"]

    def test_total_33_seasons(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["seasons"]) == 33

    def test_no_included_season_is_excluded_type(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        excluded_names = {
            "Koh-Lanta : Le Retour des Héros", "Koh-Lanta : Le Choc des Héros",
            "Koh-Lanta : La Revanche des Héros", "Koh-Lanta : La Nouvelle Édition",
            "Koh-Lanta : Le Combat des Héros", "Koh-Lanta : L'Île des Héros",
            "Koh-Lanta : La Légende", "Koh-Lanta : Les Reliques du Destin",
            "Koh-Lanta : Cambodge", "Koh-Lanta : Viêtnam", "Koh-Lanta : Panama",
            "Koh-Lanta : Pacifique",
            "Koh-Lanta : Vanuatu", "Koh-Lanta : Palau", "Koh-Lanta : Fidji",
            "Koh-Lanta : La Tribu maudite",
        }
        for s in data["seasons"]:
            if s["season_name"] in excluded_names:
                assert not s["include_in_primary_dataset"], f"{s['season_name']} should be excluded"

    def test_config_has_required_fields(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        required = ["season_name", "season_year", "season_type",
                    "include_in_primary_dataset"]
        for s in data["seasons"]:
            for field in required:
                assert field in s, f"Missing {field} in {s.get('season_name', '?')}"


class TestDryRun:
    def test_dry_run_imports(self):
        from src.scraping.scrape_all_seasons import load_config, dry_run
        config = load_config()
        assert "seasons" in config

    def test_dry_run_does_not_crash(self):
        from src.scraping.scrape_all_seasons import dry_run
        dry_run()  # dry_run now only prints, does not return


class TestFrozenFilesUnchanged:
    def test_thailande_raw_still_exists(self):
        assert os.path.exists(FROZEN_THAILANDE)

    def test_thailande_descriptive_still_exists(self):
        assert os.path.exists(FROZEN_DESCRIPTIVE)

    def test_thailande_physical_still_exists(self):
        assert os.path.exists(FROZEN_PHYSICAL)