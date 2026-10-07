"""
Step 1a: download city data into data/raw/.

    python data/download.py --sample   # last 3 months of 311 (a few minutes, for testing)
    python data/download.py            # 311 from Jan 2021 on (an hour or more, run once)

Safe to re-run. Finished months are skipped, so an interrupted download
picks up where it stopped.

What it downloads:
  311 complaints        -> data/raw/311/YYYY-MM.parquet   (one file per month)
  Restaurant inspections -> data/raw/restaurants.parquet
  Population (Census)    -> data/raw/population_zip.csv, population_borough.csv
"""
import argparse
import csv
import io
import os
import time
from datetime import date
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

load_dotenv()

RAW = Path(__file__).parent / "raw"
NYC_API = "https://data.cityofnewyork.us/resource"
HEADERS = {"X-App-Token": os.environ["NYC_APP_TOKEN"]}
PAGE_SIZE = 50_000  # rows per request; the API is happiest in chunks this size

# Only the columns we need. Fewer columns = faster downloads and a smaller database.
COLUMNS_311 = [
    "unique_key", "created_date", "closed_date", "agency", "complaint_type",
    "descriptor", "location_type", "incident_zip", "borough",
    "community_board", "status", "latitude", "longitude",
]
COLUMNS_RESTAURANTS = [
    "camis", "dba", "boro", "building", "street", "zipcode",
    "cuisine_description", "inspection_date", "action", "violation_code",
    "violation_description", "critical_flag", "score", "grade", "grade_date",
    "inspection_type", "latitude", "longitude", "nta",
]
DATASET_311 = "erm2-nwe9"          # 311 Service Requests from 2020 to Present
DATASET_RESTAURANTS = "43nn-pn8j"  # DOHMH Restaurant Inspection Results

# NYC's five boroughs are five counties in New York State (state code 36).
BOROUGH_COUNTIES = {
    "005": "BRONX", "047": "BROOKLYN", "061": "MANHATTAN",
    "081": "QUEENS", "085": "STATEN ISLAND",
}


# ---------------------------------------------------------------- helpers

def get_with_retry(url, params=None, headers=None, attempts=5):
    """GET a URL, waiting and retrying if the server is busy or hiccups."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=120)
            busy = response.status_code in (429, 500, 502, 503, 504)
        except (requests.ConnectionError, requests.Timeout) as err:
            busy, response = True, err
        if not busy:
            response.raise_for_status()  # a real error (like 404): stop right away
            return response
        if attempt == attempts:
            raise SystemExit(f"Gave up on {url} after {attempts} tries.")
        wait = 5 * attempt
        print(f"    server busy; retrying in {wait}s...")
        time.sleep(wait)


def download_pages(dataset_id, columns, where, part_dir, order=":id"):
    """Download every row matching `where`, PAGE_SIZE rows at a time, as CSV parts.

    `order` must give every row a fixed position, or pages can overlap or skip rows.
    """
    part_dir.mkdir(parents=True, exist_ok=True)
    for old in part_dir.glob("*.csv"):  # clear leftovers from an interrupted run
        old.unlink()

    offset, page, total = 0, 0, 0
    while True:
        params = {
            "$select": ", ".join(columns),
            "$order": order,
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        if where:
            params["$where"] = where
        text = get_with_retry(f"{NYC_API}/{dataset_id}.csv", params, HEADERS).text

        # Count rows with a real CSV parser: text fields can contain line breaks.
        rows = sum(1 for _ in csv.reader(io.StringIO(text))) - 1  # minus the header
        if rows <= 0:
            break
        (part_dir / f"part_{page:04d}.csv").write_text(text, encoding="utf-8")
        total += rows
        print(f"    {total:,} rows so far")
        if rows < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        page += 1
    return total


def csv_parts_to_parquet(part_dir, out_file):
    """Squash the CSV parts into one compressed Parquet file, then delete the parts."""
    parts = sorted(part_dir.glob("*.csv"))
    if not parts:
        return
    con = duckdb.connect()
    con.execute(
        f"""COPY (SELECT * FROM read_csv({[str(p) for p in parts]},
                                       all_varchar = true, header = true))
            TO '{out_file}' (FORMAT parquet)"""
    )
    for part in parts:
        part.unlink()


def month_starts(start, end):
    """Yield the first day of every month from start up to and including end's month."""
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)


# ---------------------------------------------------------------- datasets

