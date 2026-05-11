**Widget: Across ED visit bucket (last 6 months) (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across ED visit bucket (last 6 months) bar chart*

**Definition**

This chart compares the count of targeted care gaps across patient segments defined by their frequency of emergency department visits in the last 6 months.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | ED visit bucket |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Tallest bar in the 0 ED visits bucket | Positive | Most targeted gaps are concentrated in patients with no recent ED utilization, suggesting opportunities for proactive outreach before acute events occur. |
| Tallest bar in the 3+ ED visits bucket | Negative | High-frequency ED users carry the greatest burden of unaddressed gaps, indicating that complex, high-risk patients are not receiving adequate preventive or chronic care management. |
| Progressively rising bars from low to high ED visit buckets | Investigate | A stepwise increase in targeted gaps as ED utilization rises suggests a systemic failure to close care gaps before patients escalate to emergency-level care, warranting urgent care coordination review. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| cohort | ed_visit_bucket | Category axis — groups bars by ED visit bucket |