**Widget: Across coding gaps bucket (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across coding gaps bucket bar chart*

**Definition**

This chart compares the count of targeted coding gaps distributed across different coding gap bucket categories to identify where documentation and capture opportunities are concentrated.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | Coding gap bucket |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| High-complexity or chronic condition buckets show the tallest bars | Investigate | A concentration of targeted gaps in high-acuity buckets suggests significant HCC capture risk and may indicate systemic under-documentation of complex chronic conditions requiring prioritized outreach. |
| Targeted gaps are evenly distributed across all coding gap buckets | Positive | Balanced distribution across buckets indicates a broad but manageable coding gap workload, allowing care teams to address documentation opportunities systematically without overwhelming any single condition category. |
| One or two buckets dominate with disproportionately large bars | Negative | Disproportionate concentration in specific buckets signals a bottleneck in coding closure efforts, increasing the risk of missed risk adjustment revenue and incomplete patient clinical profiles for those condition categories. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_coding_gap_bucket | coding_gap_bucket | Category axis — groups bars by Coding gap bucket |