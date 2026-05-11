**Widget: Gap closure by network status (Donut Chart)**

> 📷 *Insert: Cropped screenshot of the Gap closure by network status donut*

**Definition**

Displays the distribution of closed care gaps segmented by provider network status (in-network vs. out-of-network). Answers 'Through which network status are care gaps being closed?'

**What it measures**

| Element | Description |
|---|---|
| Visual type | Donut chart |
| Primary metric | Gaps closed (GROUP) |
| Legend | Network status |
| Comparison | None |
| Visual-level filters | Responds to: gap_closure_network_status |

**How to read it**

| Pattern | Interpretation |
|---|---|
| In-network providers dominate gap closure, representing 80%+ of the donut | Strong in-network utilization supports cost control and coordinated care, reinforcing network adequacy for risk adjustment activities. |
| Out-of-network slice accounts for 40% or more of closed gaps | Significant out-of-network gap closure signals potential care leakage, higher costs, and reduced ability to influence provider coding accuracy. |
| Gap closure is nearly evenly split between in-network and out-of-network segments | Balanced split indicates insufficient network steerage, prompting outreach strategies to redirect members toward contracted providers for better HCC capture control. |

**Technical specification**

**DAX measure(s):**

Gaps closed (GROUP) = SUM(risk_group[recapture_numerator])

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| risk_group | recapture_numerator | Numerator — gaps successfully closed |
| risk_group | gap_closure_network_status | Legend / category — Network status segments |