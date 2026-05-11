**Widget: Patient list (Table)**

> 📷 *Insert: Cropped screenshot of the Patient list table*

**Definition**

A patient-level list displaying individual members identified by their unique enterprise master patient index (EMPI), with no comparative period applied.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Matrix / table |
| Primary metric | Multiple — one per column |
# | Comparison | None columns embedded in the table |
| Comparison | None — current period values only, no time comparison |
| Visual-level filters | None — responds to global filters only |

**Column definitions and directional impact**

| Column | Definition | ↑ Increasing | ↓ Decreasing |
|---|---|---|---|
| — | — | — | — |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| Member with high RAF score and multiple open coding gaps | Documented complexity is not fully captured in claims, understating true risk; prioritize a comprehensive visit to close all outstanding HCC gaps before the coding deadline. |
| Member with low recapture rate and rising PMPM cost | Care costs are climbing while risk documentation lags, creating a financial exposure for the plan; assign a care manager to coordinate a gap-closure visit and review utilization drivers. |
| Member with large gap-to-potential-risk and no recent encounter on record | Significant uncaptured risk opportunity exists but the member is not engaging with the care system; trigger an outreach campaign or home visit to re-engage and document chronic conditions. |
| Member with declining YoY RAF and stable or increasing PMPM | Risk score erosion suggests conditions are being under-coded in the current year while costs remain high, signaling a documentation-to-cost misalignment; conduct a retrospective chart review and educate the assigned PCP on HCC specificity requirements. |

**Technical specification**

**DAX measure(s):**

N/A

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| cohort | empi | Row dimension — groups rows in the matrix |