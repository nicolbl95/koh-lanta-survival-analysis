"""Tests for pilot departure enrichment pipeline — V2 (post footnotes research)."""
import os
import sys
import json
import hashlib
import pytest
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

ENRICHED_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "pilot_departures_enriched.csv")
RESEARCH_QUEUE = os.path.join(PROJECT_ROOT, "data", "enrichment", "pilot_departure_research_queue.csv")
ENRICHMENT_REPORT = os.path.join(PROJECT_ROOT, "data", "processed", "pilot_departure_enrichment_report.csv")
PRESENCE_INTERVALS = os.path.join(PROJECT_ROOT, "data", "processed", "pilot_candidate_presence_intervals.csv")
FINAL_AUDIT = os.path.join(PROJECT_ROOT, "data", "processed", "pilot_departure_final_audit.csv")
QUALITY_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "pilot_departure_quality_summary.json")

THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]

AUTHORIZED_TYPES = {
    "CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
    "VOTE_NOIR", "DETOURNEMENT_DE_VOTE",
    "DESTINS_LIES_SUITE_CONSEIL",
    "EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE",
    "COURSE_ORIENTATION", "POTEAUX", "DUEL_ELIMINATOIRE",
    "ABANDON_MEDICAL", "ABANDON_VOLONTAIRE",
    "EXCLUSION_DISCIPLINAIRE",
    "FINALISTE", "VAINQUEUR", "CO_VAINQUEUR",
    "AUTRE", "INDETERMINE",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()


class TestEnrichedOutputExists:
    def test_enriched_csv_exists(self):
        assert os.path.exists(ENRICHED_CSV)

    def test_research_queue_exists(self):
        assert os.path.exists(RESEARCH_QUEUE)

    def test_enrichment_report_exists(self):
        assert os.path.exists(ENRICHMENT_REPORT)

    def test_presence_intervals_exists(self):
        assert os.path.exists(PRESENCE_INTERVALS)

    def test_final_audit_exists(self):
        assert os.path.exists(FINAL_AUDIT)

    def test_quality_json_exists(self):
        assert os.path.exists(QUALITY_JSON)

    def test_enrich_script_exists(self):
        assert os.path.exists(os.path.join(PROJECT_ROOT, "src", "enrichment", "enrich_pilot_departures.py"))


class TestRowCounts:
    def test_total_41_candidates(self):
        df = pd.read_csv(ENRICHED_CSV)
        assert len(df) == 41

    def test_kl31_has_20(self):
        df = pd.read_csv(ENRICHED_CSV)
        assert len(df[df["season_id"] == "KL31"]) == 20

    def test_kl33_has_21(self):
        df = pd.read_csv(ENRICHED_CSV)
        assert len(df[df["season_id"] == "KL33"]) == 21


class TestMagali:
    def test_magali_single_observation(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert len(magali) == 1, "Magali must have exactly 1 observation"

    def test_magali_first_exit_order_is_5_not_16(self):
        """Magali's first exit was day 13 (5th eliminated), not her final rank 16."""
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["first_exit_order"].values[0] == 5, \
            f"first_exit_order should be 5, got {magali['first_exit_order'].values[0]}"

    def test_magali_first_exit_precedes_final(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["first_exit_order"].values[0] < magali["final_exit_order"].values[0]

    def test_magali_analysis_exit_equals_first_exit(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["analysis_exit_order"].values[0] == magali["first_exit_order"].values[0]
        assert magali["analysis_exit_order"].values[0] == 5

    def test_magali_returned_to_game(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["returned_to_game"].values[0] == True

    def test_magali_returned_after_medical(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["returned_after_medical_replacement"].values[0] == True

    def test_magali_all_cause_event_is_1(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["all_cause_exit_event"].values[0] == 1

    def test_magali_not_censored(self):
        df = pd.read_csv(ENRICHED_CSV)
        magali = df[df["candidate_name"] == "Magali"]
        assert magali["censored_at_end"].values[0] == False

    def test_magali_presence_intervals_coherent(self):
        pres = pd.read_csv(PRESENCE_INTERVALS)
        magali_pres = pres[pres["candidate_name"] == "Magali"]
        assert len(magali_pres) == 4, f"Magali should have 4 intervals, got {len(magali_pres)}"
        statuses = list(magali_pres["presence_status"])
        assert "ABSENT" in statuses, "Magali should have an ABSENT interval"
        assert "PRESENT" in statuses, "Magali should have PRESENT intervals"


class TestGabin:
    def test_gabin_is_abandon_medical(self):
        df = pd.read_csv(ENRICHED_CSV)
        gabin = df[df["candidate_name"] == "Gabin"]
        assert len(gabin) == 1
        assert gabin["departure_type_normalized"].values[0] == "ABANDON_MEDICAL"

    def test_gabin_model_category_is_autre_sortie(self):
        df = pd.read_csv(ENRICHED_CSV)
        gabin = df[df["candidate_name"] == "Gabin"]
        assert gabin["departure_model_category"].values[0] == "AUTRE_SORTIE"

    def test_gabin_all_cause_event_is_1(self):
        df = pd.read_csv(ENRICHED_CSV)
        gabin = df[df["candidate_name"] == "Gabin"]
        assert gabin["all_cause_exit_event"].values[0] == 1

    def test_gabin_mechanism_known(self):
        df = pd.read_csv(ENRICHED_CSV)
        gabin = df[df["candidate_name"] == "Gabin"]
        assert gabin["departure_mechanism_known"].values[0] == True


class TestFrederic:
    def test_frederic_is_ambassadeurs_accord(self):
        """Frédéric was eliminated by ambassador agreement, not INDETERMINE."""
        df = pd.read_csv(ENRICHED_CSV)
        fred = df[df["candidate_name"] == "Frédéric"]
        assert fred["departure_type_normalized"].values[0] == "AMBASSADEURS_ACCORD"

    def test_frederic_has_source(self):
        df = pd.read_csv(ENRICHED_CSV)
        fred = df[df["candidate_name"] == "Frédéric"]
        assert fred["departure_source_url"].values[0], "Source URL missing for Frédéric"
        assert "ambassadeur" in str(fred["departure_source_excerpt"].values[0]).lower()


class TestMathieu:
    def test_mathieu_is_epreuve_eliminatoire(self):
        """Mathieu lost a duel against Thomas and was eliminated directly."""
        df = pd.read_csv(ENRICHED_CSV)
        math = df[df["candidate_name"] == "Mathieu"]
        assert math["departure_type_normalized"].values[0] == "EPREUVE_ELIMINATOIRE"

    def test_mathieu_not_conseil(self):
        df = pd.read_csv(ENRICHED_CSV)
        math = df[df["candidate_name"] == "Mathieu"]
        assert math["departure_type_normalized"].values[0] != "CONSEIL"
        assert math["departure_type_normalized"].values[0] != "INDETERMINE"


class TestConseilRequiresEvidence:
    def test_conseil_candidates_have_source(self):
        df = pd.read_csv(ENRICHED_CSV)
        conseils = df[df["departure_type_normalized"] == "CONSEIL"]
        for _, row in conseils.iterrows():
            assert row.get("departure_source_url"), f"CONSEIL {row['candidate_name']} missing source"
            assert pd.notna(row.get("departure_source_url"))

    def test_elimine_alone_is_not_conseil(self):
        """'Éliminé' without vote evidence must not be CONSEIL."""
        df = pd.read_csv(ENRICHED_CSV)
        for name in ["Flavio", "Arnaud", "Laure"]:
            cand = df[df["candidate_name"] == name]
            if len(cand) > 0:
                t = cand["departure_type_normalized"].values[0]
                assert t != "CONSEIL", f"{name} has 0 votes — should not be CONSEIL"

    def test_no_correction_without_source(self):
        """Every VALIDATED type must have a source."""
        df = pd.read_csv(ENRICHED_CSV)
        validated = df[df["departure_review_status"] == "VALIDATED"]
        for _, row in validated.iterrows():
            assert row.get("departure_source_url"), \
                f"{row['candidate_name']} VALIDATED without source URL"
            assert pd.notna(row.get("departure_source_url"))


class TestIndetermineProperlyFlagged:
    def test_indetermine_has_needs_enrichment(self):
        df = pd.read_csv(ENRICHED_CSV)
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        for _, row in indet.iterrows():
            assert row["needs_departure_enrichment"] == True

    def test_indetermine_mechanism_known_false(self):
        df = pd.read_csv(ENRICHED_CSV)
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        for _, row in indet.iterrows():
            assert row.get("departure_mechanism_known") == False, \
                f"{row['candidate_name']} mechanism_known should be False"

    def test_indetermine_model_category_is_indetermine(self):
        """INDETERMINE model_category must be INDETERMINE, not AUTRE_SORTIE."""
        df = pd.read_csv(ENRICHED_CSV)
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        for _, row in indet.iterrows():
            assert row["departure_model_category"] == "INDETERMINE", \
                f"{row['candidate_name']} model_category should be INDETERMINE, got {row['departure_model_category']}"

    def test_indetermine_all_cause_event_is_1(self):
        df = pd.read_csv(ENRICHED_CSV)
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        for _, row in indet.iterrows():
            assert row["all_cause_exit_event"] == 1


class TestWinnersAndCensoring:
    def test_winners_are_censored(self):
        df = pd.read_csv(ENRICHED_CSV)
        winners = df[df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        assert len(winners) >= 2
        for _, row in winners.iterrows():
            assert row["censored_at_end"] == True
            assert row["all_cause_exit_event"] == 0

    def test_non_winners_have_event_1(self):
        df = pd.read_csv(ENRICHED_CSV)
        non_winners = df[~df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        for _, row in non_winners.iterrows():
            assert row["all_cause_exit_event"] == 1, \
                f"{row['candidate_name']} event={row['all_cause_exit_event']}"

    def test_finalists_have_event_1(self):
        df = pd.read_csv(ENRICHED_CSV)
        finalists = df[df["departure_type_normalized"] == "FINALISTE"]
        for _, row in finalists.iterrows():
            assert row["all_cause_exit_event"] == 1


class TestQualitySummary:
    def test_quality_json_has_both_seasons(self):
        with open(QUALITY_JSON, "r", encoding="utf-8") as f:
            q = json.load(f)
        assert "KL31" in q
        assert "KL33" in q

    def test_coverage_between_0_and_1(self):
        with open(QUALITY_JSON, "r", encoding="utf-8") as f:
            q = json.load(f)
        for sid in ["KL31", "KL33"]:
            cov = q[sid]["departure_mechanism_coverage"]
            assert 0.0 <= cov <= 1.0, f"{sid} coverage={cov} out of range"

    def test_kl33_coverage_warning_if_below_90(self):
        with open(QUALITY_JSON, "r", encoding="utf-8") as f:
            q = json.load(f)
        cov = q["KL33"]["departure_mechanism_coverage"]
        if cov < 0.90:
            assert q["KL33"]["ready_for_descriptive_departure_statistics"] in (
                "READY_WITH_WARNING", "INSUFFICIENT"
            )

    def test_all_cause_model_ready(self):
        with open(QUALITY_JSON, "r", encoding="utf-8") as f:
            q = json.load(f)
        for sid in ["KL31", "KL33"]:
            assert q[sid]["ready_for_all_cause_model"] == True, \
                f"{sid} not ready for all-cause model"

    def test_unknown_mechanism_does_not_block_all_cause(self):
        """Even with INDETERMINE candidates, all_cause_model must be ready."""
        with open(QUALITY_JSON, "r", encoding="utf-8") as f:
            q = json.load(f)
        # KL33 has 4 INDETERMINE but still ready for all-cause
        assert q["KL33"]["ready_for_all_cause_model"] == True


class TestAllTypesAuthorized:
    def test_all_departure_types_authorized(self):
        df = pd.read_csv(ENRICHED_CSV)
        types = set(df["departure_type_normalized"].unique())
        assert types.issubset(AUTHORIZED_TYPES), f"Unauthorized: {types - AUTHORIZED_TYPES}"


class TestThailandeFrozen:
    def test_thailande_files_exist_and_nonzero(self):
        for path in THAILANDE_FILES:
            assert os.path.exists(path), f"Missing: {path}"
            assert os.path.getsize(path) > 0, f"Empty: {path}"


class TestKl31EpreuveAudit:
    def test_kl31_epreuve_count_is_4(self):
        df = pd.read_csv(ENRICHED_CSV)
        kl31 = df[df["season_id"] == "KL31"]
        epreuves = kl31[kl31["departure_type_normalized"] == "EPREUVE_ELIMINATOIRE"]
        assert len(epreuves) == 4

    def test_kl31_jerome_merlier_is_epreuve(self):
        df = pd.read_csv(ENRICHED_CSV)
        j = df[df["candidate_name"] == "Jérôme Merlier"]
        assert j["departure_type_normalized"].values[0] == "EPREUVE_ELIMINATOIRE"


class TestNoDuplicates:
    def test_no_duplicate_candidates_within_season(self):
        df = pd.read_csv(ENRICHED_CSV)
        for sid in df["season_id"].unique():
            season_df = df[df["season_id"] == sid]
            dupes = season_df[season_df.duplicated(subset=["candidate_name"], keep=False)]
            assert len(dupes) == 0, f"Duplicates in {sid}: {list(dupes['candidate_name'])}"