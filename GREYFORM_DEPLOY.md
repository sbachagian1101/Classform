# Greyform — Greyhound Predictor

Greyform is a separate Streamlit app stored in the same GitHub repository as Classform.

## Streamlit Community Cloud deployment

Create a second app from the existing repository:

- Repository: `sbachagian1101/Classform`
- Branch: `main`
- Entrypoint file: `greyhound_app.py`
- Suggested app URL/subdomain: `greyformsuraj` or similar if available

Do **not** change the existing Classform deployment, whose entrypoint remains `app.py`.

## Workflow

1. Open a Racing & Sports greyhound race page.
2. Copy the complete race page as markdown/text.
3. Paste it into Greyform.
4. Choose the market/odds weight (0–40%, default 35%).
5. Press **Parse & Predict**.
6. Verify the parsed field and scratchings.
7. Review Final, Form, Market, Factors, explanations and runner history.

## Model

Form score weights:

- Recent finishing performance: 25%
- Class/grade: 18%
- Course record: 12%
- Distance record: 12%
- Box suitability: 10%
- Career consistency: 8%
- Sectional speed: 8%
- Recent trend: 7%

Current R&S odds are converted to normalised market probabilities and blended with Form using the selected market weight, capped at 40%.

Top-2 and Top-3 probabilities are estimated by race simulation. Explicit Racing & Sports scratchings are excluded automatically.
