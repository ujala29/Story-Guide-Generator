**Widget: Potential risk (cardVisual)**

> 📷 *Insert: Cropped screenshot of the Potential risk cardVisual*

**Definition**

Total HCC risk weight across all conditions (regardless of documentation status) divided by the patient count of Documented conditions only, representing the potential risk per documented patient.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | The average total HCC risk weight per documented patient, reflecting the full potential risk burden including unconfirmed and predicted conditions relative to the documented patient base. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Potential risk rises year over year | Investigate | The total risk burden per documented patient is growing, which may reflect a sicker population or increased suspected/undocumented conditions being identified — determine whether documentation is keeping pace. Cross-check Documented risk vs potential risk |
| Potential risk falls year over year | Investigate | Declining potential risk per documented patient could indicate improved coding closure, a healthier population mix, or a shrinking denominator of documented patients that masks true risk. Cross-check Gap to potential risk |
| Potential risk rises while Eligible population falls | Investigate | A smaller documented patient base driving a higher average potential risk suggests concentrated high-acuity members are dominating the score while lower-risk members may have dropped off attribution. Cross-check Risk breakdown by attribution status |

**Technical specification**

**DAX measure(s):**

Potential risk = var a  = SUM(risk_core[risk_value])
var b  = CALCULATE( sum(risk_core[patient_count]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
return
DIVIDE(a,b)
formatString: 0.000
lineageTag: 0c8d3b8e-3e21-40a1-a754-61733cf9adf0

Potential risk YoY Card = VAR py = CALCULATE([Potential risk], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([Potential risk] - py, py, 0)
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
lineageTag: 2015c982-a3c7-4638-b9c3-0c37f0d66a56

Potential risk MoM Card = VAR pm = CALCULATE([Potential risk], PREVIOUSMONTH('date'[month_of_date]))
VAR mom = DIVIDE([Potential risk] - pm, pm, 0)
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
lineageTag: 0666186b-74b7-4a06-aa4b-2feeeecf8240

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |

**Key patterns:**

| Potential risk | Documented risk | Gap to potential risk | RAF recapture rate | What it means |
| --- | --- | --- | --- | --- |
| High | Low | High | Low | Large uncaptured risk burden with poor documentation and no recapture momentum — immediate coding outreach and provider engagement are critical. |
| High | High | Low | High | High risk is well-documented and actively recaptured — this is a healthy state; monitor to ensure documentation quality is maintained. |
| High | Low | High | High | Recapture activity is strong but documentation has not yet caught up with the full risk burden — accelerate coding workflows to convert suspected conditions. |
| High | High | High | Low | Existing conditions are documented but a large new gap is emerging with no recapture effort — investigate whether new suspected conditions are being identified and acted on. |
| Low | Low | Low | Low | Overall low-risk population with minimal gaps and no recapture pressure — validate that the eligible population is correctly attributed and not under-identified. |
| Low | High | Low | High | Documented risk exceeds potential risk signal, suggesting over-coding or a denominator mismatch — audit condition flags and patient attribution for data integrity issues. |