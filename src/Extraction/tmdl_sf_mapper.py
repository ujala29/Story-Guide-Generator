"""
tmdl_sf_mapper.py
-----------------
Auto-generates bi_snowflakes_naming_matching.json from a .SemanticModel folder.

Reads every .tmdl file under definition/tables/ and extracts:
  - Snowflake object name + kind from the M Query partition block
  - Column transformations: lowercased, removed, projection, derived, created_then_removed
  - has_max_month_flag and date_column from column declarations
  - Table type: source | static_lookup | parameter | measure_container

Produces the same JSON structure as the hand-crafted
bi_snowflakes_naming_matching.json. The only field not derivable from TMDL
is table_id (stored in the .abf binary) — it is omitted from output.

Usage:
    python src/Extraction/tmdl_sf_mapper.py \
        --semantic-model "input/Risk-Management-v4_Insights_v1.SemanticModel"

    python src/Extraction/tmdl_sf_mapper.py \
        --semantic-model "input/PAC-v4_Insights_v1.SemanticModel" \
        --output "input/pac_dashboard_bi_sf_mapping.json"
"""
from __future__ import annotations

import re
import json
import sys
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Constants ─────────────────────────────────────────────────────────────────

AUTO_DATE_PREFIXES = ("LocalDateTable_", "DateTableTemplate_")

MEASURE_CONTAINER_NAMES = {
    "all dax", "all_dax", "all_dax_pac", "measures", "_measures",
    "key measures", "dax measures", "dax",
}

# Pre-truncated month columns — matched by prefix, used directly in WHERE clause
MONTH_COL_PREFIX = "month_of_"

# Raw date columns — tried in priority order when no month_of_* column exists.
# All raw date columns are wrapped in DATE_TRUNC('month', col) in the output.
# Priority 1: columns whose name ends with _start_date (primary event start)
# Priority 2: columns whose name ends with _date but not excluded
# Priority 3: any remaining dateTime column not excluded
_DATE_START_SUFFIX  = "_start_date"
_DATE_GENERIC_SUFFIX = "_date"

# dateTime columns that are never date-filter columns
_DATE_EXCLUDE_EXACT    = {"dob", "date_of_birth", "birth_date", "created_at", "updated_at", "modified_at"}
_DATE_EXCLUDE_SUFFIXES = ("_end_date", "_expiry_date", "_expire_date", "_birth_date")


# ── M Query helpers ───────────────────────────────────────────────────────────

def _extract_mquery(content: str) -> tuple[str | None, str | None]:
    """
    Extract the M Query source block and partition type from a TMDL file.

    Returns (mq, partition_type) where partition_type is 'm' or 'calculated'.
    Handles both 'partition ... = m' and 'partition ... = calculated' blocks.
    """
    m = re.search(
        r'^\tpartition\s+.*?=\s*(m|calculated)\b',
        content, re.MULTILINE | re.IGNORECASE,
    )
    if not m:
        return None, None

    partition_type = m.group(1).lower()
    after = content[m.start():]
    cut = re.search(r'\n\tannotation\s', after)
    block = after[: cut.start()] if cut else after

    src = re.search(r'\bsource\s*=\s*\n?(.*)', block, re.DOTALL | re.IGNORECASE)
    if not src:
        return None, partition_type

    lines = [ln.strip() for ln in src.group(1).split('\n') if ln.strip()]
    return '\n'.join(lines), partition_type


def _extract_sf_object(mq: str) -> tuple[str | dict | None, str | None]:
    """
    Parse the Snowflake object name and kind from an M Query.

    Pattern 1 — simple string:
        {[Name= "DATE_VIEW", Kind="View"]}[Data]

    Pattern 2 — conditional DB_TYPE:
        {[Name= if DB_TYPE = "Postgres" then "pg_view" else "SF_VIEW", Kind="View"]}[Data]

    NOTE: no re.DOTALL here — each [Name=...] pattern is on a single line,
    and DOTALL would cause (.*?) to span across multiple lines and pick up
    the wrong match.
    """
    # Pattern 2 first: conditional DB_TYPE (more specific)
    cond_m = re.search(
        r'\[Name\s*=\s*if\s+DB_TYPE\s*=\s*"Postgres"\s+then\s+"([^"]+)"\s+else\s+"([^"]+)"\s*,\s*Kind\s*=\s*"(View|Table)"\s*\]',
        mq, re.IGNORECASE,
    )
    if cond_m:
        return {"snowflake": cond_m.group(2), "postgres": cond_m.group(1)}, cond_m.group(3)

    # Pattern 1: simple quoted name — only match the object/view lookup line, not the DB or schema lines
    simple_m = re.search(
        r'\[Name\s*=\s*"([^"]+)"\s*,\s*Kind\s*=\s*"(View|Table)"\s*\]',
        mq, re.IGNORECASE,
    )
    if simple_m:
        return simple_m.group(1), simple_m.group(2)

    return None, None


