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

import sys
from datetime import datetime, timedelta, timezone

import requests

TIMEOUT = 20
USER_AGENT = "opportunity-sweeper/1.0 (personal eligibility tracker)"


def _warn(source: str, exc: Exception) -> None:
    print(f"[opportunity_sweeper] {source} fetch failed: {exc}", file=sys.stderr)


def fetch_reliefweb(appname: str = "opportunity-sweeper") -> list[dict]:
    """ReliefWeb jobs + funding reports (humanitarian/NGO sector).

    Docs: https://apidoc.reliefweb.int/ . Since 2025-11-01 a pre-approved
    `appname` is required for sustained use — request one via the docs site
    if the default gets rate-limited or rejected.
    """
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
        docs = (data.get("procnotices") or {}) if isinstance(data, dict) else {}
        for _key, doc in docs.items():
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


def fetch_ted_eu(query: str = "marine environmental coastal consultancy") -> list[dict]:
    """EU TED (Tenders Electronic Daily) Search API — no auth required.

    Docs: https://docs.ted.europa.eu/api/2.0/search.html
    """
    items: list[dict] = []
    try:
        resp = requests.post(
            "https://api.ted.europa.eu/v3/notices/search",
            json={"query": query, "limit": 50, "fields": ["title", "publication-date", "links"]},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for notice in resp.json().get("notices", []):
            links = notice.get("links", {})
            items.append({
                "title": str(notice.get("title", "Untitled")),
                "url": links.get("html", {}).get("ENG") or links.get("pdf", {}).get("ENG") or "https://ted.europa.eu",
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
