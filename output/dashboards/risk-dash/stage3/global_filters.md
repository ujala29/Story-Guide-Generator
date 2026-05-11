## Global Filters

| Filter Name | What it does | Default |
|---|---|---|
| LOB | Filters all visuals to a specific line of business (e.g., Medicare, Medicaid, Commercial). Set this first — it controls which Payers are available. | All |
| Payer | Narrows data to a single payer within the selected line of business. Set this before selecting a Plan. | All |
| Plan | Filters to a specific plan within the selected Payer. Always set LOB and Payer first. | All |
| Organization | Limits data to a specific organization. Affects member counts, RAF scores, and HCC metrics across all pages. | All |
| ACO | Filters to a specific Accountable Care Organization. Use alongside Organization to avoid double-filtering unintended populations. | All |
| Practice | Narrows data to a specific practice group. PCP selections are nested within this filter — set Practice before selecting a PCP. | All |
| PCP | Filters to an individual primary care physician within the selected Practice. | All |
| Attribution status | Limits data to members with a specific attribution status (e.g., attributed, pending, unattributed). | All |

## Page-specific Filters

### Overview LM

| Filter Name | What it does | Default |
|---|---|---|
| Year | Limits data to a specific calendar year on this page. | All |
| Month | Narrows data to a specific month within the selected year. | All |
| Period mode | Controls the date window used for all change indicators (▲/▼ tiles) on this page. "YTD" compares from January 1 of the current year to the selected month. "Rolling" uses a continuous trailing 12-month window ending on the current date. Does not affect primary KPI values. | YTD |

### Overview LY

| Filter Name | What it does | Default |
|---|---|---|
| Year | Limits data to a specific calendar year on this page. | All |
| Month | Narrows data to a specific month within the selected year. | All |
| Period mode | Controls the date window used for all change indicators (▲/▼ tiles) on this page. "YTD" compares from January 1 of the current year to the selected month. "Rolling" uses a continuous trailing 12-month window ending on the current date. Does not affect primary KPI values. | YTD |
| Plan slicer | Filters the year-over-year comparison chart to a specific plan on this page only. | All |