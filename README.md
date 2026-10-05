# Ask the City

Ask any question about New York City. An AI agent finds the right open data,
writes and runs its own analysis, catches its own mistakes, and answers with a
chart, the caveats, and the exact code it used.

Status: Step 0 (setup).

## Run it locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then add your keys
python hello_city.py
```
