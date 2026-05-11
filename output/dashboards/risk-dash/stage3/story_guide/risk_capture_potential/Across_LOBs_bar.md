**Widget: Across LOBs (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the Across LOBs bar chart*

**Definition**

This chart compares the count of targeted patients across each Line of Business (LoB), revealing which lines carry the highest risk adjustment outreach burden.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Vertical bar chart |
| Primary metric | Targeted patients |
| Category axis | LoB |
| Tooltip | None |
| Comparison | None |
| Visual-level filters | None — responds to global filters only |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
| A LoB bar is significantly taller than all others | Investigate | A disproportionately high number of targeted patients in one LoB may indicate concentrated coding gaps or population health risks requiring prioritized intervention resources. |
| Multiple LoB bars are uniformly high | Negative | Broadly elevated targeted patient counts across several lines of business suggest systemic under-documentation of chronic conditions, posing widespread risk adjustment revenue leakage. |
| A LoB bar is notably shorter than peers | Positive | A low targeted patient count in a LoB indicates strong prior coding capture and effective outreach completion, reflecting well-managed risk adjustment performance for that population. |

**Technical specification**

**DAX measure(s):**

Targeted patients = DISTINCTCOUNT(cohort[empi])+0
formatString: #,0
lineageTag: 97838794-e786-4b00-ae14-2f7d9508b327

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| cohort | empi | Member identifier — distinct count for targeted patients |
| payer | contract_name | Source column — contributes to measure calculation |