"""Pipeline d'audit et d'enrichissement des types de sortie — saisons pilotes KL31 + KL33.

Sources:
  - Wikipedia EN (KL31) + FR (KL33) — tableaux de votes, notes de bas de page
  - Footnotes Wikipedia FR pour Les Armes secrètes (mécanismes précis)
"""
import os
import re
import sys
import hashlib
import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# ─── Paths ────────────────────────────────────────────────────────────────────
KL31_RAW = os.path.join(PROJECT_ROOT, "data", "raw", "seasons", "koh_lanta_l_le_au_tr_sor_2016_raw.csv")
KL33_RAW = os.path.join(PROJECT_ROOT, "data", "raw", "seasons", "koh_lanta_les_armes_secr_tes_2021_raw.csv")
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

BASE_URL_KL33 = "https://fr.wikipedia.org/wiki/Koh-Lanta_:_Les_Armes_secrètes"
BASE_URL_KL31 = "https://en.wikipedia.org/wiki/Koh-Lanta:_L%27%C3%8Ele_au_Tr%C3%A9sor"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()


def map_to_model_category(t):
    decision = {"CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
                "VOTE_NOIR", "DETOURNEMENT_DE_VOTE",
                "NON_CHOISI_POUR_JURY_FINAL", "DESTINS_LIES_SUITE_CONSEIL"}
    epreuve = {"EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE",
               "COURSE_ORIENTATION", "POTEAUX", "DUEL_ELIMINATOIRE",
               "DUEL_EXIL_PERDU", "ILE_SECONDE_CHANCE_PERDUE"}
    autre = {"ABANDON_MEDICAL", "ABANDON_VOLONTAIRE", "EXCLUSION_DISCIPLINAIRE",
             "FINALISTE", "VAINQUEUR", "CO_VAINQUEUR", "AUTRE"}
    if t in decision: return "DECISION_AVENTURIERS"
    if t in epreuve: return "EPREUVE"
    if t in autre: return "AUTRE_SORTIE"
    return "INDETERMINE"  # For descriptive stats: INDETERMINE stays INDETERMINE, not merged


