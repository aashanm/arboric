"""
Arboric Constraint Satisfaction

Dependency graph analysis, validation, and topological sorting
for multi-workload scheduling with constraints.
"""

from uuid import UUID

from arboric.core.models import Workload


class DependencyGraphError(ValueError):
    """Base exception for dependency graph issues."""

    pass


class CircularDependencyError(DependencyGraphError):
    """Raised when circular dependencies are detected."""

    pass


class InvalidDependencyError(DependencyGraphError):
    """Raised when a dependency references an unknown workload."""

    pass


class DependencyGraph:
    """
    Manages and validates workload dependency relationships.

    Provides:
    - Circular dependency detection (DFS-based)
    - Topological sorting (Kahn's algorithm)
    - Dependency chain analysis
    - Graph structure validation
    """

    def __init__(self, workloads: list[Workload]):
        """
        Initialize and validate dependency graph.

        Args:
            workloads: List of workloads with potential dependencies

        Raises:
            InvalidDependencyError: If dependencies reference unknown workloads
            CircularDependencyError: If circular dependencies exist
        """
        self.workloads: dict[UUID, Workload] = {w.id: w for w in workloads}
        self.adjacency_list: dict[UUID, list[UUID]] = {}
        self.reverse_adjacency: dict[UUID, list[UUID]] = {}

        self._build_graph()
        self._validate_graph()

    def _build_graph(self) -> None:
        """Build adjacency list representation of dependency graph."""
        # Initialize adjacency lists for all workloads first
        for wid in self.workloads:
            self.adjacency_list[wid] = []
            self.reverse_adjacency[wid] = []

        # For each workload, add its prerequisites to the graph
        for workload in self.workloads.values():
            for dep in workload.dependencies:
                prereq_id = dep.source_workload_id

                if prereq_id not in self.workloads:
                    raise InvalidDependencyError(
                        f"Workload '{workload.name}' depends on unknown "
                        f"workload ID {prereq_id}"
                    )

                if prereq_id == workload.id:
                    raise InvalidDependencyError(
                        f"Workload '{workload.name}' cannot depend on itself"
                    )

                # adjacency_list: workload -> its prerequisites
                self.adjacency_list[workload.id].append(prereq_id)
                # reverse: prerequisite -> workloads that depend on it
                self.reverse_adjacency[prereq_id].append(workload.id)

    def _validate_graph(self) -> None:
        """Detect circular dependencies using DFS."""
        visited: set[UUID] = set()
        rec_stack: set[UUID] = set()

        def has_cycle(node: UUID) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for prereq in self.adjacency_list[node]:
                if prereq not in visited:
                    if has_cycle(prereq):
                        return True
                elif prereq in rec_stack:
                    # Back edge detected - cycle exists
                    return True

            rec_stack.remove(node)
            return False

        for wid in self.workloads:
            if wid not in visited:
                if has_cycle(wid):
                    raise CircularDependencyError(
                        "Circular dependency detected. All workloads must "
                        "form a directed acyclic graph (DAG)."
                    )

    def topological_sort(self) -> list[UUID]:
        """
        Return workload IDs in topologically sorted order.

        Uses Kahn's algorithm (BFS-based topological sort).
        Workloads with no dependencies come first.

        Returns:
            List of workload IDs in execution order
        """
        # Calculate in-degrees (number of prerequisites)
        in_degree: dict[UUID, int] = {
            wid: len(prereqs)
            for wid, prereqs in self.adjacency_list.items()
        }

        # Start with workloads that have no dependencies
        queue: list[UUID] = [
            wid for wid, deg in in_degree.items() if deg == 0
        ]
        sorted_order: list[UUID] = []

        while queue:
            current = queue.pop(0)
            sorted_order.append(current)

            # Reduce in-degree for dependent workloads
            for dependent in self.reverse_adjacency[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # If not all workloads processed, cycle exists
        if len(sorted_order) != len(self.workloads):
            raise CircularDependencyError(
                "Failed to produce topological sort - cycle detected"
            )

        return sorted_order

    def get_workload_level(self, workload_id: UUID) -> int:
        """
        Get dependency level of a workload.

        Level 0: No dependencies
        Level 1: Depends only on level 0 workloads
        Level N: Depends on at least one level N-1 workload

        Args:
            workload_id: UUID of the workload

        Returns:
            Integer representing dependency level
        """
        if not self.adjacency_list[workload_id]:
            return 0

        prereq_levels = [
            self.get_workload_level(prereq)
            for prereq in self.adjacency_list[workload_id]
        ]
        return max(prereq_levels) + 1
