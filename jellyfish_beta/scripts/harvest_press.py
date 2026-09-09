"""Find candidate jellyfish reports via Google News RSS and write a triage CSV.

    python scripts/harvest_press.py                      # default queries
    python scripts/harvest_press.py --query "méduses Blue-Bay" --query "méduses Belle-Mare"

Output: data/raw/harvest_candidates.csv with beaches, dates found, species and
sting hints per article. Triage the rows by hand into data/events/mru_events.csv,
keeping the article URL as source_url. Google News only indexes recent
months, so for history use the newspapers' own search pages and the
Tripadvisor Mauritius forum, then feed titles and snippets through
``jellymru.harvest.candidate_from_item``.
"""
import argparse
import csv
import time

import _common  # noqa: F401
from jellymru.config import DATA_DIR
from jellymru.harvest import DEFAULT_QUERIES, candidate_from_item, fetch_rss, google_news_rss_url

FIELDS = ["published", "source", "title", "link", "beaches", "dates_found", "species_hint", "stings_hint", "relevant", "query"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", help="add a query (repeatable); defaults used if none")
    ap.add_argument("--lang", default="fr")
    ap.add_argument("--country", default="MU")
    ap.add_argument("--out", default=str(DATA_DIR / "raw" / "harvest_candidates.csv"))
    args = ap.parse_args()

    queries = args.query or DEFAULT_QUERIES
    rows, seen = [], set()
    for q in queries:
        url = google_news_rss_url(q, args.lang, args.country)
        try:
            items = fetch_rss(url)
        except Exception as exc:  # network errors should not kill the run
            print(f"[warn] {q!r}: {exc}")
            continue
        for it in items:
            cand = candidate_from_item(it)
            if cand["link"] in seen:
                continue
            seen.add(cand["link"])
            cand["query"] = q
            rows.append(cand)
        time.sleep(1.0)

    rows.sort(key=lambda r: (not r["relevant"], r["published"]), reverse=False)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    relevant = sum(1 for r in rows if r["relevant"])
    print(f"wrote {len(rows)} candidates ({relevant} keyword-relevant) -> {args.out}")


if __name__ == "__main__":
    main()
