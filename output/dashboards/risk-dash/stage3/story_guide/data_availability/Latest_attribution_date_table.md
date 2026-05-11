**Widget: Latest attribution date (Table)**

> 📷 *Insert: Cropped screenshot of the Latest attribution date table*

**Definition**

This table displays the most recent dates on which member attribution and risk score execution were last updated in the risk adjustment system.

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
| Latest attribution date | The most recent date on which the member attribution roster was refreshed, indicating when patients were last assigned to a provider or care program. | A more recent date signals that attribution data is current and members are being actively assigned, reducing the risk of acting on stale rosters. | An older or regressing date warns that attribution has not been refreshed recently, meaning care managers may be working from outdated member assignments. |
| Latest risk execution | The most recent date on which the RAF scoring engine was run, reflecting when HCC-based risk scores were last calculated and loaded into the dashboard. | A more recent execution date confirms that risk scores incorporate the latest coded diagnoses and claims, supporting accurate gap identification and prioritization. | An older execution date indicates that risk scores may be stale, potentially causing analysts to miss newly documented conditions or recently closed gaps. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| Recent attribution date with stale risk execution date | New members have been attributed but RAF scores have not been recalculated, meaning current risk scores do not reflect the latest panel composition; trigger a risk execution refresh immediately to ensure accurate gap identification. |
| Stale attribution date with recent risk execution date | Risk scores are being recalculated against an outdated member panel, potentially scoring members who have left or missing newly assigned members; re-run attribution before relying on these RAF values for care management outreach. |
| Both attribution date and risk execution date are stale | Neither the member panel nor the risk scores reflect current reality, making any gap analysis or PMPM projections unreliable; escalate to the data operations team to investigate and resolve the pipeline failure before any clinical or financial decisions are made. |
| Both attribution date and risk execution date are current and aligned | The member panel and RAF scores are synchronized and up to date, indicating a healthy data pipeline; analysts can confidently use this row's gap-to-potential-risk and recapture rate metrics for accurate performance reporting and care manager prioritization. |

**Technical specification**

**DAX measure(s):**

Latest attribution date = MAX(attribution[month_of_date])

Latest risk execution = CALCULATE(MAX(cohort[month_of_measurement]),ALL('date'))

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| attribution | month_of_date | Time intelligence — drives YoY/MoM comparison |
| cohort | month_of_measurement | Source column — contributes to measure calculation |
| payer | payer_name | Row dimension — groups rows in the matrix |
| payer | plan_name | Row dimension — groups rows in the matrix |
| payer | date_incurred_through | Row dimension — groups rows in the matrix |
| payer | date_paid_through | Row dimension — groups rows in the matrix |