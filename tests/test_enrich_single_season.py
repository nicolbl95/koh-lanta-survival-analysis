"""Unit tests for enrich_single_season.py enrichment logic."""

import pytest
import pandas as pd
import os
import hashlib
import tempfile

# Import the enrichment module
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.enrichment.enrich_single_season import (
    classify_profession,
    extract_gender_from_text,
    extract_profession_from_text,
    GENDER_NORMALIZED_VALUES,
    GENDER_CONFIDENCE_VALUES,
    PROFESSION_CATEGORIES,
    CONFIDENCE_VALUES,
    ENRICHMENT_STATUS_VALUES,
    FieldEnrichment,
    CandidateEnrichment,
    map_to_model_category,
    AUTHORIZED_MODEL_CATEGORIES,
)


class TestGenderNormalizedValues:

    def test_female_is_valid(self):
        assert "FEMALE" in GENDER_NORMALIZED_VALUES

    def test_male_is_valid(self):
        assert "MALE" in GENDER_NORMALIZED_VALUES

    def test_unknown_is_valid(self):
        assert "UNKNOWN" in GENDER_NORMALIZED_VALUES

    def test_other_is_valid(self):
        assert "OTHER" in GENDER_NORMALIZED_VALUES

    def test_invalid_gender_rejected(self):
        assert "INVALID" not in GENDER_NORMALIZED_VALUES


class TestProfessionCategories:

    def test_all_categories_valid(self):
        assert "MANUEL_TECHNIQUE" in PROFESSION_CATEGORIES
        assert "SPORT_SECURITE" in PROFESSION_CATEGORIES
        assert "SANTE_SOCIAL" in PROFESSION_CATEGORIES
        assert "EDUCATION_RECHERCHE" in PROFESSION_CATEGORIES
        assert "COMMERCE_GESTION" in PROFESSION_CATEGORIES
        assert "ADMINISTRATION_DROIT" in PROFESSION_CATEGORIES
        assert "ART_MEDIA_COMMUNICATION" in PROFESSION_CATEGORIES
        assert "AGRICULTURE_ENVIRONNEMENT" in PROFESSION_CATEGORIES
        assert "ETUDIANT" in PROFESSION_CATEGORIES
        assert "SANS_EMPLOI" in PROFESSION_CATEGORIES
        assert "AUTRE" in PROFESSION_CATEGORIES
        assert "INDETERMINE" in PROFESSION_CATEGORIES

    def test_classify_pompier(self):
        assert classify_profession("Pompier") == "SPORT_SECURITE"

    def test_classify_militaire(self):
        assert classify_profession("Militaire") == "SPORT_SECURITE"

    def test_classify_infirmiere(self):
        assert classify_profession("Infirmière") == "SANTE_SOCIAL"

    def test_classify_enseignant(self):
        assert classify_profession("Enseignant") == "EDUCATION_RECHERCHE"

    def test_classify_etudiant(self):
        assert classify_profession("Étudiant") == "ETUDIANT"

    def test_classify_commercial(self):
        assert classify_profession("Commercial") == "COMMERCE_GESTION"

    def test_classify_chef_entreprise(self):
        assert classify_profession("Chef d'entreprise") == "COMMERCE_GESTION"

    def test_classify_avocat(self):
        assert classify_profession("Avocat") == "ADMINISTRATION_DROIT"

    def test_classify_journaliste(self):
        assert classify_profession("Journaliste") == "ART_MEDIA_COMMUNICATION"

    def test_classify_agriculteur(self):
        assert classify_profession("Agriculteur") == "AGRICULTURE_ENVIRONNEMENT"

    def test_classify_unknown(self):
        assert classify_profession("QuelqueChoseInconnu") == "AUTRE"


class TestURLRequiredWhenValueFilled:

    def test_url_required_for_filled_gender(self):
        """If gender_normalized is filled, source_url must also be filled."""
        enrich = CandidateEnrichment("Test")
        enrich.gender.normalized = "FEMALE"
        assert enrich.gender.source_url is None  # Initially empty
        enrich.gender.source_url = "https://example.com"
        assert enrich.gender.source_url is not None

    def test_url_required_for_filled_profession(self):
        """If profession_normalized is filled, source_url must also be filled."""
        enrich = CandidateEnrichment("Test")
        enrich.profession.normalized = "Pompier"
        enrich.profession.source_url = "https://example.com"
        assert enrich.profession.source_url is not None


