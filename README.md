# Class-Only Race Analyser — Mobile / GitHub / Streamlit

This is the mobile-ready Streamlit version of the supplied **ClassOnlyRaceAnalyser v4**.

It preserves the supplied France + Australia **class-only scoring model** and changes the interface/deployment packaging for easier phone use.

## What is mobile-optimised

- responsive page padding and text sizing;
- large touch-friendly Analyse / Clear / Export buttons;
- horizontally scrollable top tabs;
- **Mobile Cards** prediction view as the default;
- optional sortable desktop/table view;
- horse explanations use a mobile-friendly selector instead of a long nested tab row;
- parsed runner history uses a selector instead of one tab per horse;
- the Clear button clears the text area, active analysis **and** uploaded-file widget;
- numeric odds remain numeric and are not used in the class score.

## GitHub repository structure

Upload the **contents of this folder** to the root of one GitHub repository:

```text
your-repository/
├── .streamlit/
│   └── config.toml
├── app.py
├── race_parser.py
├── class_model.py
├── feedback_model.json
├── requirements.txt
├── METHOD.md
├── VALIDATION.md
├── VERSION.txt
├── sample_data/
└── tests/
```

`run.bat` can remain in the repository but Streamlit Community Cloud does not use it.

## Deploy on Streamlit Community Cloud

1. Create or sign in to your GitHub account.
2. Create a new repository, for example `class-only-race-analyser`.
3. Upload the contents of this package to the repository root. Make sure `.streamlit/config.toml` is included.
4. Open **Streamlit Community Cloud** at `https://share.streamlit.io` and sign in with GitHub.
5. Connect your GitHub account/repository access if prompted.
6. Click **Create app**.
7. Select the repository and branch (normally `main`).
8. Set the app entry point / main file to `app.py`.
9. Deploy.
10. Streamlit will provide a permanent `*.streamlit.app` URL.

### Python version

The project is written for modern Python. Streamlit Community Cloud currently lets you choose a supported Python version in Advanced settings. Python 3.12 is a sensible deployment choice for this package.

## Use it like a phone app

Open the deployed Streamlit URL on your phone. In your phone browser, use the browser menu and choose **Add to Home Screen** / **Install** where that option is available. This gives you a home-screen icon that opens the hosted app.

This is a **mobile web app**, not a native Android APK or iOS App Store application.

## Local Windows use

The supplied `run.bat` is retained. Double-click it to create a local virtual environment, install requirements and run the same Streamlit app on your Windows computer.

## Updating the hosted app

After deployment, edit or replace files in the GitHub repository and commit the changes. Streamlit Community Cloud tracks the repository and redeploys the app from the updated source.

## Model scope

This conversion preserves the supplied v4 model:

- France class logic;
- Australian BM / restricted-class logic;
- prize-money class proxy;
- automatic scratched-runner removal;
- numeric odds display;
- odds = 0% influence on class score.

It does **not** add the later experimental Australian fitness/form/market-movement model discussed separately.
