**Widget: Across days since last PCP visit bucket (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across days since last PCP visit bucket bar chart*

**Definition**

This chart compares the volume of targeted care gaps distributed across patient segments defined by how many days have elapsed since their last primary care physician visit.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | Days since last PCP visit bucket |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Tallest bars concentrated in the longest days-since-visit buckets (e.g., 365+ days) | Negative | A high volume of targeted gaps among patients overdue for PCP visits indicates a disengaged population at elevated risk for unmanaged chronic conditions and poor risk capture. |
| Tallest bars concentrated in the shortest days-since-visit buckets (e.g., 0–90 days) | Positive | Gaps clustering among recently seen patients suggest care teams have active touchpoints available to close those gaps quickly and improve HCC coding accuracy. |
| Roughly equal bar heights across all days-since-visit buckets | Investigate | A uniform distribution of gaps across visit recency segments may signal systemic documentation or coding deficiencies that persist regardless of patient engagement frequency. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_days_since_last_pcp_visit_bucket | days_since_last_pcp_visit_bucket | Category axis — groups bars by Days since last PCP visit bucket |