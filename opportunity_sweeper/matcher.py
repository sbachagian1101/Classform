from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PROFILE_PATH = Path(__file__).parent / "profile.yaml"


def load_profile() -> dict[str, Any]:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hits(text: str, terms: list[str]) -> list[str]:
    text_low = text.lower()
    return [t for t in terms if t.lower() in text_low]


def score_opportunity(title: str, description: str, profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Keyword-based eligibility scoring.

    Returns (score 0-1, matched_persona_labels, matched_keywords). A keyword
    hit is worth more than a geography/type hit since it is the strongest
    eligibility signal; the score is capped at 1.0 per persona and the best
    persona score wins.
    """
    text = f"{title}\n{description}"
    excludes = profile.get("exclude_keywords") or []
    if _hits(text, excludes):
        return 0.0, [], []

    best_score = 0.0
    matched_personas: list[str] = []
    matched_keywords: set[str] = set()

    for _key, persona in (profile.get("personas") or {}).items():
        kw_hits = _hits(text, persona.get("keywords") or [])
        geo_hits = _hits(text, persona.get("geography") or [])
        type_hits = _hits(text, persona.get("opportunity_types") or [])
        funder_hits = _hits(text, persona.get("trusted_funders") or [])

        if not kw_hits and not funder_hits:
            continue  # require at least one substantive keyword or funder match

        # A trusted funder is a named organisation that already funds/employs
        # this persona, so it counts for more than a generic keyword hit.
        score = min(1.0, 0.2 * len(kw_hits) + 0.1 * len(geo_hits)
                    + 0.1 * len(type_hits) + 0.3 * len(funder_hits))
        if score > 0:
            matched_personas.append(persona.get("label", _key))
            matched_keywords.update(kw_hits + geo_hits + type_hits + funder_hits)
            best_score = max(best_score, score)

    return best_score, matched_personas, sorted(matched_keywords)


def llm_score_opportunity(title: str, description: str, profile: dict[str, Any]) -> tuple[float, str] | None:
    """Optional smarter scoring via the Claude API, used only when
    ANTHROPIC_API_KEY is set. Falls back silently to None (caller should use
    score_opportunity instead) if the key is missing or the call fails, so
    this is never required for the sweeper to work.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    personas_desc = "\n".join(
        f"- {p.get('label', k)}: keywords={p.get('keywords')}, geography={p.get('geography')}, "
        f"trusted_funders={p.get('trusted_funders')}"
        for k, p in (profile.get("personas") or {}).items()
    )
    prompt = (
        "You score whether a job/consultancy/tender/grant posting is relevant to any of these "
        "eligibility profiles:\n" + personas_desc +
        f"\n\nPosting title: {title}\nPosting description: {description[:2000]}\n\n"
        "Reply with exactly two lines:\nSCORE: <number 0-1>\nREASON: <one short sentence>"
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        reply = resp.content[0].text
        score_line = next(l for l in reply.splitlines() if l.upper().startswith("SCORE"))
        reason_line = next((l for l in reply.splitlines() if l.upper().startswith("REASON")), "")
        score = float(score_line.split(":", 1)[1].strip())
        reason = reason_line.split(":", 1)[1].strip() if ":" in reason_line else ""
        return max(0.0, min(1.0, score)), reason
    except Exception:
        return None
