# Texas Audit

A Python Playwright app for auditing Texas Chicken informative websites from a friendly UI.

The first version supports:

- URL input
- UI checks
- Content checks
- Functional smoke checks
- Session-only AI provider settings
- A readable results table

## AI Provider Settings

Each QA engineer can use their own AI provider key from the sidebar.

Supported provider settings are prepared for:

- OpenAI
- Anthropic / Claude
- Google Gemini
- Azure OpenAI
- Custom API

Keys are entered in a password field and are not written to project files or reports.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Run The App

```bash
streamlit run app/main.py
```

## Run Tests

```bash
pytest
```