# ── Transformation extraction ─────────────────────────────────────────────────

def _extract_transformations(mq: str) -> dict:
    """
    Walk M Query steps and build the transformations dict.

    Detected patterns:
      Text.Lower              → lowercased: true
      RemoveColumns           → col: {type: removed}
      SelectColumns           → __projection__: {type: select_columns, columns: [...]}
      DuplicateColumn+Rename  → col: {type: derived, source_column: ...}
      AddColumn then Remove   → col: {type: created_then_removed, m_expression: ...}
      AddColumn then kept     → col: {type: created, m_expression: ...}
      Table.Distinct          → deduplicated_on: [...], col: {type: deduplicated}
    """
    trans: dict = {}
    col_trans: dict = {}

    # ── lowercased ──────────────────────────────────────────────────────────
    if re.search(r'Table\.TransformColumnNames\s*\(.*?Text\.Lower', mq, re.DOTALL | re.IGNORECASE):
        trans["lowercased"] = True

    # ── AddColumn: intermediate columns created in M ─────────────────────────
    # Each call is normally on one logical line after stripping.
    created: dict[str, str] = {}  # raw_name -> m_expression
    for ln in mq.split('\n'):
        m = re.search(
            r'Table\.AddColumn\s*\([^,]+,\s*"([^"]+)"\s*,\s*each\s+(.+)',
            ln, re.IGNORECASE,
        )
        if m:
            col_name = m.group(1)
            expr = m.group(2).rstrip('),').strip()
            created[col_name] = expr

    # ── DuplicateColumn: copies an existing column ───────────────────────────
    duplicated: dict[str, str] = {}  # copy_name -> source_col
    for m in re.finditer(
        r'Table\.DuplicateColumn\s*\([^,]+,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)',
        mq, re.IGNORECASE,
    ):
        duplicated[m.group(2)] = m.group(1)  # copy_name -> source

    # ── RenameColumns: collect ALL rename pairs ──────────────────────────────
    renames: dict[str, str] = {}  # old -> new
    for block_m in re.finditer(
        r'Table\.RenameColumns\s*\([^,]+,\s*\{(.*?)\}\s*\)',
        mq, re.DOTALL | re.IGNORECASE,
    ):
        for pair in re.finditer(
            r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\}', block_m.group(1)
        ):
            renames[pair.group(1)] = pair.group(2)

    def final_name(original: str) -> str:
        return renames.get(original, original)

    created_final = {final_name(k): v for k, v in created.items()}
    duplicated_final = {final_name(k): v for k, v in duplicated.items()}

    # ── RemoveColumns: collect across all steps ──────────────────────────────
    removed: set[str] = set()
    for m in re.finditer(
        r'Table\.RemoveColumns\s*\([^,]+,\s*\{(.*?)\}\s*\)',
        mq, re.DOTALL | re.IGNORECASE,
    ):
        for col in re.findall(r'"([^"]+)"', m.group(1)):
            removed.add(col)

    # ── SelectColumns: keep-only projection ─────────────────────────────────
    select_m = re.search(
        r'Table\.SelectColumns\s*\([^,]+,\s*\{(.*?)\}\s*\)',
        mq, re.DOTALL | re.IGNORECASE,
    )
    select_cols = re.findall(r'"([^"]+)"', select_m.group(1)) if select_m else None

    # ── Table.Distinct: deduplication on specific columns ────────────────────
    dedup_cols: list[str] = []
    for m in re.finditer(
        r'Table\.Distinct\s*\([^,]+,\s*\{(.*?)\}\s*\)',
        mq, re.DOTALL | re.IGNORECASE,
    ):
        for col in re.findall(r'"([^"]+)"', m.group(1)):
            dedup_cols.append(col)
    if dedup_cols:
        trans["deduplicated_on"] = dedup_cols

    # ── Build col_trans ──────────────────────────────────────────────────────
    for col in sorted(removed):
        if col in created_final:
            col_trans[col] = {
                "type": "created_then_removed",
                "m_expression": created_final[col],
            }
        else:
            col_trans[col] = {"type": "removed"}

    for name, source_col in sorted(duplicated_final.items()):
        if name not in removed:
            col_trans[name] = {"type": "derived", "source_column": source_col}

    for name, expr in sorted(created_final.items()):
        if name not in removed and name not in col_trans:
            # AddColumn creates a brand-new column (not a copy) → type "created"
            col_trans[name] = {"type": "created", "m_expression": expr}

    for col in dedup_cols:
        col_trans[col] = {"type": "deduplicated"}

    if select_cols:
        col_trans["__projection__"] = {"type": "select_columns", "columns": select_cols}

    if col_trans:
        trans["columns"] = col_trans

    return trans


