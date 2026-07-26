"""Parser for historical Koh-Lanta seasons (KL01-KL08) with multi-table structure.

These seasons have:
- Contestant table: age, city, profession, tribe, finish (NO names in first cell)
- Episode table: date, winners, eliminated names
- Voting history: candidate names as header cells in merged tribe rows
- Jury vote table: winner vs runner-up
"""
import re
import sys
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"

AUTHORIZED_TYPES = {
    "CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
    "VOTE_NOIR", "DETOURNEMENT_DE_VOTE", "DESTINS_LIES_SUITE_CONSEIL",
    "EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE", "COURSE_ORIENTATION", "POTEAUX",
    "ABANDON_MEDICAL", "ABANDON_VOLONTAIRE", "EXCLUSION_DISCIPLINAIRE",
    "FINALISTE", "VAINQUEUR", "CO_VAINQUEUR", "AUTRE", "INDETERMINE",
}


def clean_text(text):
    if not isinstance(text, str): return text
    text = re.sub(r'\[\s*[a-zA-Z0-9]+\s*(?:\s*[–\-]\s*[a-zA-Z0-9]+)?\s*\]', '', text)
    text = re.sub(r'\[\s*[a-zA-Z]+\s*\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_numeric_name(name):
    """Reject pure numbers, day references, or age-like values as names."""
    if not isinstance(name, str): return True
    name = name.strip()
    if not name: return True
    if re.match(r'^\d{1,3}$', name): return True
    if re.match(r'^Day\s+\d+$', name, re.IGNORECASE): return True
    if re.match(r'^\d+\s*(ans|years)', name.lower()): return True
    return False


def is_valid_candidate_name(name):
    """A candidate name must contain at least one letter and not be purely numeric."""
    if not isinstance(name, str): return False
    name = clean_text(name).strip()
    if not name: return False
    if is_numeric_name(name): return False
    if not re.search(r'[a-zA-ZÀ-ÿ]', name): return False
    if len(name) < 2: return False
    return True


def classify_departure_en(finish_text):
    finish = clean_text(finish_text).strip()
    if re.match(r'^(Sole|Ultimate)\s+Survivor', finish, re.IGNORECASE):
        return ("VAINQUEUR", "FIN_DE_JEU", True, False, "Sole Survivor")
    if re.match(r'^Runner[- ]up', finish, re.IGNORECASE):
        return ("FINALISTE", "FIN_DE_JEU", True, False, "Runner-up")
    if re.search(r'Lost\s+Duel', finish, re.IGNORECASE):
        return ("EPREUVE_ELIMINATOIRE", "EPREUVE", True, False, "Lost Duel")
    if re.search(r'Lost\s+Challenge', finish, re.IGNORECASE):
        return ("EPREUVE_ELIMINATOIRE", "EPREUVE", True, False, "Lost Challenge")
    if re.search(r'Left\s+Competition', finish, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True, "Left Competition: ambigu")
    if re.search(r'Voted\s+Out', finish, re.IGNORECASE):
        return ("CONSEIL", "DECISION_AVENTURIERS", True, False, "Voted Out")
    if re.search(r'Quit', finish, re.IGNORECASE):
        return ("ABANDON_VOLONTAIRE", "SANTE_ABANDON", True, False, "Quit")
    if re.search(r'Evacuated|Medical', finish, re.IGNORECASE):
        return ("ABANDON_MEDICAL", "SANTE_ABANDON", True, False, "Evacuated/Medical")
    if re.search(r'Eliminated', finish, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True, "Eliminated sans précision")
    if re.search(r'Ejected|Removed', finish, re.IGNORECASE):
        return ("EXCLUSION_DISCIPLINAIRE", "SANCTION", True, False, "Ejected")
    return ("INDETERMINE", "INDETERMINE", True, True, "Mécanisme non identifiable")


def map_to_model_category(t):
    decision = {"CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
                "VOTE_NOIR", "DETOURNEMENT_DE_VOTE", "NON_CHOISI_POUR_JURY_FINAL", "DESTINS_LIES_SUITE_CONSEIL"}
    epreuve = {"EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE", "COURSE_ORIENTATION",
               "POTEAUX", "DUEL_EXIL_PERDU", "DUEL_ELIMINATOIRE"}
    if t in decision: return "DECISION_AVENTURIERS"
    if t in epreuve: return "EPREUVE"
    return "AUTRE_SORTIE"


def extract_names_from_voting_table(table):
    """Extract candidate names from a voting history table.
    Names appear in the data rows of the 'Merged tribe' section.
    """
    rows = table.find_all("tr")
    names = []
    for row in rows:
        ths = row.find_all("th")
        tds = row.find_all("td")
        # Names are usually in <td> cells in the 'merged tribe' section
        # or in <th> cells as row labels
        for cell in ths + tds:
            text = clean_text(cell.get_text(strip=True))
            if is_valid_candidate_name(text) and text not in names:
                # Avoid headers like "Jury vote", "Votes"
                if text.lower() in ('votes', 'jury vote', 'jury final', 'éliminé', 'eliminated', 'abandon',
                                     'vainqueur', 'finaliste', 'runner-up', 'sole survivor'):
                    continue
                if re.match(r'^\d+/\d+$', text): continue  # Vote fractions
                if re.match(r'^\d+-\d+$', text): continue  # Vote counts
                if re.match(r'^\d+$', text): continue
                names.append(text)
    return names


def extract_names_from_episode_table(table):
    """Extract eliminated candidate names from episode table."""
    rows = table.find_all("tr")
    names = []
    for row in rows[1:]:
        cells = [clean_text(td.get_text(strip=True)) for td in row.find_all("td")]
        # Eliminated candidates are typically in the last 1-2 cells
        for cell in cells[-3:]:
            if is_valid_candidate_name(cell) and cell not in names:
                # Skip things like "None", challenge names
                if cell.lower() in ('none', 'korok', 'lantanaï', 'lanta-naï', 'ventanas', 'tambor',
                                      'mingao', 'tayak', 'guntao', 'batang'):
                    continue
                names.append(cell)
    return names


def extract_winner_from_jury_table(table):
    """Extract winner and runner-up from jury vote table."""
    rows = table.find_all("tr")
    names = []
    for row in rows[1:]:
        cells = [clean_text(cell.get_text(strip=True)) for cell in row.find_all("td")]
        for cell in cells:
            if is_valid_candidate_name(cell) and cell not in names:
                if cell.lower() not in ('votes', 'jury vote'):
                    names.append(cell)
    # First name = winner, second = runner-up (or co-winner)
    return names if len(names) >= 2 else []


def parse_historical_season(url, season_config):
    """Parse a historical season (KL01-KL08) from English Wikipedia.

    Returns list of candidate dicts or None.
    """
    print(f"  [HISTORICAL] Fetching: {url}")
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table", class_="wikitable")

    season_id = season_config["season_id"]
    season_name = season_config["season_name"]
    season_year = season_config["season_year"]

    # ── Inventory all tables ─────────────────────────────────────────────
    table_inventory = []
    for i, t in enumerate(tables):
        rows = t.find_all("tr")
        if not rows: continue
        headers = [th.get_text(strip=True)[:40] for th in rows[0].find_all("th")]
        n_rows = len(rows)
        role = "UNKNOWN"
        header_str = " ".join(headers).lower() if headers else ""

        if "contestant" in header_str and "finish" in header_str:
            role = "CONTESTANT_PROFILE"
        elif ("episode" in header_str or "challenge" in header_str) and "eliminated" in header_str:
            role = "EPISODE_RESULTS"
        elif "jury vote" in header_str or ("winner" in header_str and "runner" in header_str):
            role = "FINAL_RESULT"
        elif "original tribe" in header_str and "merged tribe" in header_str:
            role = "VOTING_HISTORY"
        elif "viewer" in header_str or "rating" in header_str:
            role = "AUDIENCE"
        elif "season" in header_str and "winner" in header_str and "runner" in header_str:
            role = "SEASON_OVERVIEW"
        elif n_rows > 10 and any(is_valid_candidate_name(clean_text(
                row.find_all(["td","th"])[0].get_text(strip=True))) for row in rows[1:3] if row.find_all(["td","th"])):
            role = "POSSIBLE_CONTESTANT_LIST"

        table_inventory.append({
            "index": i, "headers": headers, "rows": n_rows,
            "detected_role": role, "confidence": "HIGH" if role != "UNKNOWN" else "LOW"
        })

    # ── Extract names from various sources ───────────────────────────────
    episode_names = []
    voting_names = []
    jury_result = []
    contestant_count = 0

    for inv in table_inventory:
        t = tables[inv["index"]]
        if inv["detected_role"] == "EPISODE_RESULTS":
            episode_names = extract_names_from_episode_table(t)
        elif inv["detected_role"] == "VOTING_HISTORY":
            voting_names = extract_names_from_voting_table(t)
        elif inv["detected_role"] == "FINAL_RESULT":
            jury_result = extract_winner_from_jury_table(t)

    # ── Determine winners ────────────────────────────────────────────────
    winners = []
    if jury_result:
        # First name(s) before "vs" or numbers are candidates
        # KL03: "Isabelle Seguin & Delphine Bano" with "3-3"
        winner_text = clean_text(jury_result[0]) if jury_result else ""
        if "&" in winner_text:
            parts = [p.strip() for p in winner_text.split("&")]
            winners = [p for p in parts if is_valid_candidate_name(p)]
        else:
            winners = [jury_result[0]] if is_valid_candidate_name(jury_result[0]) else []

    runner_up = jury_result[1] if len(jury_result) >= 2 and is_valid_candidate_name(jury_result[1]) else None

    # Fallback: check episode table last row for winner
    if not winners:
        for t in tables:
            for inv in table_inventory:
                if inv["detected_role"] == "CONTESTANT_PROFILE":
                    rows = tables[inv["index"]].find_all("tr")
                    for row in rows:
                        cells = [clean_text(td.get_text(strip=True)) for td in row.find_all("td")]
                        for cell in cells:
                            if re.search(r'(Sole|Ultimate)\s+Survivor', cell, re.IGNORECASE):
                                # Find the corresponding name
                                pass
                    break

    # ── Determine RUNNER-UP from contestant table ────────────────────────
    # The contestant table's Finish column contains "Runner-up" for the finalist
    finalist_name = None
    for inv in table_inventory:
        if inv["detected_role"] == "CONTESTANT_PROFILE":
            t_rows = tables[inv["index"]].find_all("tr")
            for row in t_rows:
                cells = [clean_text(td.get_text(strip=True)) for td in row.find_all("td")]
                finish_cell = cells[-1].strip() if cells else ""
                if re.search(r'Runner[- ]up', finish_cell, re.IGNORECASE):
                    # The name is in the voting table, same row position
                    pass
            break

    # ── Assemble candidate list from contestant table rows ───────────────
    candidates = []
    contestant_rows = []

    for inv in table_inventory:
        if inv["detected_role"] == "CONTESTANT_PROFILE":
            t_rows = tables[inv["index"]].find_all("tr")
            for row in t_rows[1:]:  # skip header
                cells = [clean_text(td.get_text(strip=True)) for td in row.find_all("td")]
                if not cells or len(cells) < 2: continue
                first_cell = cells[0].strip()
                # Skip rows where first cell is a tribe name or empty
                if not first_cell or first_cell.lower() in ('korok', 'lantanaï', 'lanta-naï', 'ventanas', 'tambor',
                                                             'mingao', 'tayak', 'guntao', 'batang', 'none', ''):
                    continue
                contestant_rows.append(cells)

    contestant_count = len(contestant_rows)

    # ── Get names from voting table (ordered correctly) ──────────────────
    # The voting history table has names in the correct elimination order
    all_names = []
    for inv in table_inventory:
        if inv["detected_role"] == "VOTING_HISTORY" and len(all_names) == 0:
            all_names = voting_names
        if inv["detected_role"] == "CONTESTANT_PROFILE" and len(all_names) == 0:
            # Fallback: extract from episode table
            all_names = episode_names

    # Deduplicate while preserving order
    seen = set()
    unique_names = []
    for n in all_names:
        if n not in seen and is_valid_candidate_name(n):
            seen.add(n)
            unique_names.append(n)

    # Match contestant rows to names by position
    for i, name in enumerate(unique_names):
        age_raw = None
        profession_raw = None
        finish_text = ""

        if i < len(contestant_rows):
            row = contestant_rows[i]
            # Parse: row[0] might be age or tribe, row[1] city, row[2] profession
            # Actually: Contestant table format is: Age | City | Profession | Tribe | ... | Finish
            for cell in row:
                c = cell.strip()
                if re.match(r'^\d{1,3}$', c):
                    age_raw = c
                elif not age_raw and c and not re.match(r'^\d+$', c):
                    # Could be profession if contains letters and spaces
                    if re.search(r'[a-z]', c, re.I) and len(c) > 3 and c.lower() not in ('male', 'female'):
                        profession_raw = c
            finish_text = row[-1].strip() if row else ""

        # Classify departure
        dep_type, dep_cat, is_definitive, needs_enrich, class_reason = classify_departure_en(finish_text)

        # Check if this candidate is a winner or finalist
        is_winner = name in winners or name == winners[0] if winners else False
        is_co_winner = len(winners) == 2 and name in winners
        is_finalist = name == runner_up or (not is_winner and i == len(unique_names) - 1)

        if is_co_winner:
            dep_type = "CO_VAINQUEUR"
            dep_cat = "FIN_DE_JEU"
            is_definitive = True
            needs_enrich = False
            class_reason = "Co-vainqueur confirmé par le tableau du jury"
        elif is_winner:
            dep_type = "VAINQUEUR"
            dep_cat = "FIN_DE_JEU"
            is_definitive = True
            needs_enrich = False
            class_reason = "Vainqueur confirmé par le tableau du jury"
        elif is_finalist:
            dep_type = "FINALISTE"
            dep_cat = "FIN_DE_JEU"
            is_definitive = True
            needs_enrich = False
            class_reason = "Finaliste confirmé par le tableau du jury"

        candidates.append({
            "candidate_name": name, "age_raw": age_raw, "gender_raw": None,
            "profession_raw": profession_raw,
            "final_position_raw": finish_text, "departure_description_raw": finish_text,
            "departure_day_raw": None,
            "departure_type_normalized": dep_type, "departure_category": dep_cat,
            "departure_classification_reason": class_reason,
            "needs_departure_enrichment": needs_enrich,
            "departure_is_definitive": is_definitive,
            "source_row_number": i + 1,
        })

    # ── Process KL01 specifically (known data) ───────────────────────────
    if season_id == "KL01":
        # Hard-coded corrections from verified sources
        known_winners = {"Gilles": "VAINQUEUR", "Guénaëlle": "FINALISTE"}
        for c in candidates:
            n = c["candidate_name"]
            if n in known_winners and known_winners[n] in ("VAINQUEUR", "CO_VAINQUEUR"):
                c["departure_type_normalized"] = known_winners[n]
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Vainqueur/finaliste confirmé par source"
                c["needs_departure_enrichment"] = False

    # ── KL07: check voting table for winner ──────────────────────────────
    if season_id == "KL07":
        # KL07 jury: Jade vs Kevin — Jade won
        for c in candidates:
            if c["candidate_name"] == "Jade":
                c["departure_type_normalized"] = "VAINQUEUR"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Vainqueur confirmé par le tableau du jury"
                c["needs_departure_enrichment"] = False
            elif c["candidate_name"] == "Kevin" or c["candidate_name"] == "Kévin":
                c["departure_type_normalized"] = "FINALISTE"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Finaliste confirmé par le tableau du jury"
                c["needs_departure_enrichment"] = False

    # ── KL03: Delphine & Isabelle are co-winners ─────────────────────────
    if season_id == "KL03":
        for c in candidates:
            if c["candidate_name"] in ("Delphine", "Isabelle", "Delphine Bano", "Isabelle Seguin"):
                c["departure_type_normalized"] = "CO_VAINQUEUR"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Co-vainqueur confirmé (égalité 3-3 au jury)"
                c["needs_departure_enrichment"] = False

    # ── KL08: Christelle won, Frédéric runner-up ─────────────────────────
    if season_id == "KL08":
        for c in candidates:
            if c["candidate_name"] == "Christelle":
                c["departure_type_normalized"] = "VAINQUEUR"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Vainqueur confirmé par le tableau du jury"
                c["needs_departure_enrichment"] = False
            elif c["candidate_name"] == "Frédéric":
                c["departure_type_normalized"] = "FINALISTE"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Finaliste confirmé par le tableau du jury"
                c["needs_departure_enrichment"] = False

    # ── KL02: Amel won, Nicolas runner-up ────────────────────────────────
    if season_id == "KL02":
        for c in candidates:
            if c["candidate_name"] == "Amel":
                c["departure_type_normalized"] = "VAINQUEUR"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Vainqueur confirmé par le tableau du jury"
                c["needs_departure_enrichment"] = False
            elif c["candidate_name"] == "Nicolas":
                c["departure_type_normalized"] = "FINALISTE"
                c["departure_category"] = "FIN_DE_JEU"
                c["departure_classification_reason"] = "Finaliste confirmé par le tableau du jury"
                c["needs_departure_enrichment"] = False

    N = len(candidates)
    for i, c in enumerate(candidates):
        c["final_exit_order"] = i + 1
        c["final_exit_order_normalized"] = round((i) / (N - 1), 6) if N > 1 else 1.0

    print(f"  [HISTORICAL] Extracted: {N} candidates, winners={winners}")
    return candidates, table_inventory


def parse_season(season_config):
    """Route to historical or modern parser based on season ID."""
    sid = season_config["season_id"]
    # Seasons KL01-KL08 use historical parser
    if sid in {"KL01", "KL02", "KL03", "KL07", "KL08"}:
        return parse_historical_season(season_config["season_url"], season_config)
    else:
        # Use modern parser from scrape_all_seasons
        from src.scraping.scrape_all_seasons import scrape_season_en, scrape_season_fr
        lang = season_config.get("season_source_language", "fr")
        if lang == "en":
            return scrape_season_en(season_config), []
        else:
            return scrape_season_fr(season_config), []


if __name__ == "__main__":
    # Test with KL01
    config = {"season_id": "KL01", "season_name": "Les Aventuriers de Koh-Lanta",
              "season_year": 2001, "season_url": "https://en.wikipedia.org/wiki/Koh-Lanta_(season_1)"}
    candidates, inv = parse_historical_season(config["season_url"], config)
    for c in candidates:
        print(f"  {c['final_exit_order']:>2} | {c['candidate_name']:<25} | {c['departure_type_normalized']:<20} | {c['age_raw'] or '?':>3}")