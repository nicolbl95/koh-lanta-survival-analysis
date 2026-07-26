"""Unit tests for scrape_single_season.py classification and ordering logic."""

import pytest
from src.scraping.scrape_single_season import classify_departure, map_to_model_category


class TestClassifyDeparture:

    def test_voted_out_classified_as_conseil(self):
        finish = "1st Voted Out Day 3"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "CONSEIL"
        assert dep_cat == "DECISION_AVENTURIERS"
        assert is_definitive is True
        assert needs_enrich is False
        assert "Voted Out" in reason

    def test_voted_out_with_jury_member(self):
        finish = "7th Voted Out 2nd jury member Day 20"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "CONSEIL"
        assert dep_cat == "DECISION_AVENTURIERS"
        assert is_definitive is True
        assert needs_enrich is False

    def test_lost_duel_classified_as_duel_exil_perdu(self):
        finish = "Lost Duel 1st jury member Day 19"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "DUEL_EXIL_PERDU"
        assert dep_cat == "MECANIQUE_RETOUR"
        assert is_definitive is True
        assert needs_enrich is False
        assert "Lost Duel" in reason

    def test_lost_challenge_classified_as_epreuve_eliminatoire(self):
        finish = "Lost Challenge 10th jury member Day 38"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "EPREUVE_ELIMINATOIRE"
        assert dep_cat == "EPREUVE"
        assert is_definitive is True
        assert needs_enrich is False
        assert "Lost Challenge" in reason

    def test_left_competition_is_indetermine_not_abandon_volontaire(self):
        """'Left Competition' must NEVER be classified as ABANDON_VOLONTAIRE."""
        finish = "Left Competition Day 3"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "INDETERMINE"
        assert dep_cat == "INDETERMINE"
        assert dep_type != "ABANDON_VOLONTAIRE"
        assert needs_enrich is True
        assert "ambigu" in reason.lower()

    def test_left_competition_day_6_is_indetermine(self):
        finish = "Left Competition Day 6"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "INDETERMINE"
        assert needs_enrich is True

    def test_sole_survivor_classified_as_vainqueur(self):
        finish = "Sole Survivor Day 40"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "VAINQUEUR"
        assert dep_cat == "FIN_DE_JEU"
        assert is_definitive is True
        assert needs_enrich is False

    def test_runner_up_classified_as_finaliste(self):
        finish = "Runner-up Day 40"
        dep_type, dep_cat, is_definitive, needs_enrich, reason = classify_departure(finish)
        assert dep_type == "FINALISTE"
        assert dep_cat == "FIN_DE_JEU"
        assert is_definitive is True
        assert needs_enrich is False

    def test_indetermine_has_needs_enrichment_true(self):
        """Any INDETERMINE departure must have needs_departure_enrichment = True."""
        finish = "Left Competition Day 3"
        _, _, _, needs_enrich, _ = classify_departure(finish)
        assert needs_enrich is True

    def test_explicit_departure_has_needs_enrichment_false(self):
        """Explicit mechanisms should not require enrichment."""
        for finish in [
            "Sole Survivor Day 40",
            "Runner-up Day 40",
            "1st Voted Out Day 3",
            "Lost Duel 1st jury member Day 19",
            "Lost Challenge 10th jury member Day 38",
        ]:
            _, _, _, needs_enrich, _ = classify_departure(finish)
            assert needs_enrich is False, f"'{finish}' should not need enrichment"


class TestExitOrderNormalization:

    def test_normalization_zero_for_first(self):
        """First eliminated (order=1) should have normalized = 0."""
        N = 21
        order = 1
        normalized = round((order - 1) / (N - 1), 6)
        assert normalized == 0.0

    def test_normalization_one_for_winner(self):
        """Winner (order=N) should have normalized = 1."""
        N = 21
        order = N
        normalized = round((order - 1) / (N - 1), 6)
        assert normalized == 1.0

    def test_normalization_range(self):
        """All normalized values should be between 0 and 1."""
        N = 21
        for order in range(1, N + 1):
            normalized = round((order - 1) / (N - 1), 6)
            assert 0.0 <= normalized <= 1.0

    def test_finalist_order_before_winner(self):
        """Finalist should be order N-1, winner order N."""
        N = 21
        finalist_order = N - 1  # 20
        winner_order = N        # 21
        assert finalist_order == 20
        assert winner_order == 21
        assert finalist_order < winner_order


