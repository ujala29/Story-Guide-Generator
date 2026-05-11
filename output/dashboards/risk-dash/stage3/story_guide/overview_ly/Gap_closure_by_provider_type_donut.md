**Widget: Gap closure by provider type (Donut Chart)**

> 📷 *Insert: Cropped screenshot of the Gap closure by provider type donut*

**Definition**

Displays the distribution of closed care gaps across provider types to reveal which care settings are driving documentation and coding completeness. Answers 'Through which provider types are risk adjustment gaps being closed?'

**What it measures**

| Element | Description |
|---|---|
| Visual type | Donut chart |
| Primary metric | Gaps closed (GROUP) |
| Legend | Provider type |
| Comparison | None |
| Visual-level filters | Responds to: gap_closure_provider_type |

**How to read it**

| Pattern | Interpretation |
|---|---|
| Primary Care Physicians dominate with 65%+ of gap closures | PCP-led outreach is highly effective, but over-reliance on one provider type creates vulnerability if PCP engagement declines. |
| Specialists and ancillary providers share closures nearly equally with no single type exceeding 30% | Gap closure is broadly distributed, suggesting a well-coordinated multi-specialty strategy but potential inefficiency from lack of a clear accountability owner. |
| Telehealth or urgent care providers account for a disproportionately large slice | Non-traditional care settings are capturing significant RAF opportunities, warranting investment in structured coding workflows for those channels. |

**Technical specification**

**DAX measure(s):**

Gaps closed (GROUP) = SUM(risk_group[recapture_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_group | recapture_numerator | Numerator — gaps successfully closed |
| risk_group | gap_closure_provider_type | Legend / category — Provider type segments |