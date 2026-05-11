**Widget: Risk model/sub-models (Table)**

> 📷 *Insert: Cropped screenshot of the Risk model/sub-models table*

**Definition**

This table breaks down risk adjustment performance by risk model and sub-model, showing population size, documented and potential RAF scores, recapture rates, and open coding gaps.

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
| Eligible population | The count of members enrolled and eligible for risk adjustment scoring under each risk model and sub-model. | Rising values indicate a larger member pool subject to risk adjustment, expanding the scope of coding and gap closure efforts. | Falling values suggest membership attrition or eligibility changes that reduce the population available for risk capture activities. |
| Documented risk | The aggregate RAF score derived from HCC conditions that have already been coded and submitted for the eligible population. | Rising values reflect improved coding completeness, meaning more chronic and complex conditions are being captured and documented. | Falling values signal potential coding gaps, loss of previously documented conditions, or a healthier mix of members with fewer confirmed HCCs. |
| Gap to potential risk | The difference between the maximum potential RAF score (including suspected and dropped conditions) and the currently documented RAF score, representing uncaptured risk opportunity. | Rising values indicate a growing volume of unaddressed coding opportunities, suggesting that documentation efforts are not keeping pace with identified risk. | Falling values show that gaps are being closed and suspected conditions are being confirmed and coded, improving RAF completeness. |
| RAF recapture rate | The percentage of the total potential RAF score that has been successfully recaptured through confirmed coding of previously open or suspected HCC gaps. | Rising values demonstrate that a greater share of the potential risk score is being converted to documented risk, reflecting effective coding and clinical outreach programs. | Falling values indicate that fewer RAF points are being recaptured relative to the opportunity, signaling underperformance in gap closure workflows. |
| Risk recapture rate | The percentage of individual risk gaps (HCC-level opportunities) that have been successfully closed through confirmed diagnosis coding within the measurement period. | Rising values reflect stronger clinical engagement and documentation practices, with more HCC gaps being resolved per member. | Falling values suggest deteriorating gap closure efficiency, potentially due to reduced provider engagement, workflow barriers, or insufficient outreach. |
| Open gaps (Dropped) | The count of HCC conditions that were coded in a prior period but have not been recaptured or reconfirmed in the current period, representing lapsed diagnoses. | Rising values signal that previously documented conditions are going unaddressed, putting historical RAF scores at risk and indicating a need for retrospective coding review. | Falling values indicate successful recapture of lapsed conditions, preserving continuity of risk scores from prior periods. |
| Open gaps (Suspected) | The count of HCC conditions that have been algorithmically or clinically identified as likely present but not yet confirmed through a coded diagnosis in the current period. | Rising values reflect a growing pipeline of unconfirmed risk opportunities, which may indicate insufficient clinical visits, incomplete chart reviews, or delayed provider documentation. | Falling values show that suspected conditions are being evaluated and either confirmed through coding or appropriately ruled out, reducing the unresolved gap inventory. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| Large eligible population with high Gap to potential risk and low RAF recapture rate | Significant uncaptured revenue exists at scale; prioritize this risk model for targeted outreach campaigns and provider education to close coding gaps before the measurement year ends. |
| High Open gaps (Suspected) combined with low Risk recapture rate and moderate Documented risk | Members have probable but unconfirmed conditions that are not being pursued, understating true risk; deploy care managers to schedule diagnostic visits and validate suspected HCCs through clinical documentation. |
| Elevated Open gaps (Dropped) alongside a declining RAF recapture rate relative to sub-model peers | Previously captured conditions are not being re-documented in the current period, threatening RAF score regression; alert coders and PCPs to re-confirm chronic conditions at every eligible encounter. |
| Small eligible population with disproportionately high Gap to potential risk and high Open gaps (Suspected) | A concentrated high-complexity cohort is being under-coded, creating outsized per-member risk leakage; assign dedicated risk adjustment nurses to this sub-model for one-on-one chart review and in-home assessment scheduling. |

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

Risk recapture rate = DIVIDE(SUM(risk_core[recapture_numerator]),SUM(risk_core[recapture_denominator]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 833f191f-3194-4c8f-b39c-de1b45c3b006

Open gaps (Dropped) = SUM(risk_core[recapture_denominator])-SUM(risk_core[recapture_numerator])

Open gaps (Suspected) = SUM(risk_core[suspect_denominator])-SUM(risk_core[suspect_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| risk_core | suspect_numerator | Numerator — suspected gaps closed |
| risk_core | suspect_denominator | Denominator — total suspected gaps |
| measure | risk_model_name | Row dimension — groups rows in the matrix |
| measure | risk_model_sub_type | Row dimension — groups rows in the matrix |