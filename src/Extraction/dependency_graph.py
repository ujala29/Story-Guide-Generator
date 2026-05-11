# pipeline/stage1_extraction/dependency_graph.py
#
# PURPOSE:
#   Builds and analyzes the measure→measure dependency graph (DAG).
#   Answers questions like:
#     - Which measures call other measures?
#     - What is the safe evaluation order (topological sort)?
#     - How deep is the deepest dependency chain?
#     - Which measures are referenced most often?
#
# WHY THIS MATTERS:
#   DAX measures often build on each other. Before any DAX→SQL conversion
#   or story guide generation, we need to know the dependency structure
#   so we process measures in the correct order (leaves first, roots last).
#
# ALGORITHM:
#   Uses Kahn's Algorithm (BFS with in-degree tracking) for topological sort.
#   Cycle protection is included in get_depth() via a visited set.
#
# CALLED BY:
#   pipeline/stage1_extraction/extractor.py → run_extraction()

import re
from collections import defaultdict, deque

from models import MeasureSchema, DependencyEdge


class MeasureDependencyGraph:
    """
    Directed Acyclic Graph (DAG) of measure-to-measure dependencies.

    After construction, call:
      enrich_measures()    → adds depends_on / depth / is_leaf to each MeasureSchema
      topological_order()  → returns measure names sorted leaf-first
      build_edges()        → returns DependencyEdge list for the JSON output
      build_summary()      → returns aggregate stats (depth, top referenced)

    Usage:
        graph    = MeasureDependencyGraph(all_measures)
        measures = graph.enrich_measures(all_measures)
        edges    = graph.build_edges()
        order    = graph.topological_order()
    """

    def __init__(self, measures: list[MeasureSchema]):
        """
        Builds the dependency map by scanning each measure's DAX for
        [MeasureName] references to other known measures.

        self.deps       → {measure_name: [direct_dependencies]}
        self.dependents → {measure_name: [measures_that_call_it]}
        """
        self.measures    = measures
        self.measure_map = {m.name: m for m in measures}
        self.deps:        dict[str, list[str]] = {}
        self.dependents:  dict[str, list[str]] = defaultdict(list)
        self._build()

    def _build(self):
        """
        Scans each measure's DAX for [SomeName] tokens.
        If SomeName is a known measure (not self), it's recorded as a dependency.
        Also builds the reverse map (dependents) for Kahn's algorithm.
        """
        for m in self.measures:
            refs = [
                r.strip() for r in re.findall(r"\[([^\]]+)\]", m.dax)
                if r.strip() in self.measure_map and r.strip() != m.name
            ]
            self.deps[m.name] = list(set(refs))
            for d in self.deps[m.name]:
                self.dependents[d].append(m.name)

    # ── Public Methods ──────────────────────────────────────────────────────────

    def topological_order(self) -> list[str]:
        """
        Returns all measure names sorted so that dependencies come before
        the measures that use them (leaf-first / dependency-first order).

        Algorithm: Kahn's BFS with in-degree tracking.
          1. Compute in-degree (number of dependencies) for every measure.
          2. Start queue with all measures that have 0 dependencies (leaves).
          3. Process queue: append to result, decrement dependents' in-degree.
          4. When a dependent reaches in-degree 0, add it to the queue.
          5. Append any unreached measures at the end (handles DAG cycles gracefully).

        WHY: Ensures we never process a measure before its dependencies are ready.
        """
        in_degree = {m.name: 0 for m in self.measures}
        for name, deps in self.deps.items():
            for d in deps:
                if d in in_degree:
                    in_degree[name] += 1

        queue = deque([n for n, d in in_degree.items() if d == 0])
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for dep in self.dependents.get(node, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        # append any measures not reached (cycle safety net)
        seen = set(order)
        order.extend(m.name for m in self.measures if m.name not in seen)
        return order

    def get_depth(self, name: str, visited: set = None) -> int:
        """
        Recursively computes dependency chain depth for a single measure.

        Depth definition:
          0 = leaf measure (no dependencies)
          1 = calls at least one leaf
          N = deepest chain is N levels down

        visited set prevents infinite recursion in case of cycles.
        """
        if visited is None:
            visited = set()
        if name in visited:
            return 0   # cycle guard — return 0 to avoid infinite loop
        visited.add(name)
        deps = self.deps.get(name, [])
        return 0 if not deps else 1 + max(self.get_depth(d, visited.copy()) for d in deps)

    def build_edges(self) -> list[DependencyEdge]:
        """
        Builds a DependencyEdge for every measure in the graph.
        Each edge records: direct deps, chain depth, and leaf status.
        This list is written directly into extracted_schema.json.
        """
        return [
            DependencyEdge(
                measure=n, depends_on=d,
                depth=self.get_depth(n), is_leaf=len(d) == 0
            )
            for n, d in self.deps.items()
        ]

    def enrich_measures(self, measures: list[MeasureSchema]) -> list[MeasureSchema]:
        """
        Mutates each MeasureSchema in-place to add dependency metadata:
          - depends_on  → list of direct measure dependencies
          - depth       → recursive chain depth (0 = leaf)
          - is_leaf     → True when depends_on is empty

        Called AFTER extract_tables() so measures already exist.
        Returns the same list (mutated in place, but returned for chaining).
        """
        for m in measures:
            m.depends_on = self.deps.get(m.name, [])
            m.depth      = self.get_depth(m.name)
            m.is_leaf    = len(m.depends_on) == 0
        return measures

    def build_summary(self) -> dict:
        """
        Produces aggregate statistics about the dependency graph.
        Used in ExtractionSummary and for LLM context in story guide generation.

        Returns:
          measures_with_dependencies  → count of measures that call other measures
          max_dependency_depth        → deepest chain across all measures
          most_referenced_measures    → top-10 measures by how many others depend on them
        """
        ref_counts = {n: len(d) for n, d in self.dependents.items()}
        top_refs   = sorted(ref_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "measures_with_dependencies": sum(1 for d in self.deps.values() if d),
            "max_dependency_depth":       max(
                (self.get_depth(m.name) for m in self.measures), default=0
            ),
            "most_referenced_measures":   [
                {"name": n, "dependent_count": c} for n, c in top_refs
            ],
        }