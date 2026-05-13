# pipeline/stage1_extraction/tmdl_parser.py
#
# PURPOSE:
#   Reads the SemanticModel's TMDL files and extracts:
#     - Tables (with type classification)
#     - Columns (physical and calculated)
#     - DAX Measures (3 encoding formats)
#     - Relationships between tables
#
# TMDL FORMAT NOTES:
#   - TMDL uses TAB (\t) indentation — all regex anchors use \t, not spaces.
#   - One file per table under: <SemanticModel>/definition/tables/*.tmdl
#   - Relationships live in a single file: definition/relationships.tmdl
#
# WHAT EACH CLASS DOES:
#   TMDLExtractor   ← public API: extract_tables(), extract_relationships()
#
# CALLED BY:
#   pipeline/stage1_extraction/extractor.py -> run_extraction()

import re
from pathlib import Path
from typing import Optional

from models import (
    ColumnSchema, MeasureSchema, TableSchema, RelationshipSchema
)


class TMDLExtractor:
    """
    Parses all TMDL files in a SemanticModel folder.

    Usage:
        tmdl = TMDLExtractor("path/to/Report.SemanticModel")
        tables        = tmdl.extract_tables()
        relationships = tmdl.extract_relationships()
    """

    # Table names that are known to be parameter/slicer-value tables.
    # These hold user-selectable values (e.g. observation window lengths),
    # not real data — so they are classified as "parameter".
    PARAM_TABLES = {
        "parameter", "x axis scatter plot", "y axis scatter plot",
        "static_observation_window_table", "static_observation_win",
    }

    # Prefixes for Power BI auto-generated hidden date tables.
    # These are created internally when "Auto date/time" is enabled and are
    # never visible in the Power BI model view — exclude them everywhere.
    AUTO_DATE_PREFIXES = ("LocalDateTable_", "DateTableTemplate_")

    # Table names that are known measure containers.
    # These hold only DAX measures — no real columns, no data rows.
    MEASURE_CONTAINER_NAMES = {
        "all_dax_pac", "all_dax", "measures", "_measures",
        "key measures", "dax measures", "dax",
    }

    def __init__(self, semantic_model_path: str):
        """
        Sets up paths to the tables folder and relationships file.
        Asserts that the tables folder exists so failure is obvious early.
        """
        self.root       = Path(semantic_model_path)
        self.tables_dir = self.root / "definition" / "tables"
        self.rel_file   = self.root / "definition" / "relationships.tmdl"
        assert self.tables_dir.exists(), f"Tables folder not found: {self.tables_dir}"

    # ── Public API ─────────────────────────────────────────────────────────────

    def _is_auto_date_table(self, name: str) -> bool:
        """Returns True for Power BI auto-generated hidden date tables."""
        return any(name.startswith(p) for p in self.AUTO_DATE_PREFIXES)

    def extract_tables(self) -> list[TableSchema]:
        """
        Reads every .tmdl file in the tables folder alphabetically.
        Returns a list of TableSchema — one per file.
        Files that fail to parse are silently skipped (returns empty list entry filtered).
        Auto-generated hidden date tables (LocalDateTable_*, DateTableTemplate_*) are excluded.
        """
        return [t for f in sorted(self.tables_dir.glob("*.tmdl"))
                if (t := self._parse_table_file(f)) and not self._is_auto_date_table(t.name)]

    def extract_all_measures(self, tables: list[TableSchema]) -> list[MeasureSchema]:
        """
        Flattens measures from all tables into a single list.
        Used by MeasureDependencyGraph which needs a flat view across all tables.
        """
        return [m for t in tables for m in t.measures]

    def extract_relationships(self) -> list[RelationshipSchema]:
        """
        Reads relationships.tmdl and returns all relationships.
        Returns an empty list if the file does not exist (some models have none).
        """
        if not self.rel_file.exists():
            return []
        return self._parse_relationships(
            self.rel_file.read_text(encoding="utf-8", errors="ignore")
        )

    # ── Table classification ────────────────────────────────────────────────────

    def _classify_table(self, name, columns, measures, power_query) -> str:
        """
        Assigns one of 4 table types based on name, content, and Power Query.

        Types:
          "measure_container" -> only DAX measures, no physical data rows
          "parameter"         -> slicer values / user-input parameters
          "static_lookup"     -> hardcoded reference data via #table() in Power Query
          "source"            -> real data table connected to a database (Snowflake etc.)

        WHY THIS MATTERS:
          Story guide chapters treat each type differently.
          measure_containers are excluded from data dictionary (ch10).
          Parameters are explained in the filter chapter (ch06).
        """
        n = name.lower()

        # name-based measure container check
        if n in self.MEASURE_CONTAINER_NAMES:
            return "measure_container"

        # content-based: has measures but zero real (non-calculated) columns
        real_cols = [c for c in columns if not c.is_calculated]
        if measures and not real_cols:
            return "measure_container"

        # name-based parameter check
        if n in self.PARAM_TABLES or any(k in n for k in ["parameter", "static_", "x axis", "y axis"]):
            return "parameter"

        # Power Query content check for static lookup tables
        if power_query:
            pq = power_query.lower()
            has_hardcode = any(k in pq for k in ['#table', '{"', "table {"])
            no_db        = not any(k in pq for k in ["snowflake", "sql", "odbc", "oledb", "server"])
            if has_hardcode and no_db:
                return "static_lookup"

        return "source"

    # ── Table file parser ───────────────────────────────────────────────────────

    def _parse_table_file(self, path: Path) -> Optional[TableSchema]:
        """
        Full parse pipeline for a single .tmdl file.
        Order matters: name first, then columns, then measures, then Power Query.
        Classification needs all four inputs.
        """
        content  = path.read_text(encoding="utf-8", errors="ignore")
        lines    = content.split("\n")
        name     = self._get_table_name(lines, path.stem)
        columns  = self._parse_columns(lines, name)
        measures = self._parse_measures(lines, name)
        pq       = self._parse_power_query(lines)
        return TableSchema(
            name=name,
            table_type=self._classify_table(name, columns, measures, pq),
            columns=columns,
            measures=measures,
            power_query=pq,
        )

    def _get_table_name(self, lines, fallback) -> str:
        """
        Finds the table name from the first 'table' declaration line.
        Handles both quoted ('My Table') and unquoted (MyTable) formats.
        Falls back to the file stem if no match found.
        """
        for line in lines:
            m = re.match(r"^table\s+'([^']+)'", line) or re.match(r"^table\s+(\S+)", line)
            if m:
                return m.group(1)
        return fallback

    # ── Measure parser ──────────────────────────────────────────────────────────
    # TMDL stores DAX in 3 formats — this parser handles all three:
    #
    #   Format A (single line):
    #       \tmeasure 'Name' = EXPRESSION
    #
    #   Format B (backtick multiline):
    #       \tmeasure 'Name' = ```
    #           EXPRESSION LINE 1
    #           EXPRESSION LINE 2
    #       ```
    #
    #   Format C (bare multiline — no backticks):
    #       \tmeasure 'Name' =
    #           EXPRESSION LINE 1
    #           EXPRESSION LINE 2
    #       \t\tformatString = ...   ← signals end of DAX

    def _parse_measures(self, lines: list, table_name: str) -> list[MeasureSchema]:
        """
        Line-by-line state machine that detects and extracts all measures.
        Handles all 3 DAX encoding formats (A, B, C — see comment above).
        Skips measures with empty names or empty DAX bodies.
        """
        measures = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # detect the start of a measure declaration (tab-indented)
            m = re.match(r"^\t(measure\s+'([^']+)'|measure\s+(\S+))\s*=\s*(.*)", line)
            if not m:
                i += 1
                continue

            measure_name = m.group(2) or m.group(3)
            after_eq     = m.group(4).strip()
            dax          = ""

            # ── Format B: backtick-fenced multiline ──
            if after_eq == "```" or after_eq.startswith("```"):
                dax_lines = []
                i += 1
                while i < len(lines):
                    s = lines[i].strip()
                    if s == "```":
                        break
                    dax_lines.append(s)
                    i += 1
                dax = "\n".join(dax_lines).strip()

            # ── Format C: empty after =, multiline follows without backticks ──
            elif after_eq == "":
                dax_lines = []
                i += 1
                while i < len(lines):
                    l = lines[i]
                    # stop when next TMDL keyword is encountered at tab level
                    if re.match(r"^\t(measure|column|partition|annotation|hierarchy)\s", l):
                        i -= 1
                        break
                    # stop at metadata lines (not part of DAX)
                    if re.match(r"^\t\t(formatString|lineageTag|isHidden|displayFolder)\s", l):
                        i -= 1
                        break
                    s = l.strip()
                    if s:
                        dax_lines.append(s)
                    i += 1
                dax = "\n".join(dax_lines).strip()

            # ── Format A: single line after = ──
            else:
                dax = after_eq

            # Check if measure is hidden — look ahead up to 5 lines
            is_hidden = False
            for k in range(i + 1, min(i + 6, len(lines))):
                if re.search(r"isHidden\s*=\s*true", lines[k], re.IGNORECASE):
                    is_hidden = True
                    break
                if re.match(r"^\t(measure|column)\s", lines[k]):
                    break

            if measure_name and dax.strip():
                measures.append(MeasureSchema(
                    name=measure_name,
                    table=table_name,
                    dax=dax.strip(),
                    is_visible=not is_hidden,
                    referenced_tables=self._tables_from_dax(dax),
                    referenced_columns=self._cols_from_dax(dax),
                ))
            i += 1
        return measures

    # ── Column parser ───────────────────────────────────────────────────────────

    def _parse_columns(self, lines: list, table_name: str) -> list[ColumnSchema]:
        """
        Extracts all column declarations from a table's TMDL lines.
        Handles both physical columns (from data source) and calculated columns (DAX).
        A column is 'calculated' if it has a type: calculated flag or expression property.
        """
        columns = []
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(r"^\t(column\s+'([^']+)'|column\s+(\S+))", line)
            if not m:
                i += 1
                continue
            col_name             = m.group(2) or m.group(3)
            dtype, is_calc, expr = "string", False, None
            j = i + 1
            while j < len(lines):
                l = lines[j]
                s = l.strip()
                # stop at next TMDL keyword
                if re.match(r"^\t(column|measure|partition|annotation|hierarchy)\s", l):
                    break
                if s.startswith("dataType:"):
                    dtype = s.split(":", 1)[1].strip()
                if "calculatedTableColumn" in s or "type: calculated" in s.lower():
                    is_calc = True
                if re.match(r"^\s*expression\s*[=:]", s):
                    expr    = s.split("=", 1)[-1].split(":", 1)[-1].strip()
                    is_calc = True
                j += 1
            columns.append(ColumnSchema(
                name=col_name, data_type=dtype,
                is_calculated=is_calc, expression=expr,
            ))
            i += 1
        return columns

    # ── Power Query parser ──────────────────────────────────────────────────────

    def _parse_power_query(self, lines: list) -> Optional[str]:
        """
        Extracts the M (Power Query) expression from the TMDL file.
        Tries two patterns:
          1. type = m block with backtick fence
          2. expression = ``` block
        Returns the stripped M code, or None if not found.
        Used by _classify_table() to detect static lookup tables.
        """
        content = "\n".join(lines)
        for pattern in [r"type\s*=\s*m\b.*?```(.*?)```", r"expression\s*=\s*```(.*?)```"]:
            m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    # ── Relationships parser ────────────────────────────────────────────────────

    def _parse_relationships(self, content: str) -> list[RelationshipSchema]:
        """
        Reads relationships.tmdl and extracts all relationship blocks.
        Each block is split by the 'relationship' keyword.
        Format: fromColumn / toColumn stored as "TableName.ColumnName".
        isActive: false marks inactive (dashed) relationships.
        """
        rels = []
        for block in re.split(r"(?=^relationship\s)", content, flags=re.MULTILINE):
            if not block.strip().startswith("relationship"):
                continue
            from_raw = self._get_prop(block, "fromColumn")
            to_raw   = self._get_prop(block, "toColumn")
            if not from_raw or not to_raw:
                continue
            from_table, from_col = self._split_tc(from_raw)
            to_table,   to_col   = self._split_tc(to_raw)
            # Skip relationships that involve auto-generated hidden date tables
            if self._is_auto_date_table(from_table) or self._is_auto_date_table(to_table):
                continue
            rels.append(RelationshipSchema(
                from_table=from_table, from_column=from_col,
                to_table=to_table,     to_column=to_col,
                direction=self._get_prop(block, "crossFilteringBehavior") or "singleDirection",
                is_active=not bool(re.search(r"isActive\s*:\s*false", block, re.IGNORECASE)),
            ))
        return rels

    # ── DAX reference extractors ────────────────────────────────────────────────

    def _tables_from_dax(self, dax: str) -> list[str]:
        """
        Extracts all table names referenced in a DAX expression.
        Handles both quoted ('TableName'[Column]) and unquoted (TableName[Column]) styles.
        Returns a deduplicated list.
        """
        return list(set(
            re.findall(r"'([^']+)'\[", dax) +
            re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\[", dax)
        ))

    def _cols_from_dax(self, dax: str) -> list[str]:
        """
        Extracts all 'Table[Column]' or Table[Column] references from a DAX expression.
        Returns deduplicated full references (used for lineage tracking).
        """
        return list(set(
            re.findall(r"'[^']+'\[[^\]]+\]", dax) +
            re.findall(r"[A-Za-z_][A-Za-z0-9_]*\[[^\]]+\]", dax)
        ))

    # ── Generic helpers ─────────────────────────────────────────────────────────

    def _get_prop(self, block: str, key: str) -> Optional[str]:
        """Extracts a single property value from a TMDL block by key name."""
        m = re.search(rf"^\s*{key}\s*:\s*(.+)$", block, re.MULTILINE)
        return m.group(1).strip() if m else None

    def _split_tc(self, raw: str) -> tuple[str, str]:
        """Splits a 'TableName.ColumnName' string into a (table, column) tuple."""
        p = raw.split(".", 1)
        return (p[0].strip(), p[1].strip()) if len(p) == 2 else (raw.strip(), "")