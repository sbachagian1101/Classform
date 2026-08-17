# Soccerform deployment

Deploy as a separate Streamlit Community Cloud app from the existing repository.

- Repository: `sbachagian1101/Classform`
- Branch: `main`
- Main file path: `soccer_app.py`
- Suggested app name: `soccerformsuraj`

Workflow:
1. Paste/upload the complete FootyStats page for the **home team**.
2. Paste/upload the complete FootyStats page for the **away team**.
3. Click **Parse & Predict**.
4. Review 1X2, BTTS and Over/Under 2.5 probabilities, likely scores, team indices and explanations.

The model does not use bookmaker odds. It uses FootyStats venue splits, goals, xG/xGA, last-10 overall and relevant-venue form, BTTS/O2.5 tendencies, plus low-weight H2H.