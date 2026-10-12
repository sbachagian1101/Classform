import io
from PIL import Image

from betledger_store import Ledger, Settings, Bet, WON
from betledger_reader import ReadResult
from betledger_watch import Watcher, thumbprint, frames_differ


def _png(color, size=(200, 120)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_frames_differ_only_on_change():
    a = thumbprint(_png((250, 250, 250)))
    b = thumbprint(_png((245, 245, 245)))   # tiny shift, same frame
    c = thumbprint(_png((20, 20, 20)))
    assert frames_differ(None, a)
    assert not frames_differ(a, b)
    assert frames_differ(a, c)


def test_watcher_logs_once_per_new_frame_and_alerts(tmp_path):
    led = Ledger(tmp_path / "w.sqlite3")
    led.save_settings(Settings(daily_win_limit=10))
    calls = []
    alerts = []

    def fake_reader(png):
        calls.append(1)
        from datetime import datetime
        return ReadResult(bets=[Bet("R1", "Sel", stake=10, odds=3, status=WON, returns=30,
                                    settled_at=datetime.now().isoformat())], balance=120.0, reader="fake")

    w = Watcher(led, fake_reader, notifier=lambda t, m: alerts.append(m))
    s1 = w.process_frame(_png((255, 255, 255)))
    s2 = w.process_frame(_png((255, 255, 255)))   # identical frame -> no reader call
    s3 = w.process_frame(_png((0, 0, 0)))         # new frame -> reader again, same bet -> update
    assert len(calls) == 2 and s2 is None
    assert s1.profit == 20 and s3.profit == 20
    assert len(led.all_bets()) == 1
    assert len(alerts) == 1 and "WIN limit" in alerts[0]   # alert raised once, not twice
    assert led.balances()[-1][1] == 120.0
