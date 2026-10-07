# Standard definitions

Use these whenever a question uses one of these everyday words, so the same question
gets the same answer every time. If you use something else, say why.

| Everyday term | Standard definition (complaints_311) |
|---|---|
| Rat complaints | complaint_type = 'Rodent'. Also report descriptor = 'Rat Sighting' when the question is specifically about rats. |
| Noise complaints | complaint_type IN ('Noise - Residential', 'Noise - Street/Sidewalk', 'Noise - Commercial', 'Noise - Vehicle', 'Noise - Park', 'Noise - Helicopter', 'Noise - House of Worship', 'Noise') |
| Heat complaints | complaint_type = 'HEAT/HOT WATER' |
| Street cleanliness | complaint_type IN ('Dirty Condition', 'Missed Collection', 'Litter Basket Complaint') |
| Parking problems | complaint_type IN ('Illegal Parking', 'Blocked Driveway') |
| Disorder complaints (the closest proxy for "safety") | agency = 'NYPD' AND complaint_type IN ('Drug Activity', 'Drinking', 'Disorderly Youth', 'Illegal Fireworks', 'Panhandling', 'Urinating in Public', 'Encampment') |

| Everyday term | Standard definition (restaurant_inspections) |
|---|---|
| A restaurant's current grade | Its most recent row with grade IN ('A','B','C'), ordered by grade_date |
| Number of inspections | count(DISTINCT (restaurant_id, inspection_date)) |
| Last month | The last full calendar month, never the current partial one |

## Rates per resident

Default to the **last 12 full months** and report "per 10,000 residents per year". If you use
a longer period, divide by the number of years and label it "per year". Never present a total
over several years as if it were a yearly rate.

## Safety, crime and danger

None of these tables holds crime data. 311 complaints are reports to the city, and serious
crime goes to 911. For "dangerous" or "safe" questions: say plainly that the data can't
measure safety, then offer the disorder-complaints proxy above, per 10,000 residents.

## When a definition decides the answer

If another reasonable definition would change the conclusion (for example, rats only versus
all rodents), check it with one extra query and say so in one sentence. Don't present a
close result as a clear winner.
