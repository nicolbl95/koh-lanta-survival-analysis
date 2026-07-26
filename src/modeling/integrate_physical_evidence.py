"""
Binary physical score — MUSCULAR_ATHLETIC_BINARY_V2.
1 = documented muscular/athletic build, strength/combat sport, or high physical training
0 = ordinary physical profile
null = ambiguous indicators
"""

import os
import sys
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

ENRICHED_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_enriched_v1.csv")
QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_physical_research_queue.csv")
METHODOLOGY_DOC = os.path.join(PROJECT_ROOT, "docs", "physical_scoring_methodology_draft.md")

ALL_COLUMNS = [
    "candidate_name", "season_name", "age_raw", "gender_normalized",
    "profession_raw", "profession_normalized", "profession_category",
    "physical_search_query_1", "physical_search_query_2", "physical_search_query_3",
    "explicit_sport_activity", "sport_name", "sport_frequency", "sport_intensity",
    "competition_level", "years_of_practice", "physical_job_evidence",
    "other_physical_evidence", "physical_source_url_1", "physical_source_excerpt_1",
    "physical_source_quality_1", "physical_source_url_2", "physical_source_excerpt_2",
    "physical_source_quality_2", "evidence_status", "manual_review_required",
    "research_notes",
    "physical_score", "physical_score_justification", "physical_score_sources",
    "physical_score_confidence", "physical_score_reviewer_status",
    "physical_score_based_on_profession_only",
    "physical_evidence_strength", "physical_evidence_count",
    "manual_research_required", "manual_research_priority",
    "manual_research_request", "manual_research_result",
    "manual_research_source_url", "manual_research_source_excerpt",
    "manual_research_review_status",
    "physical_score_definition_version",
    "physical_zero_reason",
    "physical_positive_reason",
    "documented_muscular_build",
    "muscularity_evidence_text",
    "muscularity_source_url",
    "muscularity_source_quality",
    "muscularity_evidence_period",
    "muscularity_reviewer_status",
    "manual_evidence_source_url",
    "manual_evidence_source_title",
    "manual_evidence_exact_excerpt",
    "manual_evidence_added_by",
]

DIRECT_PHYSICAL_PROFESSIONS = {
    "boxeuse", "boxeur", "handballeuse", "handballeur", "footballeuse",
    "footballeur", "rugbyman", "joueuse de rugby", "nageuse", "nageur",
    "cycliste", "combattant", "coach sportif", "préparateur physique",
    "éducateur sportif", "professeur de fitness", "entraîneur sportif",
    "moniteur de ski", "guide de haute montagne", "maître-nageuse",
    "maître-nageur", "sauveteur sportif", "professeur d'éducation physique",
    "professeur de sport", "pompier", "pompière",
    "militaire", "soldat", "sergent", "commando",
    "policier", "policière", "inspecteur de police",
    "gendarme", "sauveteur en mer", "garde-côte",
    "instructeur d'arts martiaux", "professeur de natation", "guide sportif",
    "sportif", "sportive", "athlète", "sportif professionnel",
    "sportive professionnelle",
}

DANCE_KEYWORDS = {"danseuse", "danseur", "danse", "chorégraphique"}


def infer_binary_physical_score(profession_normalized, explicit_sport_activity,
                                sport_frequency, sport_intensity,
                                competition_level, evidence_strength,
                                documented_muscular_build, muscularity_evidence_text,
                                muscularity_evidence_period):
    """Return binary score dict — MUSCULAR_ATHLETIC_BINARY_V2."""
    p = (profession_normalized or "").strip().lower()
    mb = documented_muscular_build if isinstance(documented_muscular_build, bool) else (
        str(documented_muscular_build).strip().lower() == "true" if documented_muscular_build else False)

    result = {
        "physical_score": "0",
        "physical_score_justification": "Aucune pratique sportive intensive, aucun niveau de compétition, aucune musculature documentée et aucune profession nécessitant une condition physique supérieure à la moyenne ne sont documentés. Le profil est donc classé dans la catégorie physique ordinaire.",
        "physical_score_confidence": "MEDIUM",
        "physical_score_reviewer_status": "VALIDATED",
        "physical_score_based_on_profession_only": False,
        "physical_evidence_strength": "INSUFFICIENT",
        "physical_evidence_count": "0",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_zero_reason": "NO_QUALIFYING_PHYSICAL_INDICATOR",
        "physical_positive_reason": "",
        "manual_research_required": False,
        "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    }

    # 1. Documented muscular build → 1
    if mb and muscularity_evidence_period in (
        "", "PRE_SEASON", "CONTEMPORARY_TO_SEASON",
        "POST_SEASON_REFERRING_TO_PRIOR_CONDITION", "USER_MANUAL_RESEARCH",
    ):
        result.update(
            physical_score="1", physical_score_confidence="MEDIUM",
            physical_score_reviewer_status="VALIDATED",
            physical_positive_reason="MUSCULAR_BUILD",
            physical_evidence_strength="STRONG", physical_evidence_count="2",
            evidence_status="SUFFICIENT_EVIDENCE", physical_zero_reason="",
            physical_score_based_on_profession_only=False,
            manual_research_required=False, manual_research_priority="NONE",
            manual_research_review_status="VALIDATED",
        )
        return result

    # 2. Direct physical profession → 1
    if any(k in p for k in DIRECT_PHYSICAL_PROFESSIONS):
        result.update(
            physical_score="1", physical_score_confidence="HIGH",
            physical_score_reviewer_status="VALIDATED",
            physical_score_based_on_profession_only=True,
            physical_positive_reason="DIRECT_PHYSICAL_PROFESSION",
            physical_evidence_strength="STRONG", physical_evidence_count="1",
            evidence_status="SUFFICIENT_EVIDENCE", physical_zero_reason="",
            manual_research_required=False, manual_research_priority="NONE",
            manual_research_review_status="VALIDATED",
        )
        return result

    # 3. Dance → null
    if any(d in p for d in DANCE_KEYWORDS):
        result.update(
            physical_score="", physical_score_confidence="LOW",
            physical_score_reviewer_status="A_REVOIR",
            physical_score_based_on_profession_only=True,
            physical_positive_reason="",
            physical_evidence_strength="MODERATE", physical_evidence_count="1",
            evidence_status="PARTIAL_EVIDENCE", physical_zero_reason="",
            manual_research_required=True, manual_research_priority="MEDIUM",
            manual_research_review_status="NOT_STARTED",
        )
        return result

    return result


MANUAL_OVERRIDES = {
    # ─── Pre-validated 1 ──────────────────────────────────────────────────
    "Céline Parat-Yeghiayan": {
        "physical_score": "1", "physical_score_confidence": "HIGH",
        "physical_score_reviewer_status": "VALIDATED",
        "physical_positive_reason": "ENDURANCE_TRAINING",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "3",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_justification": "Pratique régulière et soutenue du trail, participation à plusieurs parcours.",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    },
    "Huw Francis": {
        "physical_score": "1", "physical_score_confidence": "HIGH",
        "physical_positive_reason": "MULTIPLE_QUALIFYING_INDICATORS",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "3",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_justification": "Trail régulier et moniteur de ski.",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    },
    "Carole Poncelet": {
        "physical_score": "1", "physical_score_confidence": "HIGH",
        "physical_positive_reason": "HIGH_PHYSICAL_TRAINING",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "3",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_justification": "Escrime compétitive internationale vétéran et maître-nageuse.",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    },
    "Karima Neggaz": {
        "physical_score": "1", "physical_score_confidence": "MEDIUM",
        "physical_positive_reason": "DIRECT_PHYSICAL_PROFESSION",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "3",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_based_on_profession_only": True,
        "physical_score_justification": "Militaire de carrière, entraînée, pratique de course à pied.",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    },
    "Wendy Gervois": {"physical_positive_reason": "STRENGTH_OR_COMBAT_SPORT"},
    "Laurence \"Lolo\" Facione": {"physical_positive_reason": "DIRECT_PHYSICAL_PROFESSION"},
    "Gabriel Gubbels": {"physical_positive_reason": "DIRECT_PHYSICAL_PROFESSION"},
    "Carine Cazals": {
        "physical_score": "1", "physical_score_confidence": "HIGH",
        "physical_positive_reason": "HIGH_PHYSICAL_TRAINING",
        "explicit_sport_activity": "Badminton compétition + 12-15h/semaine (natation, vélo, muscu, rando)",
        "sport_name": "Badminton / natation / vélo / musculation / randonnée",
        "sport_frequency": "12 à 15 heures par semaine",
        "sport_intensity": "Soutenue",
        "competition_level": "Badminton en compétition",
        "physical_source_url_1": "https://www.ladepeche.fr/article/2016/02/12/2275269-carine-koh-lanta-m-a-permis-de-repousser-mes-limites.html",
        "physical_source_excerpt_1": "Elle pratique le badminton en compétition. L'Albigeoise fait 12 à 15 heures d'activités physiques par semaine : natation, vélo, musculation, randonnée.",
        "physical_source_quality_1": "DIRECT_INTERVIEW",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "4",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_justification": "Badminton en compétition et 12-15h hebdomadaires d'activités physiques.",
        "physical_score_sources": "https://www.ladepeche.fr/article/2016/02/12/2275269-carine-koh-lanta-m-a-permis-de-repousser-mes-limites.html",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
        "research_notes": "Score fondé sur volume hebdomadaire explicite et pratique compétitive.",
    },
    "Alain Chrisostome": {
        "physical_score": "1", "physical_score_confidence": "MEDIUM",
        "physical_positive_reason": "STRENGTH_OR_COMBAT_SPORT",
        "explicit_sport_activity": "Champion de pelote basque depuis toujours.",
        "sport_name": "Pelote basque", "sport_intensity": "Soutenue",
        "competition_level": "Champion de pelote",
        "physical_source_url_1": "https://survivor.fandom.com/wiki/Alain_Chrisostome",
        "physical_source_excerpt_1": "Il est aussi champion de pelote depuis toujours.",
        "physical_source_quality_1": "SECONDARY_DATABASE",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "2",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_justification": "Champion de pelote depuis toujours, pratique compétitive durable.",
        "physical_score_sources": "https://survivor.fandom.com/wiki/Alain_Chrisostome | https://www.terrafemina.com/article/koh-lanta-2016-qui-sont-les-candidats-liste-complete_a301201/1",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    },
    "Cécilia Siharaj": {
        "physical_score": "1", "physical_score_confidence": "MEDIUM",
        "physical_positive_reason": "MULTIPLE_QUALIFYING_INDICATORS",
        "explicit_sport_activity": "Danse professionnelle et arts martiaux.",
        "sport_name": "Danse / arts martiaux", "sport_intensity": "Soutenue",
        "physical_source_url_1": "https://www.tf1.fr/fr-ci/dossier/cecilia-kl-thailande-2016",
        "physical_source_excerpt_1": "La petite danseuse est dure au mal. Poussée par son père à être la meilleure, notamment dans les arts martiaux.",
        "physical_source_quality_1": "OFFICIAL",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "2",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_score_justification": "Danseuse professionnelle et pratique des arts martiaux.",
        "physical_score_sources": "https://www.tf1.fr/fr-ci/dossier/cecilia-kl-thailande-2016",
        "physical_zero_reason": "",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
    },

    # ─── Manual user decisions ─────────────────────────────────────────────
    "Laurence Corbellotti": {
        "physical_score": "0", "physical_score_confidence": "MEDIUM",
        "physical_score_reviewer_status": "VALIDATED",
        "physical_score_based_on_profession_only": False,
        "documented_muscular_build": False,
        "physical_evidence_strength": "INSUFFICIENT",
        "physical_zero_reason": "NO_QUALIFYING_PHYSICAL_INDICATOR",
        "physical_positive_reason": "",
        "physical_score_justification": "Les recherches manuelles n'ont pas identifié d'indicateur de musculature, de gabarit athlétique ou de pratique physique suffisamment intensive. Son activité de danse, telle qu'elle est documentée, ne suffit pas à la classer au-dessus d'un profil physique ordinaire.",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
        "research_notes": "Décision issue de la recherche manuelle de l'utilisateur. La profession d'animatrice et danseuse ne conduit pas automatiquement à un score 1.",
    },
    "Romain Palazzetti": {
        "physical_score": "1", "physical_score_confidence": "MEDIUM",
        "physical_score_reviewer_status": "VALIDATED",
        "physical_score_based_on_profession_only": False,
        "documented_muscular_build": True,
        "muscularity_evidence_text": "Gabarit musclé documenté par la recherche manuelle de l'utilisateur.",
        "muscularity_source_quality": "USER_MANUAL_RESEARCH",
        "muscularity_evidence_period": "CONTEMPORARY_TO_SEASON",
        "muscularity_reviewer_status": "VALIDATED",
        "physical_positive_reason": "MUSCULAR_BUILD",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "2",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_zero_reason": "",
        "physical_score_justification": "Romain est décrit comme ayant un gabarit musclé. Cette description textuelle, complétée par la mention de sa pratique du judo, constitue un indicateur d'un profil physique supérieur à la moyenne.",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
        "manual_evidence_exact_excerpt": "gabarit musclé",
        "manual_evidence_added_by": "USER",
        "research_notes": "Décision issue de la recherche manuelle de l'utilisateur. Ne pas fonder le score uniquement sur le mot 'judoka' : le critère déterminant est le gabarit musclé documenté.",
    },
    "Nicolas Rouyé": {
        "physical_score": "1", "physical_score_confidence": "HIGH",
        "physical_score_reviewer_status": "VALIDATED",
        "physical_score_based_on_profession_only": False,
        "documented_muscular_build": True,
        "muscularity_evidence_text": "Un article local le décrit comme « sculpté par les sports de glisse », avec un « corps d'Apollon » et un physique plutôt musclé.",
        "muscularity_source_quality": "USER_MANUAL_RESEARCH",
        "muscularity_evidence_period": "CONTEMPORARY_TO_SEASON",
        "muscularity_reviewer_status": "VALIDATED",
        "physical_positive_reason": "MUSCULAR_BUILD",
        "physical_evidence_strength": "STRONG", "physical_evidence_count": "2",
        "evidence_status": "SUFFICIENT_EVIDENCE",
        "physical_zero_reason": "",
        "physical_score_justification": "Nicolas est explicitement décrit comme sculpté par les sports de glisse, doté d'un corps d'Apollon et d'un physique musclé. Ces descriptions textuelles indiquent un profil physique supérieur à la moyenne.",
        "manual_research_required": False, "manual_research_priority": "NONE",
        "manual_research_review_status": "VALIDATED",
        "manual_evidence_exact_excerpt": "sculpté par les sports de glisse ; corps d'Apollon ; physiquement plutôt musclé",
        "manual_evidence_added_by": "USER",
        "research_notes": "Décision issue de la recherche manuelle de l'utilisateur. Le score repose sur une description textuelle explicite du physique, et non sur une analyse directe de photographies.",
    },
}


def main():
    print("=" * 70)
    print("SCORE PHYSIQUE — MUSCULAR_ATHLETIC_BINARY_V2")
    print("=" * 70)

    df_base = pd.read_csv(ENRICHED_CSV)
    rows = []

    for _, row in df_base.iterrows():
        name = row["candidate_name"]
        notes = str(row.get("enrichment_notes", "") or "")
        prof_norm = str(row.get("profession_normalized", "") or "")

        base = {
            "candidate_name": name,
            "season_name": str(row.get("season_name", "")),
            "age_raw": str(row.get("age_raw", "")),
            "gender_normalized": str(row.get("gender_normalized", "")),
            "profession_raw": str(row.get("profession_raw", "") or ""),
            "profession_normalized": prof_norm,
            "profession_category": str(row.get("profession_category", "")),
            "physical_search_query_1": "", "physical_search_query_2": "", "physical_search_query_3": "",
            "explicit_sport_activity": "", "sport_name": "", "sport_frequency": "", "sport_intensity": "",
            "competition_level": "", "years_of_practice": "",
            "physical_job_evidence": "", "other_physical_evidence": "",
            "physical_source_url_1": "", "physical_source_excerpt_1": "", "physical_source_quality_1": "",
            "physical_source_url_2": "", "physical_source_excerpt_2": "", "physical_source_quality_2": "",
            "evidence_status": "NOT_STARTED",
            "manual_review_required": str(row.get("manual_review_required", "")),
            "research_notes": "",
            "physical_score_definition_version": "MUSCULAR_ATHLETIC_BINARY_V2",
            "physical_score": "", "physical_score_justification": "", "physical_score_sources": "",
            "physical_score_confidence": "", "physical_score_reviewer_status": "",
            "physical_score_based_on_profession_only": "",
            "physical_evidence_strength": "", "physical_evidence_count": "",
            "manual_research_required": "", "manual_research_priority": "",
            "manual_research_request": "", "manual_research_result": "",
            "manual_research_source_url": "", "manual_research_source_excerpt": "",
            "manual_research_review_status": "",
            "physical_zero_reason": "",
            "physical_positive_reason": "",
            "documented_muscular_build": False,
            "muscularity_evidence_text": "",
            "muscularity_source_url": "",
            "muscularity_source_quality": "",
            "muscularity_evidence_period": "",
            "muscularity_reviewer_status": "",
            "manual_evidence_source_url": "",
            "manual_evidence_source_title": "",
            "manual_evidence_exact_excerpt": "",
            "manual_evidence_added_by": "",
        }

        inference = infer_binary_physical_score(
            prof_norm, "", "", "", "", "", False, "", "")
        base.update(inference)

        if name in MANUAL_OVERRIDES:
            base.update(MANUAL_OVERRIDES[name])

        rows.append(base)

    df = pd.DataFrame(rows, columns=ALL_COLUMNS)
    os.makedirs(os.path.dirname(QUEUE_CSV), exist_ok=True)
    df.to_csv(QUEUE_CSV, index=False, encoding="utf-8")
    print(f"File sauvegardée : {QUEUE_CSV} ({len(df.columns)} colonnes)")

    # Display
    print("\n" + "=" * 70)
    print("RÉSULTATS — 21 CANDIDATS (MUSCULAR_ATHLETIC_BINARY_V2)")
    print("=" * 70)
    cols = ["candidate_name", "physical_score", "physical_score_confidence",
            "physical_score_reviewer_status", "physical_positive_reason",
            "documented_muscular_build", "physical_zero_reason"]
    print(df[cols].to_string(index=False))

    s1 = (df["physical_score"] == "1").sum()
    s0 = (df["physical_score"] == "0").sum()
    sn = df["physical_score"].isna().sum() + (df["physical_score"] == "").sum()
    print(f"\n  physical_score = 1  : {s1}")
    print(f"  physical_score = 0  : {s0}")
    print(f"  physical_score null : {sn}")

    print("\nMODIFICATIONS (nouvelle déf.) :")
    for _, r in df[df["candidate_name"].isin(["Laurence Corbellotti", "Romain Palazzetti", "Nicolas Rouyé"])].iterrows():
        print(f"  {r['candidate_name']:<28} score={r['physical_score']} positive_reason={r['physical_positive_reason']} muscular={r['documented_muscular_build']}")

    print("\nURL MANUELLES MANQUANTES :")
    for _, r in df.iterrows():
        if str(r.get("manual_evidence_added_by") or "") == "USER" and not str(r.get("manual_evidence_source_url") or ""):
            print(f"  ⚠ {r['candidate_name']}: manual_evidence_source_url vide")

    return df


if __name__ == "__main__":
    df = main()