# ── Table classification ──────────────────────────────────────────────────────

def _classify(
    name: str, mq: str | None, partition_type: str | None,
    has_real_cols: bool, has_measures: bool,
) -> str:
    n = name.lower()

    # Measure containers: only measures, no physical data
    if n in MEASURE_CONTAINER_NAMES or (has_measures and not has_real_cols):
        return "measure_container"

    # 'calculated' partition = DAX-defined slicer/parameter table (e.g. DATATABLE, NAMEOF tuples)
    if partition_type == "calculated":
        return "parameter"

    if mq:
        mq_l = mq.lower()
        if "datatable" in mq_l:
            return "parameter"
        if "snowflake.databases" in mq_l:
            return "source"
        if any(k in mq_l for k in ("table.fromrows", "binary.decompress", "json.document", "#table(")):
            return "static_lookup"

    if n.startswith("static_"):
        return "static_lookup"

    return "source"


# ── Per-file parser ───────────────────────────────────────────────────────────

def _parse_tmdl(path: Path) -> dict | None:
    content = path.read_text(encoding="utf-8", errors="ignore")
    lines = content.split("\n")

    # Table name from first 'table' declaration
    name = path.stem
    for line in lines:
        m = re.match(r"^table\s+'([^']+)'", line) or re.match(r"^table\s+(\S+)", line)
        if m:
            name = m.group(1)
            break

    if any(name.startswith(p) for p in AUTO_DATE_PREFIXES):
        return None

    # Columns
    columns: list[dict] = []
    i = 0
    while i < len(lines):
        cm = re.match(r"^\t(column\s+'([^']+)'|column\s+(\S+))", lines[i])
        if cm:
            col_name = cm.group(2) or cm.group(3)
            dtype, is_calc = "string", False
            j = i + 1
            while j < len(lines):
                l = lines[j]
                if re.match(r"^\t(column|measure|partition|annotation|hierarchy)\s", l):
                    break
                s = l.strip()
                if s.startswith("dataType:"):
                    dtype = s.split(":", 1)[1].strip()
                if "calculatedTableColumn" in s or "type: calculated" in s.lower():
                    is_calc = True
                if re.match(r"^\s*expression\s*[=:]", s):
                    is_calc = True
                j += 1
            columns.append({"name": col_name, "dataType": dtype, "is_calc": is_calc})
        i += 1

    has_measures = bool(re.search(r"^\tmeasure\s", content, re.MULTILINE))
    real_cols = [c for c in columns if not c["is_calc"]]
    mq, partition_type = _extract_mquery(content)
    table_type = _classify(name, mq, partition_type, bool(real_cols), has_measures)

    return {
        "name": name,
        "type": table_type,
        "columns": columns,
        "real_cols": real_cols,
        "mq": mq,
    }


# ── Date column detector ──────────────────────────────────────────────────────

