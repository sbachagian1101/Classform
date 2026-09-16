#!/usr/bin/env bash
# Deploy/update the Opportunity Sweeper on the ausracing droplet.
# Safe to re-run: pulls the latest opportunity_sweeper/ code, rebuilds the
# venv, re-seeds the systemd units and Caddy route, restarts the web
# service, and leaves the hourly timer running. Does not touch data/ or
# .venv/ (both are gitignored, so a fresh clone never contains them).
#
# Mirrors the layout already used by the other apps on this box (see
# /opt/oddstracker/deploy/setup_server.sh) — one app per /opt/<name> dir,
# one systemd unit per process, one path-based route in the shared Caddyfile.
set -euo pipefail

REPO_URL="https://github.com/sbachagian1101/Classform.git"
BRANCH="claude/opportunities-sweeper-app-86cde7"
APP_DIR="/opt/opportunity-sweeper"
WEB_PORT=8536
CADDYFILE="/etc/caddy/Caddyfile"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (it writes to /opt, /etc/systemd/system and /etc/caddy)." >&2
  exit 1
fi

echo "==> Fetching opportunity_sweeper/ from ${REPO_URL}@${BRANCH}"
TMP_SRC=$(mktemp -d)
trap 'rm -rf "$TMP_SRC"' EXIT
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_SRC" --quiet

mkdir -p "$APP_DIR"
cp -a "$TMP_SRC/opportunity_sweeper/." "$APP_DIR/"

echo "==> Python venv + dependencies"
cd "$APP_DIR"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { apt-get install -y python3-venv >/dev/null; python3 -m venv .venv; }
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

mkdir -p "$APP_DIR/data"
touch "$APP_DIR/.env"   # optional: add ANTHROPIC_API_KEY=... here later for smarter matching

echo "==> Running one manual sweep to seed the database"
.venv/bin/python sweep.py || echo "WARNING: initial sweep reported an error above - the hourly timer will retry"

echo "==> Installing systemd units"
cat > /etc/systemd/system/opportunity-sweeper-web.service <<UNIT
# Written by ${APP_DIR}/deploy/setup_server.sh - edit that script, not this file.
[Unit]
Description=Opportunity Sweeper web (Streamlit on 127.0.0.1:${WEB_PORT}, public at /opportunities through Caddy)
Documentation=file://${APP_DIR}/DEPLOY.md
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${APP_DIR}/.env
Environment=STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ExecStart=${APP_DIR}/.venv/bin/python -m streamlit run app.py --server.port ${WEB_PORT} --server.address 127.0.0.1 --server.baseUrlPath opportunities --server.headless true --browser.gatherUsageStats false --server.fileWatcherType none
Restart=always
RestartSec=10
TimeoutStopSec=20
MemoryMax=400M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
StandardOutput=append:${APP_DIR}/data/web.log
StandardError=append:${APP_DIR}/data/web.log

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/opportunity-sweeper-sweep.service <<UNIT
# Written by ${APP_DIR}/deploy/setup_server.sh - edit that script, not this file.
[Unit]
Description=Opportunity Sweeper hourly sweep (fetch sources, score, store)
Documentation=file://${APP_DIR}/DEPLOY.md

[Service]
Type=oneshot
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python sweep.py
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
StandardOutput=append:${APP_DIR}/data/sweep.log
StandardError=append:${APP_DIR}/data/sweep.log
UNIT

cat > /etc/systemd/system/opportunity-sweeper-sweep.timer <<UNIT
# Written by ${APP_DIR}/deploy/setup_server.sh - edit that script, not this file.
[Unit]
Description=Run Opportunity Sweeper hourly

[Timer]
OnCalendar=hourly
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now opportunity-sweeper-web.service
systemctl enable --now opportunity-sweeper-sweep.timer
systemctl restart opportunity-sweeper-web.service

echo "==> Wiring into Caddy at /opportunities"
if ! grep -q '/opportunities\*' "$CADDYFILE"; then
  cp "$CADDYFILE" "${CADDYFILE}.bak.$(date +%Y%m%d%H%M%S)"
  python3 - "$CADDYFILE" "$WEB_PORT" <<'PYEOF'
import sys
path, port = sys.argv[1], sys.argv[2]
with open(path) as f:
    text = f.read()
marker = "    handle {\n        redir * /form/ 302\n    }\n"
block = (
    "    # Opportunity Sweeper: jobs/tenders/grants matched to CV + EMCL + CGC profiles\n"
    "    handle /opportunities* {\n"
    f"        reverse_proxy 127.0.0.1:{port}\n"
    "    }\n"
)
if marker not in text:
    print("Could not find the expected catch-all block; leaving Caddyfile untouched. Add the /opportunities route manually.", file=sys.stderr)
    sys.exit(1)
text = text.replace(marker, block + marker, 1)
with open(path, "w") as f:
    f.write(text)
PYEOF
  if command -v caddy >/dev/null; then
    caddy validate --config "$CADDYFILE" --adapter caddyfile
  fi
  systemctl reload caddy
  echo "Caddy route added and reloaded."
else
  echo "Caddy route already present, skipping."
fi

echo "==> Status"
systemctl --no-pager --lines=0 status opportunity-sweeper-web.service
systemctl --no-pager --lines=0 status opportunity-sweeper-sweep.timer
echo
echo "==> Done. Public URL: https://209-38-29-33.sslip.io/opportunities/"
echo "    Logs: ${APP_DIR}/data/web.log and ${APP_DIR}/data/sweep.log"
