# relationship_parser.py
# Parses the relationships.tmdl file and returns a list of RelationshipSchema objects.
# This file is separate from tmdl_parser.py because relationships live in their own file
# inside the SemanticModel and have a completely different structure from table definitions.

import re
from typing import Optional

from .models import RelationshipSchema


class RelationshipParser:
    """
    Stateless parser for the relationships.tmdl file.
    All methods are class-level (no instance needed) because there is no state to keep —
    the file is read once and fully processed in a single pass.
    """

    @classmethod
    def parse(cls, content: str) -> list[RelationshipSchema]:
        """
        Main entry point.  Splits the file content into individual relationship blocks
        (each block starts with the keyword "relationship") and delegates each block
        to _parse_block().  Blocks that cannot be parsed are silently skipped.
        """
        rels   = []
        # Split on every line that begins a new "relationship" declaration.
        # The lookahead (?=...) keeps the "relationship" keyword at the start of each chunk.
        blocks = re.split(r"(?=^relationship\s)", content, flags=re.MULTILINE)

        for block in blocks:
            if not block.strip().startswith("relationship"):
                continue    # skip the preamble text before the first block
            rel = cls._parse_block(block)
            if rel:
                rels.append(rel)

        return rels

    @classmethod
    def _parse_block(cls, block: str) -> Optional[RelationshipSchema]:
        """
        Extracts the five pieces of information that define one relationship:
          fromColumn  — "TableA.ColumnA" style string for the many-side
          toColumn    — "TableB.ColumnB" style string for the one-side
          direction   — cross-filter direction (defaults to "singleDirection" if absent)
          isActive    — whether the relationship is active (default True; False if explicitly set)

        Returns None if fromColumn or toColumn cannot be found (malformed block).
        """
        from_raw = cls._get_prop(block, "fromColumn")
        to_raw   = cls._get_prop(block, "toColumn")

        # Both ends of the join must be present; skip the block if either is missing
        if not from_raw or not to_raw:
            return None

        from_table, from_col = cls._split_table_col(from_raw)
        to_table,   to_col   = cls._split_table_col(to_raw)

        direction   = cls._get_prop(block, "crossFilteringBehavior") or "singleDirection"
        is_inactive = bool(re.search(r"isActive\s*:\s*false", block, re.IGNORECASE))

        return RelationshipSchema(
            from_table=from_table,
            from_column=from_col,
            to_table=to_table,
            to_column=to_col,
            direction=direction,
            is_active=not is_inactive,  # flip: absence of isActive:false means it IS active
        )

    @classmethod
    def _get_prop(cls, block: str, key: str) -> Optional[str]:
        """
        Finds a single "key: value" line inside a block and returns the value string.
        Returns None if the key is not present in the block.
        """
        m = re.search(rf"^\s*{key}\s*:\s*(.+)$", block, re.MULTILINE)
        return m.group(1).strip() if m else None

    @classmethod
    def _split_table_col(cls, raw: str):
        """
        Splits a "TableName.ColumnName" string into a (table, column) tuple.
        If there is no dot, returns the whole string as the table and an empty column.
        """
        parts = raw.split(".", 1)
        return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (raw.strip(), "")
