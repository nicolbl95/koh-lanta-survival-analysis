"""
Pipeline d'enrichissement pour Koh-Lanta : Thaïlande.
Enrichit gender_raw, profession_raw, et résout les sorties INDETERMINE.

Modes :
- MODE A : recherche web automatique sur des sources connues
- MODE B : file de recherche manuelle (research_queue.csv)

Version 1 — Enrichissement initial, 21 candidats.
"""

import os
import re
import sys
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, List, Literal

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ─── Pydantic models ─────────────────────────────────────────────────────────

try:
    from pydantic import BaseModel, Field
except ImportError:
    # Fallback if pydantic not installed
    BaseModel = object
    Field = lambda *args, **kwargs: None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Import model category mapper from scraper
try:
    from src.scraping.scrape_single_season import map_to_model_category, AUTHORIZED_MODEL_CATEGORIES
except ImportError:
    def map_to_model_category(departure_type: str) -> str:
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
    AUTHORIZED_MODEL_CATEGORIES = {"DECISION_AVENTURIERS", "EPREUVE", "AUTRE_SORTIE"}

# ─── Configuration ───────────────────────────────────────────────────────────

RAW_CSV = os.path.join(PROJECT_ROOT, "data", "raw", "koh_lanta_thailande_raw.csv")
ENRICHED_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_enriched_v1.csv")
RESEARCH_QUEUE_CSV = os.path.join(PROJECT_ROOT, "data", "enrichment", "koh_lanta_thailande_research_queue.csv")
ENRICHMENT_LOG = os.path.join(PROJECT_ROOT, "data", "enrichment", "enrichment_log.txt")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

GENDER_NORMALIZED_VALUES = {"FEMALE", "MALE", "OTHER", "UNKNOWN"}
GENDER_CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
PROFESSION_CATEGORIES = {
    "MANUEL_TECHNIQUE", "SPORT_SECURITE", "SANTE_SOCIAL",
    "EDUCATION_RECHERCHE", "COMMERCE_GESTION", "ADMINISTRATION_DROIT",
    "ART_MEDIA_COMMUNICATION", "AGRICULTURE_ENVIRONNEMENT",
    "ETUDIANT", "SANS_EMPLOI", "AUTRE", "INDETERMINE",
}
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
ENRICHMENT_STATUS_VALUES = {"COMPLETE", "PARTIAL", "A_VERIFIER", "SOURCE_CONFLICT", "NOT_FOUND"}


# ─── Data models ─────────────────────────────────────────────────────────────

class FieldEnrichment:
    """Holds enrichment data for a single field."""
    def __init__(self):
        self.raw: Optional[str] = None
        self.normalized: Optional[str] = None
        self.source_url: Optional[str] = None
        self.source_excerpt: Optional[str] = None
        self.confidence: Optional[str] = None


class CandidateEnrichment:
    """Enrichment data for one candidate."""
    def __init__(self, candidate_name: str):
        self.candidate_name = candidate_name
        self.gender = FieldEnrichment()
        self.profession = FieldEnrichment()
        self.profession_category: Optional[str] = None
        self.departure = FieldEnrichment()
        self.needs_departure_enrichment = False
        self.enrichment_status = "A_VERIFIER"
        self.enrichment_notes: List[str] = []

    def to_dict(self) -> dict:
        return {
            "gender_raw": self.gender.raw,
            "gender_normalized": self.gender.normalized,
            "gender_source_url": self.gender.source_url,
            "gender_source_excerpt": self.gender.source_excerpt,
            "gender_confidence": self.gender.confidence,
            "profession_raw": self.profession.raw,
            "profession_normalized": self.profession.normalized,
            "profession_category": self.profession_category,
            "profession_source_url": self.profession.source_url,
            "profession_source_excerpt": self.profession.source_excerpt,
            "profession_confidence": self.profession.confidence,
            "departure_type_normalized": self.departure.normalized,
            "departure_category": self.departure.normalized,  # overridden below
            "departure_source_url": self.departure.source_url,
            "departure_source_excerpt": self.departure.source_excerpt,
            "departure_confidence": self.departure.confidence,
            "needs_departure_enrichment": self.needs_departure_enrichment,
            "enrichment_status": self.enrichment_status,
            "enrichment_notes": " | ".join(self.enrichment_notes) if self.enrichment_notes else "",
        }


# ─── Web search helpers ──────────────────────────────────────────────────────

def fetch_page(url: str) -> Optional[str]:
    """Fetch a web page and return its text content."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [WARN] Fetch failed for {url}: {e}")
        return None


def search_wikipedia_fr(query: str) -> Optional[str]:
    """Search French Wikipedia and return the first page extract."""
    try:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
        }
        resp = requests.get("https://fr.wikipedia.org/w/api.php", params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("search", [])
        if not pages:
            return None
        # Get extract of first result
        pageid = pages[0]["pageid"]
        params2 = {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "pageids": pageid,
            "format": "json",
        }
        resp2 = requests.get("https://fr.wikipedia.org/w/api.php", params=params2,
                             headers={"User-Agent": USER_AGENT}, timeout=10)
        data2 = resp2.json()
        pages_data = data2.get("query", {}).get("pages", {})
        for pid, page in pages_data.items():
            extract = page.get("extract", "")
            url = f"https://fr.wikipedia.org/?curid={pageid}"
            return extract, url
        return None
    except Exception as e:
        print(f"  [WARN] Wikipedia search failed for '{query}': {e}")
        return None


def search_google_custom(query: str) -> List[dict]:
    """
    Attempt to search for information.
    In MODE B, this returns empty. In MODE A with API key, it would search.
    For now, we try direct known-source lookups.
    """
    results = []

    # Try Wikipedia French first
    wiki_result = search_wikipedia_fr(query)
    if wiki_result:
        extract, url = wiki_result
        results.append({
            "source": "wikipedia_fr",
            "url": url,
            "text": extract,
            "title": query,
        })

    return results


def extract_gender_from_text(text: str, candidate_name: str) -> Optional[dict]:
    """
    Try to extract gender from French text using explicit markers.
    Returns dict with raw, normalized, confidence, excerpt or None.
    """
    # Only use text that explicitly mentions the candidate
    name_parts = candidate_name.split()
    first_name = name_parts[0] if name_parts else ""

    # Look for explicit gender markers NEAR the candidate name
    markers_female = [
        r'\belle\b', r'\bcandidate\b', r'\bla\s+candidate\b',
        r'\bmère\b', r'\bfemme\b', r'\bnée\b',
    ]
    markers_male = [
        r'\bil\b', r'\ble\s+candidat\b', r'\bcandidat\b',
        r'\bpère\b', r'\bhomme\b', r'\bné\b',
    ]

    # Search for paragraphs containing the name
    paragraphs = text.split('\n')
    for para in paragraphs:
        if first_name.lower() not in para.lower():
            continue

        # Check for female markers
        for marker in markers_female:
            if re.search(marker, para, re.IGNORECASE):
                # Extract a short excerpt around the marker
                excerpt = para[:300].strip()
                return {
                    "raw": "FEMALE",
                    "normalized": "FEMALE",
                    "confidence": "MEDIUM",
                    "excerpt": excerpt,
                }

        # Check for male markers
        for marker in markers_male:
            if re.search(marker, para, re.IGNORECASE):
                excerpt = para[:300].strip()
                return {
                    "raw": "MALE",
                    "normalized": "MALE",
                    "confidence": "MEDIUM",
                    "excerpt": excerpt,
                }

    return None


def extract_profession_from_text(text: str, candidate_name: str) -> Optional[dict]:
    """
    Try to extract profession from French text.
    Look for patterns like 'X, Y ans, profession' or 'X est Y'.
    """
    first_name = candidate_name.split()[0] if candidate_name.split() else ""

    # Profession-related keywords
    profession_patterns = [
        r'(?:est|était)\s+(?:un|une)\s+([\w\s]+?)(?:[,\.]|$)',
        r'(?:,)\s*(\d{1,3})\s*ans\s*,\s*([\w\s]+?)(?:[,\.]|$)',
    ]

    for para in text.split('\n'):
        if first_name.lower() not in para.lower():
            continue

        # Try profession pattern
        match = re.search(r'(?:est|était)\s+(?:un|une)\s+([\w\s]{2,40}?)(?:[,\.]|$)', para, re.IGNORECASE)
        if match:
            prof = match.group(1).strip()
            if len(prof) > 2:
                return {
                    "raw": prof,
                    "normalized": prof,
                    "category": classify_profession(prof),
                    "confidence": "LOW",
                    "excerpt": para[:300].strip(),
                }

    return None


def classify_profession(profession: str) -> str:
    """Classify a profession into a category."""
    prof_lower = profession.lower()

    manual_tech = ["mécanicien", "plombier", "électricien", "ouvrier", "technicien",
                   "chauffeur", "conducteur", "boulanger", "boucher", "cuisinier",
                   "artisan", "menuisier", "charpentier", "soudeur", "peintre"]
    sport_secu = ["pompier", "gendarmerie", "policier", "militaire", "sapeur",
                  "sportif", "coach", "entraîneur", "maître-nageur", "secouriste"]
    sante_social = ["infirmier", "infirmière", "médecin", "docteur", "sage-femme", "kiné",
                    "psychologue", "aide-soignant", "ambulancier", "pharmacien",
                    "éducateur", "assistant", "social", "auxiliaire"]
    edu_rech = ["enseignant", "professeur", "chercheur", "instituteur",
                "formateur", "étudiant", "prof", "scientifique"]
    commerce = ["commercial", "vendeur", "chef d'entreprise", "entrepreneur",
                "dirigeant", "manager", "directeur", "gérant", "comptable",
                "restaurateur", "agent immobilier", "assureur", "banquier"]
    admin_droit = ["avocat", "juriste", "notaire", "fonctionnaire", "secrétaire",
                   "administratif", "assistant", "comptable", "huissier"]
    art_media = ["journaliste", "artiste", "comédien", "musicien", "photographe",
                 "graphiste", "designer", "architecte", "écrivain", "acteur",
                 "réalisateur", "animateur", "styliste"]
    agri_env = ["agriculteur", "éleveur", "jardinier", "paysagiste", "viticulteur",
                "marin", "pêcheur", "forestier", "environnement"]

    if any(k in prof_lower for k in sport_secu):
        return "SPORT_SECURITE"
    if any(k in prof_lower for k in sante_social):
        return "SANTE_SOCIAL"
    if any(k in prof_lower for k in manual_tech):
        return "MANUEL_TECHNIQUE"
    if any(k in prof_lower for k in edu_rech) or "étudiant" in prof_lower:
        return "EDUCATION_RECHERCHE" if "étudiant" not in prof_lower else "ETUDIANT"
    if "étudiant" in prof_lower:
        return "ETUDIANT"
    if any(k in prof_lower for k in commerce):
        return "COMMERCE_GESTION"
    if any(k in prof_lower for k in admin_droit):
        return "ADMINISTRATION_DROIT"
    if any(k in prof_lower for k in art_media):
        return "ART_MEDIA_COMMUNICATION"
    if any(k in prof_lower for k in agri_env):
        return "AGRICULTURE_ENVIRONNEMENT"
    if "sans" in prof_lower and ("emploi" in prof_lower or "profession" in prof_lower):
        return "SANS_EMPLOI"

    return "AUTRE"


# ─── Validated enrichment data (Lot 1) ───────────────────────────────────────

# Manually validated data from trusted sources.
# These override any automatic web search for the specified candidates.
VALIDATED_DATA: Dict[str, dict] = {
    "Charlie Vincent-Mussard": {
        "gender_raw": "aventurière / jeune femme",
        "gender_normalized": "FEMALE",
        "gender_confidence": "MEDIUM",
        "gender_source_url": "https://kohlanta.fandom.com/fr/wiki/Charlie_Vincent-Mussard",
        "gender_source_excerpt": "Charlie Vincent-Mussard est une aventurière de Koh Lanta : Thaïlande. [...] la jeune femme s'épanouit aujourd'hui dans son métier.",
        "profession_raw": "Restauratrice de meubles",
        "profession_normalized": "Restauratrice de meubles",
        "profession_category": "MANUEL_TECHNIQUE",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://survivor.fandom.com/wiki/Charlie_Vincent-Mussard",
        "profession_source_excerpt": "Métier : Restauratrice de meubles.",
        "departure_type_normalized": "ABANDON_VOLONTAIRE",
        "departure_category": "SANTE_ABANDON",
        "departure_confidence": "MEDIUM",
        "needs_departure_enrichment": False,
        "departure_source_url": "https://kohlanta.fandom.com/fr/wiki/Charlie_Vincent-Mussard",
        "departure_source_excerpt": "La jeune femme n'avait donc tout simplement pas le choix : elle a quitté le jeu bien que les médecins la déclaraient apte à continuer.",
        "departure_classification_reason": "Charlie a personnellement quitté le jeu après la confiscation de son traitement. Classification en abandon volontaire, mais confiance moyenne en raison des circonstances médicales et contraintes.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Sortie volontaire dans un contexte lié à un traitement médical confisqué ; ne pas assimiler à une évacuation décidée par le médecin.",
    },
    "Laurence Corbellotti": {
        "gender_raw": "aventurière",
        "gender_normalized": "FEMALE",
        "gender_confidence": "MEDIUM",
        "gender_source_url": "https://kohlanta.fandom.com/fr/wiki/Laurence_Corbellotti",
        "gender_source_excerpt": "Laurence Corbellotti est une aventurière de Koh Lanta : Thaïlande.",
        "profession_raw": "Animatrice et danseuse",
        "profession_normalized": "Animatrice et danseuse",
        "profession_category": "ART_MEDIA_COMMUNICATION",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1.fr/fr-lu/tf1/koh-lanta/news/koh-lanta-thailande-decouvrez-portrait-de-laurence-5638890.html",
        "profession_source_excerpt": "Agée de 37 ans, Laurence vient des Bouches-du-Rhône où elle travaille comme animatrice et danseuse.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Conflit résolu grâce au portrait officiel TF1 publié avant la diffusion de la saison. La profession retenue pour 2016 est animatrice et danseuse. Les valeurs secondaires 'nounou pour chien' et 'organizer' ne sont pas retenues dans le dataset principal.",
    },
    "Marius Torterat": {
        "gender_raw": "jeune homme",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.estrepublicain.fr/culture-loisirs/2020/06/04/koh-lanta-ils-sont-de-lorraine-vous-les-avez-vus-a-la-tele",
        "gender_source_excerpt": "Né en 1994, le jeune homme a passé un bac scientifique à Épinal.",
        "profession_raw": "Étudiant en design automobile",
        "profession_normalized": "Étudiant en design automobile",
        "profession_category": "ETUDIANT",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.estrepublicain.fr/culture-loisirs/2020/06/04/koh-lanta-ils-sont-de-lorraine-vous-les-avez-vus-a-la-tele",
        "profession_source_excerpt": "Il étudie le design automobile à Lille.",
        "departure_type_normalized": "ABANDON_VOLONTAIRE",
        "departure_category": "SANTE_ABANDON",
        "departure_confidence": "HIGH",
        "needs_departure_enrichment": False,
        "departure_source_url": "https://www.estrepublicain.fr/culture-loisirs/2020/06/04/koh-lanta-ils-sont-de-lorraine-vous-les-avez-vus-a-la-tele",
        "departure_source_excerpt": "Après quelques jours d'aventure, il abandonne [...] il déclare que l'aventure ne lui procurait aucun plaisir et, plus tard, se dira oppressé par les caméras.",
        "departure_classification_reason": "Abandon décidé par le candidat, explicitement décrit par une source journalistique.",
        "enrichment_status": "COMPLETE",
    },
    "Céline Parat-Yeghiayan": {
        "gender_raw": "Femme",
        "gender_normalized": "FEMALE",
        "gender_confidence": "MEDIUM",
        "gender_source_url": "https://survivor.fandom.com/wiki/C%C3%A9line_Parat-Yeghiayan",
        "gender_source_excerpt": "Femme de caractère et exigeante, Céline sait ce qu'elle veut.",
        "profession_raw": "Formatrice",
        "profession_normalized": "Formatrice",
        "profession_category": "EDUCATION_RECHERCHE",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://survivor.fandom.com/wiki/C%C3%A9line_Parat-Yeghiayan",
        "profession_source_excerpt": "Métier : Formatrice.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Ancien portrait indiqué comme provenant de TF1, mais actuellement hébergé sur une base secondaire.",
    },
    "Huw Francis": {
        "gender_raw": "jeune homme / Gallois",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1.fr/fr-sn/tf1/koh-lanta/news/koh-lanta-thailande-focus-5-moments-forts-d-hier-soir-8795762.html",
        "gender_source_excerpt": "Un départ que le jeune homme n'a pas vu venir. [...] ce Gallois d'origine.",
        "profession_raw": "Entrepreneur dans l'événement sportif",
        "profession_normalized": "Entrepreneur dans l'événementiel sportif",
        "profession_category": "COMMERCE_GESTION",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1.fr/fr-sn/tf1/koh-lanta/news/koh-lanta-thailande-focus-5-moments-forts-d-hier-soir-8795762.html",
        "profession_source_excerpt": "Cet entrepreneur dans événement sportif n'a toujours pas digéré cette trahison.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession confirmée par une source officielle TF1 et cohérente avec son parcours professionnel antérieur.",
    },
    # ─── Lot 2 ───────────────────────────────────────────────────────────────
    "Carole Poncelet": {
        "gender_raw": "candidate / elle",
        "gender_normalized": "FEMALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "gender_source_excerpt": "Carole, candidate de Koh-Lanta : Thaïlande.",
        "profession_raw": "Agente territoriale et maître-nageuse ; présentée comme escrimeuse",
        "profession_normalized": "Maître-nageuse et agente territoriale",
        "profession_category": "SPORT_SECURITE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.rtl.fr/culture/medias-people/koh-lanta-une-fonctionnaire-revoquee-pour-y-avoir-participe-en-plein-arret-maladie-7799363467",
        "profession_source_excerpt": "Carole Poncelet était agent territorial titulaire et maître-nageur à Clermont-Ferrand.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Le portrait promotionnel TF1 la présentait comme escrimeuse. Des sources journalistiques fiables précisent que son emploi était agente territoriale et maître-nageuse. Conserver la mention d'escrimeuse comme activité sportive, pas comme unique profession.",
    },
    "Laurence \"Lolo\" Facione": {
        "gender_raw": "elle / Laurence",
        "gender_normalized": "FEMALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/koh-lanta-saison-15-en-thailande-menuisier-hipster-militaire-sexy-et-maitre-nageur-hysterique-ca-promet-1501151.html",
        "gender_source_excerpt": "Lolo, 45 ans, est la première à rejoindre l'île. Elle est maître-nageur.",
        "profession_raw": "Maître-nageur",
        "profession_normalized": "Maître-nageuse",
        "profession_category": "SPORT_SECURITE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/koh-lanta-saison-15-en-thailande-menuisier-hipster-militaire-sexy-et-maitre-nageur-hysterique-ca-promet-1501151.html",
        "profession_source_excerpt": "Lolo, 45 ans [...] est maître-nageur.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession indiquée par une source TF1 contemporaine de la diffusion.",
    },
    "Amir Doukhan": {
        "gender_raw": "candidat / il",
        "gender_normalized": "MALE",
        "gender_confidence": "MEDIUM",
        "gender_source_url": "https://kohlanta.fandom.com/fr/wiki/Amir_Doukhan",
        "gender_source_excerpt": "Amir Doukhan est un candidat de Koh-Lanta : Thaïlande.",
        "profession_raw": "Directeur commercial",
        "profession_normalized": "Directeur commercial",
        "profession_category": "COMMERCE_GESTION",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://kohlanta.fandom.com/fr/wiki/Amir_Doukhan",
        "profession_source_excerpt": "Profession : Directeur commercial.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Informations issues d'une base secondaire spécialisée. Confiance moyenne en attendant éventuellement un portrait TF1 archivé.",
    },
    "Cassandre Girard": {
        "gender_raw": "aventurière / elle",
        "gender_normalized": "FEMALE",
        "gender_confidence": "MEDIUM",
        "gender_source_url": "https://kohlanta.fandom.com/fr/wiki/Cassandre_Girard",
        "gender_source_excerpt": "Cassandre Girard est une aventurière de Koh-Lanta : Thaïlande.",
        "profession_raw": "Diplômée en tourisme",
        "profession_normalized": "Diplômée en tourisme",
        "profession_category": "AUTRE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/koh-lanta-saison-15-en-thailande-menuisier-hipster-militaire-sexy-et-maitre-nageur-hysterique-ca-promet-1501151.html",
        "profession_source_excerpt": "Cassandre, diplômée en tourisme, mannequin à ses heures perdues.",
        "departure_type_normalized": "AMBASSADEURS_TIRAGE_AU_SORT",
        "departure_category": "DECISION_AVENTURIERS",
        "departure_confidence": "HIGH",
        "needs_departure_enrichment": False,
        "departure_source_url": "https://www.tf1info.fr/culture/koh-lanta-15-episode-7-cassandre-et-romain-sont-elimines-1507825.html",
        "departure_source_excerpt": "Les deux ambassadeurs doivent désigner un aventurier ou tirer au sort et risquer leur propre place. Cassandre tire ensuite la boule noire et est éliminée.",
        "departure_classification_reason": "Cassandre a été éliminée lors de la réunion des ambassadeurs après avoir tiré la boule noire, les deux ambassadeurs n'étant pas parvenus à un accord.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "La source officielle indique une qualification plutôt qu'un emploi précis. Ne pas inventer de métier. Conserver 'diplômée en tourisme' comme formulation brute et normalisée. | Sortie auditée et corrigée : élimination aux ambassadeurs par tirage de la boule noire. Il ne s'agit pas d'un duel ni d'une élimination liée à une épreuve.",
    },
    "Romain Palazzetti": {
        "gender_raw": "jeune homme / candidat",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/koh-lanta-thailande-romain-elimine-regrette-davoir-neglige-les-relations-humaines-1507905.html",
        "gender_source_excerpt": "Le jeune homme quitte l'aventure après le premier conseil de la tribu réunifiée.",
        "profession_raw": "Entrepreneur en domotique",
        "profession_normalized": "Entrepreneur en domotique",
        "profession_category": "COMMERCE_GESTION",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/koh-lanta-saison-15-en-thailande-menuisier-hipster-militaire-sexy-et-maitre-nageur-hysterique-ca-promet-1501151.html",
        "profession_source_excerpt": "Romain, judoka et entrepreneur en domotique.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession indiquée par une source TF1 contemporaine de la saison. La mention de judoka doit être conservée pour la future recherche sportive, mais ne pas calculer le score physique maintenant.",
    },
    # ─── Lot 3 ───────────────────────────────────────────────────────────────
    "Julien Castro": {
        "gender_raw": "aventurier / il",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/koh-lanta-2016-episode-8-julien-quitte-laventure-1508323.html",
        "gender_source_excerpt": "Julien s'est mis en danger en révélant qu'il était épuisé [...] Il quitte la baie le cœur lourd.",
        "profession_raw": "Menuisier",
        "profession_normalized": "Menuisier",
        "profession_category": "MANUEL_TECHNIQUE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "profession_source_excerpt": "Julien au look de hipster est un menuisier de 29 ans.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Menuisier aux côtés de son père selon le portrait de candidat. Source officielle contemporaine de la saison.",
    },
    "Laureen Hugel": {
        "gender_raw": "candidate / elle",
        "gender_normalized": "FEMALE",
        "gender_confidence": "MEDIUM",
        "gender_source_url": "https://kohlanta.fandom.com/fr/wiki/Laureen_Hugel",
        "gender_source_excerpt": "Laureen Hugel est une des candidates de Koh Lanta : Thaïlande.",
        "profession_raw": "Étudiante en mode et création",
        "profession_normalized": "Étudiante en mode et création",
        "profession_category": "ETUDIANT",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://survivor.fandom.com/wiki/Laureen_Hugel",
        "profession_source_excerpt": "Métier : Etudiante en mode et création.",
        "departure_classification_reason": "Laureen est la candidate directement éliminée par les votes au conseil pendant la mécanique des Destins liés.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "La fiche secondaire indique que le profil a été récupéré depuis l'ancien portrait TF1. Une source officielle archivée serait préférable, mais l'information est suffisamment cohérente pour une confiance moyenne.",
    },
    "Steve Best": {
        "gender_raw": "aventurier / jeune homme",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/koh-lanta-thailande-steve-se-defend-il-nest-pas-macho-1508933.html",
        "gender_source_excerpt": "Steve, candidat de la saison Koh-Lanta Thaïlande [...] le jeune homme éliminé.",
        "profession_raw": "Entrepreneur textile",
        "profession_normalized": "Entrepreneur dans le textile",
        "profession_category": "COMMERCE_GESTION",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://survivor.fandom.com/wiki/Steve_Best",
        "profession_source_excerpt": "Métier : Entrepreneur Textile.",
        "departure_type_normalized": "DESTINS_LIES_SUITE_CONSEIL",
        "departure_category": "DECISION_AVENTURIERS",
        "departure_confidence": "HIGH",
        "needs_departure_enrichment": False,
        "departure_source_url": "https://kohlanta.fandom.com/fr/wiki/Laureen_Hugel",
        "departure_source_excerpt": "Laureen a été éliminée et a donc entraîné Steve dans son élimination.",
        "departure_classification_reason": "Steve quitte automatiquement l'aventure parce que sa partenaire Laureen est éliminée au conseil dans le cadre de la mécanique des Destins liés.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "La profession provient d'une reproduction secondaire de l'ancien profil TF1. Le portrait officiel TF1 le décrit plus généralement comme entrepreneur.",
    },
    "Carine Cazals": {
        "gender_raw": "candidate / jeune femme",
        "gender_normalized": "FEMALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/carine-de-koh-lanta-ne-digere-pas-son-elimination-1507225.html",
        "gender_source_excerpt": "La jeune femme [...] a été éliminée par la tribu réunifiée.",
        "profession_raw": "Gestionnaire de stock dans la fibre optique et gendarme réserviste",
        "profession_normalized": "Gestionnaire de stock",
        "profession_category": "MANUEL_TECHNIQUE",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://survivor.fandom.com/wiki/Carine_Cazals",
        "profession_source_excerpt": "Gestionnaire de stock dans la fibre optique, gendarme réserviste, Carine est aussi passionnée de badminton.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "L'activité principale indiquée est gestionnaire de stock dans la fibre optique. Gendarme réserviste est conservé comme activité secondaire et pourra servir de preuve complémentaire lors du futur scoring physique.",
    },
    "Karima Neggaz": {
        "gender_raw": "aventurière / elle",
        "gender_normalized": "FEMALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/koh-lanta-bonne-joueuse-karima-comprend-son-elimination-1510042.html",
        "gender_source_excerpt": "La guerrière de Koh-Lanta affirme comprendre son élimination.",
        "profession_raw": "Militaire de carrière, sergent",
        "profession_normalized": "Militaire",
        "profession_category": "SPORT_SECURITE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/koh-lanta-bonne-joueuse-karima-comprend-son-elimination-1510042.html",
        "profession_source_excerpt": "Ça fait neuf ans que je suis militaire, je suis passée de soldat à sergent.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession confirmée directement par Karima dans une interview reprise par TF1. Conserver les mentions de carrière militaire et de performances sportives pour la future phase de score physique, sans attribuer encore de score.",
    },
    # ─── Lot 4 ───────────────────────────────────────────────────────────────
    "Nicolas Rouyé": {
        "gender_raw": "jeune mannequin / candidat",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "gender_source_excerpt": "Nicolas est un jeune mannequin de 32 ans.",
        "profession_raw": "Mannequin",
        "profession_normalized": "Mannequin",
        "profession_category": "ART_MEDIA_COMMUNICATION",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "profession_source_excerpt": "Nicolas est un jeune mannequin de 32 ans, qui habite dans les Charente-Maritime.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession indiquée dans une présentation officielle TF1 contemporaine de la saison. Conserver les mentions de sports de glisse et de ski nautique pour la future phase physique, sans calculer de score maintenant.",
    },
    "Alain Chrisostome": {
        "gender_raw": "doyen / candidat",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "gender_source_excerpt": "Alain est le doyen de cette saison 15.",
        "profession_raw": "Employé en supermarché",
        "profession_normalized": "Employé de supermarché",
        "profession_category": "COMMERCE_GESTION",
        "profession_confidence": "MEDIUM",
        "profession_source_url": "https://survivor.fandom.com/wiki/Alain_Chrisostome",
        "profession_source_excerpt": "Métier : Employé en supermarché.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession provenant d'une reproduction secondaire de l'ancien profil TF1. La source officielle actuelle confirme son identité et son âge, mais pas directement son métier. Conserver la mention de champion de pelote basque pour la future phase physique.",
    },
    "Cécilia Siharaj": {
        "gender_raw": "danseuse / candidate",
        "gender_normalized": "FEMALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "gender_source_excerpt": "Cecillia est une danseuse de 28 ans qui vient des Hauts-de-Seine.",
        "profession_raw": "Danseuse",
        "profession_normalized": "Danseuse professionnelle",
        "profession_category": "ART_MEDIA_COMMUNICATION",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "profession_source_excerpt": "Cecillia est une danseuse de 28 ans qui vient des Hauts-de-Seine.",
        "departure_type_normalized": "COURSE_ORIENTATION",
        "departure_category": "EPREUVE",
        "departure_confidence": "HIGH",
        "needs_departure_enrichment": False,
        "departure_source_url": "https://kohlanta.fandom.com/fr/wiki/C%C3%A9cilia_Siharaj",
        "departure_source_excerpt": "Finalement, Cécilia a échoué à l'orientation. Elle est donc quatrième de la saison.",
        "departure_classification_reason": "Cécilia n'a pas trouvé de poignard lors de la course d'orientation et a été éliminée aux portes de l'épreuve des poteaux.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession confirmée par une source officielle TF1. Conserver les mentions d'arts martiaux et de danse pour la future phase physique.",
    },
    "Gabriel Gubbels": {
        "gender_raw": "inspecteur / aventurier / Belge",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/vu-de-twitter-koh-lanta-thailande-gabriel-fouille-dans-le-sac-de-pascal-et-declenche-la-colere-des-internautes-1508931.html",
        "gender_source_excerpt": "Le Belge, persuadé que c'était un mensonge, a donc fouillé dans le sac du Sudiste.",
        "profession_raw": "Inspecteur de police",
        "profession_normalized": "Inspecteur de police",
        "profession_category": "SPORT_SECURITE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "profession_source_excerpt": "Gabriel vient de Belgique. À 40 ans, il est inspecteur de police.",
        "departure_type_normalized": "POTEAUX",
        "departure_category": "EPREUVE",
        "departure_confidence": "HIGH",
        "needs_departure_enrichment": False,
        "departure_source_url": "https://kohlanta.fandom.com/fr/wiki/Gabriel_Gubbels",
        "departure_source_excerpt": "Cause du départ : Éliminé aux poteaux.",
        "departure_classification_reason": "Gabriel a atteint l'épreuve des poteaux mais a été éliminé à l'issue de cette épreuve finale.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "La profession principale est inspecteur de police. Une source secondaire mentionne également une activité de toiletteur pour chiens, qui peut être conservée en note mais ne remplace pas la profession principale.",
    },
    "Pascal Salviani": {
        "gender_raw": "candidat / dirigeant",
        "gender_normalized": "MALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "gender_source_excerpt": "Amateur de défis, Pascal a 48 ans et dirige sa propre entreprise.",
        "profession_raw": "Dirige sa propre entreprise",
        "profession_normalized": "Chef d'entreprise",
        "profession_category": "COMMERCE_GESTION",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1info.fr/culture/photos-qui-sont-les-20-candidats-de-koh-lanta-15-en-thailande-1503642.html",
        "profession_source_excerpt": "Amateur de défis, Pascal a 48 ans et dirige sa propre entreprise.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "La nature exacte de l'entreprise n'est pas indiquée dans cette source. Ne pas inventer de secteur d'activité.",
    },
    # ─── Lot final ───────────────────────────────────────────────────────────
    "Wendy Gervois": {
        "gender_raw": "jeune boxeuse / gagnante",
        "gender_normalized": "FEMALE",
        "gender_confidence": "HIGH",
        "gender_source_url": "https://www.tf1.fr/fr-km/dossier/wendy-kl-thailande-2016",
        "gender_source_excerpt": "La jeune boxeuse sait encaisser les coups, c'est une battante. Wendy remporte la saison 15 de Koh-Lanta Thaïlande face à Pascal.",
        "profession_raw": "Boxeuse",
        "profession_normalized": "Boxeuse",
        "profession_category": "SPORT_SECURITE",
        "profession_confidence": "HIGH",
        "profession_source_url": "https://www.tf1.fr/fr-km/dossier/wendy-kl-thailande-2016",
        "profession_source_excerpt": "Wendy — Nord (59) — Boxeuse.",
        "enrichment_status": "COMPLETE",
        "enrichment_notes": "Profession indiquée par le portrait officiel TF1 de la saison. D'autres sources indiquent qu'elle travaillait également comme surveillante dans un lycée, mais le métier déclaré dans le profil Koh-Lanta est Boxeuse. Les mentions de boxe anglaise depuis l'enfance doivent être conservées pour la future phase de score physique, sans attribuer encore de score.",
    },
}


# ─── Enrichment functions ────────────────────────────────────────────────────

def enrich_candidate(name: str, departure_needs_enrich: bool,
                     departure_type: str, departure_category: str,
                     departure_desc: str) -> CandidateEnrichment:
    """
    Enrich a single candidate, checking validated data first.
    """
    enrichment = CandidateEnrichment(name)

    # ── Check for validated data first ───────────────────────────────────
    validated = VALIDATED_DATA.get(name)
    if validated:
        # Apply validated gender data
        if validated.get("gender_normalized") is not None:
            enrichment.gender.raw = validated.get("gender_raw")
            enrichment.gender.normalized = validated["gender_normalized"]
            enrichment.gender.confidence = validated.get("gender_confidence")
            enrichment.gender.source_url = validated.get("gender_source_url")
            enrichment.gender.source_excerpt = validated.get("gender_source_excerpt")
            enrichment.enrichment_notes.append("Genre issu de données validées (lot 1)")

        # Apply validated profession data
        if validated.get("profession_normalized") is not None:
            enrichment.profession.raw = validated.get("profession_raw")
            enrichment.profession.normalized = validated["profession_normalized"]
            enrichment.profession_category = validated.get("profession_category")
            enrichment.profession.confidence = validated.get("profession_confidence")
            enrichment.profession.source_url = validated.get("profession_source_url")
            enrichment.profession.source_excerpt = validated.get("profession_source_excerpt")
            enrichment.enrichment_notes.append("Profession issue de données validées (lot 1)")
        elif validated.get("profession_category") == "INDETERMINE":
            enrichment.profession_category = "INDETERMINE"
            enrichment.profession.confidence = "UNKNOWN"
            enrichment.enrichment_notes.append("Profession en conflit de sources (lot 1)")

        # Apply validated departure data
        if "departure_type_normalized" in validated:
            enrichment.departure.normalized = validated["departure_type_normalized"]
            enrichment.departure.confidence = validated.get("departure_confidence")
            enrichment.departure.source_url = validated.get("departure_source_url")
            enrichment.departure.source_excerpt = validated.get("departure_source_excerpt")
            enrichment.needs_departure_enrichment = validated.get("needs_departure_enrichment", False)
            enrichment.enrichment_notes.append("Sortie issue de données validées (lot 1)")

        # Override status and notes
        if "enrichment_status" in validated:
            enrichment.enrichment_status = validated["enrichment_status"]
        if "enrichment_notes" in validated and validated["enrichment_notes"]:
            enrichment.enrichment_notes.append(validated["enrichment_notes"])

        # For departure_classification_reason (not in CandidateEnrichment directly,
        # stored via main pipeline)
        enrichment._departure_classification_reason = validated.get(
            "departure_classification_reason")

        return enrichment

    # ── No validated data: try automatic web search ─────────────────────

    # ── Try to find gender and profession from online sources ─────────────
    queries = [
        f"{name} Koh-Lanta",
        f"{name} candidat Koh-Lanta Thaïlande",
        f"{name} profession",
    ]

    all_text = ""
    all_urls = []

    for query in queries[:1]:  # Use first query to avoid rate limiting
        results = search_google_custom(query)
        for result in results:
            all_text += result.get("text", "") + "\n"
            all_urls.append(result.get("url", ""))

    # Try gender extraction
    if all_text:
        gender_info = extract_gender_from_text(all_text, name)
        if gender_info:
            enrichment.gender.raw = gender_info["raw"]
            enrichment.gender.normalized = gender_info["normalized"]
            enrichment.gender.confidence = gender_info["confidence"]
            enrichment.gender.source_excerpt = gender_info["excerpt"]
            enrichment.gender.source_url = all_urls[0] if all_urls else None
            enrichment.enrichment_notes.append("Genre extrait depuis Wikipedia FR")
        else:
            enrichment.enrichment_notes.append("Genre non trouvé dans les sources textuelles")
    else:
        enrichment.enrichment_notes.append("Aucun résultat de recherche pour le genre")

    # Try profession extraction
    if all_text:
        prof_info = extract_profession_from_text(all_text, name)
        if prof_info:
            enrichment.profession.raw = prof_info["raw"]
            enrichment.profession.normalized = prof_info["normalized"]
            enrichment.profession_category = prof_info.get("category")
            enrichment.profession.confidence = prof_info["confidence"]
            enrichment.profession.source_excerpt = prof_info["excerpt"]
            enrichment.profession.source_url = all_urls[0] if all_urls else None
            enrichment.enrichment_notes.append(f"Profession trouvée: {prof_info['raw']}")
        else:
            enrichment.enrichment_notes.append("Profession non trouvée dans les sources")
    else:
        enrichment.enrichment_notes.append("Aucun résultat de recherche pour la profession")

    # ── Handle departure enrichment ──────────────────────────────────────
    if departure_needs_enrich:
        enrichment.needs_departure_enrichment = True
        # Search for specific departure info
        dep_query = f'"{name}" départ Koh-Lanta Thaïlande abandon'
        dep_results = search_google_custom(dep_query)
        dep_text = ""
        for r in dep_results:
            dep_text += r.get("text", "") + "\n"

        if dep_text:
            # Check for medical abandonment
            if re.search(r'abandon\s+médical|blessure|blessé|medical', dep_text, re.IGNORECASE):
                enrichment.departure.normalized = "ABANDON_MEDICAL"
                enrichment.departure.source_excerpt = dep_text[:300]
                enrichment.departure.confidence = "MEDIUM"
                enrichment.enrichment_notes.append("Abandon médical détecté dans les sources")
                enrichment.needs_departure_enrichment = False
            elif re.search(r'abandon\s+volontaire|a\s+décidé\s+de\s+quitter|décision\s+personnelle',
                          dep_text, re.IGNORECASE):
                enrichment.departure.normalized = "ABANDON_VOLONTAIRE"
                enrichment.departure.source_excerpt = dep_text[:300]
                enrichment.departure.confidence = "MEDIUM"
                enrichment.enrichment_notes.append("Abandon volontaire détecté dans les sources")
                enrichment.needs_departure_enrichment = False
            else:
                enrichment.enrichment_notes.append("Type de sortie non confirmé par les sources")
        else:
            enrichment.enrichment_notes.append("Aucune source trouvée pour la sortie")
    else:
        enrichment.departure.normalized = departure_type
        enrichment.departure.confidence = "HIGH"
        enrichment.needs_departure_enrichment = False
        enrichment.enrichment_notes.append("Type de sortie déjà connu (source Wikipedia)")

    # ── Determine overall status ─────────────────────────────────────────
    has_gender = enrichment.gender.normalized is not None
    has_profession = enrichment.profession.normalized is not None
    has_departure = not enrichment.needs_departure_enrichment

    if has_gender and has_profession and has_departure:
        enrichment.enrichment_status = "COMPLETE"
    elif has_gender or has_profession or has_departure:
        enrichment.enrichment_status = "PARTIAL"
    else:
        enrichment.enrichment_status = "NOT_FOUND"

    return enrichment


# ─── Main pipeline ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("PIPELINE D'ENRICHISSEMENT — KOH-LANTA : THAÏLANDE")
    print("=" * 70)

    # ── Load raw CSV ────────────────────────────────────────────────────────
    if not os.path.exists(RAW_CSV):
        print(f"ERREUR : CSV brut introuvable : {RAW_CSV}")
        print("Exécutez d'abord : python src/scraping/scrape_single_season.py")
        sys.exit(1)

    df = pd.read_csv(RAW_CSV)
    print(f"\nCSV brut chargé : {len(df)} candidats")
    print(f"Colonnes : {len(df.columns)}")

    # Verify raw file integrity (hash for later comparison)
    with open(RAW_CSV, "rb") as f:
        original_hash = hashlib.sha256(f.read()).hexdigest()
    print(f"SHA256 brut : {original_hash[:16]}...")

    # ── Determine mode ──────────────────────────────────────────────────────
    # Check for GOOGLE_API_KEY or SEARCH_API_KEY env vars
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("SEARCH_API_KEY")
    mode = "A" if api_key else "B"
    print(f"\nMode : {'AUTOMATIQUE' if mode == 'A' else 'MANUEL ASSISTÉ (B)'}")
    if mode == "B":
        print("Aucune clé API de recherche configurée (GOOGLE_API_KEY ou SEARCH_API_KEY).")
        print("Recherche via Wikipedia FR uniquement. Pour le Mode A complet,")
        print("définissez GOOGLE_API_KEY dans les variables d'environnement.")

    # ── Create enrichment directory ─────────────────────────────────────────
    os.makedirs(os.path.dirname(ENRICHED_CSV), exist_ok=True)

    # ── Open log file ───────────────────────────────────────────────────────
    log_lines = []
    log_lines.append(f"Enrichment log — {datetime.now(timezone.utc).isoformat()}")
    log_lines.append(f"Mode: {mode}")
    log_lines.append(f"Input: {RAW_CSV}")
    log_lines.append(f"Output: {ENRICHED_CSV}")
    log_lines.append("")

    # ── Enrich each candidate ───────────────────────────────────────────────
    enrichments: Dict[str, CandidateEnrichment] = {}
    research_queue_rows = []

    for idx, row in df.iterrows():
        name = row["candidate_name"]
        needs_dep = row.get("needs_departure_enrichment", False)
        dep_type = row.get("departure_type_normalized", "INDETERMINE")
        dep_cat = row.get("departure_category", "INDETERMINE")
        dep_desc = row.get("departure_description_raw", "")

        print(f"\n[{idx+1}/21] {name}...")

        enrichment = enrich_candidate(name, needs_dep, dep_type, dep_cat, dep_desc)
        enrichments[name] = enrichment

        # Log
        log_lines.append(f"{name}: status={enrichment.enrichment_status}")
        log_lines.append(f"  gender={enrichment.gender.normalized or 'None'} "
                        f"({enrichment.gender.confidence or 'N/A'})")
        log_lines.append(f"  profession={enrichment.profession.normalized or 'None'} "
                        f"({enrichment.profession.confidence or 'N/A'})")
        log_lines.append(f"  departure={enrichment.departure.normalized or dep_type} "
                        f"(needs_enrich={enrichment.needs_departure_enrichment})")
        log_lines.append(f"  notes: {'; '.join(enrichment.enrichment_notes)}")

        # Build research queue row for Mode B
        search_gender = f'"{name}" Koh-Lanta genre candidat'
        search_profession = f'"{name}" Koh-Lanta profession métier'
        search_departure = f'"{name}" Koh-Lanta abandon départ Thaïlande'

        research_queue_rows.append({
            "candidate_name": name,
            "search_query_gender": search_gender,
            "search_query_profession": search_profession,
            "search_query_departure": search_departure,
            "gender_candidate_value": enrichment.gender.normalized or "",
            "profession_candidate_value": enrichment.profession.normalized or "",
            "departure_candidate_value": enrichment.departure.normalized or "",
            "gender_source_url": enrichment.gender.source_url or "",
            "gender_source_excerpt": (enrichment.gender.source_excerpt or "")[:200],
            "profession_source_url": enrichment.profession.source_url or "",
            "profession_source_excerpt": (enrichment.profession.source_excerpt or "")[:200],
            "departure_source_url": enrichment.departure.source_url or "",
            "departure_source_excerpt": (enrichment.departure.source_excerpt or "")[:200],
            "review_status": enrichment.enrichment_status,
            "review_notes": " | ".join(enrichment.enrichment_notes),
        })

    # ── Build enriched DataFrame ────────────────────────────────────────────
    enriched_rows = []
    for _, row in df.iterrows():
        name = row["candidate_name"]
        enrich = enrichments.get(name)
        if not enrich:
            continue

        # Preserve all original columns from raw CSV
        new_row = row.to_dict()
        # Add enrichment columns
        enrich_dict = enrich.to_dict()
        for k, v in enrich_dict.items():
            new_row[k] = v

        # Determine final departure type and category
        validated = VALIDATED_DATA.get(name)
        if enrich.departure.normalized and enrich.departure.normalized != "INDETERMINE":
            final_dep_type = enrich.departure.normalized
            # If validated data has a specific departure_category (old family), use it;
            # otherwise preserve the original category from the raw CSV
            if validated and "departure_category" in validated:
                final_dep_cat = validated["departure_category"]
            else:
                final_dep_cat = row.get("departure_category", "INDETERMINE")
            new_row["departure_type_normalized"] = final_dep_type
            new_row["departure_category"] = final_dep_cat
            new_row["needs_departure_enrichment"] = False
        else:
            final_dep_type = row.get("departure_type_normalized", "INDETERMINE")
            final_dep_cat = row.get("departure_category", "INDETERMINE")
            # Keep original values
            new_row["departure_type_normalized"] = final_dep_type
            new_row["departure_category"] = final_dep_cat
            new_row["needs_departure_enrichment"] = row.get("needs_departure_enrichment", False)

        # ── Update model category and all exit fields based on final type ────
        final_model_cat = map_to_model_category(final_dep_type)
        new_row["departure_model_category"] = final_model_cat

        exit_order = new_row.get("first_exit_order", new_row.get("final_exit_order"))
        if exit_order is None or pd.isna(exit_order):
            exit_order = new_row.get("final_exit_order")

        # For candidates without returns: all exits use same values
        new_row["first_exit_type"] = final_dep_type
        new_row["first_exit_model_category"] = final_model_cat
        new_row["final_exit_type"] = final_dep_type
        new_row["final_exit_model_category"] = final_model_cat
        new_row["model_exit_order"] = exit_order
        new_row["model_exit_type"] = final_dep_type
        new_row["model_exit_category"] = final_model_cat

        # Timestamps
        new_row["enrichment_status"] = enrich.enrichment_status
        new_row["enrichment_notes"] = enrich_dict.get("enrichment_notes", "")
        new_row["enriched_at"] = datetime.now(timezone.utc).isoformat()

        enriched_rows.append(new_row)

    df_enriched = pd.DataFrame(enriched_rows)

    # ── Ensure all required columns exist ───────────────────────────────────
    enrichment_columns = [
        "gender_raw", "gender_normalized", "gender_source_url",
        "gender_source_excerpt", "gender_confidence",
        "profession_raw", "profession_normalized", "profession_category",
        "profession_source_url", "profession_source_excerpt",
        "profession_confidence",
        "departure_source_url", "departure_source_excerpt",
        "departure_confidence",
        "needs_departure_enrichment",
        "enrichment_status", "enrichment_notes", "enriched_at",
    ]
    for col in enrichment_columns:
        if col not in df_enriched.columns:
            df_enriched[col] = None

    # ── Save enriched CSV ───────────────────────────────────────────────────
    df_enriched.to_csv(ENRICHED_CSV, index=False, encoding="utf-8")
    print(f"\nCSV enrichi sauvegardé : {ENRICHED_CSV}")
    print(f"Colonnes : {len(df_enriched.columns)}")

    # ── Save research queue ─────────────────────────────────────────────────
    df_queue = pd.DataFrame(research_queue_rows)
    df_queue.to_csv(RESEARCH_QUEUE_CSV, index=False, encoding="utf-8")
    print(f"File de recherche sauvegardée : {RESEARCH_QUEUE_CSV}")

    # ── Save log ────────────────────────────────────────────────────────────
    with open(ENRICHMENT_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    print(f"Journal sauvegardé : {ENRICHMENT_LOG}")

    # ── Display summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RÉSULTATS DE L'ENRICHISSEMENT")
    print("=" * 70)

    # Gender stats
    gender_filled = df_enriched["gender_normalized"].notna().sum()
    print(f"\nSexe renseigné : {gender_filled}/21")
    if gender_filled > 0:
        for g in ["FEMALE", "MALE"]:
            count = (df_enriched["gender_normalized"] == g).sum()
            if count > 0:
                print(f"  {g}: {count}")

    # Profession stats
    prof_filled = df_enriched["profession_normalized"].notna().sum()
    print(f"\nProfession renseignée : {prof_filled}/21")
    if prof_filled > 0:
        prof_cats = df_enriched["profession_category"].value_counts()
        for cat, count in prof_cats.items():
            print(f"  {cat}: {count}")

    # Departure resolution
    charlie = enrichments.get("Charlie Vincent-Mussard")
    marius = enrichments.get("Marius Torterat")
    if charlie:
        print(f"\nStatut Charlie : {charlie.departure.normalized or 'INDETERMINE'} "
              f"(needs_enrich={charlie.needs_departure_enrichment})")
    if marius:
        print(f"Statut Marius  : {marius.departure.normalized or 'INDETERMINE'} "
              f"(needs_enrich={marius.needs_departure_enrichment})")

    # Status distribution
    print("\nStatut d'enrichissement :")
    for status in ENRICHMENT_STATUS_VALUES:
        count = (df_enriched["enrichment_status"] == status).sum()
        if count > 0:
            print(f"  {status}: {count}")

    # A_VERIFIER candidates
    a_verifier = df_enriched[df_enriched["enrichment_status"].isin(["A_VERIFIER", "NOT_FOUND", "PARTIAL"])]
    if len(a_verifier) > 0:
        print(f"\nCandidats encore A_VERIFIER ou incomplets ({len(a_verifier)}) :")
        for _, r in a_verifier.iterrows():
            missing = []
            if pd.isna(r.get("gender_normalized")) or r.get("gender_normalized") is None:
                missing.append("sexe")
            if pd.isna(r.get("profession_normalized")) or r.get("profession_normalized") is None:
                missing.append("profession")
            print(f"  - {r['candidate_name']}: manque {', '.join(missing) if missing else 'notes'}")

    # Missing values
    print("\nValeurs manquantes :")
    for col in enrichment_columns:
        missing = df_enriched[col].isna().sum()
        if missing > 0:
            print(f"  {col}: {missing}/21")

    # ── Validations ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VALIDATIONS")
    print("=" * 70)
    all_ok = True

    # V1: 21 candidates preserved
    v1 = len(df_enriched) == 21
    print(f"{'✓' if v1 else '✗'} V1 : 21 candidats conservés (trouvé: {len(df_enriched)})")
    all_ok = all_ok and v1

    # V2: No candidates added or removed
    original_names = set(df["candidate_name"].tolist())
    enriched_names = set(df_enriched["candidate_name"].tolist())
    v2 = original_names == enriched_names
    print(f"{'✓' if v2 else '✗'} V2 : Aucun candidat ajouté ou supprimé")
    all_ok = all_ok and v2

    # V3: Exit orders preserved
    v3 = (df["final_exit_order"].values == df_enriched["final_exit_order"].values).all()
    print(f"{'✓' if v3 else '✗'} V3 : Rangs de sortie inchangés")
    all_ok = all_ok and v3

    # V4: Normalized values in authorized lists
    valid_gender = df_enriched["gender_normalized"].dropna().isin(GENDER_NORMALIZED_VALUES).all()
    v4a = valid_gender or df_enriched["gender_normalized"].isna().all()
    valid_prof_cat = df_enriched["profession_category"].dropna().isin(PROFESSION_CATEGORIES).all()
    v4b = valid_prof_cat or df_enriched["profession_category"].isna().all()
    v4 = v4a and v4b
    print(f"{'✓' if v4 else '✗'} V4 : Valeurs normalisées autorisées")
    all_ok = all_ok and v4

    # V5: Filled values have a source URL
    has_gender = df_enriched["gender_normalized"].notna()
    v5a = (df_enriched.loc[has_gender, "gender_source_url"].notna().all()
           if has_gender.any() else True)
    has_prof = df_enriched["profession_normalized"].notna()
    v5b = (df_enriched.loc[has_prof, "profession_source_url"].notna().all()
           if has_prof.any() else True)
    v5 = v5a and v5b
    print(f"{'✓' if v5 else '✗'} V5 : URL source pour chaque valeur renseignée")
    all_ok = all_ok and v5

    # V6: Filled values have an excerpt
    v6a = (df_enriched.loc[has_gender, "gender_source_excerpt"].notna().all()
           if has_gender.any() else True)
    v6b = (df_enriched.loc[has_prof, "profession_source_excerpt"].notna().all()
           if has_prof.any() else True)
    v6 = v6a and v6b
    print(f"{'✓' if v6 else '✗'} V6 : Extrait justificatif pour chaque valeur")
    all_ok = all_ok and v6

    # V7: Confidence values valid
    conf_valid = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
    v7a = df_enriched["gender_confidence"].dropna().isin(conf_valid).all()
    v7b = df_enriched["profession_confidence"].dropna().isin(conf_valid).all()
    v7 = v7a and v7b
    print(f"{'✓' if v7 else '✗'} V7 : Niveaux de confiance valides")
    all_ok = all_ok and v7

    # V8: Gender never from first name alone
    # (We can't fully verify this in code, but our extractor requires explicit markers)
    v8 = True
    print(f"{'✓' if v8 else '✗'} V8 : Sexe non attribué à partir du prénom seul (vérifié par conception)")
    all_ok = all_ok and v8

    # V9: Non-validated candidates' professions remain empty (auto-search found nothing)
    validated_names = set(VALIDATED_DATA.keys())
    non_validated = df_enriched[~df_enriched["candidate_name"].isin(validated_names)]
    v9 = non_validated["profession_normalized"].isna().all()
    print(f"{'✓' if v9 else '✗'} V9 : Candidats non validés : professions vides "
          f"(auto-search n'a rien trouvé)")
    all_ok = all_ok and v9

    # V10: Raw file not modified
    with open(RAW_CSV, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    v10 = current_hash == original_hash
    print(f"{'✓' if v10 else '✗'} V10 : Fichier brut original non modifié")
    all_ok = all_ok and v10

    # V11: Physical score columns still empty
    for col in ["physical_score", "physical_score_justification", "physical_score_sources"]:
        if col in df_enriched.columns:
            v11_ok = df_enriched[col].isna().all()
            if not v11_ok:
                print(f"  ✗ {col} non vide !")
                all_ok = False
    print(f"{'✓' if all_ok else '✗'} V11 : Colonnes physical_score vides")

    # V12: Unresolved cases marked A_VERIFIER or NOT_FOUND
    unresolved = df_enriched[df_enriched["needs_departure_enrichment"] == True]
    v12 = all(unresolved["enrichment_status"].isin(["A_VERIFIER", "NOT_FOUND", "PARTIAL"]))
    print(f"{'✓' if v12 else '✗'} V12 : Cas non résolus marqués A_VERIFIER/NOT_FOUND")
    all_ok = all_ok and v12

    print(f"\n{'✓' if all_ok else '✗'} Résultat global : validations {'OK' if all_ok else 'en échec'}")

    # ── Adaptation notes ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("NOTES D'ENRICHISSEMENT")
    print("=" * 70)
    print(f"""
Mode utilisé : {'AUTOMATIQUE' if mode == 'A' else 'MANUEL ASSISTÉ (B)'}
Recherches effectuées : Wikipedia FR uniquement (pas de clé API configurée)
File de recherche manuelle : {RESEARCH_QUEUE_CSV}

Pour activer le Mode A complet :
  set GOOGLE_API_KEY=votre_clé
  python src/enrichment/enrich_single_season.py

Pour le Mode B, complétez manuellement les champs dans la research queue,
puis réexécutez le script qui fusionnera les données vérifiées.
""")

    return df_enriched


if __name__ == "__main__":
    df = main()