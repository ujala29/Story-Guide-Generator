**Widget: Across PCP - member distance (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across PCP - member distance bar chart*

**Definition**

This chart compares the volume of targeted care gaps across members grouped by their geographic distance from their assigned Primary Care Physician.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | PCP member distance bucket |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Highest targeted gaps concentrated in the farthest distance buckets | Negative | Members living far from their PCP face greater access barriers, leading to more unresolved care gaps that require outreach or telehealth intervention. |
| Highest targeted gaps concentrated in the nearest distance buckets | Investigate | Proximity to a PCP does not guarantee gap closure, suggesting care coordination, scheduling capacity, or engagement quality issues may be limiting in-office gap resolution. |
| Targeted gaps are evenly distributed across all distance buckets | Investigate | A uniform gap distribution regardless of distance indicates that access alone is not the primary driver, and broader systemic factors such as documentation practices or risk stratification accuracy should be examined. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_pcp_member_distance_bucket | pcp_member_distance_bucket | Category axis — groups bars by PCP member distance bucket |