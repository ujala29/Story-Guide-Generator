**Widget: Risk breakdown by attribution status (Table)**

> 📷 *Insert: Cropped screenshot of the Risk breakdown by attribution status table*

**Definition**

This table breaks down RAF risk scores, gap capture performance, and open coding opportunities by member churn status (e.g., retained, new, churned), comparing current-year values to the prior year.

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
| Eligible population | The count of members attributed to the plan within each churn status segment who are eligible for risk adjustment in the measurement period. | Rising membership in a segment expands the risk adjustment opportunity and may dilute or amplify aggregate RAF scores depending on the mix of new versus retained members. | Falling membership signals member attrition or attribution loss in that churn segment, which may reduce total risk revenue and limit the pool available for gap closure. |
| Documented risk | The aggregate RAF score derived from HCC conditions that have already been coded and submitted for members in each churn status segment. | Higher documented risk indicates more chronic conditions are being captured and coded, supporting accurate risk-based reimbursement for that segment. | Lower documented risk suggests coding gaps, member health improvement, or loss of high-acuity members, potentially signaling under-documentation and revenue leakage. |
| Gap to potential risk | The difference between the maximum potential RAF score (based on suspected or historical HCCs) and the currently documented RAF score, representing uncaptured risk opportunity for each churn segment. | A growing gap signals that more conditions are going uncoded relative to clinical evidence, indicating worsening documentation performance or an influx of members with unaddressed chronic conditions. | A shrinking gap indicates successful closure of coding opportunities, meaning care teams are effectively recapturing suspected or lapsed HCCs for that segment. |
| RAF recapture rate | The percentage of the prior-year RAF score that has been successfully re-documented in the current year for members in each churn status segment, measuring year-over-year HCC continuity. | A higher recapture rate means a greater proportion of previously coded conditions are being re-documented, reducing RAF erosion and stabilizing risk-based revenue. | A lower recapture rate indicates that previously coded HCCs are not being re-confirmed, leading to RAF score decay and potential reimbursement shortfalls. |
| RAF recapture rate YoY | The year-over-year percentage change in the RAF recapture rate for each churn status segment, showing whether HCC re-documentation performance is improving or deteriorating. | A positive YoY change signals that the plan is getting better at re-documenting prior-year conditions, reflecting improved coding workflows or provider engagement. | A negative YoY change warns that recapture performance is declining compared to the prior year, requiring intervention to prevent compounding RAF score erosion. |
| Risk recapture rate | The percentage of total identified risk gaps (suspected and dropped HCCs) that have been successfully closed through documented coding for members in each churn status segment. | A higher rate reflects effective gap closure efforts, meaning care managers and coders are successfully converting suspected conditions into confirmed, submitted diagnoses. | A lower rate indicates that identified risk opportunities are not being acted upon, leaving potential RAF value and associated care management insights unrealized. |
| Risk recapture rate YoY | The year-over-year percentage change in the risk recapture rate for each churn status segment, tracking whether gap closure efficiency is trending positively or negatively. | Improvement year-over-year suggests that outreach, coding, and clinical documentation programs are gaining traction within the segment. | Decline year-over-year signals that gap closure capacity or provider responsiveness has weakened relative to the prior period, warranting program review. |
| Open gaps (Dropped) | The count of HCC conditions that were coded in a prior period but have not yet been re-documented in the current year for members in each churn status segment, representing lapsed diagnosis gaps. | More dropped gaps indicate that previously confirmed chronic conditions are not being recaptured, increasing the risk of RAF score decline and potential care continuity issues. | Fewer dropped gaps mean the plan is successfully re-documenting lapsed conditions, preserving RAF scores and ensuring continuity of chronic disease management. |
| Open gaps (Suspected) | The count of HCC conditions that clinical evidence or predictive models suggest are present but have not yet been coded or confirmed for members in each churn status segment. | A growing number of suspected gaps signals a larger untapped risk documentation opportunity, but also potential under-diagnosis or insufficient provider engagement in that segment. | Fewer suspected gaps indicate that clinically implied conditions are being investigated and coded, reducing unconfirmed risk and improving the completeness of the member's health record. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| Churned members with high open suspected gaps and low RAF recapture rate | Risk is walking out the door uncaptured — prioritize retention outreach and close suspected gaps before members disenroll to protect RAF integrity. |
| New members with large gap to potential risk and declining RAF recapture rate YoY | Newly attributed members are being under-documented at intake, suppressing prospective RAF; trigger early HCC gap closure workflows and ensure comprehensive welcome visits are completed. |
| Retained members with high documented risk but rising open dropped gaps and negative risk recapture rate YoY | Previously captured conditions are not being revalidated annually, creating RAF erosion on your most stable population; implement targeted recapture campaigns focused on chronic condition re-documentation. |
| Churned members with elevated eligible population and high open dropped gaps relative to documented risk | A large volume of members is leaving with unresolved dropped gaps, signaling systemic care continuity failures; coordinate with care managers to conduct gap closure prior to attribution loss and flag these members for transition-of-care intervention. |

**Technical specification**

**DAX measure(s):**

Eligible population = CALCULATE(SUM(risk_core[patient_count]),KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))+0
formatString: #,0
lineageTag: 8c201874-31b6-4f4b-8be8-131ce92d628e

ELigible population YoY Card = VAR py = CALCULATE([Eligible population], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([Eligible population] - py, py, 0)
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
lineageTag: 4a1af66c-f9c8-4188-8212-a8ecd477cbe1

ELigible population MoM Card = VAR pm = CALCULATE([Eligible population], PREVIOUSMONTH('date'[month_of_date]))
VAR yoy = DIVIDE([Eligible population] - pm, pm, 0)
RETURN
IF(
ISBLANK(pm),
"",
SWITCH(
TRUE(),
yoy > 0, UNICHAR(9650) & " " & FORMAT(yoy, "0%") & " from LM",
yoy < 0, UNICHAR(9660) & " " & FORMAT(ABS(yoy), "0%") & " from LM",
""
)
)
lineageTag: f32d65c7-7180-468b-9269-baeebb655ab8

Documented risk = CALCULATE( DIVIDE(SUM(risk_core[risk_value]),sum(risk_core[patient_count])), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
formatString: 0.000
lineageTag: 3efdba30-4573-4f09-8390-00e0cfe385fb

Gap to potential risk = var a  = CALCULATE( SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Undocumented","Suspected"}))
var b  = CALCULATE( sum(risk_core[patient_count]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
return
DIVIDE(a,b)+0
formatString: 0.000
lineageTag: 32eac8c6-11fe-461d-bf55-d27ad8617059

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

Open gaps (Dropped) = SUM(risk_core[recapture_denominator])-SUM(risk_core[recapture_numerator])

Open gaps (Suspected) = SUM(risk_core[suspect_denominator])-SUM(risk_core[suspect_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| risk_core | suspect_numerator | Numerator — suspected gaps closed |
| risk_core | suspect_denominator | Denominator — total suspected gaps |
| static_churn_status | churn_status | Row dimension — groups rows in the matrix |