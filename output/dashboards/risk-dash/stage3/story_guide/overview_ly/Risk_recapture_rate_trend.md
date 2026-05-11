**Widget: Risk recapture rate (lineChart)**

> 📷 *Insert: Cropped screenshot of the Risk recapture rate lineChart*

**Definition**

This chart tracks the monthly risk recapture rate for the current year compared to the same months in the previous year, enabling year-over-year performance evaluation of how effectively documented chronic conditions are being recaptured during patient encounters.

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | Previous year, Current year |
| X-axis | Month |
| Comparison | YoY % change |
| Visual-level filters | None — responds to global filters only |

**How to read it**

Each line represents the percentage of eligible risk conditions successfully recaptured within a given month, with the current year line ideally trending at or above the previous year line. When the current year line falls below the previous year, it signals a recapture gap that may indicate coding deficiencies, reduced patient visit volumes, or incomplete HCC documentation workflows. Sustained divergence where the current year consistently underperforms should prompt outreach to coding teams, care managers, or providers to close documentation gaps before year-end. Conversely, if the current year line consistently exceeds the prior year, it reflects improved recapture processes and should be analyzed to identify best practices that can be replicated across other regions or provider groups.

**Technical specification**

**DAX measure(s):**

Risk recapture rate PY = CALCULATE([Risk recapture rate], SAMEPERIODLASTYEAR('date'[month_of_date]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 1fc47f63-8bb4-411d-8e6f-a9fb2c509e0b

Risk recapture rate = DIVIDE(SUM(risk_core[recapture_numerator]),SUM(risk_core[recapture_denominator]))
formatString: 0.0%;-0.0%;0.0%
lineageTag: 833f191f-3194-4c8f-b39c-de1b45c3b006

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
| date | month_of_date | Time intelligence — drives YoY/MoM comparison |
| risk_core | recapture_denominator | Denominator — total identified gaps |
| risk_core | recapture_numerator | Numerator — gaps successfully closed |
| date | month_of_year | Time intelligence — drives YoY/MoM comparison |