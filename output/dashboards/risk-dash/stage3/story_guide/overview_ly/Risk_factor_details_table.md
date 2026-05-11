**Widget: Risk factor details (Table)**

> 📷 *Insert: Cropped screenshot of the Risk factor details table*

**Definition**

This table presents year-over-year risk adjustment performance metrics at the group level, showing how well documented risk, gap closure, and recapture rates are trending across the eligible population.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Matrix / table |
| Primary metric | Multiple — one per column |
# | Comparison | YoY % change columns embedded in the table |
| Comparison | YoY and MoM change columns embedded in the table |
| Visual-level filters | None — responds to global filters only |

**Column definitions and directional impact**

| Column | Definition | ↑ Increasing | ↓ Decreasing |
|---|---|---|---|
| Eligible population (group) | The total count of members in the group who are eligible for risk adjustment evaluation during the measurement period. | Rising membership signals a growing population requiring risk documentation and gap closure resources. | Falling membership may indicate attrition, eligibility changes, or panel reductions that could affect overall RAF and revenue projections. |
| Documented risk (GROUP) | The aggregate RAF score derived from HCC conditions that have already been coded and submitted for the group during the measurement period. | Higher documented risk reflects improved coding completeness, more accurate capture of member acuity, and stronger risk-adjusted revenue. | Lower documented risk suggests coding gaps, missed diagnoses, or member health improvement, potentially leading to underpayment relative to true clinical burden. |
| Gap to potential risk (GROUP) | The difference between the group's potential RAF score (including suspected but uncaptured HCCs) and the currently documented RAF score, representing unclosed coding opportunity. | A growing gap indicates that more suspected conditions are going undocumented, signaling deteriorating coding performance or insufficient outreach. | A shrinking gap reflects successful closure of HCC coding opportunities, improving alignment between clinical reality and submitted risk scores. |
| Risk recapture rate (GROUP) | The percentage of identified HCC coding gaps that were successfully closed and documented for the group during the measurement period. | A higher recapture rate demonstrates effective care management outreach and provider engagement in closing suspected diagnosis gaps. | A declining recapture rate signals that fewer gaps are being resolved, risking RAF score degradation and potential revenue shortfalls. |
| Risk recapture rate YoY (GROUP) | The year-over-year percentage change in the group's risk recapture rate, measuring whether gap closure performance is improving or declining relative to the prior year. | A positive YoY change indicates the group is closing a greater proportion of gaps than the prior year, reflecting program improvement. | A negative YoY change signals that gap closure efficiency has worsened compared to the prior year, warranting investigation into outreach or documentation workflows. |
| open dropped gaps (GROUP) | The count of HCC coding gaps that were previously identified but have been removed from active pursuit without being resolved, typically due to clinical review or administrative decisions. | A rising number of dropped gaps may indicate overly aggressive gap identification, clinical invalidation of suspected conditions, or workflow inefficiencies causing premature gap closure. | Fewer dropped gaps suggests better upfront gap quality, more accurate suspect algorithms, or improved follow-through before gaps are abandoned. |
| open suspected gaps (GROUP) | The count of HCC conditions that algorithms or clinical review have flagged as likely present but not yet documented or coded for members in the group. | More open suspected gaps signals a growing backlog of unaddressed coding opportunities, increasing risk of RAF score underrepresentation if not acted upon. | Fewer open suspected gaps indicates that the group is actively working through its pipeline, either by closing gaps through documentation or by dropping clinically invalid suspects. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| High gap to potential risk combined with low recapture rate and large open suspected gaps | The group is leaving significant RAF value on the table with no momentum to close it; prioritize outreach campaigns and targeted chart reviews to convert suspected gaps before the coding window closes. |
| Declining recapture rate YoY alongside a growing volume of open dropped gaps | Gaps are being abandoned rather than resolved, signaling workflow or provider engagement breakdown; investigate why gaps are being dropped and implement re-engagement protocols with the group's care team. |
| Strong recapture rate with negative recapture rate YoY and stable or rising open suspected gaps | Performance is eroding from a previously strong baseline, suggesting early-stage capacity or documentation fatigue; intervene now with coder support or provider education before the decline becomes a trend. |
| Large eligible population with low documented risk and high gap to potential risk | The group has a broad, under-documented membership base representing a high-value RAF recovery opportunity; deploy population-level HCC gap closure programs and ensure annual wellness visits are scheduled to surface undocumented conditions. |

**Technical specification**

**DAX measure(s):**

Eligible population (group) = sum(risk_group[patient_count])

Documented risk (GROUP) = CALCULATE(DIVIDE(SUM(risk_group[risk_value]), SUM(risk_group[patient_count])), KEEPFILTERS(risk_group[risk_documentation_flag] = "Documented")) + 0

Gap to potential risk (GROUP) = VAR a = CALCULATE(SUM(risk_group[risk_value]), KEEPFILTERS(risk_group[risk_documentation_flag] IN { "Undocumented", "Suspected" })) VAR b = CALCULATE(SUM(risk_group[patient_count]), KEEPFILTERS(risk_group[risk_documentation_flag] = "Documented")) RETURN DIVIDE(a,b)+0

Risk recapture rate (GROUP) = DIVIDE(SUM(risk_group[recapture_numerator]), SUM(risk_group[recapture_denominator]))

Risk recapture rate YoY (GROUP) = VAR py = [Risk recapture rate PY (GROUP)] RETURN DIVIDE([Risk recapture rate (GROUP)] - py, py)

open dropped gaps (GROUP) = SUM(risk_group[recapture_denominator]) - SUM(risk_group[recapture_numerator])

open suspected gaps (GROUP) = SUM(risk_group[suspect_denominator]) - SUM(risk_group[suspect_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_group | patient_count | Patient/member count — used as denominator |
| risk_group | risk_value | HCC risk weight — summed for numerator or denominator |
| risk_group | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_group | recapture_numerator | Numerator — gaps successfully closed |
| risk_group | recapture_denominator | Denominator — total identified gaps |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_group | suspect_numerator | Numerator — suspected gaps closed |
| risk_group | suspect_denominator | Denominator — total suspected gaps |
| risk_group | risk_factor_description | Row dimension — groups rows in the matrix |
| risk_group | risk_factor_code | Row dimension — groups rows in the matrix |