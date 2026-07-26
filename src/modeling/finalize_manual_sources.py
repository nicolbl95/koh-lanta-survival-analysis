"""Finalize manual sources for Nicolas Rouyé and Romain Palazzetti, then freeze."""
import os
import sys
import json
import hashlib
import pandas as pd
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_physical_research_queue.csv")
FROZEN_PHYSICAL_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv")
FROZEN_META_JSON = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1_metadata.json")

NICOLAS_OVERRIDES = {
    "manual_evidence_source_url": "https://www.charentelibre.fr/charente-maritime/jonzac/koh-lanta-nicolas-rouye-le-beau-robinson-charentais-a-ete-elimine-6131310",
    "manual_evidence_source_title": "Koh Lanta : Nicolas Rouyé, le beau Robinson charentais a été éliminé",
    "manual_evidence_exact_excerpt": "Le beau gosse de la saison ; au corps d'Apollon ; sculpté par les sports de glisse.",
    "manual_evidence_added_by": "USER",
    "manual_source_complete": True,
    "muscularity_source_url": "https://www.charentelibre.fr/charente-maritime/jonzac/koh-lanta-nicolas-rouye-le-beau-robinson-charentais-a-ete-elimine-6131310",
    "muscularity_source_quality": "RECOGNIZED_PRESS",
    "muscularity_evidence_period": "CONTEMPORARY_TO_SEASON",
    "muscularity_reviewer_status": "VALIDATED",
    "documented_muscular_build": True,
    "physical_score": "1",
    "physical_score_confidence": "MEDIUM",
    "physical_positive_reason": "MUSCULAR_BUILD",
    "physical_score_based_on_profession_only": False,
    "physical_score_justification": "Nicolas est décrit par un article de presse comme ayant un corps d'Apollon et comme étant sculpté par les sports de glisse. Cette description textuelle explicite justifie son classement dans le groupe présentant un profil physique supérieur à la moyenne.",
    "physical_score_source_status": "VERIFIED_SOURCE",
    "research_notes": "La date exacte n'était pas visible dans l'extrait transmis. La confiance reste MEDIUM en raison du ton promotionnel des formulations employées.",
    "physical_freeze_ready": True,
}

ROMAIN_OVERRIDES = {
    "manual_evidence_source_url": "https://kohlanta.fandom.com/fr/wiki/Romain_Palazzetti",
    "manual_evidence_source_title": "Romain Palazzetti | Wiki Koh Lanta | Fandom",
    "manual_evidence_exact_excerpt": "Classification manuelle de l'utilisateur : Romain présente un gabarit musclé.",
    "manual_evidence_added_by": "USER",
    "manual_source_complete": True,
    "manual_source_validation_note": "La page Fandom confirme l'identité de Romain Palazzetti et sa participation à Koh-Lanta : Thaïlande. Le classement physique ne provient pas d'une description textuelle présente sur cette page, mais d'une évaluation manuelle explicitement validée par l'utilisateur.",
    "documented_muscular_build": True,
    "muscularity_evidence_text": "Évaluation manuelle validée par l'utilisateur : gabarit musclé.",
    "muscularity_source_url": "https://kohlanta.fandom.com/fr/wiki/Romain_Palazzetti",
    "muscularity_source_quality": "USER_MANUAL_RESEARCH",
    "muscularity_evidence_period": "CONTEMPORARY_TO_SEASON",
    "muscularity_reviewer_status": "VALIDATED",
    "physical_score": "1",
    "physical_score_confidence": "MEDIUM",
    "physical_score_reviewer_status": "VALIDATED",
    "physical_score_based_on_profession_only": False,
    "physical_positive_reason": "MUSCULAR_BUILD",
    "physical_score_justification": "Romain est classé dans le groupe physique supérieur à la moyenne sur la base d'une évaluation manuelle validée par l'utilisateur indiquant un gabarit musclé. Sa mention comme judoka constitue un élément contextuel complémentaire, mais elle ne suffit pas à elle seule à déterminer le score.",
    "physical_zero_reason": "",
    "manual_research_required": False,
    "manual_research_priority": "NONE",
    "manual_research_review_status": "VALIDATED",
    "physical_score_source_status": "USER_VALIDATED_MANUAL_CLASSIFICATION",
    "research_notes": "Décision manuelle assumée par l'utilisateur. La page Fandom est conservée comme référence d'identité et de profil, sans lui attribuer une description musculaire absente de son texte.",
    "physical_freeze_ready": True,
}


