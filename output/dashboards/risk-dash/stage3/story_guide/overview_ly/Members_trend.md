**Widget: Members (lineChart)**

> 📷 *Insert: Cropped screenshot of the Members lineChart*

**Definition**

This chart tracks the monthly member count for the current year compared to the same months in the prior year, enabling year-over-year trend analysis of membership volume.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | Previous year, Current year |
| X-axis | Month |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

Compare the current year line against the prior year line each month to identify whether membership is growing, declining, or holding steady relative to the same period last year. A widening gap where the current year line rises above the prior year indicates membership growth, while a current year line trending below the prior year signals attrition or enrollment challenges that may affect risk adjustment revenue. Pay close attention to the YoY % change to quantify the magnitude of these shifts, particularly around open enrollment periods or contract changes where sudden inflections are common. Significant membership drops should prompt investigation into disenrollment drivers, plan changes, or data completeness issues, as member count directly impacts the total risk score pool and expected revenue.

**Technical specification**

**DAX measure(s):**

#Members PY = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))

#Members = SUM(attribution[member_count])+0
formatString: #,0
lineageTag: d67d72a2-2db7-4495-b98f-0d57ba71fa97

#Members trend = SUM(attribution[member_count])
formatString: #,0
lineageTag: 9d17c184-8b39-4e94-a2fe-e31935811bd0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| attribution | member_count | Patient/member count — used as denominator |
| date | month_of_year | Time intelligence — drives YoY/MoM comparison |