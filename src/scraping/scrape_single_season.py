"""
Scraper for a single season of Koh-Lanta.
Test season: Koh-Lanta : Thaïlande (season 15)
Source: English Wikipedia (French page was deleted)
URL: https://en.wikipedia.org/wiki/Koh-Lanta:_Tha%C3%AFlande

Version 2 — Corrections post-audit.
"""

import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import requests
from bs4 import BeautifulSoup

# ─── Configuration ───────────────────────────────────────────────────────────

SEASON_NAME = "Koh-Lanta : Thaïlande"
SEASON_YEAR = 2016
# NOTE: The French Wikipedia page https://fr.wikipedia.org/wiki/Koh-Lanta_:_Thaïlande
# does not exist (HTTP 404). It was deleted following an admissibility discussion.
# The English Wikipedia page is used as the primary source instead.
SEASON_URL = "https://en.wikipedia.org/wiki/Koh-Lanta:_Tha%C3%AFlande"
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ─── Authorized departure values ─────────────────────────────────────────────

AUTHORIZED_DEPARTURE_TYPES = {
    "CONSEIL",
    "AMBASSADEURS_ACCORD",
    "AMBASSADEURS_TIRAGE_AU_SORT",
    "VOTE_NOIR",
    "DETOURNEMENT_DE_VOTE",
    "AUTRE_VOTE",
    "EPREUVE_ELIMINATOIRE",
    "ELIMINATION_INITIALE",
    "DESTINS_LIES",
    "DESTINS_LIES_SUITE_CONSEIL",
    "COURSE_ORIENTATION",
    "POTEAUX",
    "NON_CHOISI_POUR_JURY_FINAL",
    "AUTRE_EPREUVE",
    "ABANDON_MEDICAL",
    "ABANDON_VOLONTAIRE",
    "EXCLUSION_DISCIPLINAIRE",
    "DUEL_EXIL_PERDU",
    "ILE_SECONDE_CHANCE_PERDUE",
    "ELIMINATION_PROVISOIRE_AVEC_RETOUR",
    "AUTRE_MECANIQUE_RETOUR",
    "FINALISTE",
    "VAINQUEUR",
    "AUTRE",
    "INDETERMINE",
}

AUTHORIZED_DEPARTURE_CATEGORIES = {
    "DECISION_AVENTURIERS",
    "EPREUVE",
    "SANTE_ABANDON",
    "SANCTION",
    "MECANIQUE_RETOUR",
    "FIN_DE_JEU",
    "AUTRE",
    "INDETERMINE",
}

AUTHORIZED_MODEL_CATEGORIES = {
    "DECISION_AVENTURIERS",
    "EPREUVE",
    "AUTRE_SORTIE",
}

# ─── Model category mapping ──────────────────────────────────────────────────

def map_to_model_category(departure_type: str) -> str:
    """Map a detailed departure type to one of three model categories."""
    decision_types = {
        "CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
        "VOTE_NOIR", "DETOURNEMENT_DE_VOTE", "AUTRE_VOTE",
        "NON_CHOISI_POUR_JURY_FINAL", "DESTINS_LIES_SUITE_CONSEIL",
    }
    epreuve_types = {
        "EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE", "DESTINS_LIES",
        "COURSE_ORIENTATION", "POTEAUX", "DUEL_EXIL_PERDU",
        "ILE_SECONDE_CHANCE_PERDUE", "AUTRE_EPREUVE",
    }
    if departure_type in decision_types:
        return "DECISION_AVENTURIERS"
    if departure_type in epreuve_types:
        return "EPREUVE"
    return "AUTRE_SORTIE"


# ─── Helper functions ────────────────────────────────────────────────────────


