**Widget: Payer/plan details (Table)**

> 📷 *Insert: Cropped screenshot of the Payer/plan details table*

**Definition**

This table summarizes risk adjustment performance metrics by payer and plan, showing how effectively each plan is identifying, targeting, and recapturing HCC-based risk gaps.

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
| Latest risk execution | The most recent date or run cycle on which the risk adjustment scoring and gap identification process was executed for the plan. | A more recent date indicates the plan's risk data is current and reflects up-to-date coding and gap analysis. | An older date suggests the risk execution is stale, meaning gap lists and RAF scores may not reflect the most recent clinical activity. |
| Targeted patients | The count of members who have been selected for outreach or intervention based on identified HCC coding gaps or risk recapture opportunities. | Rising counts indicate broader outreach efforts or a larger population with unresolved risk gaps requiring attention. | Falling counts may reflect successful gap closure reducing the actionable population, or a narrowing of targeting criteria. |
| Targeted gaps | The total number of HCC coding gaps identified across all targeted patients that have been flagged for clinical review and potential recapture. | More gaps signal a larger uncaptured risk opportunity, suggesting either a growing at-risk population or improved gap detection sensitivity. | Fewer gaps indicate successful closure of previously identified conditions or a reduction in the actionable risk opportunity pipeline. |
| Risk recapture rate cohort | The percentage of documented risk gaps within the cohort that have been successfully recaptured through confirmed HCC coding in the current period. | Higher rates reflect improved care manager and provider effectiveness in closing documented risk gaps through timely coding. | Lower rates signal that documented gaps are not being resolved, pointing to workflow, engagement, or coding compliance issues. |
| Potential Risk recapture rate cohort | — | — | — |
| RAF recapture rate cohort | The percentage of the total potential RAF score uplift that has actually been achieved through confirmed HCC recapture within the cohort. | Rising RAF recapture rates indicate that risk adjustment efforts are translating into measurable improvements in composite risk scores. | Declining rates signal that actual RAF gains are falling short of the identified opportunity, indicating execution or documentation gaps. |
| Potential RAF recapture rate cohort | The share of total RAF opportunity across all identified gaps — both confirmed and suspected — that remains available for recapture within the cohort. | An increasing potential rate means more RAF value is being surfaced through gap identification, expanding the opportunity for score improvement. | A decreasing potential rate suggests the pipeline of unaddressed RAF opportunity is being consumed, either through successful recapture or gap expiration. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| High targeted patients and targeted gaps but low risk recapture rate | The plan is identifying broad risk opportunities but failing to close them, indicating a workflow or engagement bottleneck; care managers should audit outreach effectiveness and prioritize high-RAF members for immediate intervention. |
| Large gap between potential RAF recapture rate and actual RAF recapture rate with recent latest risk execution | Despite a recent execution cycle, significant RAF value is being left uncaptured, signaling that coding completeness or provider documentation quality is underperforming; medical directors should initiate targeted coder education and retrospective chart review. |
| High potential risk recapture rate cohort but low targeted patients count | The plan holds substantial untapped risk value but is under-targeting its eligible population, representing a missed revenue and quality opportunity; analysts should expand member targeting criteria and refresh the gap identification algorithm. |
| RAF recapture rate cohort closely matching potential RAF recapture rate cohort with high targeted gaps | The plan is efficiently converting identified gaps into captured RAF, demonstrating a mature and effective risk adjustment program; this plan should be used as a benchmark model and its workflows replicated across underperforming plans. |

**Technical specification**

**DAX measure(s):**

Latest risk execution = CALCULATE(MAX(cohort[month_of_measurement]),ALL('date'))

Targeted patients = DISTINCTCOUNT(cohort[empi])+0
formatString: #,0
lineageTag: 97838794-e786-4b00-ae14-2f7d9508b327

Targeted gaps = COUNTROWS(cohort)+0

Risk recapture rate cohort = CALCULATE([Risk recapture rate], risk_core[max_month_flag]=TRUE())

Potential Risk recapture rate cohort = CALCULATE(
DIVIDE(
SUM(risk_core[recapture_numerator]) + [Targeted gaps],
SUM(risk_core[recapture_denominator]),
0
), KEEPFILTERS(risk_core[max_month_flag]=TRUE()
))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 29ab719a-6792-4bf8-b6d2-d58f9a09f892

RAF recapture rate cohort = CALCULATE([RAF recapture rate],risk_core[max_month_flag]=TRUE())

Potential RAF recapture rate cohort = var a = CALCULATE(sum(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented"}),risk_core[max_month_flag]=TRUE())
var b = CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented", "Undocumented"}),risk_core[max_month_flag]=TRUE())
var c = a + CALCULATE(sum(cohort[risk_value]))
var d = DIVIDE(c,b)
return
d

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| cohort | month_of_measurement | Source column — contributes to measure calculation |
| cohort | empi | Member identifier — distinct count for targeted patients |
| risk_core | max_month_flag | Source column — contributes to measure calculation |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| cohort | risk_value | HCC risk weight — summed for numerator or denominator |
| payer | payer_name | Row dimension — groups rows in the matrix |
| payer | plan_name | Row dimension — groups rows in the matrix |