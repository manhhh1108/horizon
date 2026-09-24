# Horizon X Media Tool

Desktop tool (Windows) batch-processing story scripts through ChatGPT + Grok
(logged-in browser, no API). See `docs/superpowers/specs/` for the design spec.

## Dev setup
    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.txt

## Run
    .venv/Scripts/python.exe main.py

## Tests
    .venv/Scripts/python.exe -m pytest -q
