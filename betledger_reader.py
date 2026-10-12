"""Turn a Bet365 bet-slip / My Bets screenshot into Bet records.

Two readers, tried in order:
1. Claude vision (needs ANTHROPIC_API_KEY or an `ant auth login` profile).
2. Local OCR with Tesseract (needs the `tesseract` binary + pytesseract), then
   a regex parser. The regex parser is also exposed as ``parse_slip_text`` so
   pasted text and tests work without any image at all.

Nothing here touches bet365.com. Input is only ever an image the user supplies.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from betledger_store import Bet, OPEN, WON, LOST, VOID, CASHED_OUT

VISION_MODEL = "claude-opus-5-5"

_STATUS_WORDS = {
    "won": WON, "win": WON, "winner": WON, "paid": WON,
    "lost": LOST, "loss": LOST, "lose": LOST,
    "void": VOID, "voided": VOID, "refunded": VOID,
    "cashed out": CASHED_OUT, "cash out": CASHED_OUT, "cashed-out": CASHED_OUT,
    "open": OPEN, "pending": OPEN, "unsettled": OPEN, "in-play": OPEN, "in play": OPEN,
}


@dataclass
class ReadResult:
    bets: list[Bet]
    balance: Optional[float]
    reader: str
    raw: str = ""
    warnings: list[str] | None = None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _money(s: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*(?:\.\d{1,2})?", s.replace(" ", ""))
    return float(m.group().replace(",", "")) if m else None


def _normalise_status(s: str | None) -> str:
    if not s:
        return OPEN
    s = s.strip().lower()
    for k, v in _STATUS_WORDS.items():
        if k in s:
            return v
    return OPEN


def synth_ref(selection: str, stake: float, placed_at: str | None) -> str:
    """Stable fallback id when the slip's bet reference isn't readable."""
    key = f"{selection.strip().lower()}|{stake:.2f}|{(placed_at or '')[:16]}"
    return "auto-" + hashlib.sha1(key.encode()).hexdigest()[:10]


def _to_bet(d: dict, source: str) -> Optional[Bet]:
    selection = (d.get("selection") or "").strip()
    stake = d.get("stake")
    if not selection or stake in (None, ""):
        return None
    try:
        stake = float(stake)
    except (TypeError, ValueError):
        return None
    odds = d.get("odds")
    try:
        odds = float(odds) if odds not in (None, "") else None
    except (TypeError, ValueError):
        odds = None
    status = _normalise_status(d.get("status"))
    returns = d.get("returns")
    try:
        returns = float(returns) if returns not in (None, "") else None
    except (TypeError, ValueError):
        returns = None
    if returns is None:
        if status == WON and odds:
            returns = round(stake * odds, 2)
        elif status == VOID:
            returns = stake
        else:
            returns = 0.0
    placed = d.get("placed_at") or None
    settled = d.get("settled_at") or (datetime.now().isoformat(timespec="seconds") if status != OPEN else None)
    conf = float(d.get("confidence", 0.8) or 0.8)
    ref = (d.get("bet_ref") or "").strip() or synth_ref(selection, stake, placed)
    return Bet(
        bet_ref=ref, selection=selection, event=(d.get("event") or "").strip(), stake=stake, odds=odds,
        status=status, returns=round(returns, 2), placed_at=placed, settled_at=settled,
        bet_type=(d.get("bet_type") or "single").lower(), confidence=conf,
        needs_review=conf < 0.8 or ref.startswith("auto-"), source=source,
    )


# --------------------------------------------------------------------------
# 1. Claude vision
# --------------------------------------------------------------------------
_SYSTEM = """You read screenshots of a Bet365 bet slip, "My Bets" list, or account page and return JSON only.
Return exactly this shape and nothing else:
{"balance": number|null,
 "bets": [{"bet_ref": string|null, "selection": string, "event": string, "bet_type": "single"|"multi"|"each_way"|"other",
           "stake": number, "odds": number|null, "status": "open"|"won"|"lost"|"void"|"cashed_out",
           "returns": number|null, "placed_at": ISO-8601 string|null, "settled_at": ISO-8601 string|null,
           "confidence": number 0-1}]}