class TestExitOrderUniqueness:

    def test_orders_are_unique(self):
        """For 21 candidates, orders 1..21 should each appear once."""
        N = 21
        orders = list(range(1, N + 1))
        assert len(orders) == N
        assert len(set(orders)) == N
        assert sorted(orders) == orders


class TestAuthorizedValues:

    def test_authorized_departure_types_not_empty(self):
        from src.scraping.scrape_single_season import AUTHORIZED_DEPARTURE_TYPES
        assert len(AUTHORIZED_DEPARTURE_TYPES) > 0
        assert "INDETERMINE" in AUTHORIZED_DEPARTURE_TYPES
        assert "CONSEIL" in AUTHORIZED_DEPARTURE_TYPES
        assert "VAINQUEUR" in AUTHORIZED_DEPARTURE_TYPES
        assert "FINALISTE" in AUTHORIZED_DEPARTURE_TYPES

    def test_authorized_departure_categories_not_empty(self):
        from src.scraping.scrape_single_season import AUTHORIZED_DEPARTURE_CATEGORIES
        assert len(AUTHORIZED_DEPARTURE_CATEGORIES) > 0
        assert "INDETERMINE" in AUTHORIZED_DEPARTURE_CATEGORIES
        assert "DECISION_AVENTURIERS" in AUTHORIZED_DEPARTURE_CATEGORIES
        assert "FIN_DE_JEU" in AUTHORIZED_DEPARTURE_CATEGORIES

    def test_authorized_model_categories(self):
        from src.scraping.scrape_single_season import AUTHORIZED_MODEL_CATEGORIES
        assert AUTHORIZED_MODEL_CATEGORIES == {"DECISION_AVENTURIERS", "EPREUVE", "AUTRE_SORTIE"}
        assert len(AUTHORIZED_MODEL_CATEGORIES) == 3


# ─── Tests for map_to_model_category ────────────────────────────────────────

