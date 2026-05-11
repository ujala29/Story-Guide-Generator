**Widget: Risk recapture rate by disease (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Risk recapture rate by disease bar chart*

**Definition**

This chart compares the year-over-year risk recapture rate across individual diseases, showing how effectively each condition's documented risk is being captured relative to the prior period.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Risk recapture rate (GROUP) |
| Category axis | Disease |
| Tooltip | Risk recapture rate change %, Open gaps (Dropped), Open gaps (Suspected) |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Bar height increases significantly YoY for a disease | Positive | Improved recapture rate indicates that previously missed or suspected diagnoses for this condition are now being documented and closed, strengthening risk accuracy. |
| Bar height decreases or drops notably YoY for a disease | Negative | Declining recapture rate signals that open gaps are going unaddressed and suspected conditions are not being confirmed, leading to potential RAF score erosion for that disease. |
| Bar shows minimal YoY change despite high Open gaps (Suspected) in tooltip | Investigate | Stagnant recapture rate alongside a large suspected gap volume suggests coding or outreach workflows are failing to convert clinical suspicions into confirmed diagnoses, warranting targeted intervention. |

**Technical specification**

**DAX measure(s):**

Risk recapture rate (GROUP) = DIVIDE(SUM(risk_group[recapture_numerator]), SUM(risk_group[recapture_denominator]))

Risk recapture rate YoY (GROUP) = VAR py = [Risk recapture rate PY (GROUP)] RETURN DIVIDE([Risk recapture rate (GROUP)] - py, py)

open dropped gaps (GROUP) = SUM(risk_group[recapture_denominator]) - SUM(risk_group[recapture_numerator])

open suspected gaps (GROUP) = SUM(risk_group[suspect_denominator]) - SUM(risk_group[suspect_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_group | recapture_denominator | Denominator — total identified gaps |
| risk_group | recapture_numerator | Numerator — gaps successfully closed |
| risk_group | suspect_numerator | Numerator — suspected gaps closed |
| risk_group | suspect_denominator | Denominator — total suspected gaps |
| risk_group | disease | Category axis — groups bars by Disease |