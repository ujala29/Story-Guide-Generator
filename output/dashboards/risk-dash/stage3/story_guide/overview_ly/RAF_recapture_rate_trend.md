**Widget: RAF recapture rate (lineChart)**

> 📷 *Insert: Cropped screenshot of the RAF recapture rate lineChart*

**Definition**

This chart tracks the monthly RAF recapture rate for the current year compared to the same months in the prior year, revealing whether the organization is improving its ability to re-document chronic conditions in the current coding cycle.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | Previous year, Current year |
| X-axis | Month |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

Each line represents the percentage of previously documented HCC conditions that have been successfully recaptured through a qualifying encounter in the given month; a rising current-year line indicates improving recapture performance over the coding year. When the current-year line consistently tracks above the prior-year line, the organization is outperforming its historical baseline, while a persistent gap below the prior year signals a risk of revenue leakage and incomplete risk score submission. Pay close attention to mid-year divergence, as a widening negative gap in months 6 through 9 leaves limited time to close the shortfall before the coding deadline. If the current-year rate lags the prior year by more than a few percentage points, investigate whether specific provider groups, care gaps, or scheduling backlogs are driving the underperformance and prioritize targeted outreach to high-RAF members not yet seen.

**Technical specification**

**DAX measure(s):**

RAF recapture rate PY = CALCULATE([RAF recapture rate], SAMEPERIODLASTYEAR('date'[month_of_date]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 3485c63e-820e-4a28-b324-ceb573bafa13

RAF recapture rate = var a = CALCULATE(sum(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented"}))
var b = CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented", "Undocumented"}))
return
DIVIDE(a,b)
formatString: 0.0%;-0.0%;0.0%
lineageTag: 70ebc3c8-8fb8-48dc-815a-23f345128994

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_year | Time intelligence — drives YoY/MoM comparison |