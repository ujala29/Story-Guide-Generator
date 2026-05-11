# Glossary of Terms — Risk Management Dashboard

---

## Acronyms & Abbreviations

| Term | Meaning |
|------|---------|
| HCC | Hierarchical Condition Category — a risk classification system used in Medicare Advantage and other managed care models to group diagnoses by clinical severity |
| RAF | Risk Adjustment Factor — a numeric score representing the relative expected cost of a patient's care based on their documented diagnoses and demographics |
| PMPM | Per Member Per Month — average cost or utilization measured per enrolled member for each calendar month |
| YoY | Year over Year — comparison of a metric value in the current period against the same period in the prior year |
| MoM | Month over Month — comparison of a metric value in the current month against the immediately preceding month |
| YTD | Year to Date — cumulative value of a metric from the start of the current calendar or plan year through the current period |
| KPI | Key Performance Indicator — a measurable value used to evaluate progress toward a defined business or clinical objective |
| LOB | Line of Business — a distinct product or payer program (e.g., Medicare Advantage, Medicaid, Commercial) under which members are enrolled |
| PCP | Primary Care Provider — the clinician designated as the member's primary point of care and typically responsible for coordinating risk documentation |
| PM | Previous Month — the calendar month immediately before the current reporting period, used as a baseline for MoM comparisons |
| PY | Prior Year — the same calendar month or period in the year preceding the current reporting period, used as a baseline for YoY comparisons |

---

## Domain Terms

| Term | Meaning |
|------|---------|
| Attributed population | All members assigned to the organization for care management and risk accountability purposes; the broadest population denominator in the dashboard |
| Attribution | The process of assigning members to a specific provider, practice, or organization based on care utilization or enrollment rules |
| Coding window | The defined period during which diagnoses must be documented and submitted to count toward a member's risk score for a given plan year |
| Documented risk | Risk conditions that have been formally recorded and coded during a clinical encounter, contributing to the member's active RAF score |
| Dropped condition | A diagnosis that was documented in a prior period but has not yet been re-documented in the current coding window, creating a recapture opportunity |
| Eligible population | The subset of attributed members who have at least one documented risk entry, representing the population actively measured for risk performance |
| Gap to potential risk | The difference between a member's potential risk score and their documented risk score — the uncaptured risk value that is clinically supported but not yet coded |
| Open coding gap | A condition identified as a clinical risk for a member that has not yet been documented or confirmed in the current coding window |
| Period mode | A dashboard filter setting that controls whether metrics are calculated on a Year-to-Date (YTD) or Rolling basis |
| Potential risk | The maximum average risk score per patient achievable if all suspected, dropped, and documented conditions were fully captured and coded |
| Recapture | The act of re-documenting a previously identified or dropped condition during the current coding window, restoring its contribution to the RAF score |
| Recapture rate | The proportion of previously identified risk conditions or RAF value that has been successfully re-documented and coded in the current period |
| Rolling period | A moving time window (e.g., the most recent 12 months) that shifts forward with each new month, used as an alternative to fixed YTD calculations |
| Suspected condition | A diagnosis flagged by a risk model as likely present based on clinical indicators but not yet confirmed at a documented clinical encounter |
| Undocumented risk | Clinical risk that has been identified but lacks formal documentation in the current coding window, reducing the member's active RAF score |

---

## Metric Definitions

