**Widget: PMPM (cardVisual)**

> 📷 *Insert: Cropped screenshot of the PMPM cardVisual*

**Definition**

Calculates the average visit amount per member per month by dividing total year-to-date visit amount by total year-to-date member count.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | The average dollar amount of visit costs incurred per attributed member per month in the current year-to-date period. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| PMPM rises year-over-year | Investigate | Higher average visit costs per member may reflect increased utilization, sicker population mix, or rising unit costs — determine whether risk scores justify the spend. Cross-check Documented risk vs potential risk |
| PMPM falls year-over-year | Positive | Lower average visit costs per member suggest improved care efficiency or reduced utilization, but verify that necessary care is not being deferred. Cross-check Risk recapture rate |
| PMPM rises while Eligible population falls | Investigate | Costs per member are climbing even as the attributed population shrinks, which may indicate a higher-acuity member concentration or attribution anomalies driving inflated averages. Cross-check Risk breakdown by attribution status |

**Technical specification**

**DAX measure(s):**

PMPM = DIVIDE(SUM(attribution[ytd_visit_amount]),Sum(attribution[ytd_member_count]))

PMPM YoY Card = VAR py = CALCULATE([PMPM], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([PMPM] - py, py, 0)
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
lineageTag: 7dcefd1e-2d4f-421c-b033-176794530bf2

PMPM MoM Card = VAR pm = CALCULATE([PMPM], PREVIOUSMONTH('date'[month_of_date]))
VAR mom = DIVIDE([PMPM] - pm, pm, 0)
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
lineageTag: dd0b7737-b4dc-4d70-9457-762971f0b072

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| attribution | ytd_member_count | Patient/member count — used as denominator |
| attribution | ytd_visit_amount | Numerator — total YTD medical cost |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |