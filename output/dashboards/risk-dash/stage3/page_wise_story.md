# Risk Management — Story Guide

**Dashboard:** Risk Management | **Pages:** Overview, Risk capture potential | **Last updated:** May 11, 2026


---

## About this guide

This dashboard tracks risk capture performance across a managed care population, measuring how well documented risk scores align with potential risk and where gaps remain. It helps risk management teams understand recapture rates, PMPM costs, and open coding gaps across payers, models, attribution statuses, providers, and disease categories. The reader should first understand the overall population size and risk score landscape before drilling into why gaps exist and who is driving them.

**The funnel:**

- **Top** → What is the current state of the population's risk capture — how large is the eligible population, what is documented vs. potential risk, and how do rates and costs look today?
- **Middle** → Why do risk capture gaps exist — how are metrics trending over time, and how do they break down by payer/plan, risk model/sub-model, and attribution status?
- **Bottom** → Who and what specifically is driving risk gaps — which practices, PCPs, disease categories, and operational channels (visit type, network, provider type) are responsible?
- **Action** → Which members and providers should be prioritized for outreach and risk recapture interventions based on open coding gaps and recapture rate performance?



---

## Page 1: Overview


---

## Layer 1: The risk position


---

### Population & Risk Landscape KPI Cards

> *📷 Insert: Screenshot of KPI cards — Eligible population, #Members, Documented risk, Potential risk, Gap to potential risk, Dropped+Suspected, with their YoY multiRowCard indicators*

This KPI row establishes the full risk landscape for the attributed population: how many patients are in scope, what risk has been formally documented, what risk the clinical evidence suggests is achievable, and how large the gap between those two states is. These six cards should be read as a connected system — population size sets the denominator, documented and potential risk define the performance corridor, and the gap and dropped/suspected cards reveal where value is being left on the table.

### Eligible population

The count of patients who have at least one documented risk entry in the risk core dataset, filtered to records flagged as 'Documented.' This represents the subset of the attributed membership for whom a formal risk score has been captured and is active in the current measurement period.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                    |
|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | More patients have been formally risk-documented, which may reflect expanded outreach, improved coding workflows, or growth in the attributed panel. Verify whether the increase is proportional to overall membership growth or whether documentation rates are genuinely improving relative to the total attributed population. |
| Decreasing | Fewer patients carry an active documented risk record, which could signal patient attrition, lapses in annual wellness visits or HCC coding encounters, or administrative gaps in risk capture. A declining eligible population while #Members holds steady is a documentation quality warning sign.                              |


*Eligible population should always be compared to #Members — a widening gap between the two indicates a growing share of attributed members with no documented risk on file.*

### #Members

The total count of members attributed to the organization, drawn directly from the attribution table. This is the broadest population denominator and represents everyone the organization is accountable for under its risk-bearing contracts, regardless of whether a risk score has been documented.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                        |
|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | The attributed panel is growing, which expands both the revenue opportunity and the documentation workload. If Eligible population does not grow proportionally, the organization is taking on more members without capturing their risk, which will suppress average documented risk scores and understate true clinical complexity. |
| Decreasing | Panel shrinkage may reflect attribution losses, plan disenrollment, or contract changes. A declining member count that is not accompanied by a proportional drop in Eligible population suggests the remaining members are more consistently documented — a positive quality signal within a concerning volume trend.                 |


### Documented risk

The average risk score per patient across all patients with a documented risk flag, calculated as total documented risk value divided by the documented patient count. This metric reflects the average clinical complexity that has been formally coded and submitted for the eligible population.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | The average documented risk score is rising, which may indicate that sicker or more complex patients are being enrolled, that coding specificity is improving and capturing conditions previously undercoded, or that care management is successfully identifying and documenting chronic conditions. Cross-check against Potential risk — if both rise together, the population is genuinely more complex; if Documented risk rises while Potential risk holds flat, documentation quality is improving. |
| Decreasing | Average documented risk is falling, which could mean healthier patients are being attributed, that previously documented conditions are not being recaptured in the current year, or that coding encounters are being missed. A declining Documented risk alongside a stable or rising Potential risk is a direct signal of documentation regression and should trigger a coding audit.                                                                                                                   |


*Documented risk is the realized portion of the risk story — it must always be read alongside Potential risk to understand how much of the clinical complexity the organization is actually capturing.*

### Potential risk

The average risk score per patient that the organization could achieve if all suspected, dropped, and documented risk were fully captured and coded, calculated as total risk value across all risk documentation flag types divided by the total patient count. This represents the clinical ceiling — the risk score the population's full condition burden supports.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                                             |
|------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | The population's total clinical complexity is growing, either because sicker patients are being attributed or because analytics are surfacing more suspected conditions. An increasing Potential risk that is not matched by an increasing Documented risk means the gap is widening and more value is at risk of being uncaptured.                                        |
| Decreasing | The ceiling on achievable risk is contracting, which may reflect a healthier incoming cohort, successful care management reducing chronic condition burden, or a reduction in suspected conditions being surfaced by risk models. If Documented risk holds steady while Potential risk falls, the organization is actually closing the gap — a positive efficiency signal. |


*Potential risk sets the ceiling that Documented risk should be trending toward — the distance between them is precisely what Gap to potential risk quantifies.*

### Gap to potential risk

The difference between Potential risk and Documented risk, representing the average per-patient risk score that is clinically supported but has not yet been formally documented or coded. This is the primary measure of unrealized risk capture opportunity across the eligible population.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                             |
|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | The organization is falling further behind its documentation potential — more clinical complexity is being identified by risk models than is being captured in formal coding. This warrants investigation into whether outreach is failing, coding encounters are not occurring, or suspected conditions are not being confirmed and documented at visits. |
| Decreasing | Documentation is catching up to clinical potential, meaning coding workflows, outreach programs, or care management interventions are successfully converting suspected and dropped conditions into documented risk. A shrinking gap is the primary operational success signal for a risk documentation program.                                           |


*Gap to potential risk is the single most actionable number in this row — it directly quantifies the documentation work remaining and should be tracked against Dropped + Suspected to understand what is driving the gap.*

### Dropped + suspected

The combined average risk value per patient attributable to conditions that are either suspected (identified by risk models but not yet confirmed at a clinical encounter) or dropped (previously documented but not recaptured in the current measurement year). This metric reveals the composition of the gap — how much is new opportunity versus recapture failure.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                                           |
|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | More risk is accumulating in unresolved states — either more conditions are being flagged as suspected without follow-through at encounters, or a larger share of previously documented conditions are not being recaptured annually. A rising Dropped + Suspected alongside a rising Gap to potential risk confirms that the documentation pipeline is backing up and requires targeted intervention by condition category or provider. |
| Decreasing | Fewer conditions are sitting in unresolved states, which means outreach and coding workflows are successfully converting suspected conditions to documented and recapturing previously dropped diagnoses. If this decrease is accompanied by a rising Documented risk, the pipeline is functioning as intended.                                                                                                                          |


*Dropped + Suspected is the operational decomposition of Gap to potential risk — understanding whether the gap is driven by new suspected conditions or by recapture failures determines which intervention (outreach vs. annual visit coding) should be prioritized.*

### Reading the cards together

| Pattern                                                            | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                                          |
|--------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| #Members ↑, Eligible population flat or ↓, Gap to potential risk ↑ | The attributed panel is growing but documentation is not keeping pace — new members are being added without corresponding risk documentation encounters. The widening gap is partly a volume problem, not just a coding quality problem. Leadership should assess whether onboarding workflows include a risk documentation touchpoint within the first measurement period.                                                             |
| Documented risk ↑, Potential risk flat, Gap to potential risk ↓    | This is the ideal documentation improvement scenario: coding is getting more specific and complete without the clinical complexity ceiling rising. The organization is not just seeing sicker patients — it is doing a better job capturing the complexity that was always there. Dropped + Suspected should also be declining in this scenario.                                                                                        |
| Potential risk ↑, Documented risk flat, Dropped + Suspected ↑      | Risk models are surfacing more suspected conditions but clinical encounters are not converting them to documented diagnoses. The gap is widening from the top down — the ceiling is rising while the floor holds. This pattern points to an outreach or scheduling failure rather than a coding specificity problem, and should trigger review of suspected condition follow-up rates by care team.                                     |
| Documented risk ↓, Dropped + Suspected ↑, Gap to potential risk ↑  | Previously documented conditions are falling off without being recaptured, and they are accumulating in the 'dropped' bucket. This is a recapture failure pattern — annual wellness visits or chronic condition management encounters are either not occurring or not resulting in diagnosis coding. A coding audit focused on patients with year-over-year risk score decline is warranted.                                            |
| Eligible population ↑, #Members flat, Documented risk ↓            | More patients have a documentation record, but the average documented risk score is falling. This suggests the newly documented patients are lower-acuity, which dilutes the average. This is not necessarily a problem — it may reflect successful outreach to healthier members — but it should be distinguished from a scenario where high-acuity patients are losing their documentation status.                                    |
| Gap to potential risk ↓, Dropped + Suspected ↓, Documented risk ↑  | All three documentation performance indicators are moving in the right direction simultaneously: the gap is closing, fewer conditions are in unresolved states, and average documented risk is rising. This is the signature of a functioning end-to-end risk documentation program — suspected conditions are being confirmed, dropped conditions are being recaptured, and the coding is translating into higher average risk scores. |




