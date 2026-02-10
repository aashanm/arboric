"""
Tests for Arboric Dependency Graph and Constraint Satisfaction

Tests for cycle detection, topological sorting, and dependency graph
validation for multi-workload scheduling.
"""

from uuid import UUID

import pytest

from arboric.core.constraints import (
    CircularDependencyError,
    DependencyGraph,
    InvalidDependencyError,
)
from arboric.core.models import Workload, WorkloadDependency


class TestDependencyGraph:
    """Unit tests for dependency graph management."""

    @pytest.fixture
    def simple_workloads(self):
        """Create simple workloads for testing."""
        return [
            Workload(
                name="Job A",
                duration_hours=2.0,
                power_draw_kw=30.0,
                deadline_hours=12.0,
            ),
            Workload(
                name="Job B",
                duration_hours=2.0,
                power_draw_kw=30.0,
                deadline_hours=12.0,
            ),
        ]

    def test_empty_graph(self):
        """Empty workload list should create valid graph."""
        graph = DependencyGraph([])
        assert len(graph.workloads) == 0
        sorted_order = graph.topological_sort()
        assert sorted_order == []

    def test_single_workload_no_dependencies(self):
        """Single workload with no dependencies."""
        workload = Workload(
            name="Solo Job",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        graph = DependencyGraph([workload])
        assert len(graph.workloads) == 1
        sorted_order = graph.topological_sort()
        assert sorted_order == [workload.id]

    def test_simple_linear_chain(self):
        """A → B → C linear dependency chain."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=b.id)],
        )

        graph = DependencyGraph([a, b, c])
        sorted_order = graph.topological_sort()

        # A should come before B, B before C
        assert sorted_order.index(a.id) < sorted_order.index(b.id)
        assert sorted_order.index(b.id) < sorted_order.index(c.id)

    def test_parallel_workloads(self):
        """Multiple independent workloads."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )

        graph = DependencyGraph([a, b, c])
        sorted_order = graph.topological_sort()

        # All should be present (order doesn't matter for independent jobs)
        assert set(sorted_order) == {a.id, b.id, c.id}
        assert len(sorted_order) == 3

    def test_diamond_dependency(self):
        """Diamond: A → B, A → C, B → D, C → D."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        d = Workload(
            name="Job D",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[
                WorkloadDependency(source_workload_id=b.id),
                WorkloadDependency(source_workload_id=c.id),
            ],
        )

        graph = DependencyGraph([a, b, c, d])
        sorted_order = graph.topological_sort()

        # A must come first
        assert sorted_order[0] == a.id
        # B and C must come before D
        assert sorted_order.index(b.id) < sorted_order.index(d.id)
        assert sorted_order.index(c.id) < sorted_order.index(d.id)
        # D must be last
        assert sorted_order[-1] == d.id

    def test_detect_self_dependency(self):
        """Workload cannot depend on itself."""
        a = Workload(
            name="Self Dependent",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )

        with pytest.raises(InvalidDependencyError, match="cannot depend on itself"):
            workload_with_self_dep = Workload(
                name="Bad Job",
                duration_hours=2.0,
                power_draw_kw=30.0,
                deadline_hours=12.0,
                dependencies=[WorkloadDependency(source_workload_id=a.id)],
            )
            # Manually change ID to self (simulating configuration error)
            workload_with_self_dep.dependencies[0].source_workload_id = (
                workload_with_self_dep.id
            )
            DependencyGraph([workload_with_self_dep])

    def test_detect_circular_two_nodes(self):
        """A → B → A should raise CircularDependencyError."""
        b_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        # Create A with dependency on B (which doesn't exist yet)
        a_with_dep = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=b_id)],
        )
        a_with_dep.id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        b = Workload(
            id=b_id,
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a_with_dep.id)],
        )

        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            DependencyGraph([a_with_dep, b])

    def test_detect_circular_three_nodes(self):
        """A → B → C → A should raise CircularDependencyError."""
        a_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        b_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        c_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

        a = Workload(
            id=a_id,
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=c_id)],  # Depends on C
        )
        b = Workload(
            id=b_id,
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a_id)],  # Depends on A
        )
        c = Workload(
            id=c_id,
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=b_id)],  # Depends on B
        )

        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            DependencyGraph([a, b, c])

    def test_invalid_dependency_reference(self):
        """Dependency on non-existent workload raises error."""
        nonexistent_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        workload = Workload(
            name="Bad Job",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=nonexistent_id)],
        )

        with pytest.raises(InvalidDependencyError, match="unknown workload ID"):
            DependencyGraph([workload])

    def test_topological_sort_order(self):
        """Verify topological sort produces valid execution order."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=b.id)],
        )

        graph = DependencyGraph([a, b, c])
        sorted_order = graph.topological_sort()

        # Verify order: A before B, B before C
        assert sorted_order[0] == a.id
        assert sorted_order[1] == b.id
        assert sorted_order[2] == c.id

    def test_get_workload_level_independent(self):
        """Test level calculation for independent workload."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        graph = DependencyGraph([a])
        assert graph.get_workload_level(a.id) == 0

    def test_get_workload_level_simple_chain(self):
        """Test level calculation for A → B → C chain."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=b.id)],
        )

        graph = DependencyGraph([a, b, c])

        assert graph.get_workload_level(a.id) == 0  # No dependencies
        assert graph.get_workload_level(b.id) == 1  # Depends on level 0
        assert graph.get_workload_level(c.id) == 2  # Depends on level 1

    def test_get_workload_level_diamond(self):
        """Test level calculation for diamond dependency."""
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )
        d = Workload(
            name="Job D",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[
                WorkloadDependency(source_workload_id=b.id),
                WorkloadDependency(source_workload_id=c.id),
            ],
        )

        graph = DependencyGraph([a, b, c, d])

        assert graph.get_workload_level(a.id) == 0  # No dependencies
        assert graph.get_workload_level(b.id) == 1  # Depends on level 0
        assert graph.get_workload_level(c.id) == 1  # Depends on level 0
        assert graph.get_workload_level(d.id) == 2  # Depends on level 1 (max of B and C)

    def test_multiple_independent_chains(self):
        """Test graph with multiple independent dependency chains."""
        # Chain 1: A → B
        a = Workload(
            name="Job A",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        b = Workload(
            name="Job B",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=a.id)],
        )

        # Chain 2: C → D (independent from A/B)
        c = Workload(
            name="Job C",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
        )
        d = Workload(
            name="Job D",
            duration_hours=2.0,
            power_draw_kw=30.0,
            deadline_hours=12.0,
            dependencies=[WorkloadDependency(source_workload_id=c.id)],
        )

        graph = DependencyGraph([a, b, c, d])
        sorted_order = graph.topological_sort()

        # A before B, C before D
        assert sorted_order.index(a.id) < sorted_order.index(b.id)
        assert sorted_order.index(c.id) < sorted_order.index(d.id)
