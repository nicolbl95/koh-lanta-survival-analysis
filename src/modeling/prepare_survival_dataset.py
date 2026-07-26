"""Prepare survival dataset for single all-cause model.
Only 3 predictors: age, gender_normalized, physical_score.
"""
import os
import sys
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

ENRICHED_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_enriched_v1.csv")
PHYSICAL_QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_physical_research_queue.csv")
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_survival_ready_v1.csv")

PRIMARY_MODEL_FEATURES = ["age", "gender_normalized", "physical_score"]
EXCLUDED_FEATURES = ["profession_raw", "profession_normalized", "profession_category",
                     "higher_education_job_proxy"]

DEPARTURE_KEPT_COLUMNS = [
    "departure_type_normalized", "departure_category", "departure_model_category",
    "departure_description_raw", "departure_classification_reason",
]


def main():
    print("=" * 70)
    print("PRÉPARATION DATASET DE SURVIE — ALL-CAUSE MODEL")
    print("=" * 70)

    df = pd.read_csv(ENRICHED_CSV)
    phys = pd.read_csv(PHYSICAL_QUEUE_CSV)

    # Merge physical score
    phys_score = phys[["candidate_name", "physical_score",
                       "physical_score_confidence", "physical_score_reviewer_status",
                       "physical_positive_reason", "physical_zero_reason",
                       "documented_muscular_build"]]
    merged = df.merge(phys_score, on="candidate_name", how="left")

    # ── Build numeric age ───────────────────────────────────────────────
    merged["age"] = pd.to_numeric(merged["age_raw"], errors="coerce")

    # ── Keep gender_normalized ──────────────────────────────────────────
    merged["gender"] = merged["gender_normalized"]

    # ── Normalize physical_score ────────────────────────────────────────
    ps = merged["physical_score_y"] if "physical_score_y" in merged.columns else merged["physical_score"]
    merged["physical_score"] = pd.to_numeric(ps, errors="coerce")

    # ── all_cause_exit_event ─────────────────────────────────────────────
    merged["all_cause_exit_event"] = 1
    merged.loc[merged["departure_type_normalized"] == "VAINQUEUR", "all_cause_exit_event"] = 0

    # ── censored_at_end ──────────────────────────────────────────────────
    merged["censored_at_end"] = False
    merged.loc[merged["departure_type_normalized"] == "VAINQUEUR", "censored_at_end"] = True

    # ── analysis_exit_order ─────────────────────────────────────────────
    merged["analysis_exit_order"] = merged["final_exit_order"]
    N = len(merged)
    merged["analysis_exit_order_normalized"] = (
        (merged["analysis_exit_order"] - 1) / (N - 1)
    ).round(6)

    # ── Select output columns ────────────────────────────────────────────
    output_cols = (
        ["candidate_name", "season_name", "age", "gender", "physical_score"]
        + DEPARTURE_KEPT_COLUMNS
        + ["all_cause_exit_event", "censored_at_end",
           "analysis_exit_order", "analysis_exit_order_normalized",
           "physical_score_confidence", "physical_score_reviewer_status",
           "physical_positive_reason", "physical_zero_reason",
           "documented_muscular_build",
           "final_exit_order", "departure_day_raw"]
    )
    available = [c for c in output_cols if c in merged.columns]
    out = merged[available].copy()

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"\nDataset sauvegardé : {OUTPUT_CSV} ({len(out)} lignes, {len(out.columns)} colonnes)")

    # ── Report ───────────────────────────────────────────────────────────
    print(f"\nVariables du modèle principal : {PRIMARY_MODEL_FEATURES}")
    print(f"Variables exclues : {EXCLUDED_FEATURES}")

    print("\nAll-cause exit event distribution :")
    print(out["all_cause_exit_event"].value_counts().to_string())

    print(f"\nCandidat censuré : {out[out['censored_at_end']]['candidate_name'].values}")

    print("\nPhysical score distribution :")
    ps_dist = out["physical_score"].value_counts(dropna=False)
    print(ps_dist.to_string())

    null_scores = out[out["physical_score"].isna()]
    if len(null_scores) > 0:
        print(f"\n⚠ {len(null_scores)} physical_score null — pas d'imputation automatique :")
        for _, r in null_scores.iterrows():
            print(f"  - {r['candidate_name']}")

    print("\nAucune variable professionnelle ou éducative dans PRIMARY_MODEL_FEATURES ✓")
    print("Aucun modèle secondaire configuré ✓")

    return out


if __name__ == "__main__":
    df = main()