---

### Performance Rate & Cost KPI Cards

> *📷 Insert: Screenshot of KPI cards — Risk recapture rate, RAF recapture rate, PMPM, % members with open coding gaps, with their YoY multiRowCard indicators*

These four KPI cards together describe the organization's current-year risk coding performance, cost efficiency, and remaining documentation opportunity. They should be read as a system: recapture rates reflect work completed, PMPM reflects cost impact, and open coding gaps reflect work still outstanding.

### Risk recapture rate

Measures the proportion of previously identified risk conditions that have been successfully recaptured — that is, documented and coded — in the current period. It is calculated as the sum of recapture numerator events divided by the sum of eligible recapture denominator events in the risk_core table.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                            |
|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | More previously identified risk conditions are being successfully recaptured through clinical encounters or retrospective coding. This signals improving care gap closure workflows, stronger provider engagement, or more effective outreach. Verify that recapture is driven by genuine clinical documentation rather than administrative coding alone. |
| Decreasing | Fewer eligible risk conditions are being recaptured relative to the denominator. This may indicate provider documentation gaps, reduced patient visit frequency, or outreach program underperformance. Investigate whether the denominator is growing faster than the numerator — which would suggest a widening backlog of unaddressed risk conditions.  |


*Risk recapture rate should always be read alongside % Members with Open Coding Gaps — a high recapture rate paired with a high open gap rate suggests the organization is closing known gaps but new or persistent gaps are accumulating faster than they are resolved.*

### RAF recapture rate

Measures the share of Risk Adjustment Factor (RAF) value that has been recaptured through documented and coded diagnoses, calculated from risk_core records flagged with an active risk documentation status. Unlike the volume-based risk recapture rate, this metric is weighted by the RAF value of each condition, making it sensitive to whether high-acuity, high-weight diagnoses are being recaptured.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | A greater share of the total RAF value associated with known risk conditions is being documented and submitted. This signals that higher-acuity or higher-weight diagnoses are being successfully recaptured, which will positively affect risk-adjusted revenue and quality benchmarks. Confirm that increases are driven by clinically appropriate documentation of complex conditions, not by coding of lower-weight diagnoses inflating the numerator count. |
| Decreasing | High-value RAF conditions are being missed or not recaptured at the same rate as lower-weight conditions. This can suppress risk-adjusted revenue even when the volume-based risk recapture rate appears stable. Investigate whether specific chronic condition categories — such as HCC clusters for diabetes with complications or CHF — are underperforming in documentation rates.                                                                           |


*When RAF recapture rate diverges from Risk recapture rate — one rising while the other falls — it signals a mismatch between the volume and acuity of recaptured conditions, which warrants a condition-level drill-down.*

### PMPM

Per Member Per Month cost, calculated as total year-to-date visit amount divided by total year-to-date member count from the attribution table. This metric reflects the average monthly cost of care being delivered across the attributed population and serves as a high-level indicator of utilization intensity and cost efficiency.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | Average monthly cost per member is rising, which may reflect higher utilization, increased acuity in the attributed population, unit cost increases, or a shift in the mix of services being delivered. An increase is not inherently negative — if risk recapture rates are also rising, higher PMPM may reflect appropriate care delivery for a more accurately documented, higher-acuity population. Investigate whether cost growth is concentrated in specific service categories or member segments. |
| Decreasing | Average monthly cost per member is falling, which may indicate improved care management efficiency, reduced unnecessary utilization, or a shift toward lower-acuity members in the attributed population. However, a declining PMPM alongside declining recapture rates may signal reduced engagement — members are not being seen, which suppresses both cost and coding opportunity simultaneously.                                                                                                      |


*PMPM should be interpreted in the context of RAF recapture rate — a rising PMPM with a rising RAF recapture rate suggests cost is tracking with appropriately documented acuity, while a rising PMPM with flat or declining recapture rates may indicate unmanaged utilization.*

### % Members with Open Coding Gaps

Represents the count of attributed members who currently have at least one open coding gap — a condition that has been identified as a risk but has not yet been documented or recaptured in the current period. This metric is drawn directly from the attribution table and reflects the remaining documentation opportunity across the population.

| Direction  | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                                |
|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Increasing | More members have unresolved coding gaps, meaning the organization's risk documentation workload is growing. This could reflect new gap identification from predictive models or prior-year lookback, declining outreach effectiveness, or a growing attributed population with unaddressed chronic conditions. A rising open gap count late in the measurement year is a critical signal requiring prioritized intervention. |
| Decreasing | Fewer members have open coding gaps, indicating that gap closure efforts — through visits, retrospective coding, or outreach — are working. Confirm that the decrease reflects genuine documentation completion rather than gap suppression or member attribution loss. A declining open gap count paired with rising recapture rates is the strongest signal of a well-functioning risk program.                             |


*% Members with Open Coding Gaps is the leading indicator of future recapture rate performance — if open gaps remain high as the measurement year progresses, both Risk and RAF recapture rates are at risk of falling short of targets.*

### Reading the cards together

| Pattern                                                                | Interpretation                                                                                                                                                                                                                                                                                                                                                                                              |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Risk recapture rate ↑, RAF recapture rate ↓, % Open coding gaps stable | The organization is closing a high volume of coding gaps but is disproportionately recapturing low-acuity, low-RAF-weight conditions. High-value chronic conditions are likely being missed or deferred. This pattern inflates recapture volume metrics while suppressing risk-adjusted revenue impact — a condition-level review of HCC categories is warranted.                                           |
| Risk recapture rate ↑, RAF recapture rate ↑, PMPM ↑                    | The organization is successfully recapturing both the volume and acuity of risk conditions, and cost is rising in alignment with a more accurately documented, higher-acuity population. This is the expected pattern of a maturing risk program — cost growth here is likely appropriate and defensible under risk-adjusted benchmarks.                                                                    |
| % Open coding gaps ↑, Risk recapture rate ↓, RAF recapture rate ↓      | The gap backlog is growing while recapture performance is declining — a compounding risk signal. This combination suggests that outreach and documentation workflows are falling behind the pace of gap identification, and that the organization may face significant RAF revenue shortfalls if the trend continues into the final months of the measurement year.                                         |
| PMPM ↓, % Open coding gaps ↑                                           | Members are being seen less frequently (suppressing cost) while coding gaps remain open and unresolved. This pattern suggests reduced care engagement across the attributed population — members with chronic conditions are not receiving visits, which simultaneously reduces utilization cost and eliminates the clinical encounter opportunity needed to close coding gaps.                             |
| RAF recapture rate ↑, % Open coding gaps ↓, PMPM stable                | High-acuity conditions are being recaptured efficiently and the open gap inventory is shrinking, without a corresponding spike in cost. This signals effective, targeted outreach — the organization is closing the right gaps through existing care touchpoints rather than generating incremental utilization. This is the most operationally efficient pattern in this KPI row.                          |
| Risk recapture rate ↑, % Open coding gaps ↑ simultaneously             | Recapture activity is increasing, but the open gap count is also rising — indicating that new gaps are being identified or attributed members are being added faster than existing gaps are being closed. The organization may be expanding its gap identification program without proportionally scaling its closure capacity. Evaluate whether gap identification and gap closure resources are balanced. |




---

### Payer/Plan Segmentation

> *📷 Insert: Screenshot of Payer/plan details pivot table — Members, Documented risk, Gap to potential risk, PMPM, RAF recapture rate, Risk recapture rate by Payer/plan*

This table breaks the attributed population down by payer and plan, exposing how risk profile, revenue capture, and documentation performance vary across contractual relationships. At the top of the funnel, it answers which payers and plans are driving or diluting overall risk management performance.

**Key columns:**

| Column                | What to look for                                                                                                                                                                                                                                                                    |
|-----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Members               | The attributed member count for each payer/plan row. Watch for plans with disproportionately large membership relative to their risk capture metrics — high volume with poor recapture rates has outsized revenue impact.                                                           |
| Documented risk       | The average or aggregate RAF score based on conditions that have been coded and submitted. Watch for plans where documented risk is significantly lower than expected given the member demographics, which may indicate documentation gaps rather than a healthier population.      |
| Gap to potential risk | The difference between potential risk (based on suspected or historical conditions) and documented risk. A large gap signals that significant RAF value is being left uncaptured; prioritize plans where this gap is wide and membership is high.                                   |
| PMPM                  | Per-member-per-month revenue or cost for each plan. Watch for plans where PMPM is low relative to documented risk scores, which may indicate underpayment or risk adjustment reconciliation issues.                                                                                 |
| RAF recapture rate    | The percentage of RAF value from the prior period that has been successfully recaptured in the current period. Rates below organizational benchmarks indicate chronic conditions are not being re-documented annually as required.                                                  |
| RAF RR YoY change     | Year-over-year change in the RAF recapture rate. A declining trend is a leading indicator of worsening documentation compliance or reduced patient engagement; a sudden drop warrants immediate investigation.                                                                      |
| Risk recapture rate   | The percentage of total risk (broader than RAF alone) that has been recaptured. Compare this to the RAF recapture rate — a large divergence between the two may indicate model-specific coding issues or payer-specific submission rules affecting one measure more than the other. |
| Risk RR YoY change    | Year-over-year change in the risk recapture rate. Watch for plans where this is declining while RAF RR YoY is stable, or vice versa, as asymmetric trends can reveal payer-specific risk model changes or submission timing problems.                                               |


**Critical patterns:**

| Pattern                                                                                           | Interpretation                                                                                                                                                                                                                                                 |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| High Members + Large Gap to potential risk + Low RAF recapture rate                               | A high-volume plan is systematically failing to close documentation gaps, representing the largest absolute revenue risk exposure in the portfolio. This combination should be the first escalation priority.                                                  |
| Low PMPM + High Documented risk                                                                   | The plan is carrying a sicker-than-average population but receiving below-average revenue per member, suggesting a risk adjustment reconciliation problem, a submission lag, or a payer contract issue that needs financial review.                            |
| Negative RAF RR YoY change + Negative Risk RR YoY change across multiple plans                    | A broad, multi-plan decline in both recapture metrics points to a systemic operational issue — such as a workflow change, coding staff turnover, or EHR transition — rather than a plan-specific problem.                                                      |
| RAF RR YoY change positive while Risk RR YoY change is negative (or vice versa) for the same plan | Asymmetric year-over-year trends between the two recapture rate measures suggest a payer-specific risk model update or a change in submission rules that is affecting one scoring methodology but not the other; validate with the payer contract team.        |
| Small Members + Very High Gap to potential risk                                                   | A small plan with a disproportionately large risk gap may indicate a concentrated high-acuity population that is under-engaged in care; while the absolute dollar impact is smaller, the per-member opportunity is high and may reflect a care management gap. |


*The Gap to potential risk column is the most actionable metric in this table — a plan can show acceptable recapture rates and still carry a massive uncaptured RAF gap if the potential risk baseline is high, so always read gap size in conjunction with recapture rate, not as a substitute for it.*



---

## Layer 2: The diagnosis


---

### Metric Trends Over Time

> *📷 Insert: Screenshot of All line charts — Eligible population, Documented risk vs potential risk, Risk recapture rate, RAF recapture rate, PMPM, Members trends (current year vs previous year)*

These trend line charts layer current-year performance month by month against the prior year, allowing analysts to distinguish seasonal patterns from true year-over-year improvement or deterioration. Reading the charts as a system reveals whether population growth, risk documentation, recapture rates, and cost are moving in alignment or diverging in ways that require intervention.

### Members and Eligible Population Trends

These charts track the month-by-month count of enrolled members and the eligible population — the broader universe of individuals who qualify for risk management programs — comparing the current year line against the prior year line. The comparison establishes whether the denominator driving all other metrics is growing, shrinking, or stable, which is essential context for interpreting any rate-based or absolute measure elsewhere on the dashboard.

| Pattern                                          | Interpretation                                                                                                                                                                                                          |
|--------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Current year line tracking above prior year line | Population is growing year-over-year; absolute risk and cost metrics will naturally be higher, so rate-based metrics should be used for fair comparison.                                                                |
| Current year line tracking below prior year line | Population contraction may indicate attribution loss, eligibility changes, or disenrollment — investigate whether risk scores and PMPM are being affected by a healthier or sicker residual population.                 |
| Lines diverging mid-year                         | A mid-year shift in eligible population or membership often signals a contract change, eligibility redetermination, or data pipeline issue that should be validated before drawing conclusions from other trend charts. |


### Documented Risk vs Potential Risk Trend

This chart plots three lines — current-year documented risk, prior-year documented risk, and a potential risk ceiling — showing how much of the clinically identifiable risk has been captured through coding and documentation each month relative to what is theoretically achievable. The gap between the potential line and the documented lines is the unrealized risk opportunity, and the year-over-year comparison reveals whether documentation practices are improving or regressing.

| Pattern                                                               | Interpretation                                                                                                                                                         |
|-----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Current year documented line rising toward the potential line         | Documentation and coding efforts are closing the risk gap; the program is capturing a greater share of clinically supported risk scores.                               |
| Current year line above prior year line but both well below potential | Year-over-year improvement is occurring but significant untapped risk remains — prioritize outreach to members with unconfirmed conditions.                            |
| Current year line below prior year line                               | Documentation is regressing; this may reflect provider engagement issues, coding workflow changes, or a shift in population mix that warrants immediate investigation. |
| Potential line rising steeply while documented lines flatten          | The risk opportunity is expanding faster than documentation can keep pace — the gap is widening and recapture rate will likely decline in subsequent months.           |
| All three lines converging                                            | Near-complete risk capture; focus shifts to maintaining documentation quality and validating that the potential ceiling is accurately modeled.                         |


*If the gap between the potential line and the current-year documented line is widening in recent months, cross-reference the Risk Recapture Rate trend immediately — a declining recapture rate confirms a systemic documentation shortfall rather than a one-month anomaly.*

### Risk Recapture Rate and RAF Recapture Rate Trends

These charts track the percentage of identified risk conditions and RAF (Risk Adjustment Factor) scores that have been successfully recaptured through documented encounters in the current year versus the prior year, month by month. Together they measure the effectiveness of the risk closure process — risk recapture rate reflects condition-level completeness while RAF recapture rate translates that into the financial and regulatory scoring impact, making the pair essential for evaluating both clinical and revenue cycle performance.

| Pattern                                                                | Interpretation                                                                                                                                                                  |
|------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Current year line consistently above prior year line on both charts    | Recapture workflows are improving year-over-year across both clinical and financial dimensions — a strong signal of program maturity.                                           |
| Risk recapture rate improving but RAF recapture rate flat or declining | More conditions are being documented but higher-weighted RAF conditions are being missed; review which HCC categories are underperforming.                                      |
| Both lines declining in the second half of the year                    | Typical seasonal pattern if providers reduce outreach late in the year; if steeper than prior year, it may indicate provider fatigue or insufficient chase list follow-through. |
| Sharp single-month drop in current year line                           | Likely a data submission lag or encounter processing delay rather than a true performance drop — validate data completeness before escalating.                                  |


### PMPM Trend

This chart tracks the per-member-per-month cost or premium equivalent month by month for the current year versus the prior year, providing a normalized view of financial performance that accounts for population size fluctuations. The year-over-year comparison helps analysts determine whether cost trends are accelerating, decelerating, or holding steady relative to the prior period, and whether changes in risk documentation are translating into expected financial outcomes.

| Pattern                                                            | Interpretation                                                                                                                                                    |
|--------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Current year line rising above prior year line                     | Per-member costs are increasing year-over-year; assess whether this is driven by higher acuity documentation, utilization increases, or unit cost inflation.      |
| Current year line below prior year line despite higher risk scores | Risk documentation improvements have not yet translated into expected PMPM — check for payment lag, risk score submission timing, or model recalibration effects. |
| Lines tracking closely with parallel slope                         | Cost trend is stable year-over-year; the program is maintaining consistent financial performance relative to the prior period.                                    |
| Current year line diverging upward sharply mid-year                | An unexpected cost spike warrants investigation into high-cost member events, changes in eligible population mix, or a data anomaly.                              |




---

### Risk Model / Sub-Model Breakdown

> *📷 Insert: Screenshot of Risk model/sub-models pivot table — Eligible population, Documented risk, Gap to potential risk, RAF recapture rate, Risk recapture rate, Open gaps by Model/sub-model*

This table disaggregates risk performance by risk model and sub-model, revealing whether documentation gaps and recapture shortfalls are concentrated in specific model types or spread across the portfolio. At the middle of the funnel, it answers the critical question of where eligible risk is being left on the table and whether recapture efforts are appropriately targeted by model.

**Key columns:**

| Column                | What to look for                                                                                                                                                                                                                                                                                                                                                                          |
|-----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Eligible Population   | The count of members assigned to each risk model or sub-model. Watch for models with disproportionately large populations relative to their recapture performance — a large eligible base with poor recapture rates signals a systemic documentation problem at scale.                                                                                                                    |
| Documented Risk       | The total risk score or RAF value that has been successfully documented for the eligible population in each model. Compare this against eligible population size to assess documentation density; a low documented risk relative to population size suggests under-coding or incomplete encounter capture.                                                                                |
| Gap to Potential Risk | The difference between potential risk and documented risk — the uncaptured RAF opportunity remaining for each model. Large gaps in high-population models represent the greatest financial and quality exposure; prioritize models where this gap is both large in absolute terms and persistent year over year.                                                                          |
| RAF Recapture Rate    | The percentage of the prior-year RAF that has been recaptured in the current period for each model. Rates significantly below benchmark (typically 85–90%) indicate that chronic conditions documented last year are not being re-documented this year, which will cause RAF scores to decay.                                                                                             |
| Risk Recapture Rate   | Similar to RAF recapture but measured against the broader risk score framework for the model. Compare this to the RAF recapture rate within the same row — a divergence between the two rates can indicate model-specific coding behavior or that certain condition categories are being selectively recaptured.                                                                          |
| Open Gaps (Dropped)   | The count of risk conditions that were documented in a prior period but have not yet been recaptured in the current period — conditions at risk of being lost from the risk score. High dropped gap counts in a model signal that outreach or visit completion for known chronic conditions is failing for that population segment.                                                       |
| Open Gaps (Suspected) | The count of conditions suspected based on claims, labs, or predictive models but not yet documented in the current period. A high suspected gap count relative to eligible population indicates significant prospective coding opportunity; watch for models where suspected gaps far exceed dropped gaps, as this points to net-new documentation potential rather than recapture work. |


**Critical patterns:**

| Pattern                                                                                                         | Interpretation                                                                                                                                                                                                                                                                                                                     |
|-----------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A model row shows a large Gap to Potential Risk alongside a low RAF Recapture Rate and high Open Gaps (Dropped) | This model is experiencing active RAF score decay — conditions are being lost from year to year and not replaced. This is the highest-priority intervention target because the financial impact compounds: the gap grows while the recapture rate falls.                                                                           |
| A model row shows a high Eligible Population but Open Gaps (Suspected) far exceeds Open Gaps (Dropped)          | The model has a large net-new coding opportunity rather than a recapture problem. The population likely has under-documented comorbidities that have never been formally coded, requiring prospective outreach and clinical review rather than standard recapture workflows.                                                       |
| RAF Recapture Rate and Risk Recapture Rate diverge significantly within the same model row                      | The two rate methodologies are capturing different condition sets or weighting them differently for this model. Investigate whether specific HCC categories or high-weight conditions are being systematically missed, as this divergence often points to a coding pattern issue rather than a general access or outreach problem. |
| A sub-model row shows markedly worse performance than its parent model row across all metrics                   | The sub-model population has a distinct care access or documentation challenge that is being masked in the rolled-up model view. Sub-model-level intervention planning is needed; relying on model-level averages will cause this segment to be under-resourced.                                                                   |


*The Gap to Potential Risk column is only actionable when read alongside Open Gaps (Dropped) vs. Open Gaps (Suspected) — a large gap driven by dropped conditions requires recapture outreach, while one driven by suspected conditions requires prospective coding strategy; conflating the two leads to misallocated intervention resources.*



---

### Attribution Status Breakdown

> *📷 Insert: Screenshot of Risk breakdown by attribution status pivot table — Eligible population, Documented risk, Gap to potential risk, Recapture rates, Open gaps by Attribution status*

This table segments the member population by attribution status — Continued, Discontinued, and Newly Enrolled — to reveal how risk capture performance and open gap burden differ across members at different stages of the care relationship. It answers the middle-funnel question of whether risk documentation gaps are concentrated in stable long-term members or driven by population churn.

| Status         | Expected behavior                                                                                                                                                                                                                                                                                                                                                                                                             | Red flag                                                                                                                                                                                                                                                                                                                                                                                                                |
|----------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Continued      | This segment should carry the highest eligible population and the strongest RAF recapture rate and Risk recapture rate, since these members have an established care history enabling more complete documentation. Gap to potential risk should be relatively low, YoY recapture trends should be stable or improving, and open gaps (both Dropped and Suspected) should be manageable given prior-year coding as a baseline. | A high Gap to potential risk or declining RAF RR YoY change in this segment is a serious warning — it means the program is losing ground on its most documentable, highest-opportunity population. Elevated open Suspected gaps here suggest chronic conditions are going unrecaptured year over year despite member continuity, pointing to a provider engagement or coding workflow failure.                          |
| Discontinued   | Discontinued members should show a smaller eligible population relative to Continued, with recapture rates that are lower by nature since documentation opportunities ended mid-cycle. Open gaps (Dropped) are expected to be elevated here, as these members left before gaps could be closed. This segment primarily serves as a loss-quantification row rather than an actionable one.                                     | A disproportionately large eligible population in this segment relative to Continued signals high churn that is eroding the risk-bearing base. If open Suspected gaps are also high, it indicates the program is losing members who still carry unresolved risk — those conditions may resurface as undocumented liability in future periods or in other payers' books.                                                 |
| Newly Enrolled | New entrants should show lower documented risk and lower recapture rates than Continued members, which is expected since there is no prior-year coding history to build from. Gap to potential risk may appear elevated simply due to baseline uncertainty. What matters most is that open Suspected gaps are being actively worked and that YoY change metrics are not yet penalizing the overall program average.           | If Newly Enrolled members show a very high Gap to potential risk combined with low Risk recapture rate and a large open Suspected gap count, it signals that onboarding workflows are failing to initiate timely risk assessments. This is operationally urgent because the longer new members go without an initial HCC-relevant encounter, the more potential RAF value is permanently lost for the measurement year. |


*Discontinued members' open Dropped gaps represent RAF value that cannot be recovered — if this row's eligible population is large, the program's overall recapture rate may look artificially suppressed, masking stronger performance in the Continued segment that warrants separate benchmarking.*



---

## Layer 3: The action


---

### Risk Recapture Rate by Disease / Risk Factor

> *📷 Insert: Screenshot of Risk recapture rate by disease bar chart and Risk factor details table — recapture rate, open gaps (Dropped/Suspected) by disease/risk factor*

This section shifts the analytical lens from which practices or PCPs are underperforming to which specific disease categories and risk factors are driving those gaps. By ranking conditions on recapture rate and open coding gaps, it surfaces the clinical areas where documentation and risk closure efforts should be concentrated.

### Risk recapture rate by disease

This chart ranks disease categories along the horizontal axis by their Risk Recapture Rate — the share of eligible patients whose risk for that disease was successfully documented and closed in the current period. A condition positioned toward the left (lower value) has a poor recapture rate, meaning a large proportion of known or suspected risk is going uncaptured, while a condition toward the right (higher value) has strong documentation closure for that disease group. Overlaid measures for Open Gaps (Dropped) and Open Gaps (Suspected) add volume context, and the Risk Recapture Rate Change % indicates whether each disease category is trending better or worse year-over-year.

