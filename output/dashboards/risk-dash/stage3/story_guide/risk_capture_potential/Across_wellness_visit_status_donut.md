**Widget: Across wellness visit status (Donut Chart)**

> 📷 *Insert: Cropped screenshot of the Across wellness visit status donut*

**Definition**

Displays the distribution of targeted care gaps segmented by whether members have completed, scheduled, or never had a wellness visit. Answers 'Across which wellness visit status do the most targeted gaps remain open?'

**What it measures**

| Element | Description |
|---|---|
| Visual type | Donut chart |
| Primary metric | Targeted gaps |
| Legend | Wellness visit |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

| Pattern | Interpretation |
|---|---|
| Majority of targeted gaps fall in the 'No Wellness Visit' slice (>60%) | Members without any wellness visit represent the highest-risk, lowest-touch population, signaling an urgent outreach priority to close both visit and coding gaps simultaneously. |
| Gaps are roughly equal between 'No Wellness Visit' and 'Wellness Visit Completed' slices | A large share of gaps persisting even after completed visits indicates documentation or coding deficiencies during the encounter, requiring provider education on thorough HCC capture. |
| 'Wellness Visit Scheduled' slice holds a significant portion of targeted gaps | A substantial pipeline of upcoming visits presents a near-term opportunity to close gaps proactively by equipping care teams with pre-visit gap summaries before appointments occur. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| cohort | awv_status | Legend / category — Wellness visit segments |