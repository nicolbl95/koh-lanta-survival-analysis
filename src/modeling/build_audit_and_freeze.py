"""
Audit final + gel de la version descriptive + file de recherche physique.
Exécuté une seule fois après l'enrichissement complet de la saison test.
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timezone

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

ENRICHED_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_enriched_v1.csv")
FROZEN_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv")
METADATA_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1_metadata.json")
PHYSICAL_QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_physical_research_queue.csv")
METHODOLOGY_DOC = os.path.join(PROJECT_ROOT, "docs", "physical_scoring_methodology_draft.md")
AUDIT_REPORT = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_audit_report.csv")

SEASON_NAME = "Koh-Lanta : Thaïlande"
SEASON_YEAR = 2016


def determine_source_quality(row: pd.Series) -> str:
    """Determine the source quality flag for a candidate."""
    sources = set()

    gender_url = str(row.get("gender_source_url", "") or "")
    prof_url = str(row.get("profession_source_url", "") or "")
    dep_url = str(row.get("departure_source_url", "") or "")

    for url in [gender_url, prof_url, dep_url]:
        if not url or url == "nan":
            continue
        if "tf1.fr" in url or "tf1info.fr" in url:
            sources.add("OFFICIAL")
        elif "estrepublicain.fr" in url or "rtl.fr" in url:
            sources.add("RECOGNIZED_PRESS")
        elif "fandom.com" in url or "survivor.fandom.com" in url or "kohlanta.fandom.com" in url:
            sources.add("SECONDARY_DATABASE")
        else:
            sources.add("RECOGNIZED_PRESS")

    if len(sources) == 0:
        return "UNKNOWN"
    if len(sources) == 1:
        return list(sources)[0]
    return "MIXED"


def needs_manual_review(row: pd.Series) -> bool:
    """Determine if a candidate requires manual review."""
    prof_conf = str(row.get("profession_confidence", "") or "")
    gender_conf = str(row.get("gender_confidence", "") or "")
    dep_conf = str(row.get("departure_confidence", "") or "")

    if prof_conf in ("MEDIUM", "LOW"):
        return True
    if gender_conf in ("LOW", "UNKNOWN"):
        return True
    if dep_conf in ("LOW", "UNKNOWN"):
        return True

    prof_url = str(row.get("profession_source_url", "") or "")
    if "fandom.com" in prof_url and prof_conf != "HIGH":
        return True

    prof_norm = str(row.get("profession_normalized", "") or "")
    if "diplômée" in prof_norm.lower() or "étudiant" in prof_norm.lower():
        return True

    prof_raw = str(row.get("profession_raw", "") or "")
    if " et " in prof_raw.lower():
        return True

    return False


def main():
    print("=" * 70)
    print("AUDIT FINAL + GEL DESCRIPTIF + FILE RECHERCHE PHYSIQUE")
    print("=" * 70)

    # ── Load enriched CSV ───────────────────────────────────────────────────
    df = pd.read_csv(ENRICHED_CSV)
    print(f"\nCSV enrichi chargé : {len(df)} candidats")

    # ── 1. Freeze descriptive version ───────────────────────────────────────
    os.makedirs(os.path.dirname(FROZEN_CSV), exist_ok=True)
    df.to_csv(FROZEN_CSV, index=False, encoding="utf-8")
    print(f"Version descriptive gelée : {FROZEN_CSV}")

    # Compute SHA256
    with open(FROZEN_CSV, "rb") as f:
        frozen_hash = hashlib.sha256(f.read()).hexdigest()
    print(f"SHA256 : {frozen_hash}")

    # ── 2. Generate metadata ────────────────────────────────────────────────
    gender_dist = df["gender_normalized"].value_counts().to_dict()
    prof_cat_dist = df["profession_category"].value_counts().to_dict()
    dep_type_dist = df["departure_type_normalized"].value_counts().to_dict()
    model_cat_dist = df["departure_model_category"].value_counts().to_dict()

    gender_conf_dist = df["gender_confidence"].value_counts().to_dict()
    prof_conf_dist = df["profession_confidence"].value_counts().to_dict()
    dep_conf_dist = df["departure_confidence"].value_counts().to_dict()

    metadata = {
        "season_name": SEASON_NAME,
        "season_year": SEASON_YEAR,
        "candidate_count": len(df),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "descriptive_validated_v1",
        "sha256": frozen_hash,
        "genders_filled": int(df["gender_normalized"].notna().sum()),
        "professions_filled": int(df["profession_normalized"].notna().sum()),
        "gender_distribution": gender_dist,
        "profession_category_distribution": prof_cat_dist,
        "departure_type_distribution": dep_type_dist,
        "departure_model_category_distribution": model_cat_dist,
        "gender_confidence_distribution": gender_conf_dist,
        "profession_confidence_distribution": prof_conf_dist,
        "departure_confidence_distribution": dep_conf_dist,
        "returned_to_game_true": int((df["returned_to_game"] == True).sum()),
        "physical_score_filled": int(df["physical_score"].notna().sum()),
        "enrichment_status_complete": int((df["enrichment_status"] == "COMPLETE").sum()),
    }

    os.makedirs(os.path.dirname(METADATA_JSON), exist_ok=True)
    with open(METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Métadonnées : {METADATA_JSON}")

    # ── 3. Source quality flag + manual review ──────────────────────────────
    df["source_quality_flag"] = df.apply(determine_source_quality, axis=1)
    df["manual_review_required"] = df.apply(needs_manual_review, axis=1)

    # ── 4. Build audit table ────────────────────────────────────────────────
    audit_rows = []
    for _, row in df.iterrows():
        name = row["candidate_name"]
        warnings_list = []
        audit_status = "PASS"

        # Check gender
        if pd.isna(row.get("gender_normalized")):
            warnings_list.append("gender_missing")
            audit_status = "FAIL"
        elif str(row.get("gender_normalized")) not in ("FEMALE", "MALE", "OTHER"):
            warnings_list.append("gender_invalid")

        # Check profession
        if pd.isna(row.get("profession_normalized")):
            warnings_list.append("profession_missing")
            audit_status = "FAIL"
        elif str(row.get("profession_category")) not in (
            "MANUEL_TECHNIQUE", "SPORT_SECURITE", "SANTE_SOCIAL",
            "EDUCATION_RECHERCHE", "COMMERCE_GESTION", "ADMINISTRATION_DROIT",
            "ART_MEDIA_COMMUNICATION", "AGRICULTURE_ENVIRONNEMENT",
            "ETUDIANT", "SANS_EMPLOI", "AUTRE", "INDETERMINE",
        ):
            warnings_list.append("profession_category_invalid")

        # Check age
        age = row.get("age_raw")
        if pd.isna(age):
            warnings_list.append("age_missing")
        else:
            try:
                age_int = int(float(age))
                if age_int < 18 or age_int > 80:
                    warnings_list.append("age_implausible")
            except (ValueError, TypeError):
                warnings_list.append("age_non_numeric")

        # Check exit order
        order = row.get("final_exit_order")
        if pd.isna(order) or int(order) < 1 or int(order) > 21:
            warnings_list.append("exit_order_invalid")
            audit_status = "FAIL"

        # Check normalization
        norm = row.get("final_exit_order_normalized")
        if pd.isna(norm) or float(norm) < 0 or float(norm) > 1:
            warnings_list.append("normalization_invalid")
            audit_status = "FAIL"

        # Check model category coherence
        dep_type = str(row.get("departure_type_normalized", ""))
        model_cat = str(row.get("departure_model_category", ""))
        from src.scraping.scrape_single_season import map_to_model_category
        expected_cat = map_to_model_category(dep_type)
        if model_cat != expected_cat:
            warnings_list.append(f"model_category_mismatch:{model_cat}_vs_{expected_cat}")
            audit_status = "FAIL"

        # Check exit coherence
        first = row.get("first_exit_order")
        final = row.get("final_exit_order")
        model = row.get("model_exit_order")
        if not (pd.isna(first) or pd.isna(final) or pd.isna(model)):
            if row.get("returned_to_game") == False:
                if int(first) != int(final) or int(final) != int(model):
                    warnings_list.append("exit_order_incoherence")

        # Check homonymy
        if "Laurence Corbellotti" in name:
            if "lolo" in str(row.get("profession_normalized", "")).lower():
                warnings_list.append("homonym_confusion_laurence")

        if row.get("manual_review_required", False):
            warnings_list.append("manual_review_required")

        if warnings_list:
            audit_status = "PASS_WITH_WARNING" if audit_status == "PASS" else audit_status

        audit_rows.append({
            "candidate_name": name,
            "audit_status": audit_status,
            "audit_warnings": " | ".join(warnings_list) if warnings_list else "",
            "gender_confidence": row.get("gender_confidence", ""),
            "profession_confidence": row.get("profession_confidence", ""),
            "departure_confidence": row.get("departure_confidence", ""),
            "source_quality_flag": row.get("source_quality_flag", ""),
            "manual_review_required": row.get("manual_review_required", False),
        })

    df_audit = pd.DataFrame(audit_rows)
    os.makedirs(os.path.dirname(AUDIT_REPORT), exist_ok=True)
    df_audit.to_csv(AUDIT_REPORT, index=False, encoding="utf-8")
    print(f"Rapport d'audit : {AUDIT_REPORT}")

    # ── 5. Create physical research queue ────────────────────────────────────
    queue_rows = []
    for _, row in df.iterrows():
        name = row["candidate_name"]
        # Build three search queries
        q1 = f'"{name}" Koh-Lanta sport portrait'
        q2 = f'"{name}" Koh-Lanta entraînement activité sportive'
        q3 = f'"{name}" Koh-Lanta métier sport interview'

        # Detect explicit sport activity from notes
        notes = str(row.get("enrichment_notes", "") or "")
        prof_raw = str(row.get("profession_raw", "") or "")
        prof_norm = str(row.get("profession_normalized", "") or "")

        explicit_sport = ""
        sport_keywords = [
            "escrimeuse", "escrime", "judoka", "boxe", "boxeuse", "danse",
            "danseuse", "badminton", "pelote", "sport", "militaire",
            "maître-nageur", "nageur", "ski", "glisse",
        ]
        detected = []
        for kw in sport_keywords:
            if kw.lower() in notes.lower() or kw.lower() in prof_raw.lower() or kw.lower() in prof_norm.lower():
                if kw not in detected:
                    detected.append(kw)
        if detected:
            explicit_sport = ", ".join(detected)

        queue_rows.append({
            "candidate_name": name,
            "season_name": row["season_name"],
            "age_raw": row.get("age_raw", ""),
            "gender_normalized": row.get("gender_normalized", ""),
            "profession_raw": prof_raw,
            "profession_normalized": prof_norm,
            "profession_category": row.get("profession_category", ""),
            "physical_search_query_1": q1,
            "physical_search_query_2": q2,
            "physical_search_query_3": q3,
            "explicit_sport_activity": explicit_sport,
            "sport_name": "",
            "sport_frequency": "",
            "sport_intensity": "",
            "competition_level": "",
            "years_of_practice": "",
            "physical_job_evidence": "",
            "other_physical_evidence": "",
            "physical_source_url_1": "",
            "physical_source_excerpt_1": "",
            "physical_source_quality_1": "",
            "physical_source_url_2": "",
            "physical_source_excerpt_2": "",
            "physical_source_quality_2": "",
            "evidence_status": "NOT_STARTED",
            "manual_review_required": row.get("manual_review_required", False),
            "research_notes": "",
        })

    df_queue = pd.DataFrame(queue_rows)
    os.makedirs(os.path.dirname(PHYSICAL_QUEUE_CSV), exist_ok=True)
    df_queue.to_csv(PHYSICAL_QUEUE_CSV, index=False, encoding="utf-8")
    print(f"File de recherche physique : {PHYSICAL_QUEUE_CSV}")

    # ── 6. Create methodology doc ───────────────────────────────────────────
    methodology = """# Methodology Draft — Physical Score Attribution
