**Widget: % members with open coding gaps (cardVisual)**

> 📷 *Insert: Cropped screenshot of the % members with open coding gaps cardVisual*

**Definition**

The percentage of attributed members who have at least one open coding gap — a condition that should be coded but has not yet been documented.

**What it measures**

| Element | Description |
|---|---|
| Visual type | cardVisual |
| Primary metric | The share of the member population with at least one condition that should be coded but remains unaddressed, indicating the breadth of coding gap exposure across the panel. |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| % members with open coding gaps goes UP | Negative | A larger share of the panel has unaddressed conditions, increasing risk of revenue leakage and inaccurate RAF scores — Cross-check Gap to potential risk |
| % members with open coding gaps goes DOWN | Positive | Fewer members have unresolved coding gaps, indicating improved documentation outreach and stronger risk capture across the panel — Cross-check Risk recapture rate |
| % members with open coding gaps remains high while Risk recapture rate is also rising | Investigate | Gaps are being closed at an increasing rate yet the share of members with open gaps is not declining, suggesting new gaps are opening faster than they are being resolved — Cross-check Documented risk vs potential risk |

**Technical specification**

**DAX measure(s):**

% members with open coding gaps = [Members with open coding gaps]/[#Members]

Members with open coding gaps = SUM(attribution[member_with_open_coding_gap_count])
formatString: #,0
lineageTag: fb23b4af-175f-47cc-ae05-89633df943c2

#Members = SUM(attribution[member_count])+0
formatString: #,0
lineageTag: d67d72a2-2db7-4495-b98f-0d57ba71fa97

% Members with open coding gaps YoY Card = VAR py = CALCULATE([% Members with open coding gaps], SAMEPERIODLASTYEAR('date'[month_of_date]))
VAR yoy = DIVIDE([% Members with open coding gaps] - py, py, 0)
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
lineageTag: b6fcdcac-6533-47d2-87b3-b01f7bfd17a0

% Members with open coding gaps MoM Card = VAR py = CALCULATE([% Members with open coding gaps], PREVIOUSMONTH('date'[month_of_date]))
VAR yoy = DIVIDE([% Members with open coding gaps] - py, py, 0)
RETURN
IF(
ISBLANK(py),
"",
SWITCH(
TRUE(),
yoy > 0, UNICHAR(9650) & " " & FORMAT(yoy, "0%") & " from LM",
yoy < 0, UNICHAR(9660) & " " & FORMAT(ABS(yoy), "0%") & " from LM",
""
)
)
lineageTag: 2c9c5a78-7331-4c3e-bd12-bbf17302299d

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| attribution | member_count | Patient/member count — used as denominator |
| attribution | member_with_open_coding_gap_count | Numerator — members with at least one open coding gap |
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |