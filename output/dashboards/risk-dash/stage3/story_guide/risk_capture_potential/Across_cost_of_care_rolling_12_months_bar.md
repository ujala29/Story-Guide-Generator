**Widget: Across cost of care (rolling 12 months) (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across cost of care (rolling 12 months) bar chart*

**Definition**

This chart compares the number of targeted care gaps across different cost-of-care bands over a rolling 12-month period, revealing where unaddressed clinical needs concentrate among high- and low-cost patient segments.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | Cost of care (rolling 12 months) |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Tallest bars in the highest cost-of-care bands | Negative | High-cost patients carry the most unresolved care gaps, indicating that complex or chronically ill members are not receiving timely interventions that could reduce utilization and risk scores. |
| Tallest bars in the lowest cost-of-care bands | Investigate | A concentration of targeted gaps among low-cost members may signal under-documented conditions or rising-risk patients who have not yet generated high spend but could if gaps remain unaddressed. |
| Bars declining progressively from high to low cost bands | Positive | A clear downward trend from high- to low-cost bands suggests care management resources are appropriately aligned with the sickest, most expensive members, supporting effective risk stratification and closure prioritization. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_visit_amount_rolling_bucket | visit_amount_rolling_bucket | Source column — contributes to measure calculation |