## Version draft — Ne pas encore exécuter

### 1. Score Range
Score entre 1 et 3.

### 2. Profession Alone Is Insufficient
La profession seule ne suffit jamais à attribuer un score 3.

### 3. Evidence Priority
a. Pratique sportive explicite et documentée
b. Niveau de compétition
c. Fréquence et intensité d'entraînement
d. Activité professionnelle physiquement exigeante
e. Profession seule, uniquement comme indice secondaire

### 4. Interdictions
- Aucune analyse photographique
- Aucune inférence à partir du corps ou du visage
- Aucune inférence à partir du sexe
- Aucune inférence à partir de l'âge seul
- Aucune inférence à partir de stéréotypes professionnels
- Aucune utilisation de la performance obtenue pendant Koh-Lanta
- Aucune utilisation du rang final ou du type de sortie
- Aucune donnée postérieure révélant indirectement la performance

### 5. Data Leakage Prevention
Ne pas utiliser :
- Victoires aux épreuves
- Durée de présence dans le jeu
- Performances pendant la saison
- Commentaires évaluatifs de la saison
- Résultat final
- Description physique observée pendant l'émission

### 6. Missing Value Policy
Si preuves insuffisantes :
- physical_score = null
- physical_evidence_status = INSUFFICIENT_EVIDENCE
Ne jamais forcer un score pour atteindre 100% de complétude.

### 7. Multicollinearity Vigilance
- profession_category et physical_score risquent d'être corrélés
- Les métiers SPORT_SECURITE ne reçoivent pas automatiquement un score élevé
- Les preuves sportives indépendantes de la profession sont privilégiées
- Un indicateur physical_score_based_on_profession_only existera
- Les candidats dont le score repose uniquement sur la profession seront signalés
- La corrélation, les tableaux croisés et le VIF seront vérifiés avant l'interprétation

### 8. Future Columns
- physical_score (1-3 or null)
- physical_score_justification
- physical_score_sources
- physical_score_based_on_profession_only (bool)
- physical_evidence_strength (STRONG, MODERATE, WEAK, INSUFFICIENT)
- physical_evidence_count (int)
"""
    os.makedirs(os.path.dirname(METHODOLOGY_DOC), exist_ok=True)
    with open(METHODOLOGY_DOC, "w", encoding="utf-8") as f:
        f.write(methodology)
    print(f"Méthodologie : {METHODOLOGY_DOC}")

    # ── 7. Display results ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RÉSULTATS DE L'AUDIT")
    print("=" * 70)

    print(f"\nFichiers créés :")
    print(f"  - {FROZEN_CSV}")
    print(f"  - {METADATA_JSON}")
    print(f"  - {AUDIT_REPORT}")
    print(f"  - {PHYSICAL_QUEUE_CSV}")
    print(f"  - {METHODOLOGY_DOC}")

    print(f"\nSHA256 version gelée : {frozen_hash}")

    print("\nStatuts d'audit :")
    for status in ["PASS", "PASS_WITH_WARNING", "FAIL"]:
        count = (df_audit["audit_status"] == status).sum()
        if count > 0:
            print(f"  {status}: {count}")

    print("\nCandidats nécessitant une revue manuelle :")
    manual = df_audit[df_audit["manual_review_required"] == True]
    if len(manual) > 0:
        for _, r in manual.iterrows():
            print(f"  - {r['candidate_name']} (confiance: g={r['gender_confidence']}, "
                  f"p={r['profession_confidence']}, d={r['departure_confidence']})")
    else:
        print("  (aucun)")

    print("\nDistribution source_quality_flag :")
    for val, count in df_audit["source_quality_flag"].value_counts().items():
        print(f"  {val}: {count}")

    print("\nDistribution des niveaux de confiance :")
    print("  Sexe:")
    for val, count in gender_conf_dist.items():
        print(f"    {val}: {count}")
    print("  Profession:")
    for val, count in prof_conf_dist.items():
        print(f"    {val}: {count}")
    print("  Sortie:")
    for val, count in dep_conf_dist.items():
        print(f"    {val}: {count}")

    print("\nAvertissements d'audit :")
    warnings_found = df_audit[df_audit["audit_warnings"] != ""]
    if len(warnings_found) > 0:
        for _, r in warnings_found.iterrows():
            print(f"  - {r['candidate_name']}: {r['audit_warnings']}")
    else:
        print("  (aucun avertissement)")

    print(f"\nFile de recherche physique : {len(df_queue)} candidats")
    print("Aperçu (3 premières requêtes) :")
    for i in range(min(3, len(df_queue))):
        r = df_queue.iloc[i]
        print(f"  {r['candidate_name']}:")
        print(f"    q1: {r['physical_search_query_1']}")
        print(f"    q2: {r['physical_search_query_2']}")
        print(f"    q3: {r['physical_search_query_3']}")
        if r["explicit_sport_activity"]:
            print(f"    sport détecté: {r['explicit_sport_activity']}")

    print("\nScores physiques : toujours vides ✓")
    print(f"physical_score filled: {df['physical_score'].notna().sum()}/21")

    return df, df_audit


if __name__ == "__main__":
    df, df_audit = main()