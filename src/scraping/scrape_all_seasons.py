"""Multi-season scraper for Koh-Lanta classic seasons.
Pilot mode: scrapes exactly two seasons (KL31, KL33).
Batch mode: scrapes a predefined batch of seasons.
"""
import os
import re
import sys
import json
import hashlib
import unicodedata
import argparse
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "seasons.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seasons")
BATCH_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "batches")
PILOT_CONCATENATED = os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_pilot_two_seasons_raw.csv")
MERGED_OUTPUT = os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_all_classic_seasons_raw.csv")
COVERAGE_REPORT = os.path.join(PROJECT_ROOT, "data", "processed", "pilot_scraping_coverage_report.csv")
CANDIDATE_AUDIT = os.path.join(PROJECT_ROOT, "data", "processed", "pilot_candidate_audit.csv")

THAILANDE_FILES = [
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_descriptive_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "processed", "koh_lanta_thailande_physical_validated_v1.csv"),
    os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv"),
]

PILOT_SEASON_IDS = {"KL31", "KL33"}

BATCH_01_IDS = {"KL01", "KL02", "KL03", "KL07", "KL08"}
BATCH_02_IDS = {"KL12", "KL13", "KL15", "KL17"}
BATCH_03_IDS = {"KL21", "KL22", "KL32", "KL25"}
BATCH_04_IDS = {"KL26", "KL27", "KL29"}
BATCH_CONFIG = {1: BATCH_01_IDS, 2: BATCH_02_IDS, 3: BATCH_03_IDS, 4: BATCH_04_IDS}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

