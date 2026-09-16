# Opportunity Sweeper — droplet deployment

Unlike the other apps in this repo (deployed to Streamlit Community Cloud),
this one needs a real hourly background job, so it belongs on the droplet
alongside your other always-on apps.

## Layout

```
opportunity_sweeper/
├── app.py            # Streamlit table UI (reads the DB, never fetches)
├── sweep.py          # fetches sources, scores, stores — run this hourly
├── sources.py        # data source adapters (edit to add/remove sources)
├── matcher.py         # keyword scoring + optional Claude-based scoring
├── profile.yaml       # YOUR eligibility criteria — edit this first
├── db.py             # SQLite storage
├── data/opportunities.db  # created on first run, not committed to git
└── requirements.txt
```

## First-time setup on the droplet

```bash
cd /path/to/Classform/opportunity_sweeper
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Edit `profile.yaml` with your real CV / company / NGO details — the
keywords shipped in this repo were only a starting guess. Add or remove
entries under `keywords`, `geography`, and `opportunity_types` per persona.

Run one sweep manually to populate the database and check for errors:

```bash
venv/bin/python sweep.py
```

## Hourly cron job

```bash
crontab -e
```

Add:

```
0 * * * * cd /path/to/Classform/opportunity_sweeper && venv/bin/python sweep.py >> sweep.log 2>&1
```

## Serving the table

Run alongside your other droplet apps, on its own port, behind whatever
reverse proxy (nginx/caddy) you already use for the odds tracker:

```bash
venv/bin/streamlit run app.py --server.port 8502 --server.address 0.0.0.0
```

Or as a systemd service (`/etc/systemd/system/opportunity-sweeper.service`):

```ini
[Unit]
Description=Opportunity Sweeper Streamlit app
After=network.target

[Service]
WorkingDirectory=/path/to/Classform/opportunity_sweeper
ExecStart=/path/to/Classform/opportunity_sweeper/venv/bin/streamlit run app.py --server.port 8502 --server.address 0.0.0.0
Restart=on-failure
User=your-user

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now opportunity-sweeper
```

## Optional: smarter matching with Claude

The keyword matcher in `matcher.py` works with no extra setup. If you set
an `ANTHROPIC_API_KEY` environment variable (and `pip install anthropic`),
`sweep.py` will also ask Claude to judge relevance for each item and take
whichever score (keyword or Claude) is higher — this catches matches that
don't share exact keywords but are clearly relevant.

## Known source gaps

Two commonly-useful sources were left out because no compliant free API
exists (see `sources.py` docstring for details):

- **UNGM** (UN tenders) — no official public API; subscribe to UNGM's own
  free email alerts instead.
- **Devex** — jobs/funding search requires a paid membership for
  programmatic access.

If you have API access to LinkedIn, Indeed, or a paid Devex membership,
add a new adapter function to `sources.py` and append it to `ALL_SOURCES`.

## Tuning

- `profile.yaml` → `min_match_score` controls the default cutoff (the
  Streamlit sidebar lets you override it per session).
- The ReliefWeb API requires a pre-approved `appname` for sustained use as
  of Nov 2025 — request one at apidoc.reliefweb.int if the default gets
  rate-limited.
