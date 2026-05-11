**Widget: Documented risk vs potential risk (lineChart)**

> 📷 *Insert: Cropped screenshot of the Documented risk vs potential risk lineChart*

**Definition**

This chart tracks monthly documented risk scores for the current and previous year alongside the potential risk ceiling, enabling year-over-year comparison and identification of uncaptured risk opportunities.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | Previous year, Current year, Potential |
| X-axis | Month |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

Monitor the gap between the Potential risk line and the Current year Documented risk line — a widening gap signals increasing uncaptured risk that may require additional coding or documentation efforts before the period closes. Compare the Current year line against the Previous year line month-by-month to assess whether risk capture is trending ahead or behind prior performance; a consistently lower current year trajectory warrants immediate outreach to providers or coders. Look for months where all three lines converge, which indicates strong documentation completeness and alignment between potential and actual risk. If the current year line falls below the previous year line while the potential risk line remains elevated, prioritize retrospective chart reviews and targeted HCC closure campaigns for those specific months.

**Technical specification**

**DAX measure(s):**

Documented risk PY = CALCULATE([Documented risk], SAMEPERIODLASTYEAR('date'[month_of_date]))

Documented risk = CALCULATE( DIVIDE(SUM(risk_core[risk_value]),sum(risk_core[patient_count])), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
formatString: 0.000
lineageTag: 3efdba30-4573-4f09-8390-00e0cfe385fb

Potential risk = var a  = SUM(risk_core[risk_value])
var b  = CALCULATE( sum(risk_core[patient_count]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
return
DIVIDE(a,b)
formatString: 0.000
lineageTag: 0c8d3b8e-3e21-40a1-a754-61733cf9adf0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_year | Time intelligence — drives YoY/MoM comparison |