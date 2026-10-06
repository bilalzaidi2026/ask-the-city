"""
Step 1c: look at the data yourself before the agent does.

    python data/check_db.py

Runs a few questions in plain SQL. These are the same kinds of queries
the agent will write on its own in Step 2.
"""
from pathlib import Path

import duckdb

DB_FILE = Path(__file__).parent / "city.duckdb"

QUESTIONS = {
    "What's in the database?": """
        SELECT table_name, row_count, earliest, latest
        FROM table_catalog
    """,

    "Top 10 complaint types in the most recent full month": """
        SELECT complaint_type, count(*) AS complaints
        FROM complaints_311
        WHERE date_trunc('month', created_at) =
              date_trunc('month', (SELECT max(created_at) FROM complaints_311)) - INTERVAL 1 MONTH
        GROUP BY complaint_type
        ORDER BY complaints DESC
        LIMIT 10
    """,

    # Raw counts mostly track how many people live somewhere.
    # Dividing by population makes boroughs comparable.
    "Rat complaints by borough: raw count vs. per 10,000 residents": """
        SELECT c.borough,
               count(*)                                   AS complaints,
               p.population,
               round(count(*) * 10000.0 / p.population, 1) AS per_10k_residents
        FROM complaints_311 c
        JOIN population_borough p USING (borough)
        WHERE c.complaint_type = 'Rodent'
        GROUP BY c.borough, p.population
        ORDER BY per_10k_residents DESC
    """,

    # The table has one row per violation, so count each restaurant once,
    # using its most recent grade.
    "Current letter grades across all restaurants": """
        WITH latest AS (
            SELECT restaurant_id, grade,
                   row_number() OVER (PARTITION BY restaurant_id
                                      ORDER BY grade_date DESC) AS rn
            FROM restaurant_inspections
            WHERE grade IN ('A', 'B', 'C') AND grade_date IS NOT NULL
        )
        SELECT grade, count(*) AS restaurants,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS percent
        FROM latest
        WHERE rn = 1
        GROUP BY grade
        ORDER BY grade
    """,

    "Data quality: how many 311 rows are missing a location?": """
        SELECT round(100.0 * count(*) FILTER (WHERE latitude IS NULL) / count(*), 1)
                   AS pct_missing_coordinates,
               round(100.0 * count(*) FILTER (WHERE borough IS NULL) / count(*), 1)
                   AS pct_missing_borough,
               round(100.0 * count(*) FILTER (WHERE zip IS NULL) / count(*), 1)
                   AS pct_missing_zip
        FROM complaints_311
    """,
}

if __name__ == "__main__":
    # read_only=True: we look, we never change. The agent will connect the same way.
    con = duckdb.connect(str(DB_FILE), read_only=True)
    for title, sql in QUESTIONS.items():
        print(f"\n=== {title}")
        print(con.sql(sql))
    con.close()