| Metric Name | Definition |
|-------------|------------|
| #Members | Total count of members attributed to the organization; the broadest population denominator representing all members the organization is accountable for. |
| #Members PM | Total number of members enrolled in the previous month, used as the baseline for month-over-month comparisons. |
| #Members PY | Total number of members enrolled or attributed in the same month one year ago, used for year-over-year trend comparison. |
| #Members MoM | Percentage change in total member count compared to the previous month, used to identify short-term membership trends. |
| #Members YoY | Percentage change in total member count compared to the same month one year ago, used to identify longer-term membership trends. |
| #Members trend | Total number of members enrolled or active for a selected month, enabling analysts to track membership volume over time. |
| % Members with Open Coding Gaps | Percentage of attributed members who currently have at least one open coding gap — a condition identified but not yet documented or recaptured in the current period. |
| % Members with Open Coding Gaps MoM | Change in the share of members with unresolved coding gaps compared to the previous month, indicating whether gap closure efforts are improving. |
| % Members with Open Coding Gaps YoY | Change in the share of members with unresolved coding gaps compared to the same month last year, indicating year-over-year gap closure performance. |
| Members with Open Coding Gaps | Total number of members with at least one unresolved coding gap in the selected month, representing outstanding risk documentation opportunities. |
| Members with Open Coding Gaps PM | Number of members who had open coding gaps in the previous month, used as the baseline for month-over-month gap tracking. |
| Members with Open Coding Gaps PY | Number of members with open coding gaps during the same month in the prior year, used as the prior-year baseline for comparison. |
| Members with Open Coding Gaps MoM | Change in the number of members with unresolved coding gaps compared to the previous month, tracking whether gap exposure is growing or shrinking. |
| Members with Open Coding Gaps YoY | Percentage change in members with unresolved coding gaps compared to the same month last year, assessing year-over-year gap closure progress. |
| Documented Risk | Average risk score per patient across all patients with a documented risk flag, calculated as total documented risk value divided by documented patient count. |
| Documented Risk PM | Average documented risk score per patient from the previous month, used as the baseline for month-over-month risk documentation comparison. |
| Documented Risk PY | Average documented risk score per patient from the same month one year ago, used as the prior-year baseline for year-over-year comparison. |
| Documented Risk MoM | Percentage change in average documented risk score per patient compared to the previous month, tracking short-term risk capture trends. |
| Documented Risk YoY | Percentage change in average documented risk score per patient compared to the same month last year, tracking longer-term documentation improvement. |
| Documented Risk cohort | Average risk score for patients with formally documented risk in the selected month, reflecting clinical complexity of the documented population. |
| Potential Risk | Average risk score per patient achievable if all suspected, dropped, and documented risk were fully captured and coded across all risk documents. |
| Potential Risk PM | Average potential risk score per documented patient from the previous month, used to track whether overall risk exposure is trending up or down. |
| Potential Risk PY | Average potential risk score from the same month last year, enabling year-over-year comparison of total risk burden trends. |
| Potential Risk MoM | Percentage change in average potential risk score per patient compared to the previous month, identifying short-term shifts in population risk. |
| Potential Risk YoY | Percentage change in average potential risk per documented patient compared to the same month last year, assessing year-over-year risk burden trends. |
| Gap to Potential Risk | Difference between Potential Risk and Documented Risk — the average per-patient risk score that is clinically supported but not yet formally documented or coded. |
| Gap to Potential Risk PM | Gap between potential and documented risk scores from the previous month, used as the baseline for month-over-month gap trend analysis. |
| Gap to Potential Risk PY | Untapped risk value per documented patient from the same month one year ago, enabling year-over-year comparison of undocumented risk opportunity. |
| Gap to Potential Risk MoM | Percentage change in the gap between potential and documented risk compared to the previous month, indicating whether the organization is closing or widening the gap. |
| Gap to Potential Risk YoY | Percentage change in the gap between potential and documented risk compared to the same month last year, tracking year-over-year risk capture improvement. |
| PMPM | Average per-member-per-month cost, calculated as total year-to-date visit amount divided by total year-to-date member count from the attribution table. |
| PMPM PM | Average PCP visit cost per member for the previous month, used as the baseline for month-over-month spending comparison. |
| PMPM PY | Average per-member-per-month PCP visit cost from the same point in the prior year, used as the prior-year spending baseline. |
| PMPM MoM | Percentage change in average cost per member compared to the previous month, identifying short-term trends or anomalies in PCP visit spending. |
| PMPM YoY | Percentage change in average cost per member per month compared to the same point last year, assessing whether healthcare spending trends are improving. |
| RAF Recapture Rate | Share of RAF value successfully recaptured through documented and coded diagnoses, calculated from risk records flagged with an active risk documentation status. |
| RAF Recapture Rate PM | Prior month's rate at which patient risk scores were successfully recaptured through documented clinical encounters, used for month-over-month benchmarking. |
| RAF Recapture Rate PY | Percentage of at-risk RAF score successfully captured through documented diagnoses in the same period one year ago, providing a historical performance baseline. |
| RAF Recapture Rate MoM | Change in RAF recapture rate compared to the previous month, indicating whether documented risk is keeping pace with total identified risk. |
| RAF Recapture Rate YoY | Percentage change in the organization's ability to recapture patient risk scores compared to the same period last year. |
| RAF Recapture Rate cohort | Percentage of total expected risk successfully documented for a specific patient cohort in a given month, indicating how effectively risk is being captured. |
| Potential RAF Recapture Rate cohort | Percentage of potential RAF value that could be recaptured for a patient cohort in a given month, showing how effectively care teams are closing risk gaps. |
| Risk Recapture Rate | Proportion of previously identified risk conditions successfully recaptured — documented and coded — in the current period, calculated as the sum of recaptured risk values. |
| Risk Recapture Rate PM | Risk recapture rate from the previous month, used to compare current performance and track whether recapture ability is improving. |
| Risk Recapture Rate PY | Rate at which previously identified risk conditions were successfully recaptured during the same period in the prior year, providing a historical benchmark. |
| Risk Recapture Rate MoM | Percentage change in risk recapture rate compared to the previous month, tracking month-over-month momentum in closing care gaps. |
| Risk Recapture Rate YoY | Percentage change in risk recapture rate compared to the same month last year, assessing whether risk documentation and coding efforts are improving. |
| Risk Recapture Rate cohort | Percentage of previously identified at-risk patients whose conditions were successfully recaptured or re-documented within a given month at the cohort level. |
| Potential Risk Recapture Rate cohort | Potential rate at which previously identified risk gaps could be recaptured within a specific member cohort, assessing how effectively care teams are addressing gaps. |
| Eligible Population | Count of patients with at least one documented risk entry flagged as "Documented," representing the subset of attributed membership actively measured for risk. |
| Eligible Population PM | Total number of eligible patients enrolled during the previous month, used as the baseline for month-over-month population comparison. |
| Eligible Population PY | Total number of eligible patients enrolled during the same month one year ago, used as the prior-year baseline for year-over-year comparison. |
| Eligible Population MoM | Percentage change in the documented eligible patient population compared to the previous month, tracking short-term population size trends. |
| Eligible Population YoY | Percentage change in the count of documented eligible patients compared to the same month one year ago, tracking longer-term population trends. |
| Eligible Population trend | Total number of patients eligible for risk measurement in a given month, allowing analysts to track how the eligible population changes over time. |
| Cohort Eligible Gaps | Number of care gaps remaining open and uncaptured for eligible members in a given month, representing outstanding risk recapture opportunities. |
| Gaps Closed | Total number of care gaps successfully closed within the selected month, combining both recaptured and newly resolved gaps. |
| Overall Gaps Closed MoM | Percentage change in total closed care gaps compared to the previous month, assessing whether gap closure performance is improving or declining. |
| Overall Gaps Closed YoY | Percentage change in total closed care gaps compared to the same point last year, assessing year-over-year improvement in closing patient risk gaps. |
| Overall Gaps Closed PM | Total number of care gaps closed in the previous month, combining recaptured and suspected conditions, used as the prior-month performance baseline. |
| Overall Gaps Closed PY | Total number of care gaps closed during the same month one year ago, providing a prior-year baseline to evaluate gap closure performance trends. |
| Open Gaps (Dropped) | Number of dropped-condition risk recapture opportunities that have not yet been closed or addressed in the selected month. |
| Open Gaps (Suspected) | Number of suspected-condition care gaps that remain open and unaddressed for patients during the selected time period. |
| Suspected Risk | Ratio of suspected (unconfirmed) risk value relative to the documented patient population, showing how much potential risk is flagged but not yet formally confirmed. |
| Undocumented Risk | Amount of undocumented risk relative to the documented patient population, identifying how much clinical risk lacks proper documentation compared to what has been captured. |
| RAF Impact cohort | Estimated average RAF score impact per documented patient achievable by capturing currently undocumented or suspected risk conditions within a cohort. |
| Increase RAF Impact cohort | Estimated potential percentage increase in documented RAF score if all suspected and undocumented conditions in the cohort were properly captured and coded. |
| Realizable RAF Score | Estimated full potential RAF score a population could achieve if all suspected and undocumented conditions were captured and confirmed, showing the gap to current documented score. |
| Risk Factor | Highest risk factor code assigned to a patient or group for the selected month, reflecting the most severe or elevated risk classification recorded. |
| Targeted Gaps | Total number of targeted care gaps identified for members in the selected month, representing the volume of outstanding clinical intervention opportunities. |
| Targeted Patients | Total number of unique patients identified and targeted for care management or intervention in the selected month. |
| Latest Attribution Date | Most recent month for which patient attribution data is available, indicating how current the attribution dataset is. |
| Latest Measurement Date | Most recent month for which risk measurement data is available, indicating how current the risk dataset is. |
| Latest Risk Execution | Most recent month for which risk data has been processed and is available, giving analysts a reference point for the latest risk assessment cycle. |
| Selected X Axis Value | Dynamically displays whichever performance indicator the user selects for the X-axis, allowing flexible provider or population comparisons across risk and cost measures. |
| Selected Y Axis Value | Dynamically displays whichever performance indicator the user selects for the Y-axis, allowing flexible comparisons across member counts, risk rates, and cost measures. |
| Metric Value | Dynamic, context-sensitive value displayed on reports or charts, reflecting key performance indicators such as member engagement, risk documentation, and coding gap closure. |