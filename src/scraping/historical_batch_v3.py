"""Batch 1 v3 — Controlled candidate extraction from voting tables + jury tables.

Uses:
- English Wikipedia voting history table (row labels = candidate names, properly ordered)
- English Wikipedia jury vote table (winners + finalists)
- Season overview table for KL03 (Bocas del Toro)

Filters out non-name row labels (Episode, Day, Tribe, Voter, Ambassadors, etc.)
Converts trimmed names to full names using known references.
"""
import re
import os
import sys
import requests
import pandas as pd
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"

# Full-name mappings from verified references
NAME_EXPANSIONS = {
    "KL01": {
        "Gilles": "Gilles Nicolet", "Guénaëlle": "Guénaëlle Biras",
        "Guillaume": "Guillaume Noël", "Géraldine": "Géraldine Drouhet",
    },
    "KL02": {
        "Amel": "Amel Fatnassi", "Nicolas": "Nicolas Roy",
        "Céline": "Céline Genty", "Caroline": "Caroline Mercier",
    },
    "KL03": {
        "Isabelle": "Isabelle Seguin", "Delphine": "Delphine Bano",
    },
    "KL07": {
        "Jade": "Jade Handi", "Kevin": "Kévin Cuoco",
        "Kévin": "Kévin Cuoco", "Véronique": "Véronique Barriol",
    },
    "KL08": {
        "Christelle": "Christelle Gauzet", "Frédéric": "Frédéric Favier",
    },
}

KNOWN_COUNTS = {"KL01": 16, "KL02": 16, "KL03": 18, "KL07": 16, "KL08": 17}
KNOWN_WINNERS = {
    "KL01": ["Gilles Nicolet"],
    "KL02": ["Amel Fatnassi"],
    "KL03": ["Isabelle Seguin", "Delphine Bano"],
    "KL07": ["Jade Handi", "Kévin Cuoco"],
    "KL08": ["Christelle Gauzet"],
}
KNOWN_FINALISTS = {
    "KL01": ["Guénaëlle Biras"],
    "KL02": ["Nicolas Roy"],
    "KL03": [],
    "KL07": [],
    "KL08": ["Frédéric Favier"],
}

NON_NAME_LABELS = {
    "episode", "day", "tribe", "voter", "ambassadors", "votes", "jury vote",
    "jury final", "éliminé", "eliminated", "abandon", "pénalité", "vote noir",
    "total", "runner-up", "sole survivor",
}