| Pattern                                                                                               | Interpretation                                                                                                                                                                                                                                                                                                                                                               |
|-------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A disease category with a very low recapture rate positioned at the far left                          | This disease group has the highest proportion of eligible patients whose risk is not being recaptured. It represents the most urgent clinical documentation gap — outreach, coding education, or care gap closure workflows should be prioritized for this condition immediately.                                                                                            |
| A disease category with a large volume of Open Gaps (Dropped) alongside a low recapture rate          | Conditions that were coded in a prior period but not reconfirmed this year are actively eroding the risk score. This pattern signals a recapture failure — patients exist in the system but their conditions are not being re-documented at visits, requiring targeted recall or annual wellness visit campaigns.                                                            |
| A disease category with a large volume of Open Gaps (Suspected) but a moderate recapture rate         | Suspected gaps indicate patients flagged by predictive models or claims data as likely having the condition but lacking a confirmed code. A high suspected gap volume means there is significant upside potential if clinical teams can validate and document these conditions, making this a high-yield opportunity for prospective coding.                                 |
| A chronic condition (e.g., diabetes, heart failure, CKD) with a negative Risk Recapture Rate Change % | Chronic conditions are expected to be recaptured annually because they persist year over year. A declining trend in recapture rate for a chronic disease is a serious signal — it suggests worsening documentation discipline or reduced patient engagement, and should be escalated to clinical leadership given the compounding impact on risk scores over multiple years. |


### Risk factor details

| Column                  | What to look for                                                                                                                                                                                                                                                                                                                                                   |
|-------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Risk Factor Description | The plain-language name of the specific risk factor or HCC-mapped condition within a disease category. Use this to identify the precise clinical concept driving a gap, moving from the broad disease group in the bar chart down to the actionable diagnosis-level detail.                                                                                        |
| Risk Factor Code        | The HCC or clinical code associated with the risk factor. Cross-reference this with coding teams to confirm whether the correct code is being applied at the point of care; mismatches between expected and submitted codes are a common source of recapture failure.                                                                                              |
| Eligible Population     | The total number of patients who qualify for risk recapture under this risk factor. Large eligible populations with low recapture rates represent the highest absolute impact opportunities — prioritize these over small populations even if their recapture rate is similarly low.                                                                               |
| Documented Risk         | The count of patients whose risk for this factor has been successfully documented and coded in the current period. Compare this against the Eligible Population to understand the raw closure volume; a large gap between the two confirms a significant documentation shortfall.                                                                                  |
| Gap to Potential Risk   | The difference between the potential risk that could be captured and what has actually been documented. A large gap here quantifies the financial and quality impact of under-coding for this risk factor and should be used to prioritize intervention resources.                                                                                                 |
| Risk Recapture Rate     | The percentage of eligible patients for whom this risk factor has been successfully recaptured. This is the primary performance metric — any risk factor below the organizational benchmark warrants investigation into whether the issue is access, coding practice, or patient engagement.                                                                       |
| Risk RR YoY Change      | The year-over-year change in recapture rate for this risk factor. A declining trend signals deteriorating performance that may not yet be visible in absolute rates; a consistently negative trend across multiple risk factors within the same disease group points to a systemic problem rather than an isolated one.                                            |
| Open Gaps (Dropped)     | The number of patients who had this risk factor coded in a prior period but have not had it reconfirmed in the current period. High dropped gap counts for chronic or persistent conditions are the most actionable signal — these patients are known and simply need to be seen and recoded before the measurement period closes.                                 |
| Open Gaps (Suspected)   | The number of patients flagged as likely having this risk factor based on predictive models, claims history, or lab data, but who lack a confirmed code. High suspected gap counts indicate prospective coding opportunities — clinical teams should review these patients to validate and document the condition, converting suspected gaps into documented risk. |


*Prioritize the disease categories with the lowest recapture rates and the largest volumes of Dropped open gaps first — these represent conditions that were already coded and simply need reconfirmation, making them the fastest, highest-certainty path to recovering risk score before the measurement period ends.*



---

### Practice / PCP Entity Performance

> *📷 Insert: Screenshot of Practice/PCP details pivot table and scatter chart — Members, risk metrics, recapture rates, open gaps by Practice/PCP with scatter plot of same entity population*

This section translates the aggregate risk management story into specific, accountable practice and PCP names, enabling analysts to identify exactly which entities are driving the largest risk gaps, lowest recapture rates, and highest volumes of unresolved coding gaps. Each row and scatter point represents a named practice or PCP, making this the primary layer for directing targeted outreach, coding education, and intervention prioritization.

This table breaks down risk performance to the practice and PCP level, showing each entity's attributed member panel alongside documented risk, unrealized risk potential, cost efficiency, recapture rates and their year-over-year trends, and the volume and type of open coding gaps. It serves as the operational accountability layer — identifying which specific providers are underperforming on risk capture and where coding gap backlogs are concentrated.

**Key columns:**

| Column                          | What to look for                                                                                                                                                                                                                                                                               |
|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Members                         | The size of the attributed member panel for this practice or PCP. Larger panels amplify the impact of any performance gap — a low recapture rate on a large panel represents a proportionally larger revenue and quality risk than the same rate on a small panel.                             |
| Documented risk                 | The total RAF-based risk score that has been formally documented and submitted for this entity's panel. Look for entities whose documented risk is significantly lower than their potential risk, which signals incomplete or missed coding.                                                   |
| Gap to potential risk           | The difference between the entity's potential risk (based on suspected and historical conditions) and their documented risk. A large gap indicates substantial unrealized risk — prioritize entities with the highest absolute gap values, especially when combined with a large member panel. |
| PMPM                            | Per-member-per-month cost or revenue metric for the entity's panel. Unusually low PMPM relative to peers with similar documented risk may indicate undercoding; unusually high PMPM with low documented risk may signal unmanaged complexity.                                                  |
| RAF recapture rate              | The proportion of prior-year RAF conditions that have been recaptured in the current measurement year. Low rates indicate that chronic conditions documented previously are not being re-coded in annual visits — a direct compliance and revenue risk.                                        |
| RAF RR YoY change               | Year-over-year change in the RAF recapture rate. A declining value signals a worsening trend in condition recapture, even if the current rate appears acceptable. Watch for entities with both a low current rate and a negative YoY change.                                                   |
| Risk recapture rate             | The proportion of total risk (by dollar or score weight) that has been recaptured relative to what was available to recapture. Complements the RAF recapture rate by weighting recapture by risk magnitude rather than condition count.                                                        |
| Risk RR YoY change              | Year-over-year change in the risk recapture rate. Negative trends here are particularly concerning for high-risk panels, as declining recapture of high-weight conditions has an outsized financial and quality impact.                                                                        |
| % members with open coding gaps | The share of the entity's attributed members who have at least one unresolved coding gap (dropped or suspected). A high percentage indicates broad, systemic coding gap exposure across the panel rather than isolated cases.                                                                  |
| Open gaps (Dropped)             | The count of conditions that were coded in a prior period but have not been recaptured in the current year — they have 'dropped' from the record. High dropped gap counts are a direct recapture failure signal and should be cross-referenced with RAF recapture rate.                        |
| Open gaps (Suspected)           | The count of conditions that analytics or claims data suggest are present but have never been formally coded. High suspected gap counts indicate untapped risk documentation opportunity and may reflect gaps in diagnostic thoroughness or coding education.                                  |


**Reading patterns:**

| Pattern                                                                                              | Interpretation                                                                                                                                                                                                                                                                                                                                                                                               |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Large Members count + High gap to potential risk + Low RAF recapture rate + High open gaps (Dropped) | This is a highest-priority direct intervention target. The entity has a large panel with substantial unrealized risk, is failing to recapture previously documented conditions, and has a significant backlog of dropped gaps. This combination suggests systemic coding workflow failures. Immediate action: targeted coding education, chart review campaigns, and dedicated care gap closure outreach.    |
| Low RAF recapture rate + Negative RAF RR YoY change + Negative Risk RR YoY change                    | This entity is on a declining performance trajectory across both recapture dimensions. Even if current absolute rates are not yet at crisis level, the consistent downward trend signals deteriorating coding discipline or panel complexity growth outpacing documentation capacity. Flag for proactive coaching before performance drops further.                                                          |
| High % members with open coding gaps + High open gaps (Suspected) + Low gap to potential risk        | This entity has broad suspected gap exposure across its panel but a relatively small documented risk gap, suggesting the panel may be undercoded at the condition-identification level rather than the recapture level. The opportunity here is new condition documentation rather than recapture of known conditions — prioritize HCC-focused annual wellness visit campaigns and risk-stratified outreach. |
| Small Members count + Low gap to potential risk + High RAF recapture rate + Low open gaps            | This entity is a low-priority, high-performing outlier. Its panel is well-coded, recapture rates are strong, and open gap burden is minimal. This entity may serve as a best-practice benchmark — consider using its coding workflows or visit patterns as a model for lower-performing peers.                                                                                                               |


### #Members

