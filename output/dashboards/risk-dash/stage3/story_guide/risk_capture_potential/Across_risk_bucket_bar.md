**Widget: Across risk bucket (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across risk bucket bar chart*

**Definition**

This chart compares the volume of targeted care gaps distributed across different patient risk buckets, revealing where gap closure efforts are concentrated by risk severity.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | Risk bucket |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Tallest bars in high-risk buckets | Positive | Targeted gaps are appropriately concentrated among the highest-risk patients, aligning outreach efforts with the population most likely to benefit clinically and impact risk scores. |
| Tallest bars in low-risk buckets | Investigate | Disproportionate targeting of low-risk patients may indicate misaligned prioritization, potentially missing high-risk members with greater clinical need and RAF score opportunity. |
| Relatively even bars across all risk buckets | Negative | A flat distribution of targeted gaps suggests no risk-stratified prioritization strategy is in place, reducing the efficiency and clinical impact of gap closure interventions. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_risk_bucket | risk_bucket | Category axis — groups bars by Risk bucket |