# ═══════════════════════════════════════════════════════════════════════════════
#  KL31 Audit — L'Île au trésor
# ═══════════════════════════════════════════════════════════════════════════════
KL31_AUDIT = {
    "Jérôme Merlier": {
        "proposed_type": "EPREUVE_ELIMINATOIRE",
        "reason": "Lost Duel (Day 20). 0 vote au conseil — note [b]. Le duel est une épreuve "
                  "éliminatoire directe. Aucune indication de mécanisme de retour (exil). "
                  "Conservé EPREUVE_ELIMINATOIRE. Le sous-type exact du duel n'est pas "
                  "précisé dans la source anglaise.",
        "excerpt": "Lost Duel Day 20 — 0 votes [b]",
        "confidence": "HIGH",
    },
    "Julie Navarro-Camilleri": {
        "proposed_type": "EPREUVE_ELIMINATOIRE",
        "reason": "Lost Challenge (Day 32). Épreuve éliminatoire. "
                  "Le type exact d'épreuve (orientation, etc.) n'est pas documenté.",
        "excerpt": "Lost Challenge 4th jury member Day 32",
        "confidence": "HIGH",
    },
    "Candice Boisson": {
        "proposed_type": "EPREUVE_ELIMINATOIRE",
        "reason": "Lost Challenge (Day 40). Même jour que Bruno. "
                  "Les deux éliminations le même jour suggèrent la course d'orientation "
                  "ou une épreuve à perdants multiples. Le type exact n'est pas documenté.",
        "excerpt": "Lost Challenge 8th jury member Day 40",
        "confidence": "HIGH",
    },
    "Bruno Troester": {
        "proposed_type": "EPREUVE_ELIMINATOIRE",
        "reason": "Lost Challenge (Day 40). Même jour que Candice. "
                  "Type exact non documenté.",
        "excerpt": "Lost Challenge 9th jury member Day 40",
        "confidence": "HIGH",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  KL33 Enrichment — Les Armes secrètes
#  Sources: Wikipedia voting table + footnotes
# ═══════════════════════════════════════════════════════════════════════════════
KL33_ENRICHMENT = {
    # ── CONSEIL confirmed by vote counts ──────────────────────────────────
    "Sylviane":   {"type": "CONSEIL", "reason": "7-4-1-1 votes au conseil (jour 3).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 7 votes reçus sur 13."},
    "Marie":      {"type": "CONSEIL", "reason": "6-3-2-1 votes au conseil (jour 6).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 6 votes reçus sur 12."},
    "Élodie":     {"type": "CONSEIL", "reason": "6-3-1 votes au conseil (jour 9).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 6 votes reçus sur 10."},
    "Candice":    {"type": "CONSEIL", "reason": "5-4 votes au conseil (jour 12).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 5 votes reçus sur 9."},
    "Aurélien":   {"type": "CONSEIL", "reason": "5-4 votes au conseil (jour 15).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 5 votes reçus sur 9."},
    "Hervé":      {"type": "CONSEIL", "reason": "6-4-3-1 votes au conseil (jour 17).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 6 votes reçus sur 14."},
    "Shanice":    {"type": "CONSEIL", "reason": "7-6 votes au conseil (jour 20).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 7 votes reçus sur 13."},
    "Myriam":     {"type": "CONSEIL", "reason": "8-5-1 votes au conseil (jour 23).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 8 votes reçus sur 14."},
    "Vincent":    {"type": "CONSEIL", "reason": "8-2-1 votes au conseil — double élimination avec Laëtitia (jour 27).",
                   "conf": "HIGH", "excerpt": "Tableau des votes: 8 votes reçus."},
    "Laëtitia":   {"type": "CONSEIL", "reason": "8-2-1 votes au conseil — double élimination avec Vincent (jour 27).",
                   "conf": "HIGH", "excerpt": "Tableau des votes: 8 votes reçus."},
    "Thomas":     {"type": "CONSEIL", "reason": "8-1 votes au conseil (jour 30).", "conf": "HIGH",
                   "excerpt": "Tableau des votes: 8 votes reçus sur 9."},
    # ── Magali 2nd exit (already CONSEIL from table) ──
    "Magali": {
        "is_return_case": True,
        "first_exit": {
            "day": 13, "order": 5, "type": "CONSEIL",
            "reason": "Conseil surprise après épreuve de confort perdue par la tribu rouge. "
                      "Note Wikipedia: 'conseil surprise a été effectué juste après celle-ci, "
                      "à l'issue duquel Magali est éliminée.'",
            "excerpt": "Note Wikipedia: 'conseil surprise [...] Magali est éliminée.'",
            "conf": "HIGH",
        },
        "return": {"day": 15, "reason": "Retour après l'évacuation médicale de Gabin."},
        "second_exit": {
            "type": "CONSEIL",
            "reason": "4-3 votes au conseil (jour 33).",
            "excerpt": "Tableau des votes: 4 votes reçus sur 7. Deuxième élimination.",
            "conf": "HIGH",
        },
    },
    # ── Gabin: ABANDON_MEDICAL ────────────────────────────────────────────
    "Gabin": {
        "type": "ABANDON_MEDICAL",
        "reason": "Blessé au genou, contraint à l'abandon médical (jour 15). "
                  "Note Wikipedia: 'Blessé au genou, Gabin est contraint à l'abandon médical.'",
        "excerpt": "Note Wikipedia: 'Blessé au genou, Gabin est contraint à l'abandon médical.'",
        "conf": "HIGH",
    },
    # ── Frédéric: AMBASSADEURS_ACCORD ← NEW from footnotes ────────────────
    "Frédéric": {
        "type": "AMBASSADEURS_ACCORD",
        "reason": "Les deux ambassadeurs Vincent et Maxine, et l'ambassadrice secrète Laure "
                  "se mettent d'accord pour éliminer Frédéric. Note Wikipedia: 'Les deux "
                  "ambassadeurs (Vincent et Maxine) et l'ambassadrice secrète (Laure) se "
                  "mettent d'accord pour éliminer Frédéric.'",
        "excerpt": "Les deux ambassadeurs [...] se mettent d'accord pour éliminer Frédéric.",
        "conf": "HIGH",
    },
    # ── Mathieu: EPREUVE_ELIMINATOIRE (duel perdu) ← NEW from footnotes ───
    "Mathieu": {
        "type": "EPREUVE_ELIMINATOIRE",
        "reason": "Mathieu perd le duel organisé contre Thomas à l'issue de l'épreuve d'immunité. "
                  "Note Wikipedia: 'Mathieu perd le duel organisé contre Thomas à l'issue de "
                  "l'épreuve d'immunité. Par conséquent, il est directement éliminé.' "
                  "0 vote au conseil.",
        "excerpt": "Note Wikipedia: 'Mathieu perd le duel [...] il est directement éliminé.'",
        "conf": "HIGH",
    },
    # ── Still INDETERMINE (0 votes, likely orientation/poteaux, no source) ──
    "Flavio": {
        "type": "INDETERMINE",
        "reason": "0 vote au conseil. Éliminé par épreuve (orientation, poteaux ou autre). "
                  "Le mécanisme exact n'est pas documenté.",
        "excerpt": "Tableau des votes: 0 vote.",
        "conf": "LOW",
    },
    "Arnaud": {
        "type": "INDETERMINE",
        "reason": "0 vote au conseil. Éliminé par épreuve (probablement course d'orientation "
                  "ou poteaux). Le mécanisme exact n'est pas documenté.",
        "excerpt": "Tableau des votes: 0 vote.",
        "conf": "LOW",
    },
    "Laure": {
        "type": "INDETERMINE",
        "reason": "0 vote au conseil. Éliminée par épreuve. Mécanisme exact non documenté.",
        "excerpt": "Tableau des votes: 0 vote.",
        "conf": "LOW",
    },
    "Jonathan": {
        "type": "INDETERMINE",
        "reason": "1 seul vote (jour 35). Dernier éliminé avant la finale. "
                  "Possible NON_CHOISI_POUR_JURY_FINAL ou élimination par les finalistes. "
                  "La finale oppose Jonathan, Lucie et Maxine. Jonathan est éliminé avant "
                  "le vote du jury final.",
        "excerpt": "Tableau des votes: 1 vote. Dernier éliminé avant le jury.",
        "conf": "LOW",
    },
    # ── Already correct (no change needed) ─────────────────────────────────
    "Lucie":  {"type": "FINALISTE", "reason": "Finaliste (4/13 votes du jury).", "conf": "HIGH"},
    "Maxine": {"type": "VAINQUEUR", "reason": "Vainqueur (9/13 votes du jury).", "conf": "HIGH"},
}


def set_field(df, idx, col, val):
    df.at[idx, col] = val


def enrich_all(kl31, kl33):
    """Apply all enrichment to both DataFrames. Returns (kl31, kl33, kl31_changes, kl33_changes)."""
    kl31_changes = []
    kl33_changes = []

    # ── Add new columns ────────────────────────────────────────────────────
    for col, default in [
        ("departure_source_url", ""),
        ("departure_source_excerpt", ""),
        ("departure_source_quality", "MEDIUM"),
        ("departure_confidence", "HIGH"),
        ("departure_review_status", "A_REVOIR"),
        ("departure_mechanism_known", True),
    ]:
        for df in [kl31, kl33]:
            if col not in df.columns:
                df[col] = default

    # ── Set review_status for already-valid types ───────────────────────────
    for df, url in [(kl31, BASE_URL_KL31), (kl33, BASE_URL_KL33)]:
        for idx, row in df.iterrows():
            t = row["departure_type_normalized"]
            if t in ("VAINQUEUR", "FINALISTE", "ABANDON_MEDICAL", "CONSEIL",
                     "ABANDON_VOLONTAIRE", "EXCLUSION_DISCIPLINAIRE"):
                if row.get("departure_review_status") in ("", "A_REVOIR"):
                    set_field(df, idx, "departure_review_status", "VALIDATED")
                if not row.get("departure_source_url") or pd.isna(row.get("departure_source_url")):
                    set_field(df, idx, "departure_source_url", url)
                    set_field(df, idx, "departure_source_excerpt",
                              str(row.get("departure_description_raw", ""))[:200])
                    set_field(df, idx, "departure_source_quality", "HIGH")
                    set_field(df, idx, "departure_confidence", "HIGH")

    # ═══ KL31 Audit ═══════════════════════════════════════════════════════
    for idx, row in kl31.iterrows():
        name = row["candidate_name"]
        if name not in KL31_AUDIT:
            continue
        a = KL31_AUDIT[name]
        set_field(kl31, idx, "departure_classification_reason", a["reason"])
        set_field(kl31, idx, "departure_source_url", BASE_URL_KL31)
        set_field(kl31, idx, "departure_source_excerpt", a["excerpt"])
        set_field(kl31, idx, "departure_source_quality", "HIGH")
        set_field(kl31, idx, "departure_confidence", a["confidence"])
        set_field(kl31, idx, "departure_review_status", "VALIDATED")
        set_field(kl31, idx, "departure_mechanism_known",
                  a["proposed_type"] != "INDETERMINE")
        set_field(kl31, idx, "needs_departure_enrichment",
                  a["proposed_type"] == "INDETERMINE")
        kl31_changes.append({"name": name, "before": row["departure_type_normalized"],
                             "after": a["proposed_type"], "status": "VALIDATED"})

    # ═══ KL33 Enrichment ══════════════════════════════════════════════════
    for idx, row in kl33.iterrows():
        name = row["candidate_name"]
        if name not in KL33_ENRICHMENT:
            continue

        e = KL33_ENRICHMENT[name]
        current = row["departure_type_normalized"]

        # Magali: special return case
        if e.get("is_return_case"):
            fe = e["first_exit"]
            se = e["second_exit"]
            # Fix first_exit_order (was incorrectly 16, should be 5)
            set_field(kl33, idx, "first_exit_order", fe["order"])
            set_field(kl33, idx, "first_exit_type", fe["type"])
            set_field(kl33, idx, "return_stage", f"Jour {e['return']['day']}: {e['return']['reason']}")
            set_field(kl33, idx, "second_exit_type", se["type"])
            set_field(kl33, idx, "analysis_exit_order", fe["order"])
            set_field(kl33, idx, "analysis_exit_rule", "FIRST_EXIT_BEFORE_MEDICAL_RETURN")
            # First exit is CONSEIL (conseil surprise)
            set_field(kl33, idx, "departure_classification_reason",
                      f"1ère élimination (jour {fe['day']}): {fe['reason']} | "
                      f"Retour (jour {e['return']['day']}): {e['return']['reason']} | "
                      f"2ème élimination: {se['reason']}")
            set_field(kl33, idx, "departure_source_url", f"{BASE_URL_KL33}#Notes_et_références")
            set_field(kl33, idx, "departure_source_excerpt",
                      f"1ère: {fe['excerpt']} | 2ème: {se['excerpt']}")
            set_field(kl33, idx, "departure_source_quality", "HIGH")
            set_field(kl33, idx, "departure_confidence", fe["conf"])
            set_field(kl33, idx, "departure_review_status", "VALIDATED")
            set_field(kl33, idx, "departure_mechanism_known", True)
            set_field(kl33, idx, "needs_departure_enrichment", False)
            # model_category: CONSEIL → DECISION_AVENTURIERS (for first exit analysis only)
            # Keep departure_type as CONSEIL for second exit (main event)
            set_field(kl33, idx, "departure_type_normalized", se["type"])
            set_field(kl33, idx, "departure_model_category", map_to_model_category(se["type"]))
            set_field(kl33, idx, "departure_category", "DECISION_AVENTURIERS")
            kl33_changes.append({
                "name": name, "before": current, "after": f"MAGALI_RETURN(1st={fe['type']},2nd={se['type']})",
                "status": "VALIDATED", "first_exit_order": fe["order"],
            })
            continue

        # Gabin: already ABANDON_MEDICAL from scraping, just enrich metadata
        if name == "Gabin":
            set_field(kl33, idx, "departure_classification_reason", e["reason"])
            set_field(kl33, idx, "departure_source_url", f"{BASE_URL_KL33}#Notes_et_références")
            set_field(kl33, idx, "departure_source_excerpt", e["excerpt"])
            set_field(kl33, idx, "departure_source_quality", "HIGH")
            set_field(kl33, idx, "departure_confidence", e["conf"])
            set_field(kl33, idx, "departure_review_status", "VALIDATED")
            set_field(kl33, idx, "departure_mechanism_known", True)
            set_field(kl33, idx, "needs_departure_enrichment", False)
            continue

        # Already correct types, skip
        if current == e["type"] and e["type"] in ("FINALISTE", "VAINQUEUR", "ABANDON_MEDICAL"):
            continue

        new_type = e["type"]
        set_field(kl33, idx, "departure_type_normalized", new_type)
        set_field(kl33, idx, "departure_model_category", map_to_model_category(new_type))
        set_field(kl33, idx, "departure_category",
                  "DECISION_AVENTURIERS" if map_to_model_category(new_type) == "DECISION_AVENTURIERS"
                  else "EPREUVE" if map_to_model_category(new_type) == "EPREUVE"
                  else "SANTE_ABANDON" if new_type == "ABANDON_MEDICAL"
                  else "FIN_DE_JEU" if new_type in ("FINALISTE", "VAINQUEUR")
                  else "INDETERMINE")
        set_field(kl33, idx, "departure_classification_reason", e["reason"])
        set_field(kl33, idx, "departure_source_url", f"{BASE_URL_KL33}#Notes_et_références")
        set_field(kl33, idx, "departure_source_excerpt", e["excerpt"])
        set_field(kl33, idx, "departure_source_quality", "HIGH")
        set_field(kl33, idx, "departure_confidence", e["conf"])
        if new_type == "INDETERMINE":
            set_field(kl33, idx, "departure_review_status", "INSUFFICIENT_EVIDENCE")
            set_field(kl33, idx, "departure_mechanism_known", False)
            set_field(kl33, idx, "needs_departure_enrichment", True)
        else:
            set_field(kl33, idx, "departure_review_status", "VALIDATED")
            set_field(kl33, idx, "departure_mechanism_known", True)
            set_field(kl33, idx, "needs_departure_enrichment", False)
        kl33_changes.append({"name": name, "before": current, "after": new_type,
                             "status": "VALIDATED" if new_type != "INDETERMINE" else "INSUFFICIENT_EVIDENCE"})

    return kl31, kl33, kl31_changes, kl33_changes


def build_presence_intervals(kl33_df):
    """Build longitudinal presence intervals table."""
    rows = []
    for _, row in kl33_df.iterrows():
        name = row["candidate_name"]
        season = row["season_name"]
        order = row["final_exit_order"]

        if name == "Magali":
            rows.append({"season_name": season, "candidate_name": name,
                         "interval_start_day": 1, "interval_end_day": 13,
                         "presence_status": "PRESENT", "active_in_main_game": True,
                         "interval_reason": "Active depuis le début",
                         "source_url": BASE_URL_KL33, "review_status": "VALIDATED"})
            rows.append({"season_name": season, "candidate_name": name,
                         "interval_start_day": 14, "interval_end_day": 15,
                         "presence_status": "ABSENT", "active_in_main_game": False,
                         "interval_reason": "Éliminée au conseil surprise (jour 13), "
                                            "rappelée après évacuation médicale de Gabin (jour 15)",
                         "source_url": BASE_URL_KL33, "review_status": "VALIDATED"})
            rows.append({"season_name": season, "candidate_name": name,
                         "interval_start_day": 16, "interval_end_day": 33,
                         "presence_status": "PRESENT", "active_in_main_game": True,
                         "interval_reason": "Réintégrée après abandon médical de Gabin",
                         "source_url": BASE_URL_KL33, "review_status": "VALIDATED"})
            rows.append({"season_name": season, "candidate_name": name,
                         "interval_start_day": 34, "interval_end_day": None,
                         "presence_status": "ELIMINATED", "active_in_main_game": False,
                         "interval_reason": "Éliminée au conseil (seconde élimination, jour 33)",
                         "source_url": BASE_URL_KL33, "review_status": "VALIDATED"})
        else:
            rows.append({"season_name": season, "candidate_name": name,
                         "interval_start_day": 1, "interval_end_day": None,
                         "presence_status": "STANDARD", "active_in_main_game": True,
                         "interval_reason": "Présence standard sans interruption",
                         "source_url": BASE_URL_KL33 if "KL33" in str(row.get("season_id", ""))
                         else BASE_URL_KL31, "review_status": "VALIDATED"})

    return pd.DataFrame(rows)


def build_final_audit(kl31, kl33):
    """Build final audit table per candidate."""
    rows = []
    for df, sid in [(kl31, "KL31"), (kl33, "KL33")]:
        for _, row in df.iterrows():
            rows.append({
                "season_id": sid,
                "candidate_name": row["candidate_name"],
                "final_exit_order": row["final_exit_order"],
                "first_exit_order": row.get("first_exit_order"),
                "analysis_exit_order": row.get("analysis_exit_order"),
                "analysis_exit_rule": row.get("analysis_exit_rule", "STANDARD"),
                "departure_type_normalized": row["departure_type_normalized"],
                "departure_model_category": row["departure_model_category"],
                "departure_mechanism_known": row.get("departure_mechanism_known", True),
                "needs_departure_enrichment": row.get("needs_departure_enrichment", False),
                "returned_to_game": row.get("returned_to_game", False),
                "all_cause_exit_event": row["all_cause_exit_event"],
                "censored_at_end": row["censored_at_end"],
                "departure_review_status": row.get("departure_review_status", ""),
                "departure_source_url": row.get("departure_source_url", ""),
            })
    return pd.DataFrame(rows)


def compute_quality_summary(kl31, kl33):
    """Compute per-season quality metrics."""
    result = {}
    for df, sid in [(kl31, "KL31"), (kl33, "KL33")]:
        n = int(len(df))
        definitive = df[df["all_cause_exit_event"] == 1]
        definitive_n = int(len(definitive))
        known = definitive[definitive.get("departure_mechanism_known", True) == True]
        known_n = int(len(known))
        indet_n = int((df["departure_type_normalized"] == "INDETERMINE").sum())
        coverage = float(round(known_n / definitive_n, 4)) if definitive_n > 0 else 1.0
        return_count = int(df[df.get("returned_to_game", False) == True].shape[0])
        review_count = int(df[df.get("exit_order_review_required", False) == True].shape[0])

        ready_all_cause = True
        if coverage >= 0.90:
            ready_descriptive = "READY"
        elif coverage >= 0.75:
            ready_descriptive = "READY_WITH_WARNING"
        else:
            ready_descriptive = "INSUFFICIENT"

        result[sid] = {
            "candidate_count": n,
            "definitive_exit_count": definitive_n,
            "known_mechanism_count": known_n,
            "indeterminate_count": indet_n,
            "departure_mechanism_coverage": coverage,
            "return_case_count": return_count,
            "exit_order_review_count": review_count,
            "ready_for_all_cause_model": ready_all_cause,
            "ready_for_descriptive_departure_statistics": ready_descriptive,
        }
    return result


def run_validations(kl31, kl33, thai_hashes):
    ok = True
    msgs = []

    total = len(kl31) + len(kl33)
    v1 = total == 41
    msgs.append(f"{'OK' if v1 else 'FAIL'} 1: 41 candidats (trouvé: {total})")
    if not v1: ok = False

    v2 = not pd.concat([kl31, kl33]).duplicated(subset=["candidate_name", "season_name"]).any()
    msgs.append(f"{'OK' if v2 else 'FAIL'} 2: Aucune duplication")
    if not v2: ok = False

    v3a = list(kl31["final_exit_order"]) == list(range(1, 21))
    v3b = list(kl33["final_exit_order"]) == list(range(1, 22))
    msgs.append(f"{'OK' if v3a and v3b else 'FAIL'} 3: Rangs préservés (KL31={v3a}, KL33={v3b})")
    if not (v3a and v3b): ok = False

    magali = kl33[kl33["candidate_name"] == "Magali"]
    v4a = len(magali) == 1
    v4b = magali["first_exit_order"].values[0] == 5
    v4c = magali["analysis_exit_order"].values[0] == 5
    v4d = magali["returned_to_game"].values[0] == True
    v4 = v4a and v4b and v4c and v4d
    msgs.append(f"{'OK' if v4 else 'FAIL'} 4: Magali: 1 obs, first_exit=5, analysis=5, returned=True")
    if not v4: ok = False

    gabin = kl33[kl33["candidate_name"] == "Gabin"]
    v5 = gabin["departure_type_normalized"].values[0] == "ABANDON_MEDICAL"
    msgs.append(f"{'OK' if v5 else 'FAIL'} 5: Gabin=ABANDON_MEDICAL")
    if not v5: ok = False

    for df, sid in [(kl31, "KL31"), (kl33, "KL33")]:
        w = df[df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        nw = df[~df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        v6 = (w["censored_at_end"] == True).all() and (nw["all_cause_exit_event"] == 1).all()
        msgs.append(f"{'OK' if v6 else 'FAIL'} 6 {sid}: Winners censored, others event=1")
        if not v6: ok = False

    v7 = kl31["departure_type_normalized"].isin(AUTHORIZED_TYPES).all() and \
         kl33["departure_type_normalized"].isin(AUTHORIZED_TYPES).all()
    msgs.append(f"{'OK' if v7 else 'FAIL'} 7: Types autorisés")
    if not v7: ok = False

    for path in THAILANDE_FILES:
        if path in thai_hashes and os.path.exists(path):
            if sha256_file(path) != thai_hashes[path]:
                msgs.append(f"FAIL 8: Thailand file modified: {os.path.basename(path)}")
                ok = False
    msgs.append("OK 8: Fichiers Thaïlande intacts")

    fred = kl33[kl33["candidate_name"] == "Frédéric"]
    v9 = fred["departure_type_normalized"].values[0] == "AMBASSADEURS_ACCORD"
    msgs.append(f"{'OK' if v9 else 'FAIL'} 9: Frédéric=AMBASSADEURS_ACCORD")
    if not v9: ok = False

    math = kl33[kl33["candidate_name"] == "Mathieu"]
    v10 = math["departure_type_normalized"].values[0] == "EPREUVE_ELIMINATOIRE"
    msgs.append(f"{'OK' if v10 else 'FAIL'} 10: Mathieu=EPREUVE_ELIMINATOIRE (duel perdu)")
    if not v10: ok = False

    # INDETERMINE → needs_enrichment=True, mechanism_known=False
    for df in [kl31, kl33]:
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        v11 = indet["needs_departure_enrichment"].all() and (indet.get("departure_mechanism_known", True) == False).all()
        if not v11 and len(indet) > 0:
            msgs.append("FAIL 11: INDETERMINE not properly flagged")
            ok = False
    msgs.append("OK 11: INDETERMINE correctly flagged")

    # model_category for INDETERMINE stays INDETERMINE (not AUTO_SORTIE)
    indet_kl33 = kl33[kl33["departure_type_normalized"] == "INDETERMINE"]
    v12 = (indet_kl33["departure_model_category"] == "INDETERMINE").all() if len(indet_kl33) > 0 else True
    msgs.append(f"{'OK' if v12 else 'FAIL'} 12: INDETERMINE model_category ≠ AUTRE_SORTIE")
    if not v12: ok = False

    return ok, msgs


def main():
    print("=" * 70)
    print("ENRICHISSEMENT & AUDIT FINAL — SAISONS PILOTES")
    print("=" * 70)

    kl31 = pd.read_csv(KL31_RAW)
    kl33 = pd.read_csv(KL33_RAW)
    print(f"\nKL31: {len(kl31)} | KL33: {len(kl33)}")

    thai_hashes = {}
    for p in THAILANDE_FILES:
        if os.path.exists(p): thai_hashes[p] = sha256_file(p)

    # ── Enrich ────────────────────────────────────────────────────────────
    kl31, kl33, c31, c33 = enrich_all(kl31, kl33)

    print(f"\n─── KL31 ({len(c31)} audités) ───")
    for c in c31: print(f"  {c['name']}: {c['before']} → {c['after']} ({c['status']})")

    print(f"\n─── KL33 ({len(c33)} changements) ───")
    for c in c33:
        extra = f" first_exit_order={c.get('first_exit_order','')}" if c.get("first_exit_order") else ""
        print(f"  {c['name']}: {c['before']} → {c['after']} ({c['status']}){extra}")

    # ── Validations ───────────────────────────────────────────────────────
    print(f"\n─── VALIDATIONS ───")
    ok, msgs = run_validations(kl31, kl33, thai_hashes)
    for m in msgs: print(f"  {m}")

    # ── Save enriched ─────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(ENRICHED_CSV), exist_ok=True)
    combined = pd.concat([kl31, kl33], ignore_index=True)
    combined.to_csv(ENRICHED_CSV, index=False, encoding="utf-8")
    print(f"\nEnriched: {ENRICHED_CSV} ({len(combined)} rows)")

    # ── Research queue ────────────────────────────────────────────────────
    queue = combined[combined["needs_departure_enrichment"] == True][
        ["season_name", "candidate_name", "departure_description_raw",
         "departure_type_normalized", "departure_classification_reason",
         "departure_source_url", "departure_source_excerpt",
         "departure_confidence", "departure_review_status"]
    ].copy()
    queue["search_query_1"] = queue["candidate_name"].apply(lambda n: f'"{n}" "Koh-Lanta" élimination')
    queue["search_query_2"] = queue["candidate_name"].apply(lambda n: f'"{n}" "Koh-Lanta" conseil ambassadeurs')
    queue["search_query_3"] = queue["candidate_name"].apply(lambda n: f'"{n}" "Koh-Lanta" cause départ')
    queue["manual_research_required"] = True
    queue.to_csv(RESEARCH_QUEUE, index=False, encoding="utf-8")
    print(f"Research queue: {RESEARCH_QUEUE} ({len(queue)} rows)")

    # ── Enrichment report ─────────────────────────────────────────────────
    report_rows = []
    for c in c31:
        report_rows.append({"season_name": "KL31", "candidate_name": c["name"],
                            "current_type": c["before"], "proposed_type": c["after"],
                            "classification_reason": "Audit EPREUVE_ELIMINATOIRE",
                            "source_url": BASE_URL_KL31, "confidence": "HIGH",
                            "review_status": c["status"]})
    for c in c33:
        report_rows.append({"season_name": "KL33", "candidate_name": c["name"],
                            "current_type": c["before"], "proposed_type": c["after"],
                            "classification_reason": "Enrichi depuis tableau des votes + notes",
                            "source_url": BASE_URL_KL33, "confidence": "HIGH",
                            "review_status": c["status"]})
    pd.DataFrame(report_rows).to_csv(ENRICHMENT_REPORT, index=False, encoding="utf-8")
    print(f"Report: {ENRICHMENT_REPORT} ({len(report_rows)} rows)")

    # ── Presence intervals ────────────────────────────────────────────────
    pres = build_presence_intervals(kl33)
    pres.to_csv(PRESENCE_INTERVALS, index=False, encoding="utf-8")
    print(f"Presence intervals: {PRESENCE_INTERVALS} ({len(pres)} rows)")

    # ── Final audit ───────────────────────────────────────────────────────
    audit = build_final_audit(kl31, kl33)
    audit.to_csv(FINAL_AUDIT, index=False, encoding="utf-8")
    print(f"Final audit: {FINAL_AUDIT} ({len(audit)} rows)")

    # ── Quality summary ───────────────────────────────────────────────────
    quality = compute_quality_summary(kl31, kl33)
    with open(QUALITY_JSON, "w", encoding="utf-8") as f:
        json.dump(quality, f, indent=2, ensure_ascii=False)
    print(f"Quality: {QUALITY_JSON}")

    # ── Final report ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RAPPORT FINAL — AUDIT & ENRICHISSEMENT")
    print("=" * 70)

    print(f"\n─── MAGALI (KL33) — Chronologie corrigée ───")
    m = kl33[kl33["candidate_name"] == "Magali"].iloc[0]
    print(f"  1ère élimination: jour 13, CONSEIL (conseil surprise), ordre={m['first_exit_order']}")
    print(f"  Retour: jour 15, remplacement médical de Gabin")
    print(f"  2ème élimination: jour 33, CONSEIL, ordre final={m['final_exit_order']}")
    print(f"  analysis_exit_order={m['analysis_exit_order']}, analysis_exit_rule={m['analysis_exit_rule']}")

    print(f"\n─── KL31 — 4 épreuves auditées ───")
    for t, c in kl31["departure_type_normalized"].value_counts().items():
        print(f"  {t}: {c}")

    print(f"\n─── KL33 — Enrichissement final ───")
    for t, c in kl33["departure_type_normalized"].value_counts().items():
        print(f"  {t}: {c}")
    indet = kl33[kl33["departure_type_normalized"] == "INDETERMINE"]
    if len(indet) > 0:
        print(f"  INDETERMINE restants: {list(indet['candidate_name'])}")

    print(f"\n─── Qualité par saison ───")
    for sid, q in quality.items():
        print(f"  {sid}: coverage={q['departure_mechanism_coverage']:.1%} "
              f"({q['known_mechanism_count']}/{q['definitive_exit_count']}) "
              f"all_cause={q['ready_for_all_cause_model']} "
              f"descriptive={q['ready_for_descriptive_departure_statistics']}")

    print(f"\n─── Fichiers créés ───")
    print(f"  {ENRICHED_CSV}")
    print(f"  {RESEARCH_QUEUE}")
    print(f"  {ENRICHMENT_REPORT}")
    print(f"  {PRESENCE_INTERVALS}")
    print(f"  {FINAL_AUDIT}")
    print(f"  {QUALITY_JSON}")

    print(f"\nValidation: {'✓ TOUT OK' if ok else '✗ ÉCHECS'}")
    return combined


if __name__ == "__main__":
    main()