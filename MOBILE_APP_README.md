# Classform Mobile Upgrade

This package replaces the desktop-style Streamlit interface with a phone-first Classform interface based on the supplied mobile design handoff.

## What stays unchanged

The prediction engine remains in the existing repository files:

- `class_model.py`
- `race_parser.py`
- `feedback_model.json`

The new `app.py` imports and uses those files directly, so the class scoring method is not replaced by UI code.

## Mobile flow

1. Onboarding
2. Today / paste or upload a race
3. Race card ordered by model or market
4. Why this score
5. Full horse form history
6. Save a horse to My Picks
7. Model record / validation snapshot

## Apply it to the existing GitHub repository

Copy these files into the root of `sbachagian1101/Classform`:

- `app.py` (replace the current `app.py`)
- `.streamlit/config.toml`

Keep all existing model/parser files and `requirements.txt`.

## Run on Windows

Your existing `run.bat` can continue to launch `app.py`. If it explicitly points to another filename, change the Streamlit command to:

```bat
streamlit run app.py
```

## Deploy for phone use

Deploy the GitHub repository on Streamlit Community Cloud with `app.py` as the entry point. Open the resulting URL on Android or iPhone.

For an app-like home-screen icon:

- Android / Chrome: menu → **Add to Home screen**
- iPhone / Safari: Share → **Add to Home Screen**

This gives a full-screen phone-first web-app experience while keeping the Python model on Streamlit.

## About APK / App Store packaging

This package is the mobile web-app version. A separate Android APK or iOS App Store binary would require a native wrapper (for example Capacitor) around the deployed URL, plus Android/iOS signing and store configuration. The prediction engine can remain hosted in Streamlit for that wrapper.