This scatter plot distributes individual PCPs across two user-selectable performance axes (X and Y), with each point sized by the number of attributed members. The axes can be set to any available risk metric (e.g., gap to potential risk, RAF recapture rate, % members with open gaps), allowing analysts to visually segment the PCP population by any two dimensions simultaneously. The plot reveals clustering, outliers, and the relationship between two performance variables across the full entity population in a single view.

| Position                                    | Interpretation                                                                                                                                                                                                                                                                                                                                                                |
|---------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Upper-right (high on both X and Y axes)     | Highest-priority intervention targets. These PCPs score poorly on both selected performance dimensions simultaneously — for example, high risk gap and low recapture rate. The combination of two adverse signals, often amplified by large bubble size (large panel), makes these entities the most urgent focus for coding intervention, outreach, and operational support. |
| Upper-left (low on X axis, high on Y axis)  | These PCPs have a mixed profile — performing well on the X-axis metric but poorly on the Y-axis metric. They represent a partial risk: one dimension is under control while the other requires attention. Intervention should be targeted specifically at the Y-axis deficiency rather than a broad overhaul.                                                                 |
| Lower-right (high on X axis, low on Y axis) | The inverse of upper-left — these PCPs have an adverse X-axis signal but are performing well on the Y-axis metric. Similar to upper-left, these are partial-risk entities requiring focused attention on the X-axis dimension. They are lower priority than upper-right quadrant entities but should not be ignored.                                                          |
| Lower-left (low on both X and Y axes)       | Lowest-priority entities. These PCPs are performing well on both selected dimensions and do not require immediate intervention. Monitor for drift toward other quadrants over time, and consider leveraging these PCPs as internal benchmarks for peer comparison and best-practice sharing.                                                                                  |




---

### Gap Closure Operational Breakdown

> *📷 Insert: Screenshot of Gap closure by type of visit donut, Gap closure by network status donut, Gap closure by provider type donut*

These three charts reveal the operational anatomy of how gaps are being closed — across the care settings where encounters occur, the network channels through which care is delivered, and the provider types driving closure activity. Together they describe the current distribution pattern of gap closure, surfacing where the organization's closure capacity is concentrated and where structural or channel gaps may exist.

### Gap closure by type of visit

This chart segments gap closures by the type of visit at which the closure was recorded, such as office visits, telehealth, preventive, or acute encounters.

| Segment                                   | Interpretation                                                                                                                                                                                                                                                                                                                                     |
|-------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Office visit dominant                     | The majority of gaps are being closed through scheduled in-person office visits, indicating a traditional, provider-driven closure model. Investigate whether patients with low visit frequency or access barriers are being systematically missed, and consider whether supplemental outreach channels could capture the residual gap population. |
| Telehealth contributing significantly     | A meaningful share of closures is occurring via telehealth, suggesting the organization has successfully extended its closure reach beyond in-person settings. Validate that telehealth-based closures are being coded and attributed correctly, and assess whether this channel can be further scaled for high-volume, low-complexity gaps.       |
| Preventive or wellness visit concentrated | Gap closures are heavily tied to annual wellness visits or preventive encounters, meaning closure activity is episodic and dependent on a single visit type. This creates risk if wellness visit rates decline; investigate whether gaps can be addressed opportunistically across other visit types to reduce concentration risk.                 |


### Gap closure by network status

This chart segments gap closures by whether the rendering provider was in-network or out-of-network at the time of the closure encounter.

| Segment                           | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                    |
|-----------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Predominantly in-network          | The vast majority of gap closures are occurring through in-network providers, reflecting strong network utilization and manageable data capture pathways. Confirm that in-network claims and encounter data are flowing completely and timely, as this concentration means any data latency in network feeds will directly suppress closure rates.                                                                |
| Significant out-of-network share  | A notable portion of closures is attributed to out-of-network providers, which may indicate member leakage, specialist referral patterns outside the network, or gaps in network adequacy for certain specialties. Investigate whether out-of-network closures are being captured reliably through supplemental data sources, and assess whether network gaps are driving members to seek care outside the panel. |
| Out-of-network closures near zero | Almost no gap closures are recorded from out-of-network encounters, which could reflect strong network stewardship or, alternatively, incomplete data capture for out-of-network claims. Validate that out-of-network encounter data is being ingested and processed, as an artificially low share may mask true closure activity occurring outside the network.                                                  |


### Gap closure by provider type

This chart segments gap closures by the type of provider who rendered the closing encounter, such as primary care physicians, specialists, nurse practitioners, or ancillary providers.

| Segment                                                            | Interpretation                                                                                                                                                                                                                                                                                                                                                                                                   |
|--------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Primary care dominant                                              | Primary care providers are driving the majority of gap closures, which is expected for preventive and chronic condition measures but may indicate over-reliance on a single provider tier. Assess whether primary care capacity constraints are creating a ceiling on closure rates, and explore whether care management teams or ancillary staff can be activated to share the closure workload.                |
| Specialist-driven closures prominent                               | A significant share of closures is occurring through specialist encounters, suggesting that members are engaging with the health system primarily through specialty care rather than primary care. Investigate whether care coordination between specialists and PCPs is functioning effectively, and confirm that specialist-rendered closures are being attributed and counted correctly in the measure logic. |
| Advanced practice or ancillary providers contributing meaningfully | Nurse practitioners, physician assistants, or ancillary providers account for a notable portion of closures, reflecting a distributed care team model. This is operationally positive if it indicates intentional panel expansion, but warrants review to ensure these provider types are credentialed and attributed correctly so their closure activity is not undercounted in quality reporting.              |




---

## Page 2: Risk capture potential


---

Which members and providers should be prioritized for outreach and risk recapture interventions based on open coding gaps and recapture rate performance?



### Payer/Plan Opportunity Summary

> *📷 Insert: Screenshot of Payer/plan pivot table with recapture rates and RAF scores alongside column chart of targeted patients by LOB*

This table enables care managers and risk coders to rank payers and plans by their untapped revenue potential, so outreach and coding resources can be directed where the financial return is highest. Use it to decide which payer/plan combinations to prioritize in the next risk execution cycle.

**Across LOBs** — This chart shows the volume of targeted patients distributed across lines of business, allowing the reader to spot which LOBs carry the heaviest patient load and may require proportionally more outreach capacity.

| Column                        | What to look for                                                                                                                                                                                                                                                                                                                                                 |
|-------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Payer/Plan                    | Identifies the specific payer and plan combination being evaluated. Look for rows where a single payer spans multiple plans with divergent performance — this signals that plan-level targeting, not just payer-level, is needed to focus outreach correctly.                                                                                                    |
| Latest Risk Execution         | Indicates the most recent date a risk capture activity (e.g., HCC coding run or chart review) was completed for this payer/plan. Look for rows where this date is stale or significantly older than peers — these plans have had the least recent attention and are most likely to have accumulated unaddressed gaps.                                            |
| Targeted Patients             | Shows the count of patients within this payer/plan who have been flagged for risk gap closure outreach. Look for rows where targeted patient volume is high but recapture rates remain low — this mismatch indicates outreach is happening but not converting, signaling a process or engagement problem worth investigating.                                    |
| Targeted Gaps                 | Reflects the total number of open risk gaps identified across targeted patients for this payer/plan. Look for rows where targeted gaps are disproportionately high relative to targeted patients — a high gaps-per-patient ratio means each outreach touch carries more revenue potential and should be prioritized.                                             |
| Risk Recapture Rate           | Measures the percentage of targeted risk gaps that have already been successfully closed and documented for this payer/plan. Look for rows where this rate is low — they represent plans where the majority of identified opportunity remains uncaptured and action is still possible.                                                                           |
| Potential Risk Recapture Rate | Estimates the maximum achievable risk recapture rate for this payer/plan if all remaining open gaps were closed. Look for rows where the gap between the current recapture rate and this potential rate is widest — that spread is the actionable upside and defines the ceiling of what focused outreach can still recover.                                     |
| RAF Recapture Rate            | Shows the proportion of Risk Adjustment Factor score that has been recaptured to date for this payer/plan, reflecting actual coding impact on reimbursement. Look for rows where the RAF recapture rate lags behind the risk recapture rate — this indicates that the gaps being closed are lower-acuity and higher-value HCC conditions are still being missed. |
| Potential RAF Recapture Rate  | Projects the total RAF score recovery achievable if all remaining open gaps for this payer/plan are addressed. Look for rows where this value is high in absolute terms — these plans represent the largest dollar-denominated revenue opportunity and should anchor the prioritization decision.                                                                |