def main():
    print("=" * 70)
    print("FINALISATION SOURCES MANUELLES + GEL PHYSIQUE")
    print("=" * 70)

    df = pd.read_csv(QUEUE_CSV)

    # Ensure all target columns are object dtype to accept string values
    all_override_cols = set(NICOLAS_OVERRIDES.keys()) | set(ROMAIN_OVERRIDES.keys())
    for col in all_override_cols:
        if col in df.columns:
            df[col] = df[col].astype(object)

    # Apply Nicolas overrides
    for col, val in NICOLAS_OVERRIDES.items():
        if col in df.columns:
            df.loc[df["candidate_name"] == "Nicolas Rouyé", col] = val
        else:
            df[col] = ""
            df.loc[df["candidate_name"] == "Nicolas Rouyé", col] = val
    print("✓ Nicolas Rouyé — sources mises à jour")

    # Apply Romain overrides
    for col, val in ROMAIN_OVERRIDES.items():
        if col in df.columns:
            df.loc[df["candidate_name"] == "Romain Palazzetti", col] = val
        else:
            df[col] = ""
            df.loc[df["candidate_name"] == "Romain Palazzetti", col] = val
    print("✓ Romain Palazzetti — sources mises à jour")

    # Save updated queue
    df.to_csv(QUEUE_CSV, index=False, encoding="utf-8")
    print(f"  Queue sauvegardée : {QUEUE_CSV}")

    # ── Freeze physical CSV ──────────────────────────────────────────────
    physical_cols = [c for c in (
        "candidate_name", "season_name", "age_raw", "gender_normalized",
        "profession_raw", "profession_normalized",
        "physical_score", "physical_score_confidence",
        "physical_score_reviewer_status", "physical_score_based_on_profession_only",
        "physical_positive_reason", "physical_zero_reason",
        "physical_evidence_strength", "physical_evidence_count",
        "documented_muscular_build", "muscularity_evidence_text",
        "muscularity_source_url", "muscularity_source_quality",
        "muscularity_evidence_period", "muscularity_reviewer_status",
        "manual_evidence_source_url", "manual_evidence_source_title",
        "manual_evidence_exact_excerpt", "manual_evidence_added_by",
        "manual_source_complete", "physical_freeze_ready",
        "physical_score_definition_version",
        "physical_score_source_status",
    ) if c in df.columns]

    frozen = df[physical_cols].copy()
    os.makedirs(os.path.dirname(FROZEN_PHYSICAL_CSV), exist_ok=True)
    frozen.to_csv(FROZEN_PHYSICAL_CSV, index=False, encoding="utf-8")

    with open(FROZEN_PHYSICAL_CSV, "rb") as f:
        frozen_hash = hashlib.sha256(f.read()).hexdigest()

    # ── Metadata JSON ────────────────────────────────────────────────────
    scores_1 = (frozen["physical_score"] == "1").sum() + (pd.to_numeric(frozen["physical_score"], errors="coerce") == 1).sum()
    scores_0 = (frozen["physical_score"] == "0").sum() + (pd.to_numeric(frozen["physical_score"], errors="coerce") == 0).sum()
    manual_class = (frozen["physical_score_source_status"] == "USER_VALIDATED_MANUAL_CLASSIFICATION").sum()

    meta = {
        "version": "physical_validated_v1",
        "physical_definition": "MUSCULAR_ATHLETIC_BINARY_V2",
        "candidate_count": len(frozen),
        "physical_score_1_count": int(scores_1),
        "physical_score_0_count": int(scores_0),
        "physical_score_null_count": int(len(frozen) - scores_1 - scores_0),
        "manual_user_classification_count": int(manual_class),
        "manual_user_classification_candidates": ["Romain Palazzetti"] if manual_class > 0 else [],
        "physical_freeze_ready": True,
        "sha256": frozen_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "predictors": ["age", "gender_normalized", "physical_score"],
    }
    with open(FROZEN_META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # ── Display ──────────────────────────────────────────────────────────
    print(f"\nFichier physique gelé : {FROZEN_PHYSICAL_CSV}")
    print(f"Métadonnées : {FROZEN_META_JSON}")
    print(f"SHA256 : {frozen_hash}")
    print(f"physical_freeze_ready : True")

    print("\nNICOLAS ROUYÉ :")
    nr = df[df["candidate_name"] == "Nicolas Rouyé"]
    print(f"  source_status: {nr['physical_score_source_status'].values[0]}")
    print(f"  source_url: {nr['manual_evidence_source_url'].values[0]}")
    print(f"  score={nr['physical_score'].values[0]}, conf={nr['physical_score_confidence'].values[0]}")

    print("\nROMAIN PALAZZETTI :")
    rp = df[df["candidate_name"] == "Romain Palazzetti"]
    print(f"  source_status: {rp['physical_score_source_status'].values[0]}")
    print(f"  source_url: {rp['manual_evidence_source_url'].values[0]}")
    print(f"  score={rp['physical_score'].values[0]}, conf={rp['physical_score_confidence'].values[0]}")
    print(f"  validation_note: {rp['manual_source_validation_note'].values[0][:100]}...")

    print(f"\nClassifications manuelles utilisateur : {manual_class}")

    return df


if __name__ == "__main__":
    df = main()