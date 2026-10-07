# Ask the City

Ask any question about New York City. An AI agent finds the right open data,
writes and runs its own analysis, catches its own mistakes, and answers with a
chart, the caveats, and the exact code it used.

Status: Step 3 (checker and tests).

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
python ask.py "Which borough has the most rat complaints per resident?"
```

## Run the tests

```bash
python tests/run_tests.py                # all test questions (about $0.50)
python tests/run_tests.py --no-checker   # same, without the checker, to compare
```

## Check consistency

```bash
python tests/consistency.py      # asks 3 questions 3 times each; flags answers that flip
```