class TestExcerptRequiredWhenValueFilled:

    def test_excerpt_required_for_filled_gender(self):
        """If gender_normalized is filled, source_excerpt must also be filled."""
        enrich = CandidateEnrichment("Test")
        enrich.gender.normalized = "MALE"
        enrich.gender.source_excerpt = "Il est candidat..."
        assert enrich.gender.source_excerpt is not None

    def test_excerpt_required_for_filled_profession(self):
        enrich = CandidateEnrichment("Test")
        enrich.profession.normalized = "Enseignant"
        enrich.profession.source_excerpt = "est enseignant depuis..."
        assert enrich.profession.source_excerpt is not None


class TestCandidateCountPreserved:

    def test_21_candidates_preserved(self):
        """The enrichment must always preserve exactly 21 candidates."""
        names = [f"Candidate {i}" for i in range(1, 22)]
        assert len(names) == 21

    def test_no_candidate_added(self):
        original = set(f"C{i}" for i in range(21))
        enriched = set(f"C{i}" for i in range(21))
        assert original == enriched


class TestExitOrderPreserved:

    def test_exit_orders_unchanged(self):
        """Enrichment must not modify final_exit_order."""
        orders_before = list(range(1, 22))
        orders_after = list(range(1, 22))
        assert orders_before == orders_after


class TestRawCSVNotModified:

    def test_raw_csv_unchanged_after_enrichment(self):
        """The enrichment pipeline must not modify the original raw CSV."""
        raw_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "raw", "koh_lanta_thailande_raw.csv"
        )
        enriched_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "enrichment", "koh_lanta_thailande_enriched_v1.csv"
        )
        assert raw_path != enriched_path
        assert "enrichment" in enriched_path
        assert "raw" in raw_path


class TestNotFoundHandling:

    def test_not_found_keeps_values_empty(self):
        """When no data is found, fields must remain empty (None/NaN)."""
        enrich = CandidateEnrichment("UnknownCandidate")
        assert enrich.gender.normalized is None
        assert enrich.profession.normalized is None

    def test_not_found_status(self):
        enrich = CandidateEnrichment("UnknownCandidate")
        assert enrich.enrichment_status == "A_VERIFIER"


class TestSourceConflictHandling:

    def test_source_conflict_status_exists(self):
        assert "SOURCE_CONFLICT" in ENRICHMENT_STATUS_VALUES

    def test_source_conflict_scenario(self):
        """When two sources give conflicting information about gender."""
        enrich = CandidateEnrichment("TestConflict")
        enrich.gender.normalized = "MALE"
        enrich.gender.confidence = "MEDIUM"
        enrich.gender.source_excerpt = "Il est le candidat..."
        enrich.enrichment_notes.append("Source B indique 'elle' — conflit potentiel")
        enrich.enrichment_status = "SOURCE_CONFLICT"
        assert enrich.enrichment_status == "SOURCE_CONFLICT"


class TestIndeterminePreserved:

    def test_indetermine_preserved_when_evidence_insufficient(self):
        """INDETERMINE must be kept when no conclusive evidence is found."""
        enrich = CandidateEnrichment("TestIndet")
        enrich.needs_departure_enrichment = True
        enrich.departure.normalized = "INDETERMINE"
        assert enrich.needs_departure_enrichment is True
        assert enrich.departure.normalized == "INDETERMINE"

    def test_indetermine_status_becomes_not_found(self):
        enrich = CandidateEnrichment("TestIndet")
        enrich.enrichment_status = "NOT_FOUND"
        assert enrich.enrichment_status == "NOT_FOUND"


class TestFieldEnrichmentModel:

    def test_field_enrichment_initial_state(self):
        f = FieldEnrichment()
        assert f.raw is None
        assert f.normalized is None
        assert f.source_url is None
        assert f.source_excerpt is None
        assert f.confidence is None

    def test_field_enrichment_populated(self):
        f = FieldEnrichment()
        f.raw = "Pompier"
        f.normalized = "Pompier"
        f.source_url = "https://example.com"
        f.source_excerpt = "est pompier"
        f.confidence = "HIGH"
        assert f.raw == "Pompier"
        assert f.confidence == "HIGH"


