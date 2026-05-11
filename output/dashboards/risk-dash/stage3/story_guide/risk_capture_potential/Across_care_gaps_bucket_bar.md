**Widget: Across care gaps bucket (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across care gaps bucket bar chart*

**Definition**

This chart compares the volume of targeted care gaps distributed across different care gap buckets, revealing which clinical categories carry the highest unaddressed gap burden.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | Care gap bucket |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| A care gap bucket bar is significantly taller than all others | Investigate | A disproportionately high concentration of targeted gaps in one bucket suggests a systemic documentation or care delivery failure in that clinical category requiring immediate outreach prioritization. |
| Targeted gap counts are evenly distributed across all buckets | Positive | Balanced distribution indicates that care gap identification efforts are broad and comprehensive, reducing the risk of overlooking any single clinical domain. |
| One or more care gap buckets show near-zero targeted gaps | Negative | Extremely low targeted gaps in a bucket may signal under-identification or incomplete risk stratification in that clinical area, potentially leaving high-risk patients unaddressed. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_care_gap_bucket | care_gap_bucket | Category axis — groups bars by Care gap bucket |