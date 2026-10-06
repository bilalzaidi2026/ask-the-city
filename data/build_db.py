"""
Step 1b: clean the downloaded files and load them into one database, data/city.duckdb.

    python data/build_db.py

Rebuilds every table from data/raw/ each time, so it's always safe to re-run.
The agent will only ever read this database; it never touches the raw files.
"""
from datetime import datetime
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
RAW = HERE / "raw"
DB_FILE = HERE / "city.duckdb"


def build(con):
    # ------------------------------------------------------------ 311 complaints
    # Everything arrives as text. Here we give each column a real type and fix
    # the known messes, so the agent doesn't have to rediscover them every time.
    print("Building complaints_311...")
    con.execute(f"""
        CREATE OR REPLACE TABLE complaints_311 AS
        SELECT
            CAST(unique_key AS BIGINT)            AS unique_key,
            CAST(created_date AS TIMESTAMP)       AS created_at,
            TRY_CAST(closed_date AS TIMESTAMP)    AS closed_at,
            agency,
            complaint_type,
            descriptor,
            location_type,
            -- Zips arrive as '10027', '10027-1234', 'N/A' or blank. Keep 5 digits or nothing.
            CASE WHEN regexp_matches(incident_zip, '^[0-9]{{5}}')
                 THEN left(incident_zip, 5) END   AS zip,
            -- 'Unspecified' means unknown. Make that explicit as NULL.
            NULLIF(upper(trim(borough)), 'UNSPECIFIED') AS borough,
            community_board,
            status,
            TRY_CAST(latitude AS DOUBLE)          AS latitude,
            TRY_CAST(longitude AS DOUBLE)         AS longitude
        FROM read_parquet('{RAW / "311" / "*.parquet"}')
        -- The same complaint can appear twice if months were re-downloaded. Keep one.
        QUALIFY row_number() OVER (PARTITION BY unique_key ORDER BY created_date) = 1
    """)

    # ------------------------------------------------------------ restaurants
    print("Building restaurant_inspections...")
    con.execute(f"""
        CREATE OR REPLACE TABLE restaurant_inspections AS
        SELECT
            camis                                  AS restaurant_id,
            dba                                    AS restaurant_name,
            NULLIF(upper(trim(boro)), '0')         AS borough,
            building,
            street,
            left(zipcode, 5)                       AS zip,
            cuisine_description                    AS cuisine,
            -- 1900-01-01 is the city's code for "new restaurant, not inspected yet".
            CASE WHEN inspection_date LIKE '1900-01-01%' THEN NULL
                 ELSE CAST(CAST(inspection_date AS TIMESTAMP) AS DATE) END AS inspection_date,
            inspection_type,
            action,
            violation_code,
            violation_description,
            critical_flag,
            TRY_CAST(score AS INTEGER)             AS score,
            NULLIF(trim(grade), '')                AS grade,
            CAST(TRY_CAST(grade_date AS TIMESTAMP) AS DATE) AS grade_date,
            -- Missing locations arrive as 0, which would put restaurants off the coast of Africa.
            NULLIF(TRY_CAST(latitude AS DOUBLE), 0)  AS latitude,
            NULLIF(TRY_CAST(longitude AS DOUBLE), 0) AS longitude,
            nta                                    AS neighborhood_code
        FROM read_parquet('{RAW / "restaurants.parquet"}')
    """)

    # ------------------------------------------------------------ population
    print("Building population tables...")
    for table, key in (("population_borough", "borough"), ("population_zip", "zip")):
        con.execute(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT CAST({key} AS VARCHAR)     AS {key},
                   CAST(population AS INTEGER) AS population,
                   CAST(acs_year AS INTEGER)   AS acs_year
            FROM read_csv('{RAW / (table + ".csv")}', all_varchar = true, header = true)
        """)
    # Keep only zips that actually show up in 311 data, i.e. NYC zips.
    con.execute("""
        DELETE FROM population_zip
        WHERE zip NOT IN (SELECT DISTINCT zip FROM complaints_311 WHERE zip IS NOT NULL)
    """)

    # ------------------------------------------------------------ catalog
    # One row per table: what it holds, how many rows, and what dates it covers.
    # The agent reads this first, so it knows how fresh each dataset is.
    print("Building table_catalog...")
    loaded_at = datetime.now().isoformat(timespec="seconds")
    con.execute(f"""
        CREATE OR REPLACE TABLE table_catalog AS
        SELECT 'complaints_311' AS table_name,
               '311 service requests: one row per complaint' AS description,
               count(*) AS row_count,
               CAST(min(created_at) AS DATE) AS earliest,
               CAST(max(created_at) AS DATE) AS latest,
               'https://data.cityofnewyork.us/d/erm2-nwe9' AS source,
               '{loaded_at}' AS loaded_at
        FROM complaints_311
        UNION ALL
        SELECT 'restaurant_inspections',
               'Restaurant inspections: one row per violation, not per inspection',
               count(*), min(inspection_date), max(inspection_date),
               'https://data.cityofnewyork.us/d/43nn-pn8j', '{loaded_at}'
        FROM restaurant_inspections
        UNION ALL
        SELECT 'population_borough', 'Residents per borough (Census ACS 5-year)',
               count(*), NULL, NULL, 'https://api.census.gov', '{loaded_at}'
        FROM population_borough
        UNION ALL
        SELECT 'population_zip', 'Residents per zip code (Census ACS 5-year)',
               count(*), NULL, NULL, 'https://api.census.gov', '{loaded_at}'
        FROM population_zip
    """)


if __name__ == "__main__":
    con = duckdb.connect(str(DB_FILE))
    build(con)
    print()
    print(con.sql("SELECT table_name, row_count, earliest, latest FROM table_catalog"))
    con.close()
    size_mb = DB_FILE.stat().st_size / 1_000_000
    print(f"Database ready: {DB_FILE} ({size_mb:,.0f} MB)")
    print("Next: python data/check_db.py")