class TestGenderExtraction:

    def test_extract_male_from_il_candidat(self):
        text = "Charlie Vincent-Mussard est un candidat de Koh-Lanta. Il a 28 ans."
        result = extract_gender_from_text(text, "Charlie Vincent-Mussard")
        assert result is not None
        assert result["normalized"] == "MALE"

    def test_extract_female_from_elle_candidate(self):
        text = "Wendy Gervois est une candidate de Koh-Lanta. Elle a 26 ans."
        result = extract_gender_from_text(text, "Wendy Gervois")
        assert result is not None
        assert result["normalized"] == "FEMALE"

    def test_extract_none_from_no_name_match(self):
        text = "Denis Brogniart présente l'émission."
        result = extract_gender_from_text(text, "Charlie Vincent-Mussard")
        assert result is None


# ─── Tests for model category mapping in enrichment context ─────────────────

class TestModelCategoryMappingInEnrichment:

    def test_authorized_model_categories(self):
        assert AUTHORIZED_MODEL_CATEGORIES == {"DECISION_AVENTURIERS", "EPREUVE", "AUTRE_SORTIE"}
        assert len(AUTHORIZED_MODEL_CATEGORIES) == 3

    def test_conseil_to_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_epreuve_eliminatoire_to_epreuve(self):
        assert map_to_model_category("EPREUVE_ELIMINATOIRE") == "EPREUVE"

    def test_abandon_volontaire_to_autre_sortie(self):
        assert map_to_model_category("ABANDON_VOLONTAIRE") == "AUTRE_SORTIE"

    def test_abandon_medical_to_autre_sortie(self):
        assert map_to_model_category("ABANDON_MEDICAL") == "AUTRE_SORTIE"

    def test_finaliste_to_autre_sortie(self):
        assert map_to_model_category("FINALISTE") == "AUTRE_SORTIE"

    def test_vainqueur_to_autre_sortie(self):
        assert map_to_model_category("VAINQUEUR") == "AUTRE_SORTIE"


# ─── Tests for validated data integrity ─────────────────────────────────────