def clean_text(text: str) -> str:
    """Remove Wikipedia references, extra whitespace, and formatting."""
    if not isinstance(text, str):
        return text
    # Remove Wikipedia reference markers like [1], [2], [note 3], [a], [b], etc.
    text = re.sub(r'\[\s*[a-zA-Z0-9]+\s*(?:\s*[–\-]\s*[a-zA-Z0-9]+)?\s*\]', '', text)
    text = re.sub(r'\[\s*[a-zA-Z]+\s*\]', '', text)
    # Remove citation needed markers
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_contestant_field(raw: str):
    """
    Parse a contestant field like:
    'Charlie Vincent-Mussard 28, Le Mans'
    -> name='Charlie Vincent-Mussard', age='28', city='Le Mans'

    Or complex cases:
    'Laurence "Lolo" Facione 45, Cergy-Pontoise'
    -> name='Laurence "Lolo" Facione', age='45', city='Cergy-Pontoise'

    'Gabriel Gubbels 40, Namur , Belgium'
    -> name='Gabriel Gubbels', age='40', city='Namur, Belgium'
    """
    raw = clean_text(raw)
    # Pattern: name (may contain letters, hyphens, quotes, spaces),
    # then a number (age), then a comma, then city
    match = re.match(r'^(.*?)\s+(\d{1,3})\s*,\s*(.*?)$', raw)
    if match:
        name = match.group(1).strip()
        age = match.group(2).strip()
        city = match.group(3).strip()
        # Remove any double-spaces or trailing commas from city
        city = re.sub(r'\s+', ' ', city).strip(',').strip()
        return name, age, city
    else:
        # Fallback: return the whole string as name
        return raw, None, None


def classify_departure(finish_text: str):
    """
    Classify the departure type and category based on the Finish text
    from the English Wikipedia contestant table.

    Returns: (departure_type_normalized, departure_category,
              departure_is_definitive, needs_departure_enrichment,
              departure_classification_reason)
    """
    finish = clean_text(finish_text).strip()

    # Sole Survivor = VAINQUEUR
    if re.match(r'^(Sole|Ultimate)\s+Survivor', finish, re.IGNORECASE):
        return ("VAINQUEUR", "FIN_DE_JEU", True, False,
                "Sole Survivor explicitement indiqué dans la source")

    # Runner-up = FINALISTE
    if re.match(r'^Runner[- ]up', finish, re.IGNORECASE):
        return ("FINALISTE", "FIN_DE_JEU", True, False,
                "Runner-up explicitement indiqué dans la source")

    # Lost Duel = DUEL_EXIL_PERDU
    if re.search(r'Lost\s+Duel', finish, re.IGNORECASE):
        return ("DUEL_EXIL_PERDU", "MECANIQUE_RETOUR", True, False,
                "Lost Duel explicitement indiqué dans la source")

    # Lost Challenge = EPREUVE_ELIMINATOIRE
    if re.search(r'Lost\s+Challenge', finish, re.IGNORECASE):
        return ("EPREUVE_ELIMINATOIRE", "EPREUVE", True, False,
                "Lost Challenge explicitement indiqué dans la source")

    # Left Competition = AMBIGUOUS — never auto-classify
    if re.search(r'Left\s+Competition', finish, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True,
                "Left Competition est ambigu : recherche complémentaire nécessaire "
                "(abandon volontaire ou médical non précisé)")

    # Voted Out = CONSEIL
    if re.search(r'Voted\s+Out', finish, re.IGNORECASE):
        return ("CONSEIL", "DECISION_AVENTURIERS", True, False,
                "Voted Out explicitement indiqué dans la source")

    # Eliminated without mechanism specification
    if re.search(r'Eliminated', finish, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True,
                "Eliminated sans précision du mécanisme dans la source")

    # Medical evacuation
    if re.search(r'Medical|Evacuated|Medically', finish, re.IGNORECASE):
        return ("ABANDON_MEDICAL", "SANTE_ABANDON", True, False,
                "Évacuation médicale explicitement indiquée dans la source")

    # Quit / Withdrew
    if re.search(r'Quit|Withdr[ae]w|Walked', finish, re.IGNORECASE):
        return ("ABANDON_VOLONTAIRE", "SANTE_ABANDON", True, False,
                "Abandon volontaire explicitement indiqué dans la source")

    # Ejected / Removed
    if re.search(r'Ejected|Removed|Disqualified', finish, re.IGNORECASE):
        return ("EXCLUSION_DISCIPLINAIRE", "SANCTION", True, False,
                "Exclusion disciplinaire explicitement indiquée dans la source")

    # Fallback
    return ("INDETERMINE", "INDETERMINE", True, True,
            "Mécanisme de sortie non identifiable dans la source")


