**Widget: Across PCP visits (rolling 12 months) (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across PCP visits (rolling 12 months) bar chart*

**Definition**

This chart compares the volume of targeted care gaps across patient segments defined by their number of PCP visits in the rolling 12-month period.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted gaps |
| Category axis | PCP visits (rolling 12 months) |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Highest targeted gaps concentrated in the zero or low PCP visit segments | Negative | Patients with little to no recent primary care engagement are accumulating unaddressed gaps, indicating a high-risk, under-served population requiring outreach prioritization. |
| Targeted gaps decrease steadily as PCP visit count increases | Positive | Higher PCP visit frequency correlates with fewer open gaps, suggesting that regular primary care contact is effectively driving gap closure and preventive care completion. |
| High targeted gaps persist even in segments with frequent PCP visits | Investigate | Patients seeing their PCP often but still carrying multiple open gaps may indicate documentation deficiencies, coding gaps, or care coordination breakdowns that warrant clinical and administrative review. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| static_patient_seen_bucket | patient_seen_bucket | Source column — contributes to measure calculation |