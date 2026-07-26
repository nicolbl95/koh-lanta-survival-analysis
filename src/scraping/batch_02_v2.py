"""Batch 2 v2 — Corrected candidate extraction with deduplication of returned players."""
import os, re, sys, requests, pandas as pd
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"

# Known reference counts
EXPECTED = {"KL12": 18, "KL13": 20, "KL15": 20, "KL17": 20}
WINNERS = {
    "KL12": ["Philippe Duron"],
    "KL13": ["Gérard Urdampilleta"],
    "KL15": ["Ugo Lartiche"],
    "KL17": ["Marc Rambaud"],
}
FINALISTS = {
    "KL12": ["Claude Dartois"],
    "KL13": ["Teheiura Teahui"],
    "KL15": ["Brice Martinet"],
    "KL17": ["Chantal Ménard"],
}

AUTHORIZED = {"CONSEIL","AMBASSADEURS_ACCORD","AMBASSADEURS_TIRAGE_AU_SORT","VOTE_NOIR",
    "DETOURNEMENT_DE_VOTE","DESTINS_LIES_SUITE_CONSEIL","EPREUVE_ELIMINATOIRE",
    "ELIMINATION_INITIALE","COURSE_ORIENTATION","POTEAUX","ABANDON_MEDICAL",
    "ABANDON_VOLONTAIRE","EXCLUSION_DISCIPLINAIRE","FINALISTE","VAINQUEUR",
    "CO_VAINQUEUR","AUTRE","INDETERMINE"}


def clean(t):
    t = re.sub(r'\[\s*[a-zA-Z0-9]+\s*(?:[–\-]\s*[a-zA-Z0-9]+)?\s*\]','',str(t))
    return re.sub(r'\s+',' ',t).strip()


def parse_name(raw):
    raw = clean(raw)
    m = re.match(r'^(.*?)\s+(\d{1,3})\s*,\s*(.*?)$', raw)
    if m: return m.group(1).strip(), m.group(2).strip()
    return raw, None


def classify_en(finish):
    f = clean(finish).strip()
    if re.match(r'^(Sole|Ultimate)\s+Survivor',f,re.I): return "VAINQUEUR"
    if re.match(r'^Runner[- ]up',f,re.I): return "FINALISTE"
    if re.search(r'Lost\s+Duel',f,re.I): return "EPREUVE_ELIMINATOIRE"
    if re.search(r'Lost\s+Challenge',f,re.I): return "EPREUVE_ELIMINATOIRE"
    if re.search(r'Left\s+Competition',f,re.I): return "INDETERMINE"
    if re.search(r'Voted\s+Out',f,re.I): return "CONSEIL"
    if re.search(r'Medic|Evacuated',f,re.I): return "ABANDON_MEDICAL"
    if re.search(r'Quit|Withdr',f,re.I): return "ABANDON_VOLONTAIRE"
    return "INDETERMINE"


def classify_fr(text):
    t = clean(text).strip()
    if re.search(r'Vainqueur|Gagnant',t,re.I): return "VAINQUEUR"
    if re.search(r'Finaliste',t,re.I): return "FINALISTE"
    if re.search(r'Abandon\s+m[ée]dical',t,re.I): return "ABANDON_MEDICAL"
    if re.search(r'Abandon\s+volontaire',t,re.I): return "ABANDON_VOLONTAIRE"
    if re.search(r'Exclu|disqualif',t,re.I): return "EXCLUSION_DISCIPLINAIRE"
    if re.search(r'[ÉE]limin[ée]',t,re.I): return "INDETERMINE"
    return "INDETERMINE"


def map_model(t):
    d={"CONSEIL","AMBASSADEURS_ACCORD","AMBASSADEURS_TIRAGE_AU_SORT","VOTE_NOIR",
       "DETOURNEMENT_DE_VOTE","NON_CHOISI_POUR_JURY_FINAL","DESTINS_LIES_SUITE_CONSEIL"}
    e={"EPREUVE_ELIMINATOIRE","ELIMINATION_INITIALE","COURSE_ORIENTATION","POTEAUX","DUEL_EXIL_PERDU"}
    if t in d: return "DECISION_AVENTURIERS"
    if t in e: return "EPREUVE"
    return "AUTRE_SORTIE"


def scrape_en_dedup(url):
    """Scrape English contestant table with 'Returned to Game' deduplication."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table", class_="wikitable")
    ct = None
    for t in tables:
        h = [th.get_text(strip=True) for th in t.find_all("th")]
        if "Contestant" in h and "Finish" in h:
            ct = t; break
    if not ct: return None

    rows = ct.find_all("tr")
    raw_rows = []
    for row in rows[1:]:
        cells = [clean(td.get_text(" ", strip=True)) for td in row.find_all("td")]
        if not cells or len(cells) < 2: continue
        first = cells[0].strip()
        if not first: continue
        name, age = parse_name(first)
        finish = cells[-1].strip() if cells else ""
        raw_rows.append({"name": name, "age": age, "finish": finish, "cells": cells})

    # Deduplicate: identify names that appear with "Returned to Game"
    # The first appearance is the original elimination; the second is after return
    name_occurrences = {}
    for r in raw_rows:
        n = r["name"]
        if "Returned to Game" in r["finish"] or "Returned to Game" in str(r["cells"]):
            name_occurrences[n] = name_occurrences.get(n, 0) + 1

    returned_names = {n for n, c in name_occurrences.items() if c >= 1}
    
    # Build canonical list: only keep first occurrence for returned players
    seen = set()
    canonical = []
    for r in raw_rows:
        n = r["name"]
        is_return = "Returned to Game" in r["finish"] or "Returned to Game" in str(r["cells"])
        n_base = n.replace(" Returned to Game", "").strip()
        
        if is_return:
            # This is a return marker - skip, but mark the canonical entry
            base_name = re.sub(r'\s*Returned\s+to\s+Game\s*', '', n, flags=re.I).strip()
            # Find the canonical entry and mark it
            for c in canonical:
                if c["name"] == base_name:
                    c["returned"] = True
                    c["second_exit"] = r
            continue
        
        if n_base not in seen:
            seen.add(n_base)
            canonical.append(r)
    
    return canonical


def build_df(candidates, sid, sname, syear, surl, lang):
    winners_set = set(WINNERS.get(sid, []))
    finalists_set = set(FINALISTS.get(sid, []))
    
    rows = []
    for i, c in enumerate(candidates):
        name = c["name"]
        age = c.get("age")
        
        # Determine type
        if name in winners_set:
            t = "VAINQUEUR" if len(winners_set) == 1 else "CO_VAINQUEUR"
        elif name in finalists_set:
            t = "FINALISTE"
        elif lang == "en":
            t = classify_en(c["finish"])
        else:
            t = classify_fr(c["finish"])
        
        is_w = t in ("VAINQUEUR", "CO_VAINQUEUR")
        returned = c.get("returned", False)
        second = c.get("second_exit")
        first_order = i + 1
        
        rows.append({
            "season_id": sid, "season_name": sname, "season_year": syear,
            "season_url": surl, "candidate_name": name, "gender_raw": None,
            "age_raw": age, "profession_raw": None,
            "final_position_raw": c["finish"], "final_exit_order": first_order,
            "final_exit_order_normalized": round(i / (len(candidates) - 1), 6) if len(candidates) > 1 else 1.0,
            "departure_day_raw": None, "departure_description_raw": c["finish"],
            "departure_type_normalized": t, "departure_category": "FIN_DE_JEU" if is_w or t == "FINALISTE" else "INDETERMINE",
            "departure_model_category": map_model(t),
            "departure_classification_reason": f"Source: {surl}",
            "needs_departure_enrichment": t == "INDETERMINE",
            "departure_is_definitive": True,
            "returned_to_game": returned,
            "first_exit_order": first_order, "second_exit_order": None,
            "returned_after_medical_replacement": returned,
            "same_day_exit_group": None, "exit_order_ambiguity": False,
            "exit_order_review_required": False,
            "analysis_exit_order": first_order, "analysis_exit_rule": "FIRST_EXIT_BEFORE_MEDICAL_RETURN" if returned else "STANDARD",
            "all_cause_exit_event": 0 if is_w else 1,
            "censored_at_end": is_w, "source_row_number": i + 1,
        })
    df = pd.DataFrame(rows)
    df["scraped_at"] = pd.Timestamp.now().isoformat()
    return df


def main():
    seasons = {
        "KL12": {"name": "Koh-Lanta : Viêtnam", "year": 2010,
                 "url": "https://en.wikipedia.org/wiki/Koh-Lanta:_Vi%C3%AAtnam", "lang": "en"},
        "KL13": {"name": "Koh-Lanta : Raja Ampat", "year": 2011,
                 "url": "https://en.wikipedia.org/wiki/Koh-Lanta:_Raja_Ampat", "lang": "en"},
        "KL15": {"name": "Koh-Lanta : Malaisie", "year": 2012,
                 "url": "https://fr.wikipedia.org/wiki/Koh-Lanta_:_Malaisie", "lang": "fr"},
        "KL17": {"name": "Koh-Lanta : Johor", "year": 2015,
                 "url": "https://en.wikipedia.org/wiki/Koh-Lanta:_Johor", "lang": "en"},
    }
    
    from src.scraping.scrape_all_seasons import slugify_season_name
    all_dfs = []
    
    for sid, s in seasons.items():
        print(f"\n=== {sid}: {s['name']} ===")
        
        if s["lang"] == "en":
            candidates = scrape_en_dedup(s["url"])
        else:
            # French: use parse_contestant_field approach
            resp = requests.get(s["url"], headers={"User-Agent": USER_AGENT}, timeout=30)
            soup = BeautifulSoup(resp.text, "lxml")
            tables = soup.find_all("table", class_="wikitable")
            ct = tables[0]
            rows = ct.find_all("tr")
            candidates = []
            for row in rows[1:]:
                cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
                if not cells or len(cells) < 2: continue
                name = cells[1].strip() if len(cells) > 1 else ""
                if not name: continue
                depart = cells[-1].strip() if cells else ""
                age = cells[3].strip() if len(cells) > 3 else None
                candidates.append({"name": clean(name), "age": clean(age) if age else None, "finish": depart, "returned": False})
        
        if not candidates:
            print(f"  FAILED: no candidates")
            continue
        
        print(f"  Extracted: {len(candidates)} (expected {EXPECTED[sid]})")
        
        # Deduplicate by name (keep first occurrence for returns)
        seen = set()
        deduped = []
        for c in candidates:
            n = c["name"]
            if n in seen: continue
            seen.add(n)
            deduped.append(c)
        
        if len(deduped) != len(candidates):
            print(f"  Deduped to: {len(deduped)}")
            candidates = deduped
        
        df = build_df(candidates, sid, s["name"], s["year"], s["url"], s["lang"])
        
        slug = slugify_season_name(s["name"])
        out = os.path.join(PROJECT_ROOT, "data", "raw", "seasons", f"{slug}_{s['year']}_raw.csv")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8")
        print(f"  Saved: {out}")
        
        w = df[df["departure_type_normalized"].isin(["VAINQUEUR","CO_VAINQUEUR"])]
        print(f"  Winners: {list(w['candidate_name'])}")
        all_dfs.append(df)
    
    # Concatenate
    batch_dir = os.path.join(PROJECT_ROOT, "data", "raw", "batches")
    os.makedirs(batch_dir, exist_ok=True)
    batch = pd.concat(all_dfs, ignore_index=True)
    bp = os.path.join(batch_dir, "koh_lanta_batch_02_raw.csv")
    batch.to_csv(bp, index=False, encoding="utf-8")
    total = len(batch)
    print(f"\nBatch: {bp} ({total} candidates, {len(batch.season_id.unique())} seasons)")
    for sid in sorted(batch.season_id.unique()):
        n = len(batch[batch.season_id == sid])
        print(f"  {sid}: {n}")
    print(f"Total: {total} (expected 78)")


if __name__ == "__main__":
    main()