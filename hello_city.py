"""
Step 0 check: can we talk to both services this project depends on?

1. Claude (the agent's brain)
2. NYC Open Data (the city's data)

Run:  python hello_city.py
"""
import os

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

# Read ANTHROPIC_API_KEY, NYC_APP_TOKEN and CLAUDE_MODEL from the .env file
load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# 311 Service Requests from 2020 to Present. Every dataset on the portal has an ID like this.
DATASET_311 = "erm2-nwe9"


def check_nyc_data():
    """Fetch the 3 most recent 311 complaints."""
    url = f"https://data.cityofnewyork.us/resource/{DATASET_311}.json"
    params = {
        "$select": "created_date, complaint_type, borough",
        "$order": "created_date DESC",
        "$limit": 3,
    }
    headers = {"X-App-Token": os.environ["NYC_APP_TOKEN"]}
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()  # stop with a clear error if the request failed
    return response.json()


def check_claude(rows):
    """Ask Claude to describe the rows in one sentence."""
    client = Anthropic()  # picks up ANTHROPIC_API_KEY automatically
    message = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"In one sentence, summarize these NYC 311 complaints: {rows}",
        }],
    )
    return message.content[0].text


if __name__ == "__main__":
    print("1. Asking NYC Open Data for the latest 311 complaints...")
    rows = check_nyc_data()
    for row in rows:
        print(f"   {row['created_date'][:16]}  {row.get('borough', '?'):<13}  {row['complaint_type']}")

    print(f"\n2. Asking Claude ({MODEL}) to summarize them...")
    print("  ", check_claude(rows))

    print("\nBoth connections work. Step 0 done.")
