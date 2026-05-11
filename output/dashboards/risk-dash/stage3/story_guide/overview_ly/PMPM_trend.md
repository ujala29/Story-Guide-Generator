**Widget: PMPM (lineChart)**

> 📷 *Insert: Cropped screenshot of the PMPM lineChart*

**Definition**

This chart tracks the average Per Member Per Month (PMPM) cost for the current year compared to the prior year across each calendar month, with year-over-year percentage change as the key comparison metric.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | Previous year, Current year |
| X-axis | Month |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

Compare the current year line (PMPM) against the prior year line (PMPM PY) month by month to identify whether costs are trending higher, lower, or in line with historical patterns. A widening gap where the current year line rises above the prior year signals accelerating cost growth, which may indicate increased utilization, higher acuity, or coding changes that warrant further investigation. Conversely, a narrowing gap or crossover where current year falls below prior year could reflect care management improvements, membership mix shifts, or seasonal timing differences. Use the YoY % change to quickly flag months exceeding an acceptable threshold and prioritize those periods for root cause analysis.

**Technical specification**

**DAX measure(s):**

PMPM PY = CALCULATE([PMPM], SAMEPERIODLASTYEAR('date'[month_of_date]))

PMPM = DIVIDE(SUM(attribution[ytd_visit_amount]),Sum(attribution[ytd_member_count]))

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| attribution | ytd_member_count | Patient/member count — used as denominator |
| attribution | ytd_visit_amount | Numerator — total YTD medical cost |
| date | month_of_year | Time intelligence — drives YoY/MoM comparison |