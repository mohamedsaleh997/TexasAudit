# AGENTS.md

## Project Overview

This project is a Python-based Playwright application for running website UI, content, and functional checks from a user-friendly interface.

## Stack

- Python
- Playwright Python
- Streamlit
- Pytest

## Development Rules

- Use Python only.
- Keep Playwright logic separate from UI code.
- Keep checks small, readable, and independently testable.
- Prefer stable selectors and Playwright auto-waiting.
- Do not use fixed sleeps unless there is a clear documented reason.
- Return structured results from test services so the UI can display them cleanly.

## Structure

```text
app/
  core/
  models/
  services/
  ui/
tests/
```

## Test Types

- UI checks: visual/page structure signals such as title, headings, buttons, inputs, links, and images.
- Content checks: visible text, missing title/meta description, broken or empty content signals.
- Functional checks: basic navigation and interaction smoke checks.

