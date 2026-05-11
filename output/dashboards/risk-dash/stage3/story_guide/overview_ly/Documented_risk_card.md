**Widget: Documented risk (cardVisual)**

> 📷 *Insert: Cropped screenshot of the Documented risk cardVisual*

**Definition**

The average HCC risk weight per patient for conditions that have been coded at a clinical encounter, calculated as total documented risk value divided by total patient count, restricted to Documented records only.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | The average documented HCC risk weight per patient, indicating how much risk has been formally captured through clinical coding for the selected population. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Documented risk increases year over year | Positive | More HCC risk weight is being formally captured per patient through clinical coding, indicating improved documentation completeness and coding accuracy. Cross-check Documented risk vs potential risk |
| Documented risk decreases year over year | Negative | Fewer conditions are being coded per patient compared to last year, suggesting documentation gaps, provider disengagement, or reduced encounter frequency. Cross-check Gap to potential risk |
| Documented risk rises while eligible population falls | Investigate | Average coded risk per patient is climbing even as the member base shrinks, which may reflect selective retention of sicker members or denominator distortion rather than genuine coding improvement. Cross-check Eligible population |

**Technical specification**

**DAX measure(s):**

Documented risk = CALCULATE( DIVIDE(SUM(risk_core[risk_value]),sum(risk_core[patient_count])), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
formatString: 0.000
lineageTag: 3efdba30-4573-4f09-8390-00e0cfe385fb

Documented risk YoY Card = VAR py = CALCULATE([Documented risk], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([Documented risk] - py, py, 0)
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
lineageTag: bcda2fdc-47e5-4001-89f4-8cae48e21b3d

Documented risk MoM Card = VAR pm = CALCULATE([Documented risk], PREVIOUSMONTH('date'[month_of_date]))
VAR mom = DIVIDE([Documented risk] - pm, pm, 0)
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
lineageTag: 70f197a4-9c94-42a5-a151-cf0951b30cfa

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |

**Key patterns:**

| Documented risk | Potential risk | Gap to potential risk | RAF recapture rate | What it means |
| --- | --- | --- | --- | --- |
| High | High | Low | High | Most available risk is being captured and recaptured effectively — maintain current coding and outreach workflows to sustain performance. |
| High | High | High | Low | Strong coding base exists but a large uncaptured opportunity remains and recapture is failing — escalate gap closure outreach and review visit completion rates. |
| High | Low | Low | High | Population risk ceiling is low but nearly fully documented — focus shifts to member growth or risk stratification rather than coding improvement. |
| Low | High | High | Low | Critical under-documentation with a large uncaptured risk pool and poor recapture — immediate provider coding education and gap closure campaigns are required. |
| Low | High | High | High | Recapture efforts are active but documented risk remains low, suggesting newly identified gaps are outpacing closure — prioritize high-value HCC conditions in outreach. |
| Low | Low | Low | Low | Overall risk profile is uniformly low across all dimensions — validate whether the population is genuinely low-acuity or whether data completeness and member attribution are the root issues. |