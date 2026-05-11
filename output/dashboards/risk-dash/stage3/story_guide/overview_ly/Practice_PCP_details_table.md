**Widget: Practice/PCP details (Table)**

> 📷 *Insert: Cropped screenshot of the Practice/PCP details table*

**Definition**

This table compares year-over-year risk adjustment performance metrics at the practice and individual PCP level, covering member panel size, documented and potential risk scores, cost, and coding gap closure rates.

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
| #Members | The total count of attributed members assigned to a given practice or PCP during the measurement period. | Rising member counts indicate panel growth, which may amplify both risk capture opportunities and resource demands for that provider. | Falling member counts may signal attribution loss, panel shrinkage, or member churn that could reduce the provider's overall risk and revenue impact. |
| Documented risk | The aggregate RAF score derived exclusively from HCC conditions that have already been coded and submitted for the attributed member panel. | Rising documented risk reflects improved coding completeness or a genuinely sicker panel, both of which support more accurate and higher risk-adjusted revenue. | Falling documented risk suggests coding gaps are widening, conditions are not being recaptured annually, or the panel is becoming healthier over time. |
| Gap to potential risk | The difference between the maximum achievable RAF score (based on suspected and dropped HCC conditions) and the currently documented RAF score, representing uncaptured risk opportunity. | A growing gap signals that more conditions are going uncoded relative to what is clinically suspected, indicating deteriorating coding performance or missed recapture opportunities. | A shrinking gap indicates the practice is successfully closing coding opportunities and moving documented risk closer to the full potential risk of the panel. |
| PMPM | The average per-member-per-month cost associated with the attributed panel, used as a proxy for resource utilization and financial risk. | Rising PMPM suggests higher utilization or acuity among panel members, which may warrant care management intervention to control costs. | Falling PMPM may reflect improved care management effectiveness, healthier member mix, or reduced utilization across the panel. |
| RAF recapture rate | The percentage of previously documented HCC conditions (from a prior period) that were successfully re-coded and submitted in the current period, measuring continuity of chronic condition documentation. | A higher recapture rate indicates the PCP or practice is consistently re-documenting known chronic conditions each year, preserving risk-adjusted revenue. | A declining recapture rate signals that previously coded conditions are being dropped, threatening revenue integrity and accurate representation of member acuity. |
| RAF recapture rate YoY | The year-over-year percentage change in the RAF recapture rate, showing whether the practice's ability to re-document prior HCC conditions is improving or deteriorating. | A positive YoY change means the practice is recapturing a greater share of prior-year HCCs compared to the previous year, reflecting coding process improvement. | A negative YoY change indicates the practice is recapturing fewer prior-year HCCs than before, signaling a regression in chronic condition documentation continuity. |
| Risk recapture rate | The percentage of total identified coding gaps (both suspected and dropped conditions) that were successfully closed through documented diagnosis coding in the current period. | Rising risk recapture rates indicate the practice is effectively converting open coding opportunities into documented diagnoses, maximizing risk-adjusted revenue. | Falling risk recapture rates suggest coding gap closure efforts are losing effectiveness, leaving more potential risk unaddressed. |
| Risk recapture rate YoY | The year-over-year percentage change in the overall risk recapture rate, tracking whether gap closure performance is trending better or worse compared to the prior year. | A positive YoY trend signals that the practice is closing a larger proportion of coding gaps than it did the prior year, reflecting improved engagement with risk capture workflows. | A negative YoY trend indicates the practice is closing fewer gaps relative to the prior year, warranting investigation into workflow, provider engagement, or outreach effectiveness. |
| % members with open coding gaps | The proportion of a practice's attributed members who have at least one unresolved HCC coding gap (either suspected or dropped) in the current period. | A rising percentage means more of the panel has unaddressed risk documentation opportunities, indicating broader coding gap exposure across the practice. | A falling percentage reflects successful gap closure efforts, with fewer members carrying unresolved HCC opportunities. |
| Open gaps (Dropped) | The count of HCC conditions that were coded in a prior period but have not yet been re-documented in the current period, representing lapsed chronic condition recapture. | More dropped gaps indicate that previously known chronic conditions are not being re-coded, putting prior-year risk-adjusted revenue at risk of loss. | Fewer dropped gaps signal that the practice is successfully recapturing chronic conditions from prior years, maintaining coding continuity and revenue stability. |
| Open gaps (Suspected) | The count of HCC conditions that have been clinically suspected based on claims, labs, or other data signals but have not yet been formally diagnosed and coded by the provider. | A growing number of suspected gaps means more potential diagnoses remain unconfirmed, representing an expanding untapped risk capture and revenue opportunity. | Fewer suspected gaps indicate that the practice is actively evaluating and coding clinically suspected conditions, reducing unconfirmed risk exposure. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| High % members with open coding gaps combined with low RAF recapture rate and large Gap to potential risk | The practice is systematically under-documenting chronic conditions, leaving significant revenue and risk accuracy on the table — prioritize a targeted chart review and provider education campaign for this PCP. |
| Declining RAF recapture rate YoY alongside rising Open gaps (Dropped) and stable or growing panel size (#Members) | Coding gaps are being abandoned rather than closed as the panel grows, signaling workflow capacity issues — escalate to care management leadership to add outreach resources or reduce panel load. |
| High RAF recapture rate with negative RAF recapture rate YoY and increasing Open gaps (Suspected) | A previously strong performer is losing momentum with a growing backlog of unvalidated conditions — investigate whether new suspected gaps are being generated faster than the PCP can address them and adjust gap prioritization logic. |
| Elevated PMPM combined with high Documented risk but low Risk recapture rate YoY and minimal Gap to potential risk | The practice has a genuinely high-acuity panel that is well-documented but cost growth is outpacing risk score improvement — flag for medical director review to assess care management intensity and utilization patterns rather than coding behavior. |

**Technical specification**

**DAX measure(s):**

#Members = SUM(attribution[member_count])+0
formatString: #,0
lineageTag: d67d72a2-2db7-4495-b98f-0d57ba71fa97

#Members YoY Card = VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([#Members] - py, py, 0)
RETURN
IF(
ISBLANK(py),
"",
SWITCH(
TRUE(),
yoy > 0, UNICHAR(9650) & " " & FORMAT(yoy, "0%") & " from LY",
yoy < 0, UNICHAR(9660) & " " & FORMAT(ABS(yoy), "0%") & " from LY",
""
)
)
lineageTag: 576e42ab-15fd-49df-b033-fc1e5df1ecf0

#Members MoM Card = VAR pm = CALCULATE([#Members], PREVIOUSMONTH('date'[month_of_date]))
VAR mom = DIVIDE([#Members] - pm, pm, 0)
RETURN
IF(
ISBLANK(pm),
"",
SWITCH(
TRUE(),
mom > 0, UNICHAR(9650) & " " & FORMAT(mom, "0%") & " from LM",
mom < 0, UNICHAR(9660) & " " & FORMAT(ABS(mom), "0%") & " from LM",
""
)
)
lineageTag: 702faa0d-6bc8-4c21-89ad-dbcbb88ea93b

Documented risk = CALCULATE( DIVIDE(SUM(risk_core[risk_value]),sum(risk_core[patient_count])), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
formatString: 0.000
lineageTag: 3efdba30-4573-4f09-8390-00e0cfe385fb

Gap to potential risk = var a  = CALCULATE( SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Undocumented","Suspected"}))
var b  = CALCULATE( sum(risk_core[patient_count]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
return
DIVIDE(a,b)+0
formatString: 0.000
lineageTag: 32eac8c6-11fe-461d-bf55-d27ad8617059

PMPM = DIVIDE(SUM(attribution[ytd_visit_amount]),Sum(attribution[ytd_member_count]))

RAF recapture rate = var a = CALCULATE(sum(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented"}))
var b = CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented", "Undocumented"}))
return
DIVIDE(a,b)
formatString: 0.0%;-0.0%;0.0%
lineageTag: 70ebc3c8-8fb8-48dc-815a-23f345128994

RAF recapture rate YoY = var py = [RAF recapture rate PY]
return
DIVIDE([RAF recapture rate] - py, py)
formatString: 0%;-0%;0%
lineageTag: 4232eb66-0fc0-487a-95ef-d7ed152d1c8d

Risk recapture rate = DIVIDE(SUM(risk_core[recapture_numerator]),SUM(risk_core[recapture_denominator]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 833f191f-3194-4c8f-b39c-de1b45c3b006

Risk recapture rate YoY = var py = [Risk recapture rate PY]
return
DIVIDE([Risk recapture rate] - py, py)
formatString: 0%;-0%;0%
lineageTag: 50b1c5b5-875d-4871-80cf-71a306f4cff5

% members with open coding gaps = [Members with open coding gaps]/[#Members]

Open gaps (Dropped) = SUM(risk_core[recapture_denominator])-SUM(risk_core[recapture_numerator])

Open gaps (Suspected) = SUM(risk_core[suspect_denominator])-SUM(risk_core[suspect_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| attribution | member_count | Patient/member count — used as denominator |
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| attribution | ytd_member_count | Patient/member count — used as denominator |
| attribution | ytd_visit_amount | Numerator — total YTD medical cost |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| attribution | member_with_open_coding_gap_count | Numerator — members with at least one open coding gap |
| risk_core | suspect_numerator | Numerator — suspected gaps closed |
| risk_core | suspect_denominator | Denominator — total suspected gaps |
| pcp | practice_name | Row dimension — groups rows in the matrix |
| pcp | pcp_name | Row dimension — groups rows in the matrix |