def extract_day(finish_text: str):
    """Extract the day number from a Finish text like '1st Voted Out Day 3'."""
    day_match = re.search(r'Day\s+(\d+)', finish_text, re.IGNORECASE)
    return f"Day {day_match.group(1)}" if day_match else None


# ─── Main scraping logic ─────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print("SCRAPING KOH-LANTA : THAÏLANDE (SAISON 15) — v2")
    print("=" * 70)
    print(f"\nURL traitée : {SEASON_URL}")
    print("NOTE : La page française a été supprimée. Utilisation de la page anglaise.")

    # ── Fetch page ───────────────────────────────────────────────────────────
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(SEASON_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # ── Find tables ──────────────────────────────────────────────────────────
    all_wikitables = soup.find_all("table", class_="wikitable")
    print(f"\nNombre de tableaux wikitable trouvés : {len(all_wikitables)}")

    # Identify contestant tables
    contestant_tables = []
    for i, table in enumerate(all_wikitables):
        headers_list = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Contestant" in headers_list and "Finish" in headers_list:
            contestant_tables.append((i, table))
            print(f"  Tableau {i} identifié comme tableau des candidats "
                  f"(headers: {headers_list})")

    if not contestant_tables:
        print("ERREUR : Aucun tableau de candidats trouvé !")
        sys.exit(1)

    print(f"\nTableau(x) sélectionné(s) : {[t[0] for t in contestant_tables]}")
    table_idx, contestant_table = contestant_tables[0]

    # ── Parse the contestant table ───────────────────────────────────────────
    rows = contestant_table.find_all("tr")
    print(f"Nombre de lignes dans le tableau : {len(rows)}")

    header_cells = [th.get_text(strip=True) for th in rows[0].find_all("th")]
    print(f"Colonnes originales : {header_cells}")

    candidates = []
    source_row_number = 0

    for row in rows[1:]:  # Skip header row
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        if not cells or len(cells) < 2:
            continue
        if not cells[0].strip():
            continue

        source_row_number += 1
        raw_contestant = cells[0].strip()

        # The "Finish" column is always the last cell.
        finish_text = cells[-1].strip() if cells else ""

        # Parse contestant field
        name, age, city = parse_contestant_field(raw_contestant)

        # Classify departure (v2: classification includes reason and enrichment flag)
        dep_type, dep_cat, is_definitive, needs_enrich, class_reason = (
            classify_departure(finish_text)
        )

        # Extract day
        departure_day = extract_day(finish_text)

        candidates.append({
            "candidate_name": name,
            "age_raw": age,
            "finish_text": finish_text,
            "departure_day_raw": departure_day,
            "departure_type_normalized": dep_type,
            "departure_category": dep_cat,
            "departure_is_definitive": is_definitive,
            "needs_departure_enrichment": needs_enrich,
            "departure_classification_reason": class_reason,
            "source_row_number": source_row_number,
        })

    print(f"\nNombre exact de candidats extraits : {len(candidates)}")
    N = len(candidates)  # Total number of candidates

    # ── Assign final_exit_order (strict 1..N by table order) ────────────────
    for i, c in enumerate(candidates):
        c["final_exit_order"] = i + 1

    # ── Compute final_exit_order_normalized ──────────────────────────────────
    for c in candidates:
        order = c["final_exit_order"]
        c["final_exit_order_normalized"] = round((order - 1) / (N - 1), 6)

    # ── Identify same-day exits ─────────────────────────────────────────────
    day_to_candidates = {}
    for c in candidates:
        day = c["departure_day_raw"]
        if day:
            day_to_candidates.setdefault(day, []).append(c["candidate_name"])

    for c in candidates:
        day = c["departure_day_raw"]
        if day and len(day_to_candidates.get(day, [])) >= 2:
            c["same_day_exit_group"] = day
        else:
            c["same_day_exit_group"] = None

    # ── Create DataFrame ─────────────────────────────────────────────────────
    columns = [
        "season_name", "season_year", "season_url", "candidate_name",
        "gender_raw", "age_raw", "profession_raw",
        "final_position_raw", "final_exit_order", "final_exit_order_normalized",
        "departure_day_raw", "same_day_exit_group",
        "departure_description_raw", "departure_type_normalized",
        "departure_category", "departure_model_category",
        "departure_classification_reason",
        "needs_departure_enrichment", "departure_is_definitive",
        "had_temporary_elimination", "returned_to_game",
        "first_exit_order", "first_exit_type", "first_exit_model_category",
        "first_exit_description",
        "final_exit_type", "final_exit_model_category", "final_exit_description",
        "model_exit_order", "model_exit_type", "model_exit_category",
        "physical_score", "physical_score_justification",
        "physical_score_sources", "source_row_number", "scraped_at",
    ]

    data_rows = []
    for c in candidates:
        dep_type = c["departure_type_normalized"]
        model_cat = map_to_model_category(dep_type)
        exit_order = c["final_exit_order"]
        finish = c["finish_text"]
        data_rows.append({
            "season_name": SEASON_NAME,
            "season_year": SEASON_YEAR,
            "season_url": SEASON_URL,
            "candidate_name": c["candidate_name"],
            "gender_raw": None,
            "age_raw": c["age_raw"],
            "profession_raw": None,
            "final_position_raw": finish,
            "final_exit_order": exit_order,
            "final_exit_order_normalized": c["final_exit_order_normalized"],
            "departure_day_raw": c["departure_day_raw"],
            "same_day_exit_group": c["same_day_exit_group"],
            "departure_description_raw": finish,
            "departure_type_normalized": dep_type,
            "departure_category": c["departure_category"],
            "departure_model_category": model_cat,
            "departure_classification_reason": c["departure_classification_reason"],
            "needs_departure_enrichment": c["needs_departure_enrichment"],
            "departure_is_definitive": c["departure_is_definitive"],
            "had_temporary_elimination": False,
            "returned_to_game": False,
            "first_exit_order": exit_order,
            "first_exit_type": dep_type,
            "first_exit_model_category": model_cat,
            "first_exit_description": finish,
            "final_exit_type": dep_type,
            "final_exit_model_category": model_cat,
            "final_exit_description": finish,
            "model_exit_order": exit_order,
            "model_exit_type": dep_type,
            "model_exit_category": model_cat,
            "physical_score": None,
            "physical_score_justification": None,
            "physical_score_sources": None,
            "source_row_number": c["source_row_number"],
        })

    df = pd.DataFrame(data_rows, columns=columns)
    df["scraped_at"] = datetime.now(timezone.utc).isoformat()

    # ── Create output directory ──────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # ── Save CSV ─────────────────────────────────────────────────────────────
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    # ── Display results ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RÉSULTATS")
    print("=" * 70)

    print(f"\nColonnes finales ({len(columns)}) :")
    for col in columns:
        print(f"  - {col}")

    print(f"\nNombre de valeurs manquantes par colonne :")
    for col in columns:
        missing = df[col].isna().sum()
        if missing > 0:
            print(f"  {col}: {missing}/{len(df)}")

    print("\nLes 21 candidats (ordre de sortie) :")
    display_cols = [
        "candidate_name", "final_exit_order", "final_exit_order_normalized",
        "departure_day_raw", "departure_type_normalized", "needs_departure_enrichment",
    ]
    for _, row in df.iterrows():
        print(f"  {row['final_exit_order']:>2} | "
              f"{row['candidate_name']:<28} | "
              f"norm={row['final_exit_order_normalized']:.4f} | "
              f"{str(row['departure_day_raw']):>8} | "
              f"{row['departure_type_normalized']:<24} | "
              f"enrich={row['needs_departure_enrichment']}")

    print("\nDistribution de departure_type_normalized :")
    dist = df["departure_type_normalized"].value_counts()
    for val, count in dist.items():
        print(f"  {val}: {count}")

    print("\nDistribution de departure_category :")
    dist_cat = df["departure_category"].value_counts()
    for val, count in dist_cat.items():
        print(f"  {val}: {count}")

    # INDETERMINE
    indeterminate = df[df["departure_type_normalized"] == "INDETERMINE"]
    if len(indeterminate) > 0:
        print(f"\nCandidats classés INDETERMINE ({len(indeterminate)}) :")
        for _, row in indeterminate.iterrows():
            print(f"  - {row['candidate_name']} (ordre {row['final_exit_order']}): "
                  f"{row['departure_classification_reason']}")
    else:
        print("\nAucun candidat classé INDETERMINE.")

    # Sorties nécessitant enrichissement
    needs_enrich = df[df["needs_departure_enrichment"] == True]
    if len(needs_enrich) > 0:
        print(f"\nSorties nécessitant un enrichissement ({len(needs_enrich)}) :")
        for _, row in needs_enrich.iterrows():
            print(f"  - {row['candidate_name']} (ordre {row['final_exit_order']}): "
                  f"{row['departure_type_normalized']} — {row['departure_classification_reason']}")

    # Same-day exits
    same_day = df[df["same_day_exit_group"].notna()]
    if len(same_day) > 0:
        print(f"\nSorties simultanées (même jour) — {len(same_day)} candidats concernés :")
        for day_val in same_day["same_day_exit_group"].unique():
            names = same_day[same_day["same_day_exit_group"] == day_val]["candidate_name"].tolist()
            orders = same_day[same_day["same_day_exit_group"] == day_val]["final_exit_order"].tolist()
            print(f"  {day_val}: {', '.join(f'{n} (ordre {o})' for n, o in zip(names, orders))}")

    # Confirm finalist and winner
    finalist = df[df["departure_type_normalized"] == "FINALISTE"]
    winner = df[df["departure_type_normalized"] == "VAINQUEUR"]
    if len(finalist) > 0:
        for _, r in finalist.iterrows():
            print(f"\nFinaliste : {r['candidate_name']} — rang {r['final_exit_order']}")
    if len(winner) > 0:
        for _, r in winner.iterrows():
            print(f"Vainqueur  : {r['candidate_name']} — rang {r['final_exit_order']}")

    print(f"\nChemin du CSV : {OUTPUT_PATH}")

    # ── Validations ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VALIDATIONS")
    print("=" * 70)

    all_ok = True

    # V1: Exactly 21 candidates
    v1 = len(df) == 21
    print(f"{'OK' if v1 else 'FAIL'} V1 : 21 candidats exactement (trouve: {len(df)})")
    all_ok = all_ok and v1

    # V2: final_exit_order is 1..21 exactly once each
    orders = sorted(df["final_exit_order"].tolist())
    v2 = orders == list(range(1, 22))
    print(f"{'OK' if v2 else 'FAIL'} V2 : final_exit_order contient 1..21 exactement une fois "
          f"(trouvé: {orders})")
    all_ok = all_ok and v2

    # V3: first candidate has normalized = 0
    first = df.loc[df["final_exit_order"] == 1, "final_exit_order_normalized"].values
    v3 = len(first) > 0 and first[0] == 0.0
    print(f"{'✓' if v3 else '✗'} V3 : premier candidat a final_exit_order_normalized = 0 "
          f"(trouvé: {first[0] if len(first) > 0 else 'N/A'})")
    all_ok = all_ok and v3

    # V4: winner has normalized = 1
    winner_norm = df.loc[df["departure_type_normalized"] == "VAINQUEUR", "final_exit_order_normalized"].values
    if len(winner_norm) > 0:
        v4 = winner_norm[0] == 1.0
        print(f"{'✓' if v4 else '✗'} V4 : vainqueur a final_exit_order_normalized = 1 "
              f"(trouvé: {winner_norm[0]})")
    else:
        v4 = False
        print("✗ V4 : aucun vainqueur trouvé")
    all_ok = all_ok and v4

    # V5: all normalized values between 0 and 1
    norms = df["final_exit_order_normalized"]
    v5 = (norms >= 0).all() and (norms <= 1).all()
    print(f"{'✓' if v5 else '✗'} V5 : toutes les valeurs normalisées entre 0 et 1 "
          f"(min={norms.min():.4f}, max={norms.max():.4f})")
    all_ok = all_ok and v5

    # V6: finalist and winner have different orders
    if len(finalist) > 0 and len(winner) > 0:
        v6 = finalist["final_exit_order"].values[0] != winner["final_exit_order"].values[0]
        print(f"{'✓' if v6 else '✗'} V6 : finaliste et vainqueur ont des rangs différents "
              f"(finaliste={finalist['final_exit_order'].values[0]}, "
              f"vainqueur={winner['final_exit_order'].values[0]})")
    else:
        v6 = False
        print("✗ V6 : finaliste ou vainqueur non trouvé")
    all_ok = all_ok and v6

    # V7: Left Competition is never ABANDON_VOLONTAIRE
    left_comp = df[df["departure_description_raw"].str.contains("Left Competition", na=False)]
    v7 = all(left_comp["departure_type_normalized"] != "ABANDON_VOLONTAIRE")
    print(f"{'✓' if v7 else '✗'} V7 : 'Left Competition' jamais classé ABANDON_VOLONTAIRE "
          f"({len(left_comp)} occurrences)")
    all_ok = all_ok and v7

    # V8: INDETERMINE → needs_departure_enrichment = True
    indet = df[df["departure_type_normalized"] == "INDETERMINE"]
    v8 = indet["needs_departure_enrichment"].all() if len(indet) > 0 else True
    print(f"{'✓' if v8 else '✗'} V8 : toute sortie INDETERMINE a needs_departure_enrichment = True")
    all_ok = all_ok and v8

    # V9: physical_score columns still empty
    v9a = df["physical_score"].isna().all()
    v9b = df["physical_score_justification"].isna().all()
    v9c = df["physical_score_sources"].isna().all()
    v9 = v9a and v9b and v9c
    print(f"{'✓' if v9 else '✗'} V9 : colonnes physical_score vides")
    all_ok = all_ok and v9

    # V10: no duplicate candidate_name
    dupes = df[df.duplicated(subset=["candidate_name"], keep=False)]
    v10 = len(dupes) == 0
    print(f"{'✓' if v10 else '✗'} V10 : aucun doublon sur candidate_name "
          f"({len(dupes)} doublons)" if not v10 else "")
    all_ok = all_ok and v10

    # V11: candidate_name non vide
    v11 = df["candidate_name"].notna().all() and (df["candidate_name"].str.strip() != "").all()
    print(f"{'✓' if v11 else '✗'} V11 : candidate_name non vide")
    all_ok = all_ok and v11

    # V12: season_name, season_url filled
    v12a = df["season_name"].notna().all()
    v12b = df["season_url"].notna().all()
    v12 = v12a and v12b
    print(f"{'✓' if v12 else '✗'} V12 : season_name et season_url renseignés")
    all_ok = all_ok and v12

    # V13: age_raw not entirely empty
    v13 = not df["age_raw"].isna().all()
    print(f"{'✓' if v13 else '✗'} V13 : age_raw non entièrement vide "
          f"({df['age_raw'].notna().sum()}/{len(df)})")
    all_ok = all_ok and v13

    # V14: CSV created
    v14 = os.path.exists(OUTPUT_PATH)
    print(f"{'✓' if v14 else '✗'} V14 : CSV créé à {OUTPUT_PATH}")
    all_ok = all_ok and v14

    # V15: departure_model_category contains only valid values
    valid_model_cats = {"DECISION_AVENTURIERS", "EPREUVE", "AUTRE_SORTIE"}
    v15 = df["departure_model_category"].isin(valid_model_cats).all()
    print(f"{'✓' if v15 else '✗'} V15 : departure_model_category valide (3 catégories)")
    all_ok = all_ok and v15

    # V16: CONSEIL → DECISION_AVENTURIERS
    conseils = df[df["departure_type_normalized"] == "CONSEIL"]
    v16 = (conseils["departure_model_category"] == "DECISION_AVENTURIERS").all()
    print(f"{'✓' if v16 else '✗'} V16 : CONSEIL → DECISION_AVENTURIERS ({len(conseils)} candidats)")
    all_ok = all_ok and v16

    # V17: ABANDON_VOLONTAIRE → AUTRE_SORTIE
    abandons_v = df[df["departure_type_normalized"] == "ABANDON_VOLONTAIRE"]
    v17 = len(abandons_v) == 0 or (abandons_v["departure_model_category"] == "AUTRE_SORTIE").all()
    print(f"{'✓' if v17 else '✗'} V17 : ABANDON_VOLONTAIRE → AUTRE_SORTIE ({len(abandons_v)} candidats)")
    all_ok = all_ok and v17

    # V18: ABANDON_MEDICAL → AUTRE_SORTIE
    abandons_m = df[df["departure_type_normalized"] == "ABANDON_MEDICAL"]
    v18 = len(abandons_m) == 0 or (abandons_m["departure_model_category"] == "AUTRE_SORTIE").all()
    print(f"{'✓' if v18 else '✗'} V18 : ABANDON_MEDICAL → AUTRE_SORTIE ({len(abandons_m)} candidats)")
    all_ok = all_ok and v18

    # V19: EPREUVE_ELIMINATOIRE → EPREUVE
    epreuves = df[df["departure_type_normalized"] == "EPREUVE_ELIMINATOIRE"]
    v19 = (epreuves["departure_model_category"] == "EPREUVE").all()
    print(f"{'✓' if v19 else '✗'} V19 : EPREUVE_ELIMINATOIRE → EPREUVE ({len(epreuves)} candidats)")
    all_ok = all_ok and v19

    # V20: FINALISTE → AUTRE_SORTIE
    finalistes = df[df["departure_type_normalized"] == "FINALISTE"]
    v20 = (finalistes["departure_model_category"] == "AUTRE_SORTIE").all()
    print(f"{'✓' if v20 else '✗'} V20 : FINALISTE → AUTRE_SORTIE ({len(finalistes)} candidats)")
    all_ok = all_ok and v20

    # V21: VAINQUEUR → AUTRE_SORTIE
    vainqueurs = df[df["departure_type_normalized"] == "VAINQUEUR"]
    v21 = (vainqueurs["departure_model_category"] == "AUTRE_SORTIE").all()
    print(f"{'✓' if v21 else '✗'} V21 : VAINQUEUR → AUTRE_SORTIE ({len(vainqueurs)} candidats)")
    all_ok = all_ok and v21

    # V22: NON_CHOISI_POUR_JURY_FINAL → DECISION_AVENTURIERS
    non_choisi = df[df["departure_type_normalized"] == "NON_CHOISI_POUR_JURY_FINAL"]
    v22 = (non_choisi["departure_model_category"] == "DECISION_AVENTURIERS").all()
    print(f"{'✓' if v22 else '✗'} V22 : NON_CHOISI_POUR_JURY_FINAL → DECISION_AVENTURIERS "
          f"({len(non_choisi)} candidats)")
    all_ok = all_ok and v22

    # V23: POTEAUX → EPREUVE
    poteaux = df[df["departure_type_normalized"] == "POTEAUX"]
    v23 = len(poteaux) == 0 or (poteaux["departure_model_category"] == "EPREUVE").all()
    print(f"{'✓' if v23 else '✗'} V23 : POTEAUX → EPREUVE ({len(poteaux)} candidats)")
    all_ok = all_ok and v23

    # V24: returned_to_game = False → model_exit_order = first_exit_order = final_exit_order
    no_return = df[df["returned_to_game"] == False]
    if len(no_return) > 0:
        v24a = (no_return["model_exit_order"] == no_return["first_exit_order"]).all()
        v24b = (no_return["first_exit_order"] == no_return["final_exit_order"]).all()
        v24 = v24a and v24b
    else:
        v24 = True
    print(f"{'✓' if v24 else '✗'} V24 : sans retour → model_exit = first_exit = final_exit")
    all_ok = all_ok and v24

    # V25: all 21 candidates have returned_to_game = False
    v25 = (df["returned_to_game"] == False).all()
    print(f"{'✓' if v25 else '✗'} V25 : 21 candidats returned_to_game = False")
    all_ok = all_ok and v25

    # V26: departure_category preserved (not replaced)
    v26 = "departure_category" in df.columns
    print(f"{'✓' if v26 else '✗'} V26 : colonne departure_category préservée")
    all_ok = all_ok and v26

    # V27: DUEL_EXIL_PERDU → EPREUVE
    duels = df[df["departure_type_normalized"] == "DUEL_EXIL_PERDU"]
    v27 = len(duels) == 0 or (duels["departure_model_category"] == "EPREUVE").all()
    print(f"{'✓' if v27 else '✗'} V27 : DUEL_EXIL_PERDU → EPREUVE ({len(duels)} candidats)")
    all_ok = all_ok and v27

    # Informational warnings (non-blocking)
    print("\n--- Avertissements informatifs (non bloquants) ---")
    if df["gender_raw"].isna().all():
        print("⚠ gender_raw : entièrement vide — enrichissement requis")
    else:
        print(f"✓ gender_raw : {df['gender_raw'].notna().sum()}/{len(df)} renseignés")

    if df["profession_raw"].isna().all():
        print("⚠ profession_raw : entièrement vide — enrichissement requis")
    else:
        print(f"✓ profession_raw : {df['profession_raw'].notna().sum()}/{len(df)} renseignés")

    print(f"\n{'✓' if all_ok else '✗'} Résultat global : {14 if all_ok else 'certaines'} validations "
          f"{'OK' if all_ok else 'en échec'}")

    # ── Adaptation notes ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ADAPTATIONS")
    print("=" * 70)
    print(f"""
1. PAGE SOURCE :
   La page française a été supprimée. Page anglaise utilisée.

2. GENRE (gender_raw) ET PROFESSION (profession_raw) :
   Non disponibles dans la source. Colonnes laissées vides.
   Enrichissement requis en phase ultérieure.

3. LEFT COMPETITION :
   Classé INDETERMINE (ni ABANDON_VOLONTAIRE, ni ABANDON_MEDICAL
   sans information complémentaire). needs_departure_enrichment = True.

4. ORDRE DE SORTIE :
   Ordre strict 1→{N} basé sur l'ordre du tableau source.
   Le finaliste = {N-1}, le vainqueur = {N}.
   Les sorties le même jour sont signalées dans same_day_exit_group.
""")

    return df


if __name__ == "__main__":
    df = main()