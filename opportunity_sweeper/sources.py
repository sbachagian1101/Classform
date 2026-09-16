"""Source adapters for the opportunity sweeper.

Each adapter is a plain function `fetch() -> list[dict]` returning raw items
with keys: title, url, description, published_date, source, category
(category is one of "job", "grant", "tender"). Every adapter is defensive:
network/parsing failures are caught and logged to stderr so one broken
source never kills the whole sweep.

Only official, no-scraping data sources are included. Two commonly-wanted
sources were deliberately left out because no compliant free API exists:

- UNGM (UN Global Marketplace) tenders: no official public API; only
  third-party scrapers of unclear ToS standing. Subscribe to UNGM's own
  email alerts instead (ungm.org account, free).
- Devex: jobs/funding search is membership-gated; a paid Devex membership
  would be needed for programmatic access.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

TIMEOUT = 20
USER_AGENT = "opportunity-sweeper/1.0 (personal eligibility tracker)"


def _warn(source: str, exc: Exception) -> None:
    print(f"[opportunity_sweeper] {source} fetch failed: {exc}", file=sys.stderr)


def fetch_reliefweb(appname: str | None = None) -> list[dict]:
    """ReliefWeb jobs + funding reports (humanitarian/NGO sector).

    Docs: https://apidoc.reliefweb.int/ . Since 2025-11-01 ReliefWeb requires
    a pre-approved `appname` (request one at apidoc.reliefweb.int/parameters)
    — until then this returns 403 for everyone, which is expected and not a
    bug. Set RELIEFWEB_APPNAME in .env once you have one; no code change
    needed.
    """
    appname = appname or os.environ.get("RELIEFWEB_APPNAME", "opportunity-sweeper")
    items: list[dict] = []
    try:
        resp = requests.post(
            f"https://api.reliefweb.int/v2/jobs?appname={appname}",
            json={"limit": 50, "sort": ["date.created:desc"]},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for entry in resp.json().get("data", []):
            f = entry.get("fields", {})
            items.append({
                "title": f.get("title", "Untitled"),
                "url": f.get("url_alias") or f.get("url") or "",
                "description": (f.get("body") or "")[:2000],
                "published_date": f.get("date", {}).get("created", ""),
                "source": "ReliefWeb Jobs",
                "category": "job",
            })
    except Exception as exc:
        _warn("ReliefWeb jobs", exc)

    try:
        resp = requests.post(
            f"https://api.reliefweb.int/v2/reports?appname={appname}",
            json={"limit": 50, "sort": ["date.created:desc"],
                  "filter": {"field": "theme.name", "value": "Funding"}},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for entry in resp.json().get("data", []):
            f = entry.get("fields", {})
            items.append({
                "title": f.get("title", "Untitled"),
                "url": f.get("url_alias") or f.get("url") or "",
                "description": (f.get("body") or "")[:2000],
                "published_date": f.get("date", {}).get("created", ""),
                "source": "ReliefWeb Funding",
                "category": "grant",
            })
    except Exception as exc:
        _warn("ReliefWeb funding", exc)

    return items


def fetch_grants_gov(keyword: str = "environment marine coastal conservation") -> list[dict]:
    """US Grants.gov Search2 API — no auth required.

    Docs: https://grants.gov/api/api-guide
    """
    items: list[dict] = []
    try:
        resp = requests.post(
            "https://api.grants.gov/v1/api/search2",
            json={"keyword": keyword, "rows": 50, "oppStatuses": "forecasted|posted"},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for opp in resp.json().get("data", {}).get("oppHits", []):
            opp_id = opp.get("id") or opp.get("number", "")
            items.append({
                "title": opp.get("title", "Untitled"),
                "url": f"https://www.grants.gov/search-results-detail/{opp_id}" if opp_id else "https://www.grants.gov",
                "description": opp.get("agencyName", ""),
                "published_date": opp.get("openDate", ""),
                "source": "Grants.gov",
                "category": "grant",
            })
    except Exception as exc:
        _warn("Grants.gov", exc)
    return items


def fetch_remoteok(tags: tuple[str, ...] = ("environment", "sustainability", "marine")) -> list[dict]:
    """RemoteOK public JSON feed — no auth required.

    Docs: https://remoteok.com/api . First element of the response is
    metadata, not a job — skip it.
    """
    items: list[dict] = []
    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
        for row in rows[1:] if rows else []:
            row_tags = " ".join(row.get("tags") or []).lower()
            text = f"{row.get('position', '')} {row.get('description', '')} {row_tags}".lower()
            if not any(t in text for t in tags):
                continue
            items.append({
                "title": f"{row.get('position', 'Untitled')} @ {row.get('company', '')}",
                "url": row.get("url", "https://remoteok.com"),
                "description": (row.get("description") or "")[:2000],
                "published_date": row.get("date", ""),
                "source": "RemoteOK",
                "category": "job",
            })
    except Exception as exc:
        _warn("RemoteOK", exc)
    return items


def fetch_world_bank_procurement(sector: str | None = None) -> list[dict]:
    """World Bank Procurement Notices API — no auth required.

    Base: https://search.worldbank.org/api/v2/procnotices
    """
    items: list[dict] = []
    try:
        params = {"format": "json", "rows": 50}
        if sector:
            params["sector"] = sector
        resp = requests.get(
            "https://search.worldbank.org/api/v2/procnotices",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_docs = data.get("procnotices") if isinstance(data, dict) else None
        # The API has returned this keyed by notice id (a dict of dicts) in
        # some responses and as a plain list in others - handle both.
        if isinstance(raw_docs, dict):
            docs = list(raw_docs.values())
        elif isinstance(raw_docs, list):
            docs = raw_docs
        else:
            docs = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            items.append({
                "title": doc.get("notice_title", "Untitled"),
                "url": doc.get("notice_url") or doc.get("url") or "https://projects.worldbank.org/en/projects-operations/procurement",
                "description": f"{doc.get('project_name', '')} · {doc.get('country', '')}",
                "published_date": doc.get("submission_date", ""),
                "source": "World Bank Procurement",
                "category": "tender",
            })
    except Exception as exc:
        _warn("World Bank procurement", exc)
    return items


def _ted_title(field) -> str:
    """notice-title arrives multilingual, e.g. {"eng": ["Some title"]}."""
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        for value in field.values():
            if value:
                return value[0] if isinstance(value, list) else str(value)
    return "Untitled"


def fetch_ted_eu(terms: tuple[str, ...] = (
    "marine environmental", "coastal engineering",
    "environmental impact assessment", "marine consultancy",
)) -> list[dict]:
    """EU TED (Tenders Electronic Daily) Search API — no auth required.

    Docs: https://docs.ted.europa.eu/api/latest/index.html . TED uses an
    expert-search query syntax (FT~"..." for full-text), not a plain
    keyword string, and returns multilingual field values.
    """
    items: list[dict] = []
    query = " OR ".join(f'FT~"{t}"' for t in terms) + " SORT BY publication-date DESC"
    try:
        resp = requests.post(
            "https://api.ted.europa.eu/v3/notices/search",
            json={
                "query": query,
                "fields": ["publication-number", "notice-title", "publication-date"],
                "limit": 50,
                "scope": "ACTIVE",
                "paginationMode": "ITERATION",
            },
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for notice in resp.json().get("notices", []):
            pub_number = notice.get("publication-number", "")
            url = f"https://ted.europa.eu/en/notice/-/detail/{pub_number}" if pub_number else "https://ted.europa.eu"
            items.append({
                "title": _ted_title(notice.get("notice-title")),
                "url": url,
                "description": "",
                "published_date": notice.get("publication-date", ""),
                "source": "EU TED Tenders",
                "category": "tender",
            })
    except Exception as exc:
        _warn("TED EU", exc)
    return items


# Registry the sweeper iterates over. Add/remove adapters here.
ALL_SOURCES = [
    fetch_reliefweb,
    fetch_grants_gov,
    fetch_remoteok,
    fetch_world_bank_procurement,
    fetch_ted_eu,
]


def fetch_all() -> list[dict]:
    results: list[dict] = []
    for fetcher in ALL_SOURCES:
        results.extend(fetcher())
    return results