def download_311(start):
    print(f"\n311 complaints, {start:%b %Y} to now")
    folder = RAW / "311"
    folder.mkdir(parents=True, exist_ok=True)
    today = date.today()
    this_month = date(today.year, today.month, 1)

    for month in month_starts(start, today):
        out_file = folder / f"{month:%Y-%m}.parquet"
        # A past month never changes much, so skip it once downloaded.
        # The current month is still filling up, so always fetch it fresh.
        if out_file.exists() and month < this_month:
            print(f"  {month:%Y-%m}: already downloaded, skipping")
            continue
        next_month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
        where = (f"created_date >= '{month}T00:00:00' "
                 f"AND created_date < '{next_month}T00:00:00'")
        print(f"  {month:%Y-%m}:")
        # Sort by date, then ID. Sorting a date-filtered query by the internal
        # row ID (:id) took 75 seconds per request in testing; this takes 1 to 10.
        rows = download_pages(DATASET_311, COLUMNS_311, where, folder / "_parts",
                              order="created_date, unique_key")
        csv_parts_to_parquet(folder / "_parts", out_file)
        print(f"  {month:%Y-%m}: done, {rows:,} rows")


def download_restaurants():
    print("\nRestaurant inspections (full snapshot)")
    rows = download_pages(DATASET_RESTAURANTS, COLUMNS_RESTAURANTS, None,
                          RAW / "_restaurant_parts")
    csv_parts_to_parquet(RAW / "_restaurant_parts", RAW / "restaurants.parquet")
    print(f"  done, {rows:,} rows")


def census(year, geography, extra=""):
    """Ask the Census Bureau's ACS 5-year survey for total population (B01003_001E)."""
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": "B01003_001E", "for": geography}
    if extra:
        params["in"] = extra
    # The Census API now requires a free key: https://api.census.gov/data/key_signup.html
    if os.getenv("CENSUS_API_KEY"):
        params["key"] = os.environ["CENSUS_API_KEY"]
    response = get_with_retry(url, params)
    try:
        return response.json()  # list of rows; the first row is the header
    except ValueError:
        # Not data. Show what came back, so the problem is visible instead of a riddle.
        raise RuntimeError(f"Census sent back status {response.status_code}, not data: "
                           f"{response.text[:200]!r}")


# Official 2020 Census counts per borough. Used only if the Census API is unreachable,
# so per-capita answers still work. (Source: 2020 Decennial Census, table P1.)
BOROUGH_POPULATION_2020 = {
    "BRONX": 1_472_654, "BROOKLYN": 2_736_074, "MANHATTAN": 1_694_251,
    "QUEENS": 2_405_464, "STATEN ISLAND": 495_747,
}


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def download_population():
    print("\nPopulation (US Census, American Community Survey 5-year estimates)")
    # Try the newest survey first; fall back a year if it isn't published yet.
    for year in (2024, 2023):
        try:
            boroughs = census(year, "county:" + ",".join(BOROUGH_COUNTIES), "state:36")
            zips = census(year, "zip code tabulation area:*")
        except (requests.HTTPError, RuntimeError, SystemExit) as err:
            print(f"  {year} survey failed: {err}")
            continue
        write_csv(RAW / "population_borough.csv", ["borough", "population", "acs_year"],
                  [[BOROUGH_COUNTIES[county], pop, year] for pop, _state, county in boroughs[1:]])
        write_csv(RAW / "population_zip.csv", ["zip", "population", "acs_year"],
                  [[zcta, pop, year] for pop, zcta in zips[1:]
                   if zcta.startswith(("10", "11"))])  # NYC zips start 100-104 or 110-116
        print(f"  done ({year} survey)")
        return

    # Census unreachable: keep going with official 2020 borough counts, and no zip data.
    if not os.getenv("CENSUS_API_KEY"):
        print("  No CENSUS_API_KEY in .env. Get a free key at "
              "https://api.census.gov/data/key_signup.html")
    print("  Census API unavailable. Using official 2020 Census counts for boroughs;")
    print("  zip-level population is skipped. Re-run later with: "
          "python data/download.py --population-only")
    write_csv(RAW / "population_borough.csv", ["borough", "population", "acs_year"],
              [[b, pop, 2020] for b, pop in BOROUGH_POPULATION_2020.items()])
    write_csv(RAW / "population_zip.csv", ["zip", "population", "acs_year"], [])


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download NYC data for Ask the City")
    parser.add_argument("--sample", action="store_true",
                        help="only the last 3 months of 311 (fast, for testing)")
    parser.add_argument("--start", default="2021-01",
                        help="first month of 311 data to fetch, as YYYY-MM")
    parser.add_argument("--population-only", action="store_true",
                        help="only re-fetch population (e.g. after a Census outage)")
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    if args.sample:
        today = date.today()
        months_back = today.month - 3
        start = date(today.year + (months_back - 1) // 12, (months_back - 1) % 12 + 1, 1)
    else:
        start = date.fromisoformat(args.start + "-01")

    # Most important first: if something fails late, the core data is already saved.
    if not args.population_only:
        download_311(start)
        download_restaurants()
    download_population()
    print("\nAll downloads finished. Next: python data/build_db.py")