*Prioritize payers and plans where the gap between Potential RAF Recapture Rate and current RAF Recapture Rate is largest — this spread, not patient volume alone, defines where closing one more gap delivers the greatest reimbursement impact.*



---

### Member Segment Outreach Structure

> *📷 Insert: Screenshot of Collection of bar, clustered bar, and donut charts segmenting targeted gaps by coding gap bucket, risk bucket, wellness visit status, PCP-member distance, PCP visit frequency, care gap bucket, cost of care, days since last PCP visit, and ED utilization*

These nine charts distribute targeted care gap patients across key member characteristics — from risk level and visit history to geography and ED utilization — so care teams can match outreach channel, message urgency, and intervention type to each subgroup's specific situation. Together they move the team from a single undifferentiated outreach list to a structured, segment-aware action plan.

### Across coding gaps bucket

Segments targeted gap members by the number of open coding gaps they carry, revealing which members represent the greatest risk-capture opportunity and warrant the most intensive clinical documentation outreach.

| Segment         | Interpretation                                                                                                                       | Suggested outreach action                                                                                                        |
|-----------------|--------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| 1 coding gap    | Member has a single unresolved coding gap; likely a straightforward documentation miss that can be resolved in one encounter.        | Send automated portal message or SMS prompting member to schedule next available PCP visit for gap closure.                      |
| 2–3 coding gaps | Member has multiple unresolved conditions that may be under-documented, suggesting moderate risk-capture opportunity.                | Phone outreach by care coordinator to schedule a dedicated visit; brief PCP on gaps to address before appointment.               |
| 4+ coding gaps  | Member carries a high volume of unresolved coding gaps, indicating significant potential HCC recapture and possible care complexity. | Assign to care manager for chart review, then schedule an extended or AWV-combined visit with pre-visit gap summary sent to PCP. |


### Across risk bucket

Segments targeted gap members by their overall risk tier (e.g., low, moderate, high, very high), which determines the clinical intensity and urgency of outreach needed to close gaps safely.

| Segment               | Interpretation                                                                                                                    | Suggested outreach action                                                                                                       |
|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| Low risk              | Member has few active conditions and low predicted utilization; gaps are likely preventive or administrative in nature.           | Mail or automated digital outreach with self-scheduling link for preventive visit or AWV.                                       |
| Moderate risk         | Member has emerging chronic conditions or moderate HCC burden; gaps may reflect care drift or missed follow-up.                   | Phone outreach by care coordinator to schedule PCP visit; include gap checklist in pre-visit prep.                              |
| High / Very high risk | Member has complex, multi-condition profile with high predicted cost; unresolved gaps represent both clinical and financial risk. | Assign to dedicated care manager; initiate warm phone outreach within 48 hours and coordinate multi-gap closure visit with PCP. |


### Across wellness visit status

Segments targeted gap members by their Annual Wellness Visit (AWV) completion status, since the AWV is a high-yield encounter for closing multiple gaps simultaneously.

| Segment             | Interpretation                                                                                                                            | Suggested outreach action                                                                                                                     |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| AWV completed       | Member has had a recent AWV, so gaps remaining open likely require a separate focused clinical encounter or documentation update.         | Send PCP a gap closure alert for chart addendum or schedule a brief follow-up telehealth visit to address outstanding gaps.                   |
| AWV due / overdue   | Member has not completed their AWV this year; scheduling one creates an immediate opportunity to address multiple gaps in a single visit. | Phone or SMS outreach to schedule AWV; provide member with a plain-language explanation of AWV benefits to improve show rate.                 |
| AWV never completed | Member has no AWV history, suggesting low preventive engagement and potentially significant unaddressed care gaps.                        | Assign to outreach coordinator for personal phone call; offer flexible scheduling options including telehealth AWV to reduce access barriers. |


### Across PCP - member distance

Segments targeted gap members by the geographic distance between their home and their attributed PCP, identifying members for whom travel is a likely barrier to in-person gap closure.

| Segment    | Interpretation                                                                                                             | Suggested outreach action                                                                                                               |
|------------|----------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| 0–5 miles  | Member lives close to their PCP; distance is not a barrier and in-person visits are the most efficient gap closure path.   | Standard phone or portal outreach to schedule in-person PCP or AWV appointment.                                                         |
| 6–20 miles | Moderate distance may create scheduling friction, especially for members without reliable transportation.                  | Phone outreach offering both in-person and telehealth options; connect to transportation benefit if available.                          |
| 21+ miles  | Member lives far from their PCP; travel burden is a significant barrier and may explain low visit frequency and open gaps. | Prioritize telehealth visit for gap closure; explore PCP reassignment to a closer provider or refer to mobile health unit if available. |


### Across PCP visits (rolling 12 months)

Segments targeted gap members by how many PCP visits they have had in the past 12 months, distinguishing engaged patients from those who are disengaged or relying on non-primary care settings.

| Segment        | Interpretation                                                                                                                                     | Suggested outreach action                                                                                                                      |
|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| 0 PCP visits   | Member has had no PCP contact in the past year; gaps are entirely unaddressed and the member may be disengaged from primary care.                  | High-priority personal phone outreach by care manager; assess barriers to care and offer telehealth or home visit as first re-engagement step. |
| 1–2 PCP visits | Member has minimal PCP engagement; some care is occurring but not enough to address accumulating gaps.                                             | Phone outreach to schedule a gap-focused visit; share pre-visit gap summary with PCP to maximize the encounter.                                |
| 3–5 PCP visits | Member is regularly engaged with their PCP; gaps may be slipping through busy encounters rather than reflecting access issues.                     | Send PCP a targeted gap alert for next scheduled visit; no additional member outreach needed unless gaps remain open after visit.              |
| 6+ PCP visits  | Member is a high utilizer of primary care; persistent gaps despite frequent visits suggest documentation or workflow issues at the practice level. | Escalate to practice-level quality review; work with PCP office to embed gap closure into existing visit workflow or order sets.               |


### Across care gaps bucket

Segments targeted gap members by the total number of open care gaps they carry, enabling the care team to triage outreach effort toward members with the highest gap burden.

| Segment       | Interpretation                                                                                                | Suggested outreach action                                                                                                                            |
|---------------|---------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 care gap    | Member has a single open gap; a focused, low-touch outreach is likely sufficient to achieve closure.          | Automated SMS or portal message with a direct link to schedule the specific service needed to close the gap.                                         |
| 2–3 care gaps | Member has several open gaps that could be addressed in one or two coordinated visits with some pre-planning. | Phone outreach to schedule a combined gap closure visit; send PCP a pre-visit gap checklist.                                                         |
| 4+ care gaps  | Member has a high gap burden indicating fragmented or absent preventive and chronic care management.          | Assign to care manager for a comprehensive care plan review; schedule an extended visit or series of visits with a prioritized gap closure sequence. |


### Across cost of care (rolling 12 months)

Segments targeted gap members by their total cost of care over the past 12 months, helping the team identify whether high-cost members have unresolved gaps that may be driving avoidable utilization.

| Segment                    | Interpretation                                                                                                                         | Suggested outreach action                                                                                                                 |
|----------------------------|----------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Low cost (bottom quartile) | Member has minimal recent utilization; gaps may reflect low engagement with the health system rather than active disease.              | Low-touch digital or mail outreach to schedule preventive visit; focus messaging on wellness and gap closure benefits.                    |
| Moderate cost              | Member has typical utilization patterns; gaps are likely addressable through standard PCP visit coordination.                          | Phone outreach to schedule PCP visit with gap closure agenda; no escalation needed unless gaps remain open after contact.                 |
| High cost (top quartile)   | Member is a high utilizer; open gaps alongside high cost suggest potential for care management intervention to reduce avoidable spend. | Assign to care manager for utilization review and care plan development; coordinate gap closure within a broader cost-reduction strategy. |


### Across days since last PCP visit bucket

Segments targeted gap members by how recently they last visited their PCP, indicating how urgent re-engagement outreach needs to be and how long gaps have likely been accumulating.

| Segment      | Interpretation                                                                                                             | Suggested outreach action                                                                                                                                             |
|--------------|----------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0–90 days    | Member had a recent PCP visit; gaps may have been missed during the encounter or require a short follow-up.                | Send PCP a gap alert for chart addendum or schedule a brief telehealth follow-up to close remaining gaps.                                                             |
| 91–180 days  | Member is overdue for a follow-up visit; gaps have been open for several months and are at risk of further drift.          | Phone outreach to schedule a PCP visit within 30 days; include gap summary in appointment reminder.                                                                   |
| 181–365 days | Member has not seen their PCP in over six months; care continuity is disrupted and multiple gaps are likely accumulating.  | Priority phone outreach by care coordinator; assess barriers and offer telehealth or same-week appointment to re-establish care.                                      |
| 365+ days    | Member has been absent from primary care for over a year; significant disengagement and high risk of unmanaged conditions. | Assign to care manager for personal outreach; conduct a social determinants screening call and offer a home visit or community health worker connection to re-engage. |


