from __future__ import annotations

"""Compatibility wrapper for Harnessform's parser.

The original parser remains in ../harness_parser.py.  This package shadows that
module and loads it under a private name, then adds two safeguards needed for
normal browser copy/paste from Racing & Sports:

1. recover race number/time/name from the visible header; and
2. recover the CURRENT standalone odds price from each runner block before the
   Career / historical-form section.

This deliberately avoids using historical SP prices as today's market price.
"""

import importlib.util
import re
from pathlib import Path

_LEGACY_PATH = Path(__file__).resolve().parent.parent / "harness_parser.py"
_spec = importlib.util.spec_from_file_location("_harness_parser_legacy", _LEGACY_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load Harnessform parser from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

# Re-export the original public API so harness_model.py continues to work.
for _name in dir(_legacy):
    if not _name.startswith("__") and _name != "parse_harness_race":
        globals()[_name] = getattr(_legacy, _name)


def _visible_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw_line in (text or "").splitlines():
        line = _legacy._clean(raw_line)
        if not line:
            continue
        if re.fullmatch(r"[:\-| ]+", line):
            continue
        out.append(line)
    return out


def _repair_header(race, raw: str) -> None:
    """Recover the visible R&S race header from link-stripped browser text."""
    lines = _visible_lines(raw[:12000])
    for i in range(max(0, len(lines) - 3)):
        if not re.fullmatch(r"\d{1,2}", lines[i]):
            continue
        if i + 3 >= len(lines) or not re.fullmatch(r"\d{1,2}:\d{2}", lines[i + 1]):
            continue
        if "LOCAL" not in lines[i + 2].upper():
            continue
        # Avoid a runner number/form block: the next line must look like a race title.
        title = lines[i + 3].strip()
        if re.fullmatch(r"[0-9xX]{2,12}", title):
            continue
        race.race_no = int(lines[i])
        race.time = lines[i + 1]
        if title and title.upper() not in {"FULL FIELDS", "DRIVER", "TRAINER", "TRAINERPP"}:
            race.name = title
        break


def _current_price_from_segment(segment: str):
    """Extract today's standalone R&S price, never a historical starting price."""
    if not segment:
        return None

    # Today's price is printed above the pedigree/Career block. Historical SPs
    # occur later in the form table, so cut the segment before Career.
    upper = segment.upper()
    cut_candidates = []
    for marker in ("CAREER", "FPMARGDATE", "FP MARG DATE"):
        pos = upper.find(marker)
        if pos >= 0:
            cut_candidates.append(pos)
    head = segment[: min(cut_candidates)] if cut_candidates else segment[:5000]

    # Markdown: **$3.6** ; ordinary browser copy: $3.6
    prices = re.findall(
        r"(?mi)^\s*(?:\*\*)?\s*\$\s*(\d+(?:\.\d+)?)\s*(?:\*\*)?\s*$",
        head,
    )
    for value in prices:
        try:
            odds = float(value)
        except ValueError:
            continue
        if odds > 1.0:
            return odds

    # Conservative fallback for flattened text: only inspect the pre-Career area.
    # The race purse is not inside an individual runner segment, so the first
    # plausible dollar number here is the current market quote.
    for value in re.findall(r"\$\s*(\d+(?:\.\d+)?)", head):
        try:
            odds = float(value)
        except ValueError:
            continue
        if 1.0 < odds <= 1001.0:
            return odds
    return None


def parse_harness_race(text: str):
    race = _legacy.parse_harness_race(text)
    raw = (text or "").replace("\u202f", " ").replace("\xa0", " ")

    _repair_header(race, raw)

    for runner in race.runners:
        if getattr(runner, "scratched", False):
            runner.odds = None
            continue
        price = _current_price_from_segment(getattr(runner, "raw", ""))
        if price is not None:
            runner.odds = price

    return race


__all__ = [name for name in globals() if not name.startswith("_")]
