"""Hourly sweep entrypoint.

Run manually with `python sweep.py`, or schedule via cron (see DEPLOY.md).
Fetches every source, scores each item against profile.yaml, and stores
results in SQLite. Prints a one-line summary for cron logs.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from db import Opportunity, connect, upsert
from matcher import llm_score_opportunity, load_profile, score_opportunity
from sources import fetch_all


def run() -> None:
    profile = load_profile()
    min_score = profile.get("min_match_score", 0.25)

    raw_items = fetch_all()
    conn = connect()

    new_count = 0
    matched_count = 0
    try:
        for raw in raw_items:
            title = raw.get("title", "")
            description = raw.get("description", "")
            url = raw.get("url", "")
            if not url:
                continue

            score, personas, keywords = score_opportunity(title, description, profile)

            llm_result = llm_score_opportunity(title, description, profile)
            if llm_result is not None:
                llm_score, _reason = llm_result
                score = max(score, llm_score)

            if score < min_score:
                continue
            matched_count += 1

            opp = Opportunity(
                title=title,
                url=url,
                source=raw.get("source", "unknown"),
                category=raw.get("category", "opportunity"),
                description=description,
                published_date=raw.get("published_date", ""),
                match_score=round(score, 3),
                matched_personas=personas,
                matched_keywords=keywords,
            )
            if upsert(conn, opp):
                new_count += 1
        conn.commit()
    finally:
        conn.close()

    ts = datetime.now(timezone.utc).isoformat()
    print(
        f"[{ts}] fetched={len(raw_items)} matched={matched_count} "
        f"new={new_count} min_score={min_score}"
    )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # last-resort guard so cron logs the failure clearly
        print(f"[opportunity_sweeper] sweep failed: {exc}", file=sys.stderr)
        sys.exit(1)
