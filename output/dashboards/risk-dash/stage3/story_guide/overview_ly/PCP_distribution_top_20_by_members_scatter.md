**Widget: PCP distribution (top 20 by members) (Scatter Plot)**

> 📷 *Insert: Cropped screenshot of the PCP distribution (top 20 by members) scatter plot*

**Definition**

Each bubble represents a single Primary Care Physician (PCP) from the top 20 by member panel size, where the X-axis displays a user-selected performance or risk metric, the Y-axis displays a second user-selected metric, and bubble size encodes the number of attributed members; the chart helps identify how individual PCPs compare across two key dimensions simultaneously, revealing high-performers, underperformers, and outliers who may require targeted intervention or support.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Scatter plot with configurable axes |
| Primary metric | Y-axis: Selected Y Axis Value (selectable via dropdown) |
| Secondary metric | X-axis: selectable via dropdown |
| Bubble size | #Members — panel size |
| Category | Pcp Name — each bubble = one Pcp Name |
| Comparison | None — point-in-time distribution |
| Visual-level filters | Responds to: pcp_name |

**How to read it**

| Position | Interpretation |
|---|---|
| Upper-right (high X, high Y) | This PCP scores high on both selected metrics — for example, high RAF score and high HCC capture rate — indicating strong risk documentation and coding performance; these physicians are likely best-practice models worth studying and replicating across the network. |
| Upper-left (low X, high Y) | This PCP has a high value on the Y-axis metric but a low value on the X-axis metric, suggesting an imbalance such as high member complexity but low visit completion rates; this pattern may signal a capacity or access issue that could leave high-risk members underserved. |
| Lower-right (high X, low Y) | This PCP shows a high X-axis value but a low Y-axis value — for instance, high member panel size but low average RAF score — which may indicate undercoding or insufficient chronic condition documentation relative to the volume of patients managed. |
| Lower-left (low X, low Y) | This PCP scores low on both selected metrics, suggesting either a low-complexity panel or underperformance in risk capture and quality measures; further investigation is needed to determine whether the panel is genuinely healthier or whether documentation and coding gaps are suppressing scores. |
| Outlier far above the cluster | This PCP sits well above the main cluster on the Y-axis, representing an unusually high value that deviates significantly from peers — this could reflect exceptional performance, a data anomaly, a highly specialized or complex patient panel, or a coding irregularity that warrants immediate review and validation. |

**Technical specification**

**DAX measure(s):**

Selected Y Axis Value = SWITCH(SELECTEDVALUE('Y Axis scatter plot'[Y axis]),
"Members",[#Members],
"Documented risk",[Documented risk],
"Gap to potential risk",[Gap to potential risk],
"PMPM",[PMPM],
"RAF recapture rate",[RAF recapture rate],
"Risk recapture rate",[Risk recapture rate],
"% members with open coding gaps",[% members with open coding gaps],
"Open gaps (Dropped)",[Open gaps (Dropped)],
"Open gaps (Suspected)",[Open gaps (Suspected)],
"Eligible",[Eligible population],
BLANK())
lineageTag: 762815df-b243-4243-b779-67d16d2353c6
annotation PBI_FormatHint = {"isGeneralNumber":true}

Open gaps (Suspected) = SUM(risk_core[suspect_denominator])-SUM(risk_core[suspect_numerator])

Eligible population = CALCULATE(SUM(risk_core[patient_count]),KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))+0
formatString: #,0
lineageTag: 8c201874-31b6-4f4b-8be8-131ce92d628e

Risk recapture rate = DIVIDE(SUM(risk_core[recapture_numerator]),SUM(risk_core[recapture_denominator]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 833f191f-3194-4c8f-b39c-de1b45c3b006

RAF recapture rate = var a = CALCULATE(sum(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented"}))
var b = CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Documented", "Undocumented"}))
return
DIVIDE(a,b)
formatString: 0.0%;-0.0%;0.0%
lineageTag: 70ebc3c8-8fb8-48dc-815a-23f345128994

Open gaps (Dropped) = SUM(risk_core[recapture_denominator])-SUM(risk_core[recapture_numerator])

Gap to potential risk = var a  = CALCULATE( SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] in {"Undocumented","Suspected"}))
var b  = CALCULATE( sum(risk_core[patient_count]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
return
DIVIDE(a,b)+0
formatString: 0.000
lineageTag: 32eac8c6-11fe-461d-bf55-d27ad8617059

Members with open coding gaps = SUM(attribution[member_with_open_coding_gap_count])
formatString: #,0
lineageTag: fb23b4af-175f-47cc-ae05-89633df943c2

PMPM = DIVIDE(SUM(attribution[ytd_visit_amount]),Sum(attribution[ytd_member_count]))

Documented risk = CALCULATE( DIVIDE(SUM(risk_core[risk_value]),sum(risk_core[patient_count])), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
formatString: 0.000
lineageTag: 3efdba30-4573-4f09-8390-00e0cfe385fb

#Members = SUM(attribution[member_count])+0
formatString: #,0
lineageTag: d67d72a2-2db7-4495-b98f-0d57ba71fa97

Selected X Axis Value = SWITCH(SELECTEDVALUE('X Axis scatter plot'[X axis]),
"Members",[#Members],
"Documented risk",[Documented risk],
"Gap to potential risk",[Gap to potential risk],
"PMPM",[PMPM],
"RAF recapture rate",[RAF recapture rate],
"Risk recapture rate",[Risk recapture rate],
"% members with open coding gaps",[% members with open coding gaps],
"Open gaps (Dropped)",[Open gaps (Dropped)],
"Open gaps (Suspected)",[Open gaps (Suspected)],
"Eligible",[Eligible population],
BLANK())
lineageTag: bbf9ae6d-3586-4b9b-9fd4-6792076653d9
annotation PBI_FormatHint = {"isGeneralNumber":true}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| attribution | member_count | Patient/member count — used as denominator |
| X Axis scatter plot | X axis | Slicer table — drives X-axis metric selection |
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| risk_core | suspect_numerator | Numerator — suspected gaps closed |
| risk_core | patient_count | Patient/member count — used as denominator |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| attribution | ytd_member_count | Patient/member count — used as denominator |
| attribution | member_with_open_coding_gap_count | Numerator — members with at least one open coding gap |
| risk_core | suspect_denominator | Denominator — total suspected gaps |
| risk_core | risk_documentation_flag | Flag filter — restricts rows to specific documentation status |
| risk_core | risk_value | HCC risk weight — summed for numerator or denominator |
| attribution | ytd_visit_amount | Numerator — total YTD medical cost |
| Y Axis scatter plot | Y axis | Slicer table — drives Y-axis metric selection |
| pcp | pcp_name | Data point identity — each bubble is one Pcp Name |