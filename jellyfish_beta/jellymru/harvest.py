"""Helpers for mining press and forum reports into the event table.

The Mauritian press relays every National Coast Guard (NCG) jellyfish
communiqué, usually with a weekday and day-of-month but no year. This module
provides the pieces needed to turn such snippets into candidate event rows:

* beach-name matching tolerant of accents, hyphens and spelling variants;
* French weekday / day / month extraction;
* year resolution from weekday arithmetic, optionally anchored on a
  publication date;
* species and sting-count hints from keywords;
* a Google News RSS query builder and parser for finding new articles.

Nothing here fetches the network by itself except ``fetch_rss``; the parsing
functions are pure so they can be unit-tested offline.
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import quote_plus

# --------------------------------------------------------------------------
# Beach aliases (French and English spellings seen in the press)
# --------------------------------------------------------------------------
BEACH_ALIASES: dict[str, list[str]] = {
    "grand_baie": ["Grand-Baie", "Grand Baie"],
    "la_cuvette": ["La Cuvette"],
    "pereybere": ["Péreybère", "Pereybere", "Pereybère", "Péreybere"],
    "bain_boeuf": ["Bain-Bœuf", "Bain Boeuf", "Bain-Boeuf", "Bain Bœuf"],
    "grand_gaube": ["Grand-Gaube", "Grand Gaube"],
    "mont_choisy": ["Mont-Choisy", "Mont Choisy", "Mon-Choisy", "Mon Choisy"],
    "trou_aux_biches": ["Trou-aux-Biches", "Trou aux Biches"],
    "pointe_aux_piments": ["Pointe-aux-Piments", "Pointe aux Piments"],
    "baie_du_tombeau": ["Baie-du-Tombeau", "Baie du Tombeau"],
    "le_goulet": ["Le Goulet"],
    "albion": ["Albion"],
    "flic_en_flac": ["Flic-en-Flac", "Flic en Flac"],
    "la_preneuse": ["La Preneuse"],
    "tamarin": ["Tamarin"],
    "riviere_noire": ["Rivière-Noire", "Riviere Noire", "Rivière Noire", "Black River"],
    "la_prairie": ["La Prairie"],
    "ile_aux_benitiers": ["Île-aux-Bénitiers", "Ile aux Benitiers", "île aux Bénitiers"],
    "le_morne": ["Le Morne", "Morne"],
    "gris_gris": ["Gris-Gris", "Gris Gris"],
    "la_cambuse": ["La Cambuse", "Cambuse"],
    "blue_bay": ["Blue-Bay", "Blue Bay"],
    "pointe_desny": ["Pointe-d'Esny", "Pointe d'Esny"],
    "trou_deau_douce": ["Trou-d'Eau-Douce", "Trou d'Eau Douce", "Le Maho"],
    "ile_aux_cerfs": ["Île-aux-Cerfs", "Ile aux Cerfs", "île aux Cerfs"],
    "belle_mare": ["Belle-Mare", "Belle Mare", "Bellemare"],
    "poste_lafayette": ["Poste-Lafayette", "Poste Lafayette"],
    "bras_deau": ["Bras-d'Eau", "Bras d'Eau"],
    "roches_noires": ["Roches-Noires", "Roches Noires"],
}


def normalise(text: str) -> str:
    """Lowercase, strip accents, collapse hyphens/apostrophes/whitespace."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.replace("œ", "oe").replace("Œ", "oe")
    t = re.sub(r"[-'’‘`]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.lower().strip()


_ALIAS_INDEX = [(bid, normalise(a)) for bid, aliases in BEACH_ALIASES.items() for a in aliases]


def find_beaches(text: str) -> list[str]:
    """Beach ids mentioned in text, in order of first appearance, deduplicated."""
    norm = normalise(text)
    hits = []
    for bid, alias in _ALIAS_INDEX:
        pos = norm.find(alias)
        if pos >= 0:
            # word boundary check on both sides
            before = norm[pos - 1] if pos > 0 else " "
            after = norm[pos + len(alias)] if pos + len(alias) < len(norm) else " "
            if not before.isalnum() and not after.isalnum():
                hits.append((pos, bid))
    seen, out = set(), []
    for _, bid in sorted(hits):
        if bid not in seen:
            seen.add(bid)
            out.append(bid)
    return out


# --------------------------------------------------------------------------
# French dates
# --------------------------------------------------------------------------
FR_DAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
EN_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
FR_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
             "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
EN_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
             "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}

_DAY_WORDS = "|".join(list(FR_DAYS) + list(EN_DAYS))
_MONTH_WORDS = "|".join(list(FR_MONTHS) + list(EN_MONTHS))
_DATE_RE = re.compile(
    rf"(?:(?P<wd>{_DAY_WORDS})\s+(?:matin\s+|soir\s+|apres midi\s+)?)?"
    rf"(?:le\s+|ce\s+)?(?P<d>\d{{1,2}})(?:er|st|nd|rd|th)?\s+(?P<m>{_MONTH_WORDS})(?:\s+(?P<y>20\d\d))?"
)


def parse_dates(text: str) -> list[dict]:
    """Find '(weekday) day month (year)' mentions.

    Returns dicts with keys weekday (0=Mon or None), day, month, year (or None).
    """
    norm = normalise(text)
    out = []
    for m in _DATE_RE.finditer(norm):
        wd = m.group("wd")
        weekday = FR_DAYS.get(wd, EN_DAYS.get(wd)) if wd else None
        month = FR_MONTHS.get(m.group("m"), EN_MONTHS.get(m.group("m")))
        day = int(m.group("d"))
        if not (1 <= day <= 31) or month is None:
            continue
        year = int(m.group("y")) if m.group("y") else None
        out.append({"weekday": weekday, "day": day, "month": month, "year": year})
    return out


def candidate_years(weekday: int, day: int, month: int, start: int = 2010, end: int = 2030) -> list[int]:
    """Years in [start, end] where (day, month) falls on the given weekday."""
    years = []
    for y in range(start, end + 1):
        try:
            if date(y, month, day).weekday() == weekday:
                years.append(y)
        except ValueError:
            continue
    return years


def resolve_year(weekday: int | None, day: int, month: int, published: date | None,
                 max_age_days: int = 400) -> int | None:
    """Pick the year for a day/month mention.

    With a publication date, the event is the most recent matching date on or
    before publication (within max_age_days). Without one, return the year
    only if exactly one candidate exists in the recent window, else None.
    """
    if published is not None:
        for back in range(0, 3):
            y = published.year - back
            try:
                d = date(y, month, day)
            except ValueError:
                continue
            if d > published:
                continue
            if (published - d).days > max_age_days:
                break
            if weekday is None or d.weekday() == weekday:
                return y
        return None
    if weekday is None:
        return None
    cands = candidate_years(weekday, day, month, start=date.today().year - 2, end=date.today().year)
    return cands[0] if len(cands) == 1 else None


# --------------------------------------------------------------------------
# Content hints
# --------------------------------------------------------------------------
SPECIES_HINTS = {
    "cubozoa": ["meduse boite", "meduses boites", "box jellyfish", "box jelly", "guepe de mer", "cubozoa", "cubomeduse"],
    "physalia": ["physalie", "physalia", "galere portugaise", "man o war", "man of war", "bluebottle", "blue bottle"],
    "scyphozoa": ["cassiopee", "cassiopea", "aurelia", "pelagia", "rhizostoma"],
}
_STING_RE = re.compile(r"(\d{1,3})\s+(?:personnes|cas|baigneurs|victimes|people|swimmers|cases)")


def species_hint(text: str) -> str:
    norm = normalise(text)
    for group, keys in SPECIES_HINTS.items():
        if any(k in norm for k in keys):
            return group
    return "unknown"


def stings_hint(text: str) -> int | None:
    norm = normalise(text)
    if "piqu" not in norm and "sting" not in norm:
        return None
    m = _STING_RE.search(norm)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Google News RSS
# --------------------------------------------------------------------------
DEFAULT_QUERIES = [
    "méduses lagon Maurice",
    "méduses plage Maurice National Coast Guard",
    "méduses-boîtes Maurice",
    "physalies Maurice plage",
    "jellyfish Mauritius lagoon",
    "jellyfish Mauritius beach coast guard",
]


def google_news_rss_url(query: str, lang: str = "fr", country: str = "MU") -> str:
    ceid = f"{country}:{lang}"
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={lang}&gl={country}&ceid={quote_plus(ceid)}"


def parse_rss(xml_text: str) -> list[dict]:
    """Parse an RSS 2.0 feed into rows: title, link, published, source, description."""
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.iter("item"):
        def txt(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""
        rows.append({
            "title": txt("title"),
            "link": txt("link"),
            "published": txt("pubDate"),
            "source": txt("source"),
            "description": re.sub(r"<[^>]+>", " ", txt("description")),
        })
    return rows


def fetch_rss(url: str, session=None, timeout: int = 30) -> list[dict]:  # pragma: no cover - network
    import requests
    sess = session or requests.Session()
    resp = sess.get(url, timeout=timeout, headers={"User-Agent": "jellymru-harvest/0.1"})
    resp.raise_for_status()
    return parse_rss(resp.text)


def parse_pubdate(text: str) -> date | None:
    """RFC 2822 pubDate -> date, else None."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError):
        return None


def candidate_from_item(item: dict) -> dict:
    """Turn an RSS item (or any title+snippet+published dict) into a candidate row."""
    text = f"{item.get('title', '')}. {item.get('description', '')}"
    published = item.get("published_date") or parse_pubdate(item.get("published", ""))
    dates = parse_dates(text)
    resolved = []
    for d in dates:
        y = d["year"] or resolve_year(d["weekday"], d["day"], d["month"], published)
        resolved.append(f"{y}-{d['month']:02d}-{d['day']:02d}" if y else f"????-{d['month']:02d}-{d['day']:02d}")
    return {
        "published": published.isoformat() if published else "",
        "source": item.get("source", ""),
        "title": item.get("title", ""),
        "link": item.get("link", ""),
        "beaches": ";".join(find_beaches(text)),
        "dates_found": ";".join(resolved),
        "species_hint": species_hint(text),
        "stings_hint": stings_hint(text) or "",
        "relevant": any(k in normalise(text) for k in ["meduse", "jellyfish", "physalie"]),
    }
