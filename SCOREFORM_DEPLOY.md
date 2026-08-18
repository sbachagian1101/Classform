# ScoreForm Predictor — Streamlit deployment

The new rule-based horse-racing app lives alongside the existing Classform app and does not replace `app.py`.

## Streamlit Community Cloud

Create a new app using:

- Repository: `sbachagian1101/Classform`
- Branch: `main`
- Main file path: `scoreform_app.py`

The existing `requirements.txt` already contains the required packages (`streamlit` and `pandas`).

## Input

Paste the complete Racing & Sports **Enhanced Form** browser text, including:

1. race header and current field table;
2. each numbered runner profile;
3. Filters/Facts;
4. historical runs and Results detail lines;
5. Head to Head where available.

## Model

Fixed weights:

- Horse Suitability 30%
- Recent Form & Fitness 20%
- Ability & Class 15%
- Jockey 10%
- Trainer 10%
- Race Setup 10%
- Head-to-Head 5%

Bookmaker/Betfair odds are displayed but have **0% model weight**.

The app exposes Prediction, Breakdown, Horse explanations, Parsed data and Method tabs. Unknown evidence remains neutral and proven negative evidence can reduce a runner's score.