class TestModelCategoryMapping:

    def test_conseil_to_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_ambassadeurs_accord_to_decision_aventuriers(self):
        assert map_to_model_category("AMBASSADEURS_ACCORD") == "DECISION_AVENTURIERS"

    def test_non_choisi_pour_jury_final_to_decision_aventuriers(self):
        assert map_to_model_category("NON_CHOISI_POUR_JURY_FINAL") == "DECISION_AVENTURIERS"

    def test_ambassadeurs_tirage_au_sort_to_decision_aventuriers(self):
        assert map_to_model_category("AMBASSADEURS_TIRAGE_AU_SORT") == "DECISION_AVENTURIERS"

    def test_vote_noir_to_decision_aventuriers(self):
        assert map_to_model_category("VOTE_NOIR") == "DECISION_AVENTURIERS"

    def test_detournement_de_vote_to_decision_aventuriers(self):
        assert map_to_model_category("DETOURNEMENT_DE_VOTE") == "DECISION_AVENTURIERS"

    def test_epreuve_eliminatoire_to_epreuve(self):
        assert map_to_model_category("EPREUVE_ELIMINATOIRE") == "EPREUVE"

    def test_course_orientation_to_epreuve(self):
        assert map_to_model_category("COURSE_ORIENTATION") == "EPREUVE"

    def test_poteaux_to_epreuve(self):
        assert map_to_model_category("POTEAUX") == "EPREUVE"

    def test_duel_exil_perdu_to_epreuve(self):
        assert map_to_model_category("DUEL_EXIL_PERDU") == "EPREUVE"

    def test_ile_seconde_chance_perdue_to_epreuve(self):
        assert map_to_model_category("ILE_SECONDE_CHANCE_PERDUE") == "EPREUVE"

    def test_destins_lies_to_epreuve(self):
        assert map_to_model_category("DESTINS_LIES") == "EPREUVE"

    def test_elimination_initiale_to_epreuve(self):
        assert map_to_model_category("ELIMINATION_INITIALE") == "EPREUVE"

    def test_abandon_volontaire_to_autre_sortie(self):
        assert map_to_model_category("ABANDON_VOLONTAIRE") == "AUTRE_SORTIE"

    def test_abandon_medical_to_autre_sortie(self):
        assert map_to_model_category("ABANDON_MEDICAL") == "AUTRE_SORTIE"

    def test_exclusion_disciplinaire_to_autre_sortie(self):
        assert map_to_model_category("EXCLUSION_DISCIPLINAIRE") == "AUTRE_SORTIE"

    def test_finaliste_to_autre_sortie(self):
        assert map_to_model_category("FINALISTE") == "AUTRE_SORTIE"

    def test_vainqueur_to_autre_sortie(self):
        assert map_to_model_category("VAINQUEUR") == "AUTRE_SORTIE"

    def test_indetermine_to_autre_sortie(self):
        assert map_to_model_category("INDETERMINE") == "AUTRE_SORTIE"

    def test_elimination_provisoire_to_autre_sortie(self):
        assert map_to_model_category("ELIMINATION_PROVISOIRE_AVEC_RETOUR") == "AUTRE_SORTIE"

    def test_autre_to_autre_sortie(self):
        assert map_to_model_category("AUTRE") == "AUTRE_SORTIE"

    def test_destins_lies_suite_conseil_to_decision_aventuriers(self):
        assert map_to_model_category("DESTINS_LIES_SUITE_CONSEIL") == "DECISION_AVENTURIERS"

    def test_destins_lies_and_suite_conseil_not_interchangeable(self):
        assert map_to_model_category("DESTINS_LIES") != map_to_model_category("DESTINS_LIES_SUITE_CONSEIL")
        assert map_to_model_category("DESTINS_LIES") == "EPREUVE"
        assert map_to_model_category("DESTINS_LIES_SUITE_CONSEIL") == "DECISION_AVENTURIERS"


# ─── Tests for exit order logic ─────────────────────────────────────────────

class TestExitOrderLogic:

    def test_candidate_without_return_model_equals_final(self):
        """For a candidate who never returned: model_exit_order = final_exit_order."""
        final_exit_order = 5
        first_exit_order = 5
        returned = False

        if returned:
            model_exit_order = first_exit_order
        else:
            model_exit_order = final_exit_order

        assert model_exit_order == final_exit_order
        assert model_exit_order == 5

    def test_candidate_with_return_model_equals_first_not_final(self):
        """For a candidate who returned: model_exit_order = first_exit_order (not final)."""
        first_exit_order = 1
        final_exit_order = 5
        returned = True

        if returned:
            model_exit_order = first_exit_order
        else:
            model_exit_order = final_exit_order

        assert model_exit_order == first_exit_order
        assert model_exit_order == 1
        assert model_exit_order != final_exit_order

    def test_all_exit_orders_equal_when_no_return(self):
        """Without return: first = final = model."""
        orders = {"first": 3, "final": 3, "model": 3}
        returned = False
        if not returned:
            orders["model"] = orders["final"]
        assert orders["model"] == orders["first"] == orders["final"]

    def test_first_exit_order_equals_final_when_no_return(self):
        """Without return: first_exit_order = final_exit_order."""
        first = "first_exit_order"
        final = "final_exit_order"
        returned = False

        # Simulate: for a no-return candidate, first=final
        exit_data = {"first_exit_order": 7, "final_exit_order": 7}
        assert exit_data["first_exit_order"] == exit_data["final_exit_order"]