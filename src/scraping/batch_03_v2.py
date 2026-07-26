"""Batch 3 v2 — Corrected with dedup and co-winners."""
import os, re, sys, requests, pandas as pd
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"

EXPECTED = {"KL21": 18, "KL22": 21, "KL32": 24, "KL25": 24}
WINNERS = {
    "KL21": ["Frédéric Blancher"],
    "KL22": ["Maud Baecker"],
    "KL32": ["Alexandra Pornet"],
    "KL25": ["François Alu", "Bastien Grimal"],
}
FINALISTS = {
    "KL21": ["Clémentine Jullien"],
    "KL22": ["Cindy Poumeyrol"],
    "KL32": ["Brice Petit"],
    "KL25": ["Géraldine"],
}

def clean(t):
    t = re.sub(r'\[\s*[a-zA-Z0-9]+\s*(?:[–\-]\s*[a-zA-Z0-9]+)?\s*\]','',str(t))
    return re.sub(r'\s+',' ',t).strip()

def parse_name(raw):
    raw = clean(raw)
    m = re.match(r'^(.*?)\s+(\d{1,3})\s*,\s*(.*?)$', raw)
    if m: return m.group(1).strip(), m.group(2).strip()
    return raw, None

def classify_en(f):
    f = clean(f).strip()
    if re.search(r'^(Sole|Ultimate|Dual)\s+Survivor',f,re.I):
        return "CO_VAINQUEUR" if re.search(r'Dual',f,re.I) else "VAINQUEUR"
    if re.match(r'^Runner[- ]up',f,re.I): return "FINALISTE"
    if re.search(r'Lost\s+Duel',f,re.I): return "EPREUVE_ELIMINATOIRE"
    if re.search(r'Lost\s+Challenge',f,re.I): return "EPREUVE_ELIMINATOIRE"
    if re.search(r'Left\s+Competition',f,re.I): return "INDETERMINE"
    if re.search(r'Voted\s+Out',f,re.I): return "CONSEIL"
    if re.search(r'Medic|Evacuated',f,re.I): return "ABANDON_MEDICAL"
    if re.search(r'Quit|Withdr',f,re.I): return "ABANDON_VOLONTAIRE"
    return "INDETERMINE"

def classify_fr(t):
    t = clean(t).strip()
    if re.search(r'Vainqueur|Gagnant',t,re.I): return "VAINQUEUR"
    if re.search(r'Finaliste',t,re.I): return "FINALISTE"
    if re.search(r'Abandon\s+m[ée]dical',t,re.I): return "ABANDON_MEDICAL"
    if re.search(r'Abandon\s+volontaire',t,re.I): return "ABANDON_VOLONTAIRE"
    if re.search(r'[ÉE]limin[ée]',t,re.I): return "INDETERMINE"
    return "INDETERMINE"

def scrape_en_dedup(url):
    resp = requests.get(url, headers={"User-Agent":USER_AGENT}, timeout=30)
    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table", class_="wikitable")
    ct = None
    for t in tables:
        h = [th.get_text(strip=True) for th in t.find_all("th")]
        if "Contestant" in h and "Finish" in h: ct = t; break
    if not ct: return None
    rows = ct.find_all("tr")
    raw = []
    for row in rows[1:]:
        cells = [td.get_text(" ",strip=True) for td in row.find_all("td")]
        if not cells or len(cells)<2: continue
        first = cells[0].strip()
        if not first: continue
        name, age = parse_name(first)
        finish = cells[-1].strip() if cells else ""
        raw.append({"name":name,"age":age,"finish":finish,"cells":cells})
    # Dedup: only keep first occurrence for each name (skip "Returned to Game")
    seen = set()
    canonical = []
    for r in raw:
        n = r["name"]
        is_return = "Returned to Game" in r["finish"] or "Returned to Game" in str(r["cells"])
        base = re.sub(r'\s*Returned\s+to\s+Game\s*','', n, flags=re.I).strip()
        if is_return:
            # Mark canonical entry as returned
            for c in canonical:
                if c["name"] == base: c["returned"] = True
            continue
        if base not in seen:
            seen.add(base)
            r["returned"] = False
            canonical.append(r)
    return canonical

def build_df(candidates, sid, sname, syear, surl, lang):
    ws = set(WINNERS.get(sid,[]))
    fs = set(FINALISTS.get(sid,[]))
    rows = []
    for i, c in enumerate(candidates):
        name = c["name"]
        if name in ws:
            t = "CO_VAINQUEUR" if len(ws)==2 else "VAINQUEUR"
        elif name in fs:
            t = "FINALISTE"
        elif lang=="en":
            t = classify_en(c["finish"])
        else:
            t = classify_fr(c["finish"])
        is_w = t in ("VAINQUEUR","CO_VAINQUEUR")
        ret = c.get("returned",False)
        rows.append({
            "season_id":sid,"season_name":sname,"season_year":syear,"season_url":surl,
            "candidate_name":name,"gender_raw":None,"age_raw":c.get("age"),
            "profession_raw":None,"final_position_raw":c["finish"],
            "final_exit_order":i+1,
            "final_exit_order_normalized":round(i/(len(candidates)-1),6) if len(candidates)>1 else 1.0,
            "departure_day_raw":None,"departure_description_raw":c["finish"],
            "departure_type_normalized":t,
            "departure_category":"FIN_DE_JEU" if is_w or t=="FINALISTE" else "INDETERMINE",
            "departure_model_category":"AUTRE_SORTIE" if t in ("VAINQUEUR","CO_VAINQUEUR","FINALISTE","ABANDON_MEDICAL") else "INDETERMINE",
            "departure_classification_reason":f"Source: {surl}",
            "needs_departure_enrichment":t=="INDETERMINE","departure_is_definitive":True,
            "returned_to_game":ret,"first_exit_order":i+1,"second_exit_order":None,
            "returned_after_medical_replacement":ret,
            "same_day_exit_group":None,"exit_order_ambiguity":False,"exit_order_review_required":False,
            "analysis_exit_order":i+1,"analysis_exit_rule":"FIRST_EXIT_BEFORE_MEDICAL_RETURN" if ret else "STANDARD",
            "all_cause_exit_event":0 if is_w else 1,"censored_at_end":is_w,"source_row_number":i+1,
        })
    df = pd.DataFrame(rows)
    df["scraped_at"] = pd.Timestamp.now().isoformat()
    return df

def main():
    seasons = {
        "KL21":{"name":"Koh-Lanta : Cambodge","year":2017,"url":"https://en.wikipedia.org/wiki/Koh-Lanta:_Cambodge","lang":"en"},
        "KL22":{"name":"Koh-Lanta : La Guerre des Chefs","year":2019,"url":"https://fr.wikipedia.org/wiki/Koh-Lanta_:_La_Guerre_des_Chefs","lang":"fr"},
        "KL32":{"name":"Koh-Lanta : Les 4 Terres","year":2020,"url":"https://fr.wikipedia.org/wiki/Koh-Lanta_:_Les_4_Terres","lang":"fr"},
        "KL25":{"name":"Koh-Lanta : Le Totem Maudit","year":2022,"url":"https://en.wikipedia.org/wiki/Koh-Lanta:_Le_Totem_Maudit","lang":"en"},
    }
    from src.scraping.scrape_all_seasons import slugify_season_name
    all_dfs = []
    for sid, s in seasons.items():
        print(f"\n=== {sid}: {s['name']} ({s['year']}) ===")
        if s["lang"]=="en":
            candidates = scrape_en_dedup(s["url"])
        else:
            resp = requests.get(s["url"], headers={"User-Agent":USER_AGENT}, timeout=30)
            soup = BeautifulSoup(resp.text,"lxml")
            tables = soup.find_all("table",class_="wikitable")
            ct = tables[0]
            rows = ct.find_all("tr")
            candidates = []
            for row in rows[1:]:
                cells = [td.get_text(" ",strip=True) for td in row.find_all("td")]
                if not cells or len(cells)<2: continue
                name = cells[1].strip() if len(cells)>1 else ""
                if not name: continue
                depart = cells[-1].strip() if cells else ""
                age = cells[3].strip() if len(cells)>3 else None
                candidates.append({"name":clean(name),"age":clean(age) if age else None,"finish":depart,"returned":False})
        if not candidates:
            print("  FAILED"); continue
        print(f"  Raw: {len(candidates)} (expected {EXPECTED[sid]})")
        # Deduplicate by name
        seen = set()
        deduped = []
        for c in candidates:
            n = c["name"]
            if n in seen: continue
            seen.add(n)
            deduped.append(c)
        if len(deduped) != len(candidates):
            print(f"  Deduped: {len(deduped)}")
            candidates = deduped
        print(f"  Final: {len(candidates)}")
        df = build_df(candidates, sid, s["name"], s["year"], s["url"], s["lang"])
        slug = slugify_season_name(s["name"])
        out = os.path.join(PROJECT_ROOT,"data","raw","seasons",f"{slug}_{s['year']}_raw.csv")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8")
        print(f"  Saved: {out}")
        w = df[df["departure_type_normalized"].isin(["VAINQUEUR","CO_VAINQUEUR"])]
        print(f"  Winners: {list(w['candidate_name'])}")
        all_dfs.append(df)
    # Concatenate
    batch_dir = os.path.join(PROJECT_ROOT,"data","raw","batches")
    os.makedirs(batch_dir, exist_ok=True)
    batch = pd.concat(all_dfs, ignore_index=True)
    bp = os.path.join(batch_dir, "koh_lanta_batch_03_raw.csv")
    batch.to_csv(bp, index=False, encoding="utf-8")
    total = len(batch)
    print(f"\nBatch: {bp} ({total} candidates, {len(batch.season_id.unique())} seasons)")
    for sid in sorted(batch.season_id.unique()):
        n = len(batch[batch.season_id==sid])
        ws = batch[(batch.season_id==sid) & (batch["departure_type_normalized"].isin(["VAINQUEUR","CO_VAINQUEUR"]))]
        print(f"  {sid}: {n} candidates, winners={list(ws['candidate_name'])}")
    print(f"Total: {total} (expected 87)")

if __name__ == "__main__":
    main()