Rules: odds as decimal (convert fractional like 7/2 -> 4.5). stake is the total stake for the bet.
returns is the amount paid back (0 when lost, stake when void). balance is the account balance if shown, else null.
bet_ref is the bookmaker reference / bet ID if visible. Lower confidence when digits are blurry or cut off.
If no bets are visible return {"balance": null, "bets": []}."""


def _vision_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.path.exists(os.path.expanduser("~/.config/anthropic")))


def read_with_claude(image_bytes: bytes, media_type: str = "image/png") -> ReadResult:
    import base64
    import anthropic

    client = anthropic.Anthropic()
    data = base64.standard_b64encode(image_bytes).decode()
    resp = client.beta.messages.create(
        model=VISION_MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": "Extract every bet and the balance from this screenshot as JSON."},
        ]}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("The model declined to read this image.")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    m = re.search(r"\{.*\}", text, re.S)
    payload = json.loads(m.group() if m else text)
    bets = [b for b in (_to_bet(d, "claude") for d in payload.get("bets", [])) if b]
    bal = payload.get("balance")
    return ReadResult(bets=bets, balance=float(bal) if bal not in (None, "") else None, reader="claude", raw=text)


# --------------------------------------------------------------------------
# 2. Tesseract OCR + regex
# --------------------------------------------------------------------------
def ocr_image(image_bytes: bytes) -> str:
    import io
    from PIL import Image
    import pytesseract

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    w, h = img.size
    if w < 1200:  # upscale phone screenshots so small digits survive OCR
        img = img.resize((w * 2, h * 2))
    return pytesseract.image_to_string(img, config="--psm 6")


_REF_RE = re.compile(r"(?:bet\s*(?:ref|id|reference)|ref(?:erence)?)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{5,})", re.I)
_STAKE_RE = re.compile(r"(?:stake|total\s*stake)\s*[:]?\s*[£$€A]?\s*([\d,]+\.?\d*)", re.I)
_RETURN_RE = re.compile(r"(?:returns?|to\s*return|paid|payout|cash(?:ed)?\s*out(?:\s*for)?)\s*[:]?\s*[£$€A]?\s*([\d,]+\.?\d*)", re.I)
_ODDS_RE = re.compile(r"(?:@|odds\s*[:]?)\s*(\d+(?:\.\d+)?(?:/\d+)?)", re.I)
_BALANCE_RE = re.compile(r"balance\s*[:]?\s*[£$€A]?\s*([\d,]+\.\d{2})", re.I)
_DATE_RE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:[ ,T]+\d{1,2}:\d{2})?)")
_ODDS_ONLY_RE = re.compile(r"^\s*(?:@|odds)\s*[:]?\s*\d+(?:\.\d+)?(?:/\d+)?\s*$", re.I)
_HEADER_WORDS = {"my bets", "bet slip", "betslip", "settled", "unsettled", "open", "cash out", "all", "history", "bet history", "sports", "in-play", "in play"}
_STATUS_RE = re.compile(r"\b(won|lost|void(?:ed)?|cashed\s*out|open|pending|unsettled)\b", re.I)


def _odds_to_decimal(s: str) -> Optional[float]:
    if "/" in s:
        a, b = s.split("/")
        try:
            return round(1 + float(a) / float(b), 3)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(s: str | None) -> Optional[str]:
    if not s:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.replace(",", " ").replace("T", " ").strip(), fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def parse_slip_text(text: str, source: str = "ocr") -> ReadResult:
    """Parse OCR'd or pasted slip text. Bets are split on 'Stake' lines.

    Works for the common layout: selection / event lines, an odds marker,
    a Stake line, an optional Returns line, an optional status word and ref.
    """
    warnings: list[str] = []
    bal_m = _BALANCE_RE.search(text)
    balance = _money(bal_m.group(1)) if bal_m else None

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blocks: list[list[str]] = []
    cur: list[str] = []
    seen_stake = False
    trailer = (_RETURN_RE, _STATUS_RE, _REF_RE)

    def _is_trailer(ln: str) -> bool:
        return any(r.search(ln) for r in trailer)

    for ln in lines:
        if seen_stake and _is_trailer(ln):
            cur.append(ln)            # Returns / Won / Bet ref lines belong to the bet above
            continue
        if seen_stake:
            blocks.append(cur)        # first non-trailer line after the stake starts a new bet
            cur, seen_stake = [], False
        cur.append(ln)
        if _STAKE_RE.search(ln):
            seen_stake = True
    if cur:
        if seen_stake or not blocks:
            blocks.append(cur)
        else:
            blocks[-1].extend(cur)

    bets: list[Bet] = []
    for blk in blocks:
        joined = "\n".join(blk)
        stake_m = _STAKE_RE.search(joined)
        if not stake_m:
            continue
        stake = _money(stake_m.group(1)) or 0.0
        odds_m = _ODDS_RE.search(joined)
        odds = _odds_to_decimal(odds_m.group(1)) if odds_m else None
        ret_m = _RETURN_RE.search(joined)
        returns = _money(ret_m.group(1)) if ret_m else None
        status_m = _STATUS_RE.search(joined)
        status = _normalise_status(status_m.group(1)) if status_m else OPEN
        if status == OPEN and ret_m and re.search(r"\b(paid|cashed)\b", ret_m.group(0), re.I):
            status = CASHED_OUT if "cash" in ret_m.group(0).lower() else WON
        if status == OPEN:
            returns = None  # "To Return" on an open slip is potential, not realised
        ref_m = _REF_RE.search(joined)
        date_m = _DATE_RE.search(joined)
        # selection = first line that is not a money/odds/status/ref/date line
        noise = (_STAKE_RE, _RETURN_RE, _REF_RE, _BALANCE_RE, _DATE_RE, _STATUS_RE, _ODDS_ONLY_RE)
        content = [ln for ln in blk if not any(r.search(ln) for r in noise)
                   and ln.strip().lower() not in _HEADER_WORDS
                   and not ln.lower().startswith(("single", "double", "treble", "accumulator", "each way"))]
        if not content:
            warnings.append("A stake line was found without a readable selection; skipped.")
            continue
        sel_line = content[0]
        selection = re.split(r"\s*@\s*", sel_line)[0].strip()
        event = content[1] if len(content) > 1 else ""
        bt = "single"
        low = joined.lower()
        if "each way" in low or "e/w" in low:
            bt = "each_way"
        elif any(k in low for k in ("double", "treble", "accumulator", "multi", "fold")):
            bt = "multi"
        conf = 0.85 if odds is not None else 0.6
        if ref_m is None:
            conf -= 0.15
        d = {
            "bet_ref": ref_m.group(1) if ref_m else None, "selection": selection, "event": event, "bet_type": bt,
            "stake": stake, "odds": odds, "status": status, "returns": returns,
            "placed_at": _parse_date(date_m.group(1)) if date_m else None, "confidence": conf,
        }
        b = _to_bet(d, source)
        if b:
            bets.append(b)
    if not bets:
        warnings.append("No 'Stake' lines were recognised in the text.")
    return ReadResult(bets=bets, balance=balance, reader=source, raw=text, warnings=warnings)


def read_with_ocr(image_bytes: bytes) -> ReadResult:
    text = ocr_image(image_bytes)
    return parse_slip_text(text, source="ocr")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def read_screenshot(image_bytes: bytes, media_type: str = "image/png", prefer: str = "auto") -> ReadResult:
    """prefer: 'auto' (Claude then OCR), 'claude', or 'ocr'."""
    errors: list[str] = []
    if prefer in ("auto", "claude") and _vision_available():
        try:
            return read_with_claude(image_bytes, media_type)
        except Exception as e:  # noqa: BLE001 - surface and fall through to OCR
            errors.append(f"Claude reader failed: {e}")
            if prefer == "claude":
                raise
    elif prefer == "claude":
        raise RuntimeError("Claude reader not available: install `anthropic` and set ANTHROPIC_API_KEY.")
    try:
        res = read_with_ocr(image_bytes)
        res.warnings = (res.warnings or []) + errors
        return res
    except ImportError as e:
        raise RuntimeError(
            "No reader available. Either set ANTHROPIC_API_KEY (Claude vision) or install Tesseract + "
            "`pip install pytesseract pillow` for local OCR. " + "; ".join(errors)) from e
