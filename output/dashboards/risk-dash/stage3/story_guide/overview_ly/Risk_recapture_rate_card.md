**Widget: Risk recapture rate (cardVisual)**

> 📷 *Insert: Cropped screenshot of the Risk recapture rate cardVisual*

**Definition**

The proportion of recaptured risk out of the total eligible recapture opportunity, expressed as a percentage.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | Shows what percentage of the total recapture opportunity has been successfully acted upon, indicating how effectively the organisation is closing coding gaps. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Risk recapture rate goes UP | Positive | A higher proportion of eligible coding gaps are being successfully closed, improving RAF accuracy and revenue integrity — Cross-check Documented risk vs potential risk |
| Risk recapture rate goes DOWN | Negative | Fewer eligible conditions are being recaptured, indicating deteriorating coding outreach effectiveness and potential revenue leakage — Cross-check Gap to potential risk |
| Risk recapture rate rises while % members with open coding gaps also rises | Investigate | Recapture is improving on existing work but new gaps are accumulating faster than they are being closed, masking a growing unaddressed opportunity — Cross-check % members with open coding gaps |

**Technical specification**

**DAX measure(s):**

Risk recapture rate = DIVIDE(SUM(risk_core[recapture_numerator]),SUM(risk_core[recapture_denominator]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 833f191f-3194-4c8f-b39c-de1b45c3b006

Risk recapture rate YoY Card = var py = [Risk recapture rate PY]
var yoy = DIVIDE([Risk recapture rate] - py, py)
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
lineageTag: d9d4de6f-6bd1-454f-8595-075b621320d2

Risk recapture rate MoM Card = var pm = [Risk recapture rate PM]
var mom = DIVIDE([Risk recapture rate] - pm, pm)
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
lineageTag: e7203b06-b16b-43b2-a04c-91f0b6c46ed7

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |