**Widget: Gap to potential risk (cardVisual)**

> 📷 *Insert: Cropped screenshot of the Gap to potential risk cardVisual*

**Definition**

The average HCC risk weight of conditions that are either undocumented or suspected (not yet coded) per documented patient, representing the uncaptured risk gap per member.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | For every documented patient, this number shows how much additional HCC risk weight remains uncaptured due to conditions that have not yet been coded or confirmed. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Gap to potential risk goes DOWN (year-over-year) | Positive | More undocumented and suspected conditions are being coded, reducing the uncaptured risk weight per documented patient and improving RAF accuracy. Cross-check Documented risk vs potential risk |
| Gap to potential risk goes UP (year-over-year) | Negative | A growing volume of suspected or undocumented conditions per patient indicates coding outreach is falling behind, leaving significant risk revenue uncaptured. Cross-check % members with open coding gaps |
| Gap to potential risk rises while RAF recapture rate also rises | Investigate | Recapture activity appears active yet the uncaptured gap is still growing, suggesting new suspected conditions are being flagged faster than existing gaps are being closed. Cross-check Risk recapture rate by disease |

**Technical specification**

**DAX measure(s):**

Gap to potential risk = var a  = CALCULATE( SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Undocumented","Suspected"}))
var b  = CALCULATE( sum(risk_core[patient_count]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
return
DIVIDE(a,b)+0
formatString: 0.000
lineageTag: 32eac8c6-11fe-461d-bf55-d27ad8617059

Gap to potential risk YoY Card = VAR py = CALCULATE([Gap to potential risk], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([Gap to potential risk] - py, py, 0)
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
lineageTag: c68fb987-b505-4fbb-8010-57ad5ed9ae44

Gap to potential risk MoM Card = VAR pm = CALCULATE([Gap to potential risk], PREVIOUSMONTH('date'[month_of_date]))
VAR mom = DIVIDE([Gap to potential risk] - pm, pm, 0)
RETURN
IF(
ISBLANK(pm),
"",
SWITCH(
TRUE(),
mom > 0, UNICHAR(9650) & " " & FORMAT(mom, "0%") & " from LM",
mom < 0, UNICHAR(9660) & " " & FORMAT(ABS(mom), "0%") & " from LM",
"0%"
)
)
lineageTag: 756ae3d4-7602-45df-a310-fb01a6cf7d37

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |

**Key patterns:**

| Gap to potential risk | Documented risk | RAF recapture rate | Potential risk | What it means |
| --- | --- | --- | --- | --- |
| High | Low | Low | High | Large uncaptured opportunity with weak coding history and poor recapture activity — immediate coding outreach and care gap closure programs are urgently needed. |
| High | High | Low | High | Patients are complex and well-documented historically but recapture is stalling, suggesting suspected conditions are not being confirmed at visits — review encounter workflows and provider engagement. |
| High | Low | High | High | Recapture efforts are active but the base of documented risk is thin, meaning new suspected conditions keep inflating the gap — focus on completing annual wellness visits to anchor documentation. |
| Low | High | High | High | Strong documentation and active recapture are successfully closing gaps despite high clinical complexity — sustain current coding and outreach practices as a best-practice model. |
| Low | High | Low | Low | Risk is well-documented and the population has low clinical complexity, so the gap is naturally small — monitor for population shifts that could reintroduce uncaptured risk. |
| Low | Low | Low | Low | Overall risk profile is low across all dimensions, but weak recapture infrastructure means any increase in suspected conditions could rapidly widen the gap — invest in predictive gap identification tools now. |