"""Live screen watcher for BetLedger.

Runs on your own PC. Every few seconds it grabs the screen, and when a Bet365
window is in front and the picture has changed, it sends the frame through the
same reader the app uses and writes any bets / balance into the ledger. The
Streamlit app (betledger_app.py) shows the result and the limit alerts.

    python betledger_watch.py                 # watch while a Bet365 window is active
    python betledger_watch.py --always        # ignore window titles, watch everything
    python betledger_watch.py --interval 3 --reader ocr

Nothing is sent anywhere except the frame to the reader you chose (Claude API
or local Tesseract). Frames that don't show Bet365 are dropped immediately.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from datetime import datetime
from typing import Callable, Optional

from betledger_store import Ledger, DaySummary
from betledger_reader import read_screenshot, ReadResult

TITLE_KEYWORDS = ("bet365",)


# ----------------------------------------------------------------------------
# frame change detection (tiny grayscale thumbnail compared pixel by pixel)
# ----------------------------------------------------------------------------
def thumbprint(png_bytes: bytes, size: int = 24) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("L").resize((size, size))
    return img.tobytes()


def frames_differ(a: Optional[bytes], b: bytes, threshold: float = 0.02) -> bool:
    """True when more than `threshold` of thumbnail pixels moved by >24 levels."""
    if a is None or len(a) != len(b):
        return True
    changed = sum(1 for x, y in zip(a, b) if abs(x - y) > 24)
    return changed / len(b) > threshold


# ----------------------------------------------------------------------------
# platform bits (all optional, degrade gracefully)
# ----------------------------------------------------------------------------
def active_window_title() -> Optional[str]:
    try:
        import pygetwindow as gw  # Windows / macOS

        w = gw.getActiveWindow()
        return (w.title if w else None) or None
    except Exception:  # noqa: BLE001
        return None


def active_window_box() -> Optional[tuple[int, int, int, int]]:
    try:
        import pygetwindow as gw

        w = gw.getActiveWindow()
        if w and w.width > 200 and w.height > 200:
            return (max(w.left, 0), max(w.top, 0), w.width, w.height)
    except Exception:  # noqa: BLE001
        pass
    return None


def grab_screen(box: Optional[tuple[int, int, int, int]] = None) -> bytes:
    import mss
    from PIL import Image

    with mss.mss() as sct:
        mon = sct.monitors[1]
        if box:
            left, top, w, h = box
            mon = {"left": left, "top": top, "width": w, "height": h}
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def notify(title: str, msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {title}: {msg}", flush=True)
    try:
        from plyer import notification

        notification.notify(title=title, message=msg[:250], app_name="BetLedger", timeout=8)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------------
# core step, kept free of screen/OS calls so it can be tested
# ----------------------------------------------------------------------------
class Watcher:
    def __init__(self, ledger: Ledger, reader: Callable[[bytes], ReadResult], notifier: Callable[[str, str], None] = notify):
        self.ledger = ledger
        self.reader = reader
        self.notifier = notifier
        self._last_print: Optional[bytes] = None
        self._alerted: set[str] = set()

    def process_frame(self, png_bytes: bytes) -> Optional[DaySummary]:
        tp = thumbprint(png_bytes)
        if not frames_differ(self._last_print, tp):
            return None
        self._last_print = tp
        res = self.reader(png_bytes)
        for w in res.warnings or []:
            print("  note:", w)
        if res.balance is not None:
            self.ledger.add_balance(res.balance, source="screen")
        ins, upd = self.ledger.upsert_bets([b for b in res.bets if not b.needs_review or b.stake > 0])
        if ins or upd or res.balance is not None:
            parts = []
            if ins:
                parts.append(f"{ins} new bet(s)")
            if upd:
                parts.append(f"{upd} updated")
            if res.balance is not None:
                parts.append(f"balance {res.balance:,.2f}")
            print(f"[{datetime.now():%H:%M:%S}] logged " + ", ".join(parts), flush=True)
        summary = self.ledger.day_summary()
        self._raise_alerts(summary)
        return summary

    def _raise_alerts(self, s: DaySummary) -> None:
        for a in s.alerts:
            key = a.split(":")[0]
            if key not in self._alerted:
                self._alerted.add(key)
                self.notifier("BetLedger limit", a)
        # allow a repeat alert on a new betting day
        if not s.alerts:
            self._alerted.clear()


# ----------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=4.0, help="seconds between screen grabs (default 4)")
    ap.add_argument("--reader", choices=["auto", "claude", "ocr"], default="auto")
    ap.add_argument("--always", action="store_true", help="don't require a Bet365 window to be active")
    ap.add_argument("--db", default=None, help="path to the ledger sqlite file (default: next to the app)")
    args = ap.parse_args(argv)

    try:
        import mss  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Install the watcher extras first:  pip install mss pillow pygetwindow plyer", file=sys.stderr)
        return 2

    ledger = Ledger(args.db) if args.db else Ledger()
    watcher = Watcher(ledger, lambda png: read_screenshot(png, "image/png", prefer=args.reader))
    title_check = not args.always and active_window_title() is not None
    print("BetLedger watcher running. " + ("Watching only while a Bet365 window is active." if title_check else "Watching the whole screen.")
          + " Ctrl+C to stop.", flush=True)
    try:
        while True:
            title = active_window_title() if title_check else ""
            if title_check and not any(k in (title or "").lower() for k in TITLE_KEYWORDS):
                time.sleep(args.interval)
                continue
            try:
                png = grab_screen(active_window_box() if title_check else None)
                watcher.process_frame(png)
            except Exception as e:  # noqa: BLE001
                print(f"[{datetime.now():%H:%M:%S}] frame skipped: {e}", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
