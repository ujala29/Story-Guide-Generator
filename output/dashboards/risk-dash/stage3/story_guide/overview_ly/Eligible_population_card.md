**Widget: Eligible population (cardVisual)**

> 📷 *Insert: Cropped screenshot of the Eligible population cardVisual*

**Definition**

Displays the total count of eligible members formatted for readability, scaling to K, M, or bn depending on magnitude.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | The total number of members who are eligible for risk adjustment consideration in the selected period. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| Eligible population increases year over year | Positive | A growing eligible population expands the risk adjustment opportunity and potential revenue base, but requires sufficient coding and care management capacity to capture it. Cross-check Potential risk |
| Eligible population decreases year over year | Negative | A shrinking eligible population reduces the total risk adjustment opportunity and may signal membership attrition or attribution losses that need immediate investigation. Cross-check Payer/plan details |
| Eligible population rises while RAF recapture rate falls | Investigate | More members are eligible but a smaller proportion of risk gaps are being closed, suggesting coding capacity or outreach is not scaling with membership growth. Cross-check RAF recapture rate |

**Technical specification**

**DAX measure(s):**

Formatted Eligible population = VAR x = [Eligible population]
RETURN
SWITCH(
TRUE(),
x < 1000, FORMAT(x, "#,##0"),
x < 1000000, FORMAT(x, "#,.0") & "K",
x < 1000000000, FORMAT(x , "#,##0,,.0") & "M",
FORMAT(x, "#,,,.0") & "bn"
)
lineageTag: 9bff8b0b-bc53-4654-8210-05f9c94cd050

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

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |

**Key patterns:**

| Eligible population | Potential risk | Gap to potential risk | RAF recapture rate | What it means |
| --- | --- | --- | --- | --- |
| High | Low | Low | High | Large membership with low overall risk complexity and gaps mostly closed — population is well-managed but monitor for under-coding of chronic conditions. |
| High | High | High | Low | Maximum uncaptured risk opportunity across a large population with poor recapture — urgent scaling of coding outreach and care management is needed. |
| High | High | Low | High | High-risk large population with gaps being closed effectively — sustain current coding workflows and monitor for new gap emergence. |
| Low | High | High | Low | Small but highly complex population with significant uncaptured risk and poor recapture — prioritize intensive coding intervention for this concentrated high-risk group. |
| Low | Low | High | Low | Small population with disproportionately large gaps and low recapture — investigate whether documentation practices or visit frequency are suppressing risk capture. |
| Low | Low | Low | High | Small, low-complexity population with gaps well-controlled — limited risk adjustment upside remains; focus resources on higher-opportunity segments. |