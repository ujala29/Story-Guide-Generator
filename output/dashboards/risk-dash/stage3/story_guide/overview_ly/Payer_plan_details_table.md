**Widget: Payer/plan details (Table)**

> 📷 *Insert: Cropped screenshot of the Payer/plan details table*

**Definition**

This table compares year-over-year risk adjustment performance metrics across payers and their individual plans, covering membership size, documented and potential RAF risk, cost, and recapture effectiveness.

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
| #Members | The total count of enrolled members attributed to each payer or plan during the measurement period. | Rising membership may indicate plan growth, which can dilute or amplify risk scores and recapture rates depending on the health acuity of new enrollees. | Falling membership may signal plan attrition or disenrollment, potentially skewing per-member metrics and reducing the absolute revenue opportunity for risk capture. |
| Documented risk | The aggregate RAF score derived solely from HCC conditions that have already been coded and submitted for the current measurement period. | Higher documented risk reflects more thorough or complete coding of chronic and complex conditions, supporting stronger risk-adjusted revenue. | Lower documented risk suggests coding gaps are widening or previously captured conditions are not being recaptured, threatening revenue adequacy. |
| Gap to potential risk | The difference between a member's estimated maximum achievable RAF score and their currently documented RAF score, representing uncaptured coding opportunity. | A growing gap indicates that more conditions are going uncoded relative to clinical evidence, signaling deteriorating documentation or care gap closure performance. | A shrinking gap means the plan is successfully identifying and closing HCC coding opportunities, moving documented risk closer to the clinically supported potential. |
| PMPM | The average medical cost or premium revenue expressed on a per-member-per-month basis for each payer or plan. | Rising PMPM may reflect higher-acuity membership, increased utilization, or cost trend acceleration, warranting review of care management interventions. | Falling PMPM can indicate improved care management efficiency, healthier member mix, or successful cost containment programs. |
| RAF recapture rate | The percentage of previously documented HCC conditions from a prior period that were successfully re-documented and submitted in the current period. | A higher recapture rate means the plan is effectively re-coding chronic conditions year over year, preserving risk-adjusted revenue continuity. | A lower recapture rate signals that chronic conditions coded in prior years are not being reconfirmed, creating revenue leakage and potential audit risk. |
| RAF recapture rate YoY | The year-over-year percentage change in the RAF recapture rate, showing whether the plan's ability to re-document prior HCCs is improving or declining. | A positive YoY change indicates the plan is getting better at sustaining chronic condition documentation across annual coding cycles. | A negative YoY change flags a worsening trend in recapturing previously coded HCCs, which may require targeted outreach or provider education. |
| Risk recapture rate | The percentage of total identified RAF risk gaps — both existing and new — that were successfully closed through coding or clinical documentation in the current period. | A higher risk recapture rate reflects stronger gap closure performance across all opportunity types, maximizing risk-adjusted revenue potential. | A lower risk recapture rate indicates that identified coding opportunities are not being acted upon, leaving significant RAF value and revenue unrealized. |
| Risk recapture rate YoY | The year-over-year percentage change in the overall risk recapture rate, measuring whether gap closure effectiveness is trending positively or negatively. | A positive YoY trend demonstrates that care management and coding programs are becoming more effective at converting identified gaps into documented risk. | A negative YoY trend signals declining program effectiveness or growing complexity of remaining gaps, requiring strategic intervention to reverse the trajectory. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| Large membership with high gap to potential risk and declining RAF recapture rate YoY | A high-volume plan is leaving significant risk revenue uncaptured and getting worse at closing it — prioritize targeted outreach and coding education for this payer immediately. |
| High documented risk and high PMPM but low risk recapture rate | The plan carries a costly, complex population whose conditions are not being consistently recaptured year-over-year — audit coding completeness and schedule retrospective chart reviews to protect RAF-based reimbursement. |
| Improving RAF recapture rate YoY alongside a shrinking gap to potential risk | The plan is successfully closing coding gaps and trending toward full risk documentation — recognize and replicate the workflows or vendor strategies driving this improvement across underperforming plans. |
| Low PMPM combined with a large gap to potential risk and flat or negative risk recapture rate YoY | The plan appears low-cost but is likely undercoding chronic conditions, understating true member acuity — conduct prospective HCC gap closure campaigns to avoid future risk score resets and revenue shortfalls. |

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
| payer | payer_name | Row dimension — groups rows in the matrix |
| payer | plan_name | Row dimension — groups rows in the matrix |