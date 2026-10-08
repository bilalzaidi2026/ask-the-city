# Ask the City

Ask any question about New York City. An AI agent finds the right open data,
writes and runs its own analysis, catches its own mistakes, and answers with a
chart, the caveats, and the exact code it used.

Status: Step 6 (graded evaluations).

## Run it locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then add your keys
python hello_city.py
```

## Get the city data

```bash
python data/download.py --sample   # quick test: last 3 months of 311
python data/build_db.py            # builds data/city.duckdb
python data/check_db.py            # a first look at the data
```

For the full history, run `python data/download.py` (no --sample) once. It takes a while.

## Ask a question

```bash
python ask.py "How have heat complaints changed each winter since 2021?"
```

The answer prints in the terminal and opens as a web page with its charts
(saved to `answers/latest.html`). Add `--no-open` to skip opening the browser.

## Run the web app

```bash
python -m uvicorn web.server:app --port 8000
```

Then open http://localhost:8000. Ask a question and watch each step stream in live.

## Run the tests

```bash
python tests/run_tests.py                # all test questions (about $0.50)
python tests/run_tests.py --no-checker   # same, without the checker, to compare
```

## Check consistency

```bash
python tests/consistency.py      # asks 3 questions 3 times each; flags answers that flip
```

## Graded evaluation

```bash
python tests/evaluate.py      # 20 trap questions, each scored 1-5 by an AI grader (about $1.60)
```

A separate grader scores every answer on four dimensions (correct, trap, honest, clear),
checking numbers against the agent's actual queries. Results go to `tests/results/` and to
`web/scorecard.json`, shown publicly at http://localhost:8000/scorecard.
