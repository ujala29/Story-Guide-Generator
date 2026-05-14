# dependency_graph.py — Measure Dependency DAG

## Purpose
Builds and analyzes the measure-to-measure dependency graph (Directed Acyclic Graph). Answers: which measures call other measures, what is the safe evaluation order, how deep is the deepest dependency chain, and which measures are referenced most often.

This runs **after** `tmdl_parser.py` extracts raw measures and **before** any DAX-to-SQL conversion or story guide generation.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `list[MeasureSchema]` — raw measures from `TMDLExtractor` |
| **Output (enrich_measures)** | Same list, mutated in-place with `depends_on`, `depth`, `is_leaf` |
| **Output (build_edges)** | `list[DependencyEdge]` — written to `dependency_graph.json` |
| **Output (topological_order)** | `list[str]` — measure names sorted leaf-first |
| **Output (build_summary)** | `dict` — aggregate stats for `ExtractionSummary` |

---

## Algorithm
- **Dependency detection**: regex scan of each measure's DAX for `[MeasureName]` tokens
- **Topological sort**: Kahn's Algorithm (BFS with in-degree tracking)
- **Cycle protection**: `get_depth()` uses a `visited` set to prevent infinite recursion

---

## Function Flow

```
MeasureDependencyGraph(all_measures)
  │
  ├── __init__(measures)
  │     ├── builds self.measure_map  {name → MeasureSchema}
  │     ├── builds self.deps         {name → [direct_dep_names]}
  │     └── builds self.dependents   {name → [measures_that_call_it]}
  │           └── _build()           ← scans DAX with regex
  │
  ├── enrich_measures(measures)      ← Step 2 in extractor.py
  │     └── for each measure:
  │           m.depends_on = self.deps[m.name]
  │           m.depth      = get_depth(m.name)
  │           m.is_leaf    = len(m.depends_on) == 0
  │
  ├── build_edges()                  ← Step 2 in extractor.py
  │     └── for each measure in deps:
  │           DependencyEdge(measure, depends_on, depth, is_leaf)
  │
  ├── topological_order()            ← Step 2 in extractor.py
  │     ├── compute in-degrees
  │     ├── queue starts with 0-in-degree measures (leaves)
  │     └── Kahn's BFS → sorted name list
  │
  ├── get_depth(name, visited)       ← called by enrich_measures + build_edges
  │     └── recursive: 0 if no deps, else 1 + max(child depths)
  │           (visited set guards against cycles)
  │
  └── build_summary()                ← Step 2 in extractor.py
        └── returns {
              measures_with_dependencies,
              max_dependency_depth,
              most_referenced_measures (top 10)
            }
```

---

## Function Details

### `__init__(measures)`
Calls `_build()` to scan all measures' DAX expressions.

### `_build()`
For each measure, finds all `[SomeName]` tokens in the DAX string using regex `\[([^\]]+)\]`. If `SomeName` matches another known measure (and is not self-referential), records it as a dependency. Also builds the reverse map (`dependents`) for Kahn's algorithm.

### `enrich_measures(measures) → list[MeasureSchema]`
Mutates each `MeasureSchema` in-place. Returns same list (for method chaining convenience). Called by `extractor.py` as Step 2.

### `topological_order() → list[str]`
Kahn's BFS algorithm:
1. Compute `in_degree` (number of dependencies) for every measure
2. Seed queue with measures that have 0 dependencies (true leaves)
3. Pop from queue → append to result → decrement dependents' in-degree
4. When a dependent reaches 0 in-degree, add to queue
5. Any unreached measures are appended at end (handles cycle edge cases gracefully)

**Why this matters**: ensures we never process a measure before its dependencies.

### `get_depth(name, visited=None) → int`
Recursive depth calculator. `depth=0` means leaf (no dependencies). Depth N means the deepest dependency chain is N levels. The `visited` set (copied on each recursion) prevents infinite loops from circular references.

### `build_edges() → list[DependencyEdge]`
Creates one `DependencyEdge` per measure recording: `measure name`, `depends_on list`, `depth`, `is_leaf`. Written to `dependency_graph.json`.

### `build_summary() → dict`
Returns three aggregate stats used in `ExtractionSummary`:
- `measures_with_dependencies` — count of non-leaf measures
- `max_dependency_depth` — the deepest chain found
- `most_referenced_measures` — top 10 by `dependent_count` (how many other measures call it)

---

## File Connections

| Imports from | Used for |
|---|---|
| `models.py` | `MeasureSchema`, `DependencyEdge` |

**Called by:** `extractor.py` → `run_extraction()` (Step 2)

---

## Hardcoded Parts (Change for New Dashboards)

> **None.** The dependency detection is fully dynamic — it scans whatever measures exist in the model. No measure names, table names, or thresholds are hardcoded.

The only implicit assumption is that DAX measure references use `[MeasureName]` bracket syntax — this is standard across all Power BI models.
