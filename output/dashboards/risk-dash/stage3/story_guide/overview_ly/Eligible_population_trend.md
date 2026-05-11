**Widget: Eligible population (lineChart)**

> 📷 *Insert: Cropped screenshot of the Eligible population lineChart*

**Definition**

This chart tracks the monthly count of members eligible for risk adjustment in the current year compared to the same months in the previous year, enabling year-over-year trend analysis.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | Previous year, Current year |
| X-axis | Month |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

Compare the current-year line against the previous-year line each month to identify whether the eligible population is growing, shrinking, or holding steady relative to the prior period. A consistently higher current-year line indicates membership growth, while a lower line signals attrition that may reduce the total risk adjustment opportunity. Sudden divergences mid-year — such as a sharp drop or spike in the current-year line — can indicate plan enrollment changes, eligibility policy updates, or data loading issues that warrant investigation. Use the YoY % change to quickly quantify the magnitude of these shifts and prioritize outreach or operational responses accordingly.

**Technical specification**

**DAX measure(s):**

Eligible population PY = CALCULATE(sum(risk_core[patient_count]),SAMEPERIODLASTYEAR('date'[month_of_date]))

Eligible population trend = SUM(risk_core[patient_count])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | patient_count | Patient/member count — used as denominator |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| date | month_of_year | Time intelligence — drives YoY/MoM comparison |