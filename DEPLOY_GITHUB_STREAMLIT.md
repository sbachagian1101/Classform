# Quick Deployment Guide

## 1 — Create the GitHub repository

1. Sign in to GitHub.
2. Create a **New repository**.
3. Give it a name such as `class-only-race-analyser`.
4. Upload every file and folder from this package to the repository root.
5. Confirm that these are visible in GitHub:
   - `app.py`
   - `race_parser.py`
   - `class_model.py`
   - `feedback_model.json`
   - `requirements.txt`
   - `.streamlit/config.toml`

## 2 — Deploy with Streamlit

1. Go to `https://share.streamlit.io`.
2. Continue with GitHub.
3. Connect the GitHub repository if required.
4. Click **Create app**.
5. Select your repository.
6. Branch: normally `main`.
7. Main file path: `app.py`.
8. In Advanced settings, choose a supported Python version if needed.
9. Click **Deploy**.

## 3 — Open on mobile

1. Open the generated `https://<your-app-name>.streamlit.app` URL on your phone.
2. Use the browser menu.
3. Choose **Add to Home Screen** or **Install** when available.
4. Launch the app from the new home-screen icon.

## 4 — Update later

Edit the source files in GitHub and commit. The hosted Streamlit app will update from the repository.
