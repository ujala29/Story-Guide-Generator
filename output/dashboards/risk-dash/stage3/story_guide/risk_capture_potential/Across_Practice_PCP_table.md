**Widget: Across Practice/PCP (Table)**

> 📷 *Insert: Cropped screenshot of the Across Practice/PCP table*

**Definition**

This table summarizes risk adjustment gap activity across practices and their individual PCPs, showing the volume of HCC coding opportunities that have been prioritized for outreach or closure.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Matrix / table |
| Primary metric | Multiple — one per column |
# | Comparison | None columns embedded in the table |
| Comparison | None — current period values only, no time comparison |
| Visual-level filters | None — responds to global filters only |

**Column definitions and directional impact**

| Column | Definition | ↑ Increasing | ↓ Decreasing |
|---|---|---|---|
| Targeted gaps | The count of HCC coding gaps that have been specifically flagged and prioritized for a PCP or practice to address within the current measurement period. | Rising values indicate that more suspected or unrecaptured HCC conditions are being identified and queued for clinical review, reflecting either a growing at-risk population or more aggressive gap identification efforts. | Falling values suggest that fewer new gaps are being surfaced, which may reflect successful gap closure reducing the open queue, a shrinking attributed population, or reduced completeness in gap identification workflows. |

**Key patterns to watch**

| Pattern | What it means |
|---|---|
| High targeted gap volume concentrated in a single PCP within a practice | One PCP is carrying a disproportionate share of the practice's coding burden, signaling potential burnout or documentation support needs — prioritize that PCP for dedicated care manager outreach and coding education. |
| Practice with many PCPs but low total targeted gaps across all of them | The practice may have already achieved strong HCC capture or is being under-prioritized in gap identification — validate RAF scores against benchmarks to confirm saturation or flag for re-stratification. |
| Practice with high targeted gap volume but uneven distribution across its PCPs | Outreach workload is imbalanced within the practice, risking missed closure deadlines for overloaded PCPs — redistribute care manager assignments and consider group-level coding sessions to equalize effort. |
| Small single-PCP practice with a disproportionately high targeted gap count relative to peer practices of similar size | This PCP represents an outsized risk adjustment opportunity or has a high-complexity panel — escalate to a medical director review and assign a dedicated risk adjustment specialist to accelerate gap closure before the measurement period ends. |

**Technical specification**

**DAX measure(s):**

Targeted gaps = COUNTROWS(cohort)+0

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| pcp_2 | practice_name | Row dimension — groups rows in the matrix |
| pcp_2 | pcp_name | Row dimension — groups rows in the matrix |