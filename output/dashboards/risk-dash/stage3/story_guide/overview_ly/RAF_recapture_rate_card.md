**Widget: RAF recapture rate (cardVisual)**

> 📷 *Insert: Cropped screenshot of the RAF recapture rate cardVisual*

**Definition**

The share of total known HCC risk weight (Documented and Undocumented) that has been successfully recaptured through documented clinical encounters.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | The percentage of known recapturable HCC risk weight that has been successfully documented, indicating how effectively prior-year conditions are being recoded. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| RAF recapture rate increases year over year | Positive | A higher share of known prior-year HCC risk weight is being successfully recoded this period, indicating improved clinical documentation and coding completeness. Cross-check Documented risk vs potential risk |
| RAF recapture rate decreases year over year | Negative | Fewer prior-year conditions are being recaptured through clinical encounters, signaling documentation gaps or reduced member engagement that may understate risk scores. Cross-check Gap to potential risk |
| RAF recapture rate rises while eligible population falls | Investigate | Improving recapture on a shrinking population may reflect selection bias or attribution changes rather than genuine coding improvement across the full panel. Cross-check Eligible population |

**Technical specification**

**DAX measure(s):**

RAF recapture rate = var a = CALCULATE(sum(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented"}))
var b = CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented", "Undocumented"}))
return
DIVIDE(a,b)
formatString: 0.0%;-0.0%;0.0%
lineageTag: 70ebc3c8-8fb8-48dc-815a-23f345128994

RAF recapture rate YoY Card = var py = [RAF recapture rate PY]
var yoy = DIVIDE([RAF recapture rate] - py, py)
return
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
lineageTag: 668f644e-c22e-484b-baf8-06ad33fed68a

RAF recapture rate MoM Card = var pm = [RAF recapture rate PM]
var mom = DIVIDE([RAF recapture rate] - pm, pm)
return
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
lineageTag: 4013889d-1f3c-4ab7-9242-a290b9c6c9be

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |

**Key patterns:**

| RAF recapture rate | Gap to potential risk | Documented risk | Eligible population | What it means |
| --- | --- | --- | --- | --- |
| High | Low | High | — | Most known risk is being captured and documented effectively — maintain current coding workflows and monitor for sustainability. |
| High | High | Low | — | Recapture is strong but a large undocumented risk pool remains, suggesting suspected conditions are not yet being worked — expand gap closure outreach. |
| High | Low | Low | — | High recapture rate on a low documented risk base may indicate a small or low-acuity population — validate that eligible population size is adequate. |
| Low | High | Low | — | Critical risk capture failure — large uncaptured opportunity combined with poor documentation requires immediate coding intervention and provider engagement. |
| Low | High | High | — | Despite high documented risk, recapture of prior-year conditions is lagging — investigate whether chronic conditions are being dropped between coding cycles. |
| Low | Low | Low | — | Low activity across all risk dimensions may reflect a declining or disengaged eligible population — cross-check Eligible population trend for attribution losses. |