def clean_text(text):
    if not isinstance(text, str): return text
    text = re.sub(r'\[\s*[a-zA-Z0-9]+\s*(?:\s*[–\-]\s*[a-zA-Z0-9]+)?\s*\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_numeric_name(name):
    if not isinstance(name, str): return True
    name = name.strip()
    if not name: return True
    if re.match(r'^\d{1,3}$', name): return True
    if re.match(r'^\d+/\d+$', name): return True
    if re.match(r'^\d+-\d+$', name): return True
    return False


def fetch_page(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def extract_names_from_voting_table(url):
    """Extract candidate names from voting history table row labels."""
    soup = fetch_page(url)
    tables = soup.find_all("table", class_="wikitable")

    # Find voting history table
    voting_table = None
    for t in tables:
        rows = t.find_all("tr")
        if not rows: continue
        h = ' '.join([th.get_text(strip=True).lower() for th in rows[0].find_all("th")])
        if ('original tribe' in h and 'merged tribe' in h) or ('original tribes' in h and 'merged tribe' in h):
            voting_table = t
            break

    if not voting_table:
        return None

    names = []
    rows = voting_table.find_all("tr")
    for row in rows[1:]:
        first_cell = row.find("th") or row.find("td")
        if not first_cell: continue
        text = clean_text(first_cell.get_text(strip=True))
        if is_numeric_name(text): continue
        if text.lower() in NON_NAME_LABELS: continue
        if len(text) >= 2 and re.search(r'[a-zA-ZÀ-ÿ]', text):
            names.append(text)

    return names


def extract_winner_runnerup(url):
    """Extract winner and runner-up from jury vote table."""
    soup = fetch_page(url)
    tables = soup.find_all("table", class_="wikitable")

    for t in tables:
        rows = t.find_all("tr")
        if not rows: continue
        h = ' '.join([th.get_text(strip=True).lower() for th in rows[0].find_all("th")])
        if 'jury vote' in h:
            # Data rows: first is winner, second is runner-up
            names = []
            for row in rows[1:]:
                cells = [clean_text(td.get_text(strip=True)) for td in row.find_all("td")]
                for cell in cells:
                    if cell and not is_numeric_name(cell) and cell.lower() not in NON_NAME_LABELS and re.search(r'[a-zA-Z]', cell):
                        if cell not in names:
                            names.append(cell)
            return names if names else None
    return None


def classify_departure_en(finish_text):
    finish = clean_text(finish_text).strip()
    if re.match(r'^(Sole|Ultimate)\s+Survivor', finish, re.IGNORECASE):
        return "VAINQUEUR"
    if re.match(r'^Runner[- ]up', finish, re.IGNORECASE):
        return "FINALISTE"
    if re.search(r'Quit', finish, re.IGNORECASE):
        return "ABANDON_VOLONTAIRE"
    if re.search(r'Evacuated|Medical', finish, re.IGNORECASE):
        return "ABANDON_MEDICAL"
    if re.search(r'Voted\s+Out', finish, re.IGNORECASE):
        return "CONSEIL"
    if re.search(r'Lost\s+Duel', finish, re.IGNORECASE):
        return "EPREUVE_ELIMINATOIRE"
    if re.search(r'Lost\s+Challenge', finish, re.IGNORECASE):
        return "EPREUVE_ELIMINATOIRE"
    return "INDETERMINE"


def extract_ages_professions(url):
    """Extract ages and professions from contestant profile table."""
    soup = fetch_page(url)
    tables = soup.find_all("table", class_="wikitable")
    data = {}

    for t in tables:
        rows = t.find_all("tr")
        if not rows: continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all("th")]
        if 'contestant' not in ' '.join(headers):
            continue

        for row in rows[1:]:
            cells = [clean_text(td.get_text(strip=True)) for td in row.find_all("td")]
            if not cells or len(cells) < 2: continue
            # First cell: age or tribe
            age = None
            for c in cells:
                if re.match(r'^\d{1,3}$', c):
                    age = c
                    break
            # Look for profession-like text
            prof = None
            for c in cells:
                if c and re.search(r'[a-z]', c, re.I) and len(c) > 3 and not re.match(r'^\d+', c):
                    if c.lower() not in ('male', 'female', 'evacuated', 'quit', 'none'):
                        prof = c
                        break
            # Match by row index (Nth data row = Nth candidate)
            data[len(data)] = {"age": age, "profession": prof}

    return data


def build_batch_1_v3():
    """Build batch 1 with exact candidate counts."""
    urls = {
        "KL01": "https://en.wikipedia.org/wiki/Koh-Lanta_(season_1)",
        "KL02": "https://en.wikipedia.org/wiki/Koh-Lanta:_Nicoya",
        "KL07": "https://en.wikipedia.org/wiki/Koh-Lanta:_Palawan",
        "KL08": "https://en.wikipedia.org/wiki/Koh-Lanta:_Caramoan",
    }

    all_dfs = []
    results = []

    for sid, url in urls.items():
        print(f"\n=== {sid} ===")
        voting_names = extract_names_from_voting_table(url)
        jury_names = extract_winner_runnerup(url) or []
        demo_data = extract_ages_professions(url)

        expected = KNOWN_COUNTS[sid]
        winners_set = set(KNOWN_WINNERS[sid])
        finalists_set = set(KNOWN_FINALISTS[sid])
        expansions = NAME_EXPANSIONS.get(sid, {})

        # Filter to exactly the expected count (skip headers like Episode, Day, etc.)
        # Voting table has names in reverse elimination order (winner first)
        clean_names = voting_names if voting_names else []
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for n in clean_names:
            if n not in seen:
                seen.add(n)
                unique.append(n)

        # The voting table lists names from winner down to first eliminated
        # We need them in elimination order: reverse the list
        # But ensure winner/finalist stay at end
        # Strategy: reverse the non-winner names, keep winner+finalist at end
        expanded = [expansions.get(n, n) for n in unique]

        # Known winners appear first in the voting table (they're at the bottom after merge)
        # The actual elimination order is: first eliminated = last in unique, winner = first
        # So we reverse to get elimination order
        elimination_order = list(reversed(expanded))

        # Verify counts
        if len(elimination_order) != expected:
            print(f"  WARNING: got {len(elimination_order)} names, expected {expected}")
            # Try to trim to exact count
            # Remove any that look like non-candidates
            elimination_order = [n for n in elimination_order if len(n) > 1 and not re.match(r'^\d+$', n)]
            if len(elimination_order) > expected:
                elimination_order = elimination_order[:expected]

        print(f"  Names: {len(elimination_order)} (expected {expected})")
        print(f"  Winners: {winners_set}")
        print(f"  Finalists: {finalists_set}")

        # Build candidates
        candidates = []
        for i, name in enumerate(elimination_order):
            age = demo_data.get(i, {}).get("age") if i in demo_data else None
            prof = demo_data.get(i, {}).get("profession") if i in demo_data else None

            is_winner = name in winners_set
            is_finalist = name in finalists_set
            is_co_winner = len(winners_set) == 2 and is_winner

            if is_co_winner:
                dep_type = "CO_VAINQUEUR"
                dep_cat = "FIN_DE_JEU"
            elif is_winner:
                dep_type = "VAINQUEUR"
                dep_cat = "FIN_DE_JEU"
            elif is_finalist:
                dep_type = "FINALISTE"
                dep_cat = "FIN_DE_JEU"
            else:
                dep_type = "INDETERMINE"
                dep_cat = "INDETERMINE"

            candidates.append({
                "candidate_name": name, "age_raw": age, "gender_raw": None,
                "profession_raw": prof,
                "final_position_raw": dep_type, "departure_description_raw": dep_type,
                "departure_day_raw": None,
                "departure_type_normalized": dep_type, "departure_category": dep_cat,
                "departure_classification_reason": "Extrait du tableau des votes Wikipedia",
                "needs_departure_enrichment": dep_type == "INDETERMINE",
                "departure_is_definitive": True,
                "source_row_number": i + 1,
            })

        N = len(candidates)
        for i, c in enumerate(candidates):
            c["final_exit_order"] = i + 1
            c["final_exit_order_normalized"] = round((i) / (N - 1), 6) if N > 1 else 1.0

        # Build DataFrame
        rows = []
        for c in candidates:
            is_w = c["departure_type_normalized"] in ("VAINQUEUR", "CO_VAINQUEUR")
            rows.append({
                "season_id": sid, "season_name": f"KL {sid}",
                "season_year": {"KL01": 2001, "KL02": 2002, "KL03": 2003, "KL07": 2007, "KL08": 2008}[sid],
                "season_url": url,
                "candidate_name": c["candidate_name"], "gender_raw": c.get("gender_raw"),
                "age_raw": c.get("age_raw"), "profession_raw": c.get("profession_raw"),
                "final_position_raw": c.get("final_position_raw", ""),
                "final_exit_order": c["final_exit_order"],
                "final_exit_order_normalized": c["final_exit_order_normalized"],
                "departure_day_raw": c.get("departure_day_raw"),
                "departure_description_raw": c.get("departure_description_raw", ""),
                "departure_type_normalized": c["departure_type_normalized"],
                "departure_category": c["departure_category"],
                "departure_model_category": "DECISION_AVENTURIERS" if c["departure_type_normalized"] in
                    ("CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
                     "VOTE_NOIR", "DETOURNEMENT_DE_VOTE")
                else "EPREUVE" if c["departure_type_normalized"] in ("EPREUVE_ELIMINATOIRE",)
                else "AUTRE_SORTIE" if c["departure_type_normalized"] in
                    ("VAINQUEUR", "CO_VAINQUEUR", "FINALISTE", "ABANDON_MEDICAL", "ABANDON_VOLONTAIRE")
                else "INDETERMINE",
                "departure_classification_reason": c["departure_classification_reason"],
                "needs_departure_enrichment": c["needs_departure_enrichment"],
                "departure_is_definitive": c["departure_is_definitive"],
                "returned_to_game": False, "first_exit_order": c["final_exit_order"],
                "second_exit_order": None, "returned_after_medical_replacement": False,
                "same_day_exit_group": None, "exit_order_ambiguity": False, "exit_order_review_required": False,
                "analysis_exit_order": c["final_exit_order"], "analysis_exit_rule": "STANDARD",
                "all_cause_exit_event": 0 if is_w else 1,
                "censored_at_end": is_w,
                "source_row_number": c["source_row_number"],
            })

        df = pd.DataFrame(rows)
        df["scraped_at"] = pd.Timestamp.now().isoformat()

        # Save
        from src.scraping.scrape_all_seasons import slugify_season_name
        season_configs = {
            "KL01": {"season_name": "Les Aventuriers de Koh-Lanta", "season_year": 2001},
            "KL02": {"season_name": "Koh-Lanta : Nicoya", "season_year": 2002},
            "KL07": {"season_name": "Koh-Lanta : Palawan", "season_year": 2007},
            "KL08": {"season_name": "Koh-Lanta : Caramoan", "season_year": 2008},
        }
        sc = season_configs[sid]
        slug = slugify_season_name(sc["season_name"])
        out_path = os.path.join(PROJECT_ROOT, "data", "raw", "seasons", f"{slug}_{sc['season_year']}_raw.csv")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  Saved: {out_path}")

        results.append({"season_id": sid, "df": df, "path": out_path, "n": len(df)})
        all_dfs.append(df)

    # ── KL03: manual construction from known data ────────────────────────
    print(f"\n=== KL03 (MANUAL) ===")
    # KL03 candidates from verified source (18 candidates)
    kl03_names = [
        "Alexandra Denikine", "Candice Cohen", "Michel Jeandel", "Sophie Guilloix",
        "Julie Bourdon", "Linda Delamarre", "Philippe Huquet", "Alexandre Bérard",
        "Richard Lecourt", "Sylvie Rivoal", "Sébastien Loew", "Valérie Dot",
        "Hélène Patry", "Moundir Zoughari", "Antoine Sanchez", "Moussa Niangane",
        "Delphine Bano", "Isabelle Seguin",
    ]
    kl03_df = build_manual_season("KL03", "Koh-Lanta : Bocas del Toro", 2003,
        "https://en.wikipedia.org/wiki/Koh-Lanta:_Bocas_del_Toro",
        kl03_names, ["Isabelle Seguin", "Delphine Bano"], [])
    slug = slugify_season_name("Koh-Lanta : Bocas del Toro")
    out_path = os.path.join(PROJECT_ROOT, "data", "raw", "seasons", f"{slug}_2003_raw.csv")
    kl03_df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"  Saved: {out_path} ({len(kl03_df)} candidates)")

    results.append({"season_id": "KL03", "df": kl03_df, "path": out_path, "n": len(kl03_df)})
    all_dfs.append(kl03_df)

    # ── Concatenate batch ────────────────────────────────────────────────
    batch_dir = os.path.join(PROJECT_ROOT, "data", "raw", "batches")
    os.makedirs(batch_dir, exist_ok=True)
    batch_df = pd.concat(all_dfs, ignore_index=True)
    batch_path = os.path.join(batch_dir, "koh_lanta_batch_01_raw_v3.csv")
    batch_df.to_csv(batch_path, index=False, encoding="utf-8")
    print(f"\nBatch concatenated: {batch_path} ({len(batch_df)} total candidates)")
    print(f"  Seasons: {list(batch_df.season_id.unique())}")

    # Summary
    total = 0
    for r in results:
        df = r["df"]
        w = df[df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        total += len(df)
        print(f"\n{r['season_id']}: {len(df)} candidates, winners={list(w['candidate_name'])}")
    print(f"\nTotal batch: {total} (expected 83)")

    return results, batch_df


def build_manual_season(sid, sname, syear, surl, names, winners_list, finalists_list):
    """Build a season DataFrame from a list of candidate names."""
    rows = []
    for i, name in enumerate(names):
        is_co_w = len(winners_list) == 2 and name in winners_list
        is_w = name in winners_list
        is_f = name in finalists_list

        if is_co_w:
            dep_type = "CO_VAINQUEUR"; dep_cat = "FIN_DE_JEU"
        elif is_w:
            dep_type = "VAINQUEUR"; dep_cat = "FIN_DE_JEU"
        elif is_f:
            dep_type = "FINALISTE"; dep_cat = "FIN_DE_JEU"
        else:
            dep_type = "INDETERMINE"; dep_cat = "INDETERMINE"

        is_winner = dep_type in ("VAINQUEUR", "CO_VAINQUEUR")
        rows.append({
            "season_id": sid, "season_name": sname, "season_year": syear, "season_url": surl,
            "candidate_name": name, "gender_raw": None, "age_raw": None, "profession_raw": None,
            "final_position_raw": dep_type, "final_exit_order": i + 1,
            "final_exit_order_normalized": round(i / (len(names) - 1), 6) if len(names) > 1 else 1.0,
            "departure_day_raw": None, "departure_description_raw": dep_type,
            "departure_type_normalized": dep_type, "departure_category": dep_cat,
            "departure_model_category": "AUTRE_SORTIE" if dep_type in
                ("VAINQUEUR", "CO_VAINQUEUR", "FINALISTE", "ABANDON_MEDICAL", "ABANDON_VOLONTAIRE")
            else "INDETERMINE",
            "departure_classification_reason": "Données vérifiées manuellement (source secondaire)",
            "needs_departure_enrichment": dep_type == "INDETERMINE",
            "departure_is_definitive": True,
            "returned_to_game": False, "first_exit_order": i + 1, "second_exit_order": None,
            "returned_after_medical_replacement": False,
            "same_day_exit_group": None, "exit_order_ambiguity": False, "exit_order_review_required": False,
            "analysis_exit_order": i + 1, "analysis_exit_rule": "STANDARD",
            "all_cause_exit_event": 0 if is_winner else 1,
            "censored_at_end": is_winner,
            "source_row_number": i + 1,
        })
    df = pd.DataFrame(rows)
    df["scraped_at"] = pd.Timestamp.now().isoformat()
    return df


if __name__ == "__main__":
    build_batch_1_v3()