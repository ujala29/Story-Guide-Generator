**Widget: Gap closure by type of visit (Donut Chart)**

> 📷 *Insert: Cropped screenshot of the Gap closure by type of visit donut*

**Definition**

Displays the distribution of closed care gaps across different visit types such as office visits, telehealth, and annual wellness visits. Answers 'Through which type of visit are care gaps being closed?'

**What it measures**

| Element | Description |
|---|---|
| Visual type | Donut chart |
| Primary metric | Gaps closed (GROUP) |
| Legend | Type of visit |
| Comparison | None |
| Visual-level filters | Responds to: gap_closure_visit_type |

**How to read it**

| Pattern | Interpretation |
|---|---|
| Annual Wellness Visits dominate gap closure, representing over 60% of the donut | AWVs are the primary driver of risk gap closure, signaling strong preventive visit utilization but potential over-reliance on a single visit type. |
| Telehealth accounts for the largest slice, surpassing in-person office visits | Virtual care is effectively capturing gap closure opportunities, supporting expansion of telehealth outreach programs for hard-to-reach members. |
| Gaps are evenly distributed across office visits, AWVs, and telehealth with no dominant slice | A balanced multi-channel closure strategy reduces risk concentration but may indicate no single visit type is being fully optimized for gap closure efficiency. |

**Technical specification**

**DAX measure(s):**

Gaps closed (GROUP) = SUM(risk_group[recapture_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_group | recapture_numerator | Numerator — gaps successfully closed |
| risk_group | gap_closure_visit_type | Legend / category — Type of visit segments |