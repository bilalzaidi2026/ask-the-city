# population_borough and population_zip

Number of residents, from the US Census Bureau's American Community Survey (ACS)
5-year estimates. Used to turn raw counts into per-capita rates.

## Columns

| Column | Meaning |
|---|---|
| borough / zip | Join key. borough matches complaints_311.borough; zip matches complaints_311.zip and restaurant_inspections.zip. |
| population | Estimated residents. |
| acs_year | Last year of the 5-year survey the estimate comes from. |

## Traps

1. **These are estimates averaged over 5 years**, not a head count. Fine for
   comparing places, not exact to the person.
2. **Census zip areas are close to, but not exactly, postal zip codes.** A few postal
   zips (single buildings, PO boxes) have no residents or no census match.
3. **Tiny populations explode rates.** Midtown office zips have few residents and
   huge complaint counts. When ranking zips per capita, exclude zips with fewer than
   5,000 residents and say so.
4. **Residents are not everyone present.** Commuters and tourists aren't counted, so
   business districts look worse per resident. Mention this when it matters.
5. **One population figure is used for every year.** Fine for recent years; flag it
   for long trends.
6. **Check acs_year and row counts before using these tables.** If the Census API was
   down at download time, population_borough holds official 2020 Census counts
   (acs_year = 2020) and population_zip is empty. In that case, say zip-level
   per-capita figures aren't available instead of guessing.