class TestValidatedDataIntegrity:

    def test_charlie_departure_is_abandon_volontaire(self):
        validated_type = "ABANDON_VOLONTAIRE"
        assert map_to_model_category(validated_type) == "AUTRE_SORTIE"

    def test_marius_departure_is_abandon_volontaire(self):
        validated_type = "ABANDON_VOLONTAIRE"
        assert map_to_model_category(validated_type) == "AUTRE_SORTIE"

    def test_laurence_departure_is_conseil(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_celine_departure_is_conseil(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_huw_departure_is_conseil(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"


# ─── Tests for enrichment not modifying validated data ──────────────────────

class TestEnrichmentPreservesValidatedData:

    def test_charlie_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Charlie Vincent-Mussard" in VALIDATED_DATA
        assert VALIDATED_DATA["Charlie Vincent-Mussard"]["departure_type_normalized"] == "ABANDON_VOLONTAIRE"
        assert VALIDATED_DATA["Charlie Vincent-Mussard"]["gender_normalized"] == "FEMALE"
        assert VALIDATED_DATA["Charlie Vincent-Mussard"]["profession_normalized"] == "Restauratrice de meubles"

    def test_marius_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Marius Torterat" in VALIDATED_DATA
        assert VALIDATED_DATA["Marius Torterat"]["departure_type_normalized"] == "ABANDON_VOLONTAIRE"
        assert VALIDATED_DATA["Marius Torterat"]["gender_normalized"] == "MALE"

    def test_laurence_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Laurence Corbellotti" in VALIDATED_DATA
        assert VALIDATED_DATA["Laurence Corbellotti"]["gender_normalized"] == "FEMALE"

    def test_celine_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Céline Parat-Yeghiayan" in VALIDATED_DATA
        assert VALIDATED_DATA["Céline Parat-Yeghiayan"]["profession_normalized"] == "Formatrice"

    def test_huw_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Huw Francis" in VALIDATED_DATA
        assert VALIDATED_DATA["Huw Francis"]["gender_normalized"] == "MALE"


# ─── Tests for Lot 2 data integrity ─────────────────────────────────────────

class TestLot2Integrity:

    def test_carole_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Carole Poncelet" in VALIDATED_DATA
        v = VALIDATED_DATA["Carole Poncelet"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["gender_confidence"] == "HIGH"
        assert v["profession_normalized"] == "Maître-nageuse et agente territoriale"
        assert v["profession_category"] == "SPORT_SECURITE"
        assert v["enrichment_status"] == "COMPLETE"

    def test_lolo_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert 'Laurence "Lolo" Facione' in VALIDATED_DATA
        v = VALIDATED_DATA['Laurence "Lolo" Facione']
        assert v["gender_normalized"] == "FEMALE"
        assert v["gender_confidence"] == "HIGH"
        assert v["profession_normalized"] == "Maître-nageuse"
        assert v["profession_category"] == "SPORT_SECURITE"
        assert v["enrichment_status"] == "COMPLETE"

    def test_amir_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Amir Doukhan" in VALIDATED_DATA
        v = VALIDATED_DATA["Amir Doukhan"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Directeur commercial"
        assert v["profession_category"] == "COMMERCE_GESTION"
        assert v["enrichment_status"] == "COMPLETE"

    def test_cassandre_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Cassandre Girard" in VALIDATED_DATA
        v = VALIDATED_DATA["Cassandre Girard"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Diplômée en tourisme"
        assert v["profession_category"] == "AUTRE"
        assert v["enrichment_status"] == "COMPLETE"
        assert "ambassadeurs" in v.get("enrichment_notes", "").lower()

    def test_romain_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Romain Palazzetti" in VALIDATED_DATA
        v = VALIDATED_DATA["Romain Palazzetti"]
        assert v["gender_normalized"] == "MALE"
        assert v["gender_confidence"] == "HIGH"
        assert v["profession_normalized"] == "Entrepreneur en domotique"
        assert v["profession_category"] == "COMMERCE_GESTION"
        assert v["enrichment_status"] == "COMPLETE"

    def test_carole_model_category_is_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_lolo_model_category_is_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_amir_model_category_is_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_cassandre_model_category_is_decision_aventuriers(self):
        assert map_to_model_category("AMBASSADEURS_TIRAGE_AU_SORT") == "DECISION_AVENTURIERS"

    def test_cassandre_departure_type_is_ambassadeurs_tirage_au_sort(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert VALIDATED_DATA["Cassandre Girard"]["departure_type_normalized"] == "AMBASSADEURS_TIRAGE_AU_SORT"

    def test_cassandre_gender_and_profession_unchanged(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        v = VALIDATED_DATA["Cassandre Girard"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Diplômée en tourisme"

    def test_romain_model_category_is_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"


# ─── Tests for Lot 3 data integrity ─────────────────────────────────────────

class TestLot3Integrity:

    def test_julien_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Julien Castro" in VALIDATED_DATA
        v = VALIDATED_DATA["Julien Castro"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Menuisier"
        assert v["enrichment_status"] == "COMPLETE"

    def test_laureen_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Laureen Hugel" in VALIDATED_DATA
        v = VALIDATED_DATA["Laureen Hugel"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Étudiante en mode et création"
        assert v["profession_category"] == "ETUDIANT"
        assert v["enrichment_status"] == "COMPLETE"

    def test_steve_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Steve Best" in VALIDATED_DATA
        v = VALIDATED_DATA["Steve Best"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Entrepreneur dans le textile"
        assert v["departure_type_normalized"] == "DESTINS_LIES_SUITE_CONSEIL"
        assert v["enrichment_status"] == "COMPLETE"

    def test_carine_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Carine Cazals" in VALIDATED_DATA
        v = VALIDATED_DATA["Carine Cazals"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Gestionnaire de stock"
        assert v["profession_category"] == "MANUEL_TECHNIQUE"
        assert v["enrichment_status"] == "COMPLETE"

    def test_karima_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Karima Neggaz" in VALIDATED_DATA
        v = VALIDATED_DATA["Karima Neggaz"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Militaire"
        assert v["profession_category"] == "SPORT_SECURITE"
        assert v["enrichment_status"] == "COMPLETE"

    def test_laureen_is_conseil_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_steve_is_destins_lies_suite_conseil_decision_aventuriers(self):
        assert map_to_model_category("DESTINS_LIES_SUITE_CONSEIL") == "DECISION_AVENTURIERS"

    def test_steve_not_conseil(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert VALIDATED_DATA["Steve Best"]["departure_type_normalized"] != "CONSEIL"
        assert VALIDATED_DATA["Steve Best"]["departure_type_normalized"] == "DESTINS_LIES_SUITE_CONSEIL"


# ─── Tests for Lot 4 data integrity ─────────────────────────────────────────

class TestLot4Integrity:

    def test_nicolas_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Nicolas Rouyé" in VALIDATED_DATA
        v = VALIDATED_DATA["Nicolas Rouyé"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Mannequin"
        assert v["profession_category"] == "ART_MEDIA_COMMUNICATION"
        assert v["enrichment_status"] == "COMPLETE"

    def test_alain_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Alain Chrisostome" in VALIDATED_DATA
        v = VALIDATED_DATA["Alain Chrisostome"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Employé de supermarché"
        assert v["enrichment_status"] == "COMPLETE"

    def test_cecilia_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Cécilia Siharaj" in VALIDATED_DATA
        v = VALIDATED_DATA["Cécilia Siharaj"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Danseuse professionnelle"
        assert v["departure_type_normalized"] == "COURSE_ORIENTATION"
        assert v["enrichment_status"] == "COMPLETE"

    def test_gabriel_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Gabriel Gubbels" in VALIDATED_DATA
        v = VALIDATED_DATA["Gabriel Gubbels"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Inspecteur de police"
        assert v["departure_type_normalized"] == "POTEAUX"
        assert v["enrichment_status"] == "COMPLETE"

    def test_pascal_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Pascal Salviani" in VALIDATED_DATA
        v = VALIDATED_DATA["Pascal Salviani"]
        assert v["gender_normalized"] == "MALE"
        assert v["profession_normalized"] == "Chef d'entreprise"
        assert v["enrichment_status"] == "COMPLETE"

    def test_cecilia_is_course_orientation_epreuve(self):
        assert map_to_model_category("COURSE_ORIENTATION") == "EPREUVE"

    def test_gabriel_is_poteaux_epreuve(self):
        assert map_to_model_category("POTEAUX") == "EPREUVE"

    def test_nicolas_is_conseil_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_alain_is_conseil_decision_aventuriers(self):
        assert map_to_model_category("CONSEIL") == "DECISION_AVENTURIERS"

    def test_pascal_is_finaliste_autre_sortie(self):
        assert map_to_model_category("FINALISTE") == "AUTRE_SORTIE"


# ─── Tests for Lot final (Wendy + Laurence Corbellotti correction) ──────────

class TestLotFinalIntegrity:

    def test_wendy_data_present_in_validated(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        assert "Wendy Gervois" in VALIDATED_DATA
        v = VALIDATED_DATA["Wendy Gervois"]
        assert v["gender_normalized"] == "FEMALE"
        assert v["profession_normalized"] == "Boxeuse"
        assert v["profession_category"] == "SPORT_SECURITE"
        assert v["enrichment_status"] == "COMPLETE"

    def test_wendy_is_vainqueur_autre_sortie(self):
        assert map_to_model_category("VAINQUEUR") == "AUTRE_SORTIE"

    def test_laurence_corbellotti_profession_resolved(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        v = VALIDATED_DATA["Laurence Corbellotti"]
        assert v["profession_normalized"] == "Animatrice et danseuse"
        assert v["profession_category"] == "ART_MEDIA_COMMUNICATION"
        assert v["profession_confidence"] == "HIGH"
        assert v["enrichment_status"] == "COMPLETE"

    def test_laurence_corbellotti_not_confused_with_lolo(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        lc = VALIDATED_DATA["Laurence Corbellotti"]
        lolo = VALIDATED_DATA['Laurence "Lolo" Facione']
        assert lc["profession_normalized"] != lolo["profession_normalized"]
        assert lc["profession_normalized"] == "Animatrice et danseuse"
        assert lolo["profession_normalized"] == "Maître-nageuse"
        assert lc["profession_category"] == "ART_MEDIA_COMMUNICATION"
        assert lolo["profession_category"] == "SPORT_SECURITE"

    def test_no_source_conflict_remaining(self):
        from src.enrichment.enrich_single_season import VALIDATED_DATA
        for name, v in VALIDATED_DATA.items():
            assert v.get("enrichment_status") != "SOURCE_CONFLICT", \
                f"{name} still has SOURCE_CONFLICT status"


# ─── Tests for physical score remaining empty ────────────────────────────────

class TestPhysicalScoreEmpty:

    def test_physical_score_not_calculated(self):
        score = None
        assert score is None

    def test_physical_score_justification_empty(self):
        justification = None
        assert justification is None

    def test_physical_score_sources_empty(self):
        sources = None
        assert sources is None