def _detect_date_col(columns: list) -> str | None:
    """
    Identify the primary date-filter column for a source table.

    Priority order (first match wins):
      1. month_of_* (dateTime)     → use directly, e.g. "MONTH_OF_MEASUREMENT"
      2. *_start_date (dateTime)   → DATE_TRUNC('month', col)
      3. *_date (dateTime)         → DATE_TRUNC('month', col)
      4. any remaining dateTime    → DATE_TRUNC('month', col)

    Excluded from all priorities:
      - exact names: dob, date_of_birth, birth_date, created_at, updated_at, modified_at
      - suffix patterns: _end_date, _expiry_date, _expire_date, _birth_date
    """
    def _is_excluded(name: str) -> bool:
        n = name.lower()
        return n in _DATE_EXCLUDE_EXACT or any(n.endswith(s) for s in _DATE_EXCLUDE_SUFFIXES)

    datetime_cols = [c for c in columns if c["dataType"] == "dateTime" and not _is_excluded(c["name"])]

    # Priority 1: month_of_* → pre-truncated, use directly
    for c in datetime_cols:
        if c["name"].lower().startswith(MONTH_COL_PREFIX):
            return c["name"].upper()

    # Priority 2: *_start_date → primary event start
    for c in datetime_cols:
        if c["name"].lower().endswith(_DATE_START_SUFFIX):
            return f"DATE_TRUNC('month', {c['name'].upper()})"

    # Priority 3: *_date → generic date column
    for c in datetime_cols:
        if c["name"].lower().endswith(_DATE_GENERIC_SUFFIX):
            return f"DATE_TRUNC('month', {c['name'].upper()})"

    # No recognized date filter column found
    return None


# ── Mapping entry builder ─────────────────────────────────────────────────────

def _build_entry(tmdl: dict) -> dict:
    name = tmdl["name"]
    table_type = tmdl["type"]
    mq = tmdl["mq"]
    columns = tmdl["columns"]

    if table_type == "measure_container":
        return {"type": "measure_container", "snowflake_object": None}

    if table_type == "static_lookup":
        return {}  # caller groups these under "static_tables"

    if table_type == "parameter":
        return {"type": "parameter", "note": "DATATABLE"}

    # source table
    sf_obj, sf_kind = _extract_sf_object(mq) if mq else (None, None)

    entry: dict = {
        "bi_table": name,
        "snowflake_object": sf_obj,
        "snowflake_kind": sf_kind,
        "type": "source",
    }

    col_names_lower = {c["name"].lower() for c in columns}

    # has_max_month_flag — only for tables that import month_of_measurement
    # True  = max_month_flag column exists in the view
    # False = month_of_measurement exists but max_month_flag was NOT imported
    has_mom = any(c["name"].lower() == "month_of_measurement" for c in columns)
    if "max_month_flag" in col_names_lower:
        entry["has_max_month_flag"] = True
    elif has_mom:
        entry["has_max_month_flag"] = False

    # date_column — detect for ANY source table using priority + exclusion rules
    detected = _detect_date_col(columns)
    if detected:
        entry["date_column"] = detected

    if mq:
        trans = _extract_transformations(mq)
        if trans:
            entry["transformations"] = trans

    return entry


# ── Public API ────────────────────────────────────────────────────────────────

def generate_mapping(sm_path: Path) -> dict:
    """
    Parse all TMDL files under <sm_path>/definition/tables/ and return the
    BI→Snowflake mapping dict (same structure as bi_snowflakes_naming_matching.json).
    """
    tables_dir = sm_path / "definition" / "tables"
    if not tables_dir.exists():
        raise FileNotFoundError(f"TMDL tables folder not found: {tables_dir}")

    mapping: dict = {}
    static_tables: dict = {}

    print(f"Parsing TMDL files in: {tables_dir}\n")
    for tmdl_file in sorted(tables_dir.glob("*.tmdl")):
        tmdl = _parse_tmdl(tmdl_file)
        if tmdl is None:
            continue

        name = tmdl["name"]
        t = tmdl["type"]
        print(f"  {name:<45} {t}")

        if t == "static_lookup":
            static_tables[name] = {}
        else:
            entry = _build_entry(tmdl)
            mapping[name] = entry

    if static_tables:
        mapping["static_tables"] = static_tables

    return mapping


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Auto-generate BI→Snowflake mapping JSON from .SemanticModel TMDL files"
    )
    ap.add_argument(
        "--semantic-model", required=True,
        help="Path to the .SemanticModel folder (e.g. input/Risk-Management-v4_Insights_v1.SemanticModel)",
    )
    ap.add_argument(
        "--output",
        help="Output JSON path (default: <semantic-model-parent>/<stem>_bi_sf_mapping.json)",
    )
    args = ap.parse_args()

    sm_path = Path(args.semantic_model)

    if args.output:
        out_path = Path(args.output)
    else:
        stem = sm_path.stem.split(".")[0]
        out_path = sm_path.parent / f"{stem}_bi_sf_mapping.json"

    mapping = generate_mapping(sm_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWritten → {out_path}")


if __name__ == "__main__":
    main()