### Across ED visit bucket (last 6 months)

Segments targeted gap members by their emergency department utilization in the past six months, identifying members whose ED use may signal unmet primary care needs that are driving both gaps and avoidable costs.

| Segment       | Interpretation                                                                                                                                         | Suggested outreach action                                                                                                                                 |
|---------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0 ED visits   | Member has not used the ED recently; gaps are not associated with acute crisis and can be addressed through routine outreach.                          | Standard phone or digital outreach to schedule PCP or AWV visit for gap closure.                                                                          |
| 1 ED visit    | Member had one recent ED visit, which may indicate an acute episode that could have been managed in primary care.                                      | Phone outreach within 7 days of ED visit to schedule PCP follow-up; use visit as an opportunity to address open gaps.                                     |
| 2–3 ED visits | Member is a frequent ED user, suggesting unmanaged chronic conditions or significant access barriers to primary care.                                  | Assign to care manager; conduct a care needs assessment call and develop a care plan that addresses both ED avoidance and gap closure.                    |
| 4+ ED visits  | Member is a high ED utilizer with likely complex social and clinical needs; open gaps in this context represent both clinical risk and avoidable cost. | Escalate to complex care management program; coordinate with ED case manager for warm handoff and schedule urgent PCP visit with full gap closure agenda. |




---

### Practice and PCP Prioritization

> *📷 Insert: Screenshot of Pivot table ranking practices and PCPs by targeted gaps*

This table directs outreach resources by surfacing which practices and individual PCPs carry the highest volume of unaddressed risk capture opportunities. Use it to decide where to focus care management engagement, provider outreach, or coding support efforts first.

| Column        | What to look for                                                                                                                                                                                                                                                                                                                                                                      |
|---------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Practice Name | Identifies the practice group associated with each row. Look for practices that appear repeatedly across multiple PCPs with high gap counts — these sites represent systemic documentation or coding gaps that may benefit from a practice-level intervention rather than individual provider outreach.                                                                               |
| PCP Name      | Identifies the individual primary care provider within the practice. Look for PCPs whose targeted gap count is disproportionately high relative to their peers within the same practice — these providers are the highest-priority targets for one-on-one coding education, chart review support, or care manager assignment.                                                         |
| Targeted Gaps | Measures the total number of open, actionable risk capture gaps attributed to each PCP and their associated practice. Look for rows where this number is highest — a large targeted gap count signals the greatest potential for HCC recapture, risk score improvement, and quality-of-care alignment, making these PCPs the most impactful starting point for any outreach campaign. |


*Always sort by Targeted Gaps descending before beginning outreach planning — the top rows represent the highest return-on-effort opportunities and should be contacted first.*



---

### Member-Level Targeting List

> *📷 Insert: Screenshot of Patient-level pivot table listing individual members by EMPI for direct outreach*

This table translates population-level risk signals into a concrete, actionable roster of individual members ready for direct outreach. Use it to assign specific members to care managers, prioritize outreach queues, and ensure no high-risk individual is overlooked in your risk capture workflow.

| Column | What to look for                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
|--------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| EMPI   | This column is the unique enterprise master patient index identifier for each member, serving as the primary key to pull the individual into your outreach workflow. Every row represents one actionable person — use this ID to cross-reference the member in your care management system, EHR, or outreach platform. There is no filtering signal on this column itself; its presence in the table means the member has already met upstream criteria for inclusion in the risk capture cohort and warrants contact. |


*Every member appearing in this list has already been flagged by upstream risk criteria — do not wait for additional confirmation before initiating outreach, as delay directly translates to missed risk capture opportunity.*



---

## Page 3: Overview


---

> *Overview also shows the same metrics and widget structure as the section above, with a different comparison period (month-over-month vs year-over-year). All interpretation guidance above applies equally here.*


---

## How the funnel connects

| Layer  | Section                       | Question it answers                                                                                                                  |
|--------|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| Top    | Population & Risk KPIs        | How large is the eligible population, and what are the current levels of documented risk, potential risk, and gap to potential risk? |
| Top    | Performance Rate & Cost KPIs  | What are today's recapture rates, PMPM cost, and share of members carrying open coding gaps?                                         |
| Top    | Payer/Plan Segmentation       | How do population size, risk scores, recapture rates, and PMPM vary across payers and plans?                                         |
| Mid    | Metric Trends Over Time       | How are eligible population, documented vs. potential risk, recapture rates, and PMPM trending relative to the prior year?           |
| Mid    | Risk Model Breakdown          | How do documented risk, gap to potential risk, and recapture rates differ across risk models and sub-models?                         |
| Mid    | Attribution Status Breakdown  | How do risk capture metrics and open coding gaps vary by member attribution status?                                                  |
| Bottom | Disease / Risk Factor Rates   | Which disease categories and risk factors have the lowest recapture rates and the most open coding gaps?                             |
| Bottom | Practice / PCP Performance    | Which practices and PCPs are driving the largest risk gaps, lowest recapture rates, and most open coding gaps?                       |
| Bottom | Gap Closure Operations        | How are gaps being closed across visit types, network status, and provider types — and where do operational channel gaps remain?     |
| Action | Payer/Plan Opportunity        | Which payers and plans represent the most targetable revenue opportunity for risk recapture?                                         |
| Action | Member Segment Outreach       | How should outreach be structured across member segments to maximize gap closure?                                                    |
| Action | Practice & PCP Prioritization | Which practices and PCPs should be prioritized for risk recapture engagement?                                                        |
| Action | Member Targeting List         | Which specific members should be contacted to close open coding gaps and improve recapture rates?                                    |


### Reading across pages

| Pattern                                                                                                                                                                                                                                 | Interpretation                                                                                                                                                                                                                                                                                                                             |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A practice or PCP appears in the Bottom layer with a low risk recapture rate and high open coding gaps, and also appears in the Action layer's Practice and PCP Prioritization section.                                                 | This combination confirms the provider is both a significant driver of risk capture underperformance and a high-priority target for intervention. Risk management teams should escalate outreach to these providers immediately, focusing on closing the specific open coding gaps identified in the Bottom layer.                         |
| A payer or plan shows a large gap to potential risk and low recapture rate in the Top layer's Payer/Plan Segmentation, and also surfaces in the Action layer's Payer/Plan Opportunity Summary with high targetable revenue opportunity. | This alignment signals that the payer's underperformance is not just a documentation issue but a recoverable revenue opportunity. Teams should prioritize member outreach and provider engagement within that payer's attributed population before the coding window closes.                                                               |
| A disease category appears in the Bottom layer with the lowest recapture rate and most open coding gaps, and members with that condition appear in the Action layer's Member-Level Targeting List.                                      | This cross-page link ties a systemic clinical coding gap to specific actionable members. Outreach campaigns should be structured around that disease category, ensuring the right visit type and provider channel — identified in the Gap Closure Operational Breakdown — are used to close those gaps efficiently.                        |
| A member attribution status shows elevated open gaps and low recapture rates in the Mid layer's Attribution Status Breakdown, and members with that status are concentrated in the Action layer's Member Segment Outreach Structure.    | This pattern reveals that attribution status is shaping both where gaps accumulate and how outreach must be designed. Teams should tailor engagement strategies to the specific attribution segment — for example, unattributed or newly attributed members may require different contact approaches than continuously attributed members. |


The dashboard opens by establishing the full scope of the eligible population and the distance between documented risk and potential risk, giving risk management teams an immediate read on where recapture rates and PMPM costs stand today — and which payers are already diverging from expectations. That headline picture raises the question of why gaps exist, which the middle layer answers by tracing trends over time and decomposing performance across risk models, sub-models, and attribution statuses to reveal whether underperformance is structural, cyclical, or concentrated in specific segments. The bottom layer then names the specific disease categories, practices, and PCPs responsible for the largest open coding gaps and lowest recapture rates, and the action layer converts those findings directly into prioritized payer opportunities, member segment outreach plans, provider engagement lists, and individual member targeting — closing the loop from population-level risk landscape to the specific interventions needed to recover it.


---

*Generated by Story Guide Generator | For metric definitions or SQL queries, query the L5 Knowledge Base*