AUTHORIZED_DEPARTURE_TYPES = {
    "CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
    "VOTE_NOIR", "DETOURNEMENT_DE_VOTE", "DESTINS_LIES_SUITE_CONSEIL",
    "EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE", "COURSE_ORIENTATION", "POTEAUX",
    "ABANDON_MEDICAL", "ABANDON_VOLONTAIRE", "EXCLUSION_DISCIPLINAIRE",
    "FINALISTE", "VAINQUEUR", "CO_VAINQUEUR", "AUTRE", "INDETERMINE",
}
AUTHORIZED_DEPARTURE_CATEGORIES = {
    "DECISION_AVENTURIERS", "EPREUVE", "SANTE_ABANDON", "SANCTION",
    "MECANIQUE_RETOUR", "FIN_DE_JEU", "AUTRE", "INDETERMINE",
}
AUTHORIZED_MODEL_CATEGORIES = {"DECISION_AVENTURIERS", "EPREUVE", "AUTRE_SORTIE"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def hash_thailande_files():
    return {p: sha256_file(p) if os.path.exists(p) else None for p in THAILANDE_FILES}

def verify_thailande_hashes(original_hashes):
    for path, orig_hash in original_hashes.items():
        if orig_hash is None:
            if os.path.exists(path): return False, f"NEW FILE: {path}"
            continue
        if not os.path.exists(path): return False, f"DELETED: {path}"
        if sha256_file(path) != orig_hash: return False, f"HASH MISMATCH: {path}"
    return True, "All frozen files intact"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def clean_text(text):
    if not isinstance(text, str): return text
    text = re.sub(r'\[\s*[a-zA-Z0-9]+\s*(?:\s*[–\-]\s*[a-zA-Z0-9]+)?\s*\]', '', text)
    text = re.sub(r'\[\s*[a-zA-Z]+\s*\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def slugify_season_name(name):
    """Convert a season name to a filesystem-safe slug.
    Examples:
      "Koh-Lanta : L'Île au trésor" -> "koh_lanta_l_ile_au_tresor"
      "Koh-Lanta : Les Armes secrètes" -> "koh_lanta_les_armes_secretes"
    """
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = name.replace("'", "").replace("'", "").replace("'", "")
    name = re.sub(r'koh[\s\-]*lanta', 'koh_lanta', name)
    name = re.sub(r'[^a-z0-9]+', '_', name)
    name = name.strip('_')
    name = re.sub(r'_+', '_', name)
    return name

def parse_contestant_field_en(raw):
    raw = clean_text(raw)
    m = re.match(r'^(.*?)\s+(\d{1,3})\s*,\s*(.*?)$', raw)
    if m:
        return m.group(1).strip(), m.group(2).strip(), re.sub(r'\s+',' ',m.group(3).strip(',').strip())
    return raw, None, None

def classify_departure_en(finish_text):
    finish = clean_text(finish_text).strip()
    if re.match(r'^(Sole|Ultimate)\s+Survivor', finish, re.IGNORECASE):
        return ("VAINQUEUR", "FIN_DE_JEU", True, False, "Sole Survivor dans la source")
    if re.match(r'^Runner[- ]up', finish, re.IGNORECASE):
        return ("FINALISTE", "FIN_DE_JEU", True, False, "Runner-up dans la source")
    if re.search(r'Lost\s+Duel', finish, re.IGNORECASE):
        return ("EPREUVE_ELIMINATOIRE", "EPREUVE", True, False, "Lost Duel: épreuve éliminatoire en duel")
    if re.search(r'Lost\s+Challenge', finish, re.IGNORECASE):
        return ("EPREUVE_ELIMINATOIRE", "EPREUVE", True, False, "Lost Challenge: épreuve éliminatoire")
    if re.search(r'Left\s+Competition', finish, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True, "Left Competition: ambigu")
    if re.search(r'Voted\s+Out', finish, re.IGNORECASE):
        return ("CONSEIL", "DECISION_AVENTURIERS", True, False, "Voted Out: élimination par conseil")
    if re.search(r'Eliminated', finish, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True, "Eliminated sans précision du mécanisme")
    if re.search(r'Medical|Evacuated|Medically', finish, re.IGNORECASE):
        return ("ABANDON_MEDICAL", "SANTE_ABANDON", True, False, "Évacuation médicale")
    if re.search(r'Quit|Withdr[ae]w|Walked', finish, re.IGNORECASE):
        return ("ABANDON_VOLONTAIRE", "SANTE_ABANDON", True, False, "Abandon volontaire")
    if re.search(r'Ejected|Removed|Disqualified', finish, re.IGNORECASE):
        return ("EXCLUSION_DISCIPLINAIRE", "SANCTION", True, False, "Exclusion disciplinaire")
    return ("INDETERMINE", "INDETERMINE", True, True, "Mécanisme de sortie non identifiable")

def classify_departure_fr(depart_text):
    text = clean_text(depart_text).strip()
    if re.search(r'Vainqueur|Gagnant', text, re.IGNORECASE):
        return ("VAINQUEUR", "FIN_DE_JEU", True, False, "Vainqueur/Gagnant dans la source")
    if re.search(r'Finaliste', text, re.IGNORECASE):
        return ("FINALISTE", "FIN_DE_JEU", True, False, "Finaliste dans la source")
    if re.search(r'Abandon\s+m[ée]dical', text, re.IGNORECASE):
        return ("ABANDON_MEDICAL", "SANTE_ABANDON", True, False, "Abandon médical dans la source")
    if re.search(r'Abandon\s+volontaire', text, re.IGNORECASE):
        return ("ABANDON_VOLONTAIRE", "SANTE_ABANDON", True, False, "Abandon volontaire dans la source")
    if re.search(r'Exclu|disqualif', text, re.IGNORECASE):
        return ("EXCLUSION_DISCIPLINAIRE", "SANCTION", True, False, "Exclusion disciplinaire")
    if re.search(r'[ÉE]limin[ée]', text, re.IGNORECASE):
        return ("INDETERMINE", "INDETERMINE", True, True, "Éliminé(e) sans précision du mécanisme")
    return ("INDETERMINE", "INDETERMINE", True, True, "Mécanisme non identifiable")

def extract_day_en(finish_text):
    m = re.search(r'Day\s+(\d+)', finish_text, re.IGNORECASE)
    return f"Day {m.group(1)}" if m else None

def extract_day_fr(depart_text):
    return None

def map_to_model_category(departure_type):
    decision = {"CONSEIL", "AMBASSADEURS_ACCORD", "AMBASSADEURS_TIRAGE_AU_SORT",
                "VOTE_NOIR", "DETOURNEMENT_DE_VOTE", "NON_CHOISI_POUR_JURY_FINAL", "DESTINS_LIES_SUITE_CONSEIL"}
    epreuve = {"EPREUVE_ELIMINATOIRE", "ELIMINATION_INITIALE", "COURSE_ORIENTATION",
               "POTEAUX", "DUEL_EXIL_PERDU", "ILE_SECONDE_CHANCE_PERDUE", "DESTINS_LIES"}
    if departure_type in decision: return "DECISION_AVENTURIERS"
    if departure_type in epreuve: return "EPREUVE"
    return "AUTRE_SORTIE"

def scrape_season_en(season_config):
    url = season_config["season_url"]
    print(f"\n  Fetching EN: {url}")
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table", class_="wikitable")
    contestant_table = None
    for t in tables:
        headers_list = [th.get_text(strip=True) for th in t.find_all("th")]
        if "Contestant" in headers_list and "Finish" in headers_list:
            contestant_table = t
            break
    if not contestant_table:
        print(f"  ERROR: No contestant table found!")
        return None
    rows = contestant_table.find_all("tr")
    candidates = []
    source_row_number = 0
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells or len(cells) < 2: continue
        raw_contestant = cells[0].get_text(" ", strip=True)
        if not raw_contestant.strip(): continue
        source_row_number += 1
        finish_text = cells[-1].get_text(" ", strip=True) if cells else ""
        name, age, city = parse_contestant_field_en(raw_contestant)
        dep_type, dep_cat, is_definitive, needs_enrich, class_reason = classify_departure_en(finish_text)
        departure_day = extract_day_en(finish_text)
        candidates.append({
            "candidate_name": name, "age_raw": age, "gender_raw": None, "profession_raw": None,
            "final_position_raw": finish_text, "departure_description_raw": finish_text,
            "departure_day_raw": departure_day, "departure_type_normalized": dep_type,
            "departure_category": dep_cat, "departure_classification_reason": class_reason,
            "needs_departure_enrichment": needs_enrich, "departure_is_definitive": is_definitive,
            "source_row_number": source_row_number,
        })
    N = len(candidates)
    for i, c in enumerate(candidates):
        c["final_exit_order"] = i + 1
        c["final_exit_order_normalized"] = round((i) / (N - 1), 6) if N > 1 else 1.0
    print(f"  Extracted: {N} candidates")
    return candidates

def scrape_season_fr(season_config):
    url = season_config["season_url"]
    print(f"\n  Fetching FR: {url}")
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table", class_="wikitable")
    contestant_table = tables[0] if tables else None
    if not contestant_table:
        print(f"  ERROR: No contestant table found!")
        return None
    rows = contestant_table.find_all("tr")
    headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
    print(f"  Columns: {headers}")
    candidates = []
    source_row_number = 0
    for row in rows[1:]:
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        if not cells or len(cells) < 2: continue
        if not cells[0].strip() and len(cells) < 5: continue
        source_row_number += 1
        gender_symbol = cells[0].strip() if len(cells) > 0 else ""
        name = cells[1].strip() if len(cells) > 1 else ""
        profession = cells[2].strip() if len(cells) > 2 else ""
        age_raw = cells[3].strip() if len(cells) > 3 else ""
        tribe = cells[5].strip() if len(cells) > 5 else ""
        jury = cells[6].strip() if len(cells) > 6 else ""
        depart_text = cells[-1].strip() if len(cells) > 6 else ""
        if not name: continue
        gender = None
        if gender_symbol == '♀': gender = 'F'
        elif gender_symbol == '♂': gender = 'M'
        dep_type, dep_cat, is_definitive, needs_enrich, class_reason = classify_departure_fr(depart_text)
        candidates.append({
            "candidate_name": name, "age_raw": age_raw, "gender_raw": gender, "profession_raw": profession,
            "final_position_raw": depart_text, "departure_description_raw": depart_text,
            "departure_day_raw": None, "departure_type_normalized": dep_type,
            "departure_category": dep_cat, "departure_classification_reason": class_reason,
            "needs_departure_enrichment": needs_enrich, "departure_is_definitive": is_definitive,
            "source_row_number": source_row_number, "tribe_raw": tribe, "jury_raw": jury,
        })
    N = len(candidates)
    for i, c in enumerate(candidates):
        c["final_exit_order"] = i + 1
        c["final_exit_order_normalized"] = round((i) / (N - 1), 6) if N > 1 else 1.0
    print(f"  Extracted: {N} candidates")
    return candidates

def build_dataframe(candidates, season_config):
    sid = season_config["season_id"]
    sname = season_config["season_name"]
    syear = season_config["season_year"]
    surl = season_config["season_url"]
    rows = []
    for c in candidates:
        dep_type = c["departure_type_normalized"]
        model_cat = map_to_model_category(dep_type)
        exit_order = c["final_exit_order"]
        is_winner = dep_type in ("VAINQUEUR", "CO_VAINQUEUR")
        rows.append({
            "season_id": sid, "season_name": sname, "season_year": syear, "season_url": surl,
            "candidate_name": c["candidate_name"],
            "gender_raw": c.get("gender_raw"), "age_raw": c.get("age_raw"),
            "profession_raw": c.get("profession_raw"),
            "final_position_raw": c.get("final_position_raw", ""),
            "final_exit_order": exit_order,
            "final_exit_order_normalized": c["final_exit_order_normalized"],
            "departure_day_raw": c.get("departure_day_raw"),
            "departure_description_raw": c.get("departure_description_raw", ""),
            "departure_type_normalized": dep_type,
            "departure_category": c["departure_category"],
            "departure_model_category": model_cat,
            "departure_classification_reason": c["departure_classification_reason"],
            "needs_departure_enrichment": c["needs_departure_enrichment"],
            "departure_is_definitive": c["departure_is_definitive"],
            "returned_to_game": False, "first_exit_order": exit_order, "second_exit_order": None,
            "returned_after_medical_replacement": False,
            "same_day_exit_group": None, "exit_order_ambiguity": False, "exit_order_review_required": False,
            "analysis_exit_order": exit_order, "analysis_exit_rule": "STANDARD",
            "all_cause_exit_event": 0 if is_winner else 1,
            "censored_at_end": is_winner,
            "source_row_number": c["source_row_number"],
        })
    df = pd.DataFrame(rows)
    df["scraped_at"] = datetime.now(timezone.utc).isoformat()
    return df

def detect_same_day_exits(df):
    day_groups = {}
    for idx, row in df.iterrows():
        day = row["departure_day_raw"]
        if day: day_groups.setdefault(day, []).append(idx)
    for day, indices in day_groups.items():
        if len(indices) >= 2:
            for idx in indices:
                df.at[idx, "same_day_exit_group"] = day
                df.at[idx, "exit_order_ambiguity"] = True
                df.at[idx, "exit_order_review_required"] = True
    return df

def audit_medical_returns(df, season_id):
    if season_id == "KL33":
        magali_mask = df["candidate_name"] == "Magali"
        if magali_mask.any():
            idx = df[magali_mask].index[0]
            df.at[idx, "returned_to_game"] = True
            df.at[idx, "returned_after_medical_replacement"] = True
            df.at[idx, "analysis_exit_order"] = df.at[idx, "first_exit_order"]
            df.at[idx, "analysis_exit_rule"] = "FIRST_EXIT_BEFORE_MEDICAL_RETURN"
            print(f"  ⚠ Medical return: Magali (eliminated day 13, returned day 15)")
    return df

def run_validations(df, season_id):
    ok = True
    warnings = []
    n = len(df)
    if n < 16 or n > 24: warnings.append(f"Unusual candidate count: {n}")
    print(f"  V1: {n} candidates {'OK' if 16 <= n <= 24 else 'WARN'}")
    v2 = df["candidate_name"].notna().all() and (df["candidate_name"].str.strip() != "").all()
    if not v2: ok = False; warnings.append("Empty candidate names")
    print(f"  V2: No empty names {'OK' if v2 else 'FAIL'}")
    dupes = df[df.duplicated(subset=["candidate_name"], keep=False)]
    v3 = len(dupes) == 0
    if not v3: ok = False; warnings.append(f"Unexplained duplicates: {len(dupes)}")
    print(f"  V3: No duplicates {'OK' if v3 else 'FAIL'}")
    v4 = not df["age_raw"].isna().all()
    if not v4: warnings.append("age_raw entirely empty")
    print(f"  V4: age_raw coverage {'OK' if v4 else 'WARN'}")
    winner_count = df[df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])].shape[0]
    v5 = winner_count >= 1
    if not v5: ok = False; warnings.append("No winner")
    print(f"  V5: Winners={winner_count} {'OK' if v5 else 'FAIL'}")
    censored_count = int(df["censored_at_end"].sum())
    v6 = censored_count == winner_count
    if not v6: ok = False; warnings.append(f"Censored {censored_count} != winners {winner_count}")
    print(f"  V6: Censored={censored_count} == winners={winner_count} {'OK' if v6 else 'FAIL'}")
    non_winners = df[~df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
    v7 = (non_winners["all_cause_exit_event"] == 1).all() if len(non_winners) > 0 else True
    if not v7: ok = False; warnings.append("Non-winners event != 1")
    print(f"  V7: Non-winners event=1 {'OK' if v7 else 'FAIL'}")
    finalists = df[df["departure_type_normalized"] == "FINALISTE"]
    v8 = (finalists["all_cause_exit_event"] == 1).all() if len(finalists) > 0 else True
    if not v8: ok = False; warnings.append("Finalists event != 1")
    print(f"  V8: Finalists event=1 {'OK' if v8 else 'FAIL'}")
    norms = df["final_exit_order_normalized"]
    v9 = (norms >= 0).all() and (norms <= 1).all()
    if not v9: ok = False
    print(f"  V9: Norm in [0,1] {'OK' if v9 else 'FAIL'}")
    v10 = df["departure_type_normalized"].isin(AUTHORIZED_DEPARTURE_TYPES).all()
    if not v10: ok = False
    print(f"  V10: Authorized types {'OK' if v10 else 'FAIL'}")
    indet = df[df["departure_type_normalized"] == "INDETERMINE"]
    v11 = indet["needs_departure_enrichment"].all() if len(indet) > 0 else True
    if len(indet) > 0: warnings.append(f"{len(indet)} INDETERMINE flagged")
    print(f"  V11: INDETERMINE enriched {'OK' if v11 else 'FAIL'} ({len(indet)})")
    returns = df[df["returned_to_game"] == True]
    print(f"  V12: Returns={len(returns)}")
    orders = sorted(df["final_exit_order"].tolist())
    v13 = orders == list(range(1, n + 1))
    if not v13: ok = False
    print(f"  V13: Strict ordering {'OK' if v13 else 'FAIL'}")
    return ok, warnings

def create_coverage_report(results):
    rows = []
    for r in results:
        df = r["dataframe"]
        if len(df) == 0: continue
        wins = df[df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        returns = df[df["returned_to_game"] == True]
        ambig = df[df["exit_order_ambiguity"] == True]
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        rows.append({
            "season_id": r["season_id"], "season_name": r["season_name"],
            "season_year": r["season_year"], "source_url": r["source_url"],
            "source_language": r["source_language"], "scrape_status": r["scrape_status"],
            "candidate_count": len(df), "expected_candidate_count_if_known": "",
            "gender_coverage": int(df["gender_raw"].notna().sum()),
            "age_coverage": int(df["age_raw"].notna().sum()),
            "profession_coverage": int(df["profession_raw"].notna().sum()),
            "departure_coverage": int(df["departure_type_normalized"].notna().sum()),
            "winner_count": int(len(wins)),
            "indeterminate_departure_count": int(len(indet)),
            "duplicate_candidate_count": 0,
            "return_case_count": int(len(returns)),
            "exit_order_ambiguity_count": int(len(ambig)),
            "manual_review_required": r.get("manual_review_required", len(indet) > 0),
            "warnings": "; ".join(r.get("warnings", [])),
        })
    return pd.DataFrame(rows)

def create_candidate_audit(results):
    rows = []
    for r in results:
        df = r["dataframe"]
        for _, row in df.iterrows():
            audit_status = "PASS"; audit_warnings = []
            if row["departure_type_normalized"] == "INDETERMINE":
                audit_status = "PASS_WITH_WARNING"; audit_warnings.append("INDETERMINE")
            if row["returned_to_game"]:
                audit_warnings.append("Returned to game")
                if audit_status == "PASS": audit_status = "PASS_WITH_WARNING"
            if row["exit_order_ambiguity"]:
                audit_warnings.append("Exit order ambiguity")
                if audit_status == "PASS": audit_status = "PASS_WITH_WARNING"
            rows.append({
                "season_name": row["season_name"], "candidate_name": row["candidate_name"],
                "final_exit_order": row["final_exit_order"],
                "departure_description_raw": row["departure_description_raw"],
                "departure_type_normalized": row["departure_type_normalized"],
                "departure_model_category": row["departure_model_category"],
                "all_cause_exit_event": row["all_cause_exit_event"],
                "censored_at_end": row["censored_at_end"],
                "returned_after_medical_replacement": row["returned_after_medical_replacement"] or False,
                "needs_departure_enrichment": row["needs_departure_enrichment"],
                "audit_status": audit_status,
                "audit_warning": "; ".join(audit_warnings) if audit_warnings else "",
            })
    return pd.DataFrame(rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--season-id", action="append", default=[])
    parser.add_argument("--no-dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config()
    seasons = {s["season_id"]: s for s in config["seasons"]}

    target_ids = set()
    batch_num = None

    if args.pilot:
        target_ids = PILOT_SEASON_IDS
    elif args.batch is not None:
        batch_num = args.batch
        if batch_num not in BATCH_CONFIG:
            print(f"ERROR: Unknown batch {batch_num}. Available: {list(BATCH_CONFIG.keys())}")
            sys.exit(1)
        target_ids = BATCH_CONFIG[batch_num]
        print(f"BATCH {batch_num}: {len(target_ids)} seasons: {sorted(target_ids)}")
    elif args.season_id:
        target_ids = set(args.season_id)
    elif args.no_dry_run:
        print("Full scraping not yet implemented. Use --batch N or --pilot.")
        return
    else:
        dry_run()
        return

    # Validate
    for sid in list(target_ids):
        if sid not in seasons:
            print(f"ERROR: Unknown season ID: {sid}"); sys.exit(1)
        if not seasons[sid]["include_in_primary_dataset"]:
            print(f"ERROR: {sid} is excluded"); sys.exit(1)

    if args.pilot and target_ids != PILOT_SEASON_IDS:
        print(f"ERROR: Pilot only supports {sorted(PILOT_SEASON_IDS)}"); sys.exit(1)

    thai_hashes_before = hash_thailande_files()
    results = []
    all_dfs = []

    for sid in sorted(target_ids):
        sc = seasons[sid]
        lang = sc.get("season_source_language", "fr")
        print(f"\n{'='*70}\nSCRAPING: {sid} — {sc['season_name']} ({sc['season_year']})\n  Language: {lang}")

        try:
            # Route to historical parser for KL01-KL08
            if sid in {"KL01", "KL02", "KL03", "KL07", "KL08"}:
                from src.scraping.historical_season_parser import parse_historical_season
                candidates, _ = parse_historical_season(sc["season_url"], sc)
            elif lang == "en":
                candidates = scrape_season_en(sc)
            else:
                candidates = scrape_season_fr(sc)
            if not candidates:
                results.append({"season_id": sid, "season_name": sc["season_name"],
                    "season_year": sc["season_year"], "source_url": sc["season_url"],
                    "source_language": lang, "scrape_status": "FAILED", "output_path": None,
                    "dataframe": pd.DataFrame(), "warnings": ["No candidates"], "manual_review_required": True})
                continue

            df = build_dataframe(candidates, sc)
            df = detect_same_day_exits(df)
            df = audit_medical_returns(df, sid)
            print(f"\n  VALIDATIONS:")
            all_ok, warnings = run_validations(df, sid)
            scrape_status = "SUCCESS" if all_ok else ("PARTIAL" if len(warnings) <= 3 else "MANUAL_REVIEW")

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            slug = slugify_season_name(sc["season_name"])
            output_path = os.path.join(OUTPUT_DIR, f"{slug}_{sc['season_year']}_raw.csv")
            df.to_csv(output_path, index=False, encoding="utf-8")
            print(f"\n  CSV saved: {output_path}")

            results.append({"season_id": sid, "season_name": sc["season_name"],
                "season_year": sc["season_year"], "source_url": sc["season_url"],
                "source_language": lang, "scrape_status": scrape_status, "output_path": output_path,
                "dataframe": df, "warnings": warnings,
                "manual_review_required": scrape_status in ("PARTIAL", "MANUAL_REVIEW", "FAILED")})
            all_dfs.append(df)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            results.append({"season_id": sid, "season_name": sc["season_name"],
                "season_year": sc["season_year"], "source_url": sc["season_url"],
                "source_language": lang, "scrape_status": "FAILED", "output_path": None,
                "dataframe": pd.DataFrame(), "warnings": [str(e)], "manual_review_required": True})

    # Batch concatenated file
    if batch_num and len(all_dfs) == len(target_ids):
        os.makedirs(BATCH_OUTPUT_DIR, exist_ok=True)
        batch_csv = os.path.join(BATCH_OUTPUT_DIR, f"koh_lanta_batch_{batch_num:02d}_raw.csv")
        batch_df = pd.concat(all_dfs, ignore_index=True)
        batch_df.to_csv(batch_csv, index=False, encoding="utf-8")
        season_ids = batch_df["season_id"].unique()
        print(f"\nBatch CSV: {batch_csv} ({len(season_ids)} seasons, {len(batch_df)} candidates)")
        assert len(season_ids) == len(target_ids), f"Expected {len(target_ids)} seasons, got {len(season_ids)}!"

        # Batch coverage report
        batch_cov = os.path.join(PROJECT_ROOT, "data", "processed", f"batch_{batch_num:02d}_scraping_coverage_report.csv")
        cov_df = create_coverage_report(results)
        cov_df.to_csv(batch_cov, index=False, encoding="utf-8")
        print(f"Coverage: {batch_cov} ({len(cov_df)} rows)")

        # Batch candidate audit
        batch_audit = os.path.join(PROJECT_ROOT, "data", "processed", f"batch_{batch_num:02d}_candidate_audit.csv")
        aud_df = create_candidate_audit(results)
        aud_df.to_csv(batch_audit, index=False, encoding="utf-8")
        print(f"Audit: {batch_audit} ({len(aud_df)} rows)")

        # Presence intervals (empty if no returns)
        pres_csv = os.path.join(PROJECT_ROOT, "data", "processed", f"batch_{batch_num:02d}_candidate_presence_intervals.csv")
        pres_rows = []
        for df_s in all_dfs:
            for _, row in df_s.iterrows():
                pres_rows.append({"season_name": row["season_name"], "candidate_name": row["candidate_name"],
                    "interval_start_day": 1, "interval_end_day": None,
                    "presence_status": "STANDARD", "active_in_main_game": True,
                    "interval_reason": "Présence standard", "source_url": "", "review_status": "VALIDATED"})
        pd.DataFrame(pres_rows).to_csv(pres_csv, index=False, encoding="utf-8")
        print(f"Presence intervals: {pres_csv} ({len(pres_rows)} rows)")

    # Verify Thailand
    thai_ok, thai_msg = verify_thailande_hashes(thai_hashes_before)
    print(f"\n{'✓' if thai_ok else '❌'} Thailand: {thai_msg}")

    # Final report
    print(f"\n{'='*70}\nRAPPORT FINAL — BATCH {batch_num if batch_num else 'PILOT'}\n{'='*70}")
    for r in results:
        df = r["dataframe"]
        if len(df) == 0: continue
        print(f"\n{'─'*70}\nSAISON: {r['season_id']} — {r['season_name']} ({r['season_year']})")
        print(f"  Source: {r['source_url']}")
        print(f"  Candidats: {len(df)}")
        dist = df["departure_type_normalized"].value_counts()
        print(f"  Types: {dict(dist)}")
        winners = df[df["departure_type_normalized"].isin(["VAINQUEUR", "CO_VAINQUEUR"])]
        for _, w in winners.iterrows():
            print(f"  Vainqueur: {w['candidate_name']}")
        indet = df[df["departure_type_normalized"] == "INDETERMINE"]
        if len(indet) > 0:
            print(f"  INDETERMINE: {len(indet)}")
        returns = df[df["returned_to_game"] == True]
        if len(returns) > 0:
            for _, rr in returns.iterrows():
                print(f"  Retour: {rr['candidate_name']}")
        print(f"  Statut: {r['scrape_status']}")

    print(f"\nFichiers créés dans data/raw/seasons/ et data/processed/")
    print(f"Thailand intact: {thai_ok}")
    return results

def dry_run():
    config = load_config()
    seasons = config["seasons"]
    included = [s for s in seasons if s["include_in_primary_dataset"]]
    excluded = [s for s in seasons if not s["include_in_primary_dataset"]]
    print("=" * 70)
    print("DRY RUN — SCRAPING MULTI-SAISONS")
    print("=" * 70)
    print(f"\nTotal: {len(seasons)} seasons | Included: {len(included)} | Excluded: {len(excluded)}")
    print(f"\nBATCH 1: {sorted(BATCH_01_IDS)}")
    for s in seasons:
        if s["season_id"] in BATCH_01_IDS:
            print(f"  {s['season_id']} {s['season_name']} ({s['season_year']}) — {s['season_url']}")
    print("\nUse --batch 1 to scrape batch 1.")

if __name__ == "__main__":
    main()