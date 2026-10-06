# restaurant_inspections

Health inspections of NYC restaurants by the Department of Health (DOHMH).
Source: NYC Open Data, "DOHMH New York City Restaurant Inspection Results" (43nn-pn8j).

## The most important fact

**One row per violation, not per inspection or per restaurant.** An inspection with
4 violations appears as 4 rows. To count inspections use
`count(DISTINCT (restaurant_id, inspection_date))`. To count restaurants use
`count(DISTINCT restaurant_id)`.

## Columns

| Column | Meaning |
|---|---|
| restaurant_id | The city's ID for the restaurant (called CAMIS in city docs). |
| restaurant_name | Trading name. The same name can belong to many locations. |
| borough, zip, building, street | Address. borough uses the same spelling as complaints_311. |
| cuisine | e.g. 'Chinese', 'Pizza', 'Coffee/Tea'. |
| inspection_date | Date of inspection. NULL means a new restaurant not yet inspected. |
| inspection_type | e.g. 'Cycle Inspection / Initial Inspection', 'Cycle Inspection / Re-inspection'. |
| action | What the city did, e.g. violations cited, establishment closed. |
| violation_code, violation_description | The specific violation. NULL if none. |
| critical_flag | 'Critical' violations are more likely to make people sick. |
| score | Points for violations. **Lower is better.** |
| grade | A, B or C. Also N (not yet graded), Z (grade pending), P (pending after reopening). NULL if no grade for that inspection. |
| grade_date | When that grade was given. |
| latitude, longitude | Location. NULL if unknown. |
| neighborhood_code | City neighborhood code (NTA). |

## Traps

1. **Count the right unit** (see the top of this guide).
2. **Only some inspections produce a grade.** For "what grade does a restaurant have",
   use its most recent row with grade IN ('A','B','C').
3. **Scores: 0 to 13 is an A, 14 to 27 a B, 28 or more a C** on graded inspections.
4. **The dataset covers restaurants that are currently open.** Closed restaurants drop
   out, so long-term trends are biased toward survivors. Say so for trend questions.
5. **Most rows are recent.** A few go back to 2007, but coverage of older years is
   thin. Count rows by year before answering anything about older periods.
6. **Names are not unique.** Chains have many locations. Group by restaurant_id, and
   show the address when naming a specific restaurant.
7. **Naming individual businesses.** Inspection results are public, but present them
   factually with the date, never as a judgment beyond what the data shows.
