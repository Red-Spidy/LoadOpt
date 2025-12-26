"""
LoadOpt Solver Test Suite

Basic tests for the solver architecture.

Run with:
    python -m pytest backend/tests/test_solver.py -v
"""

import pytest
import time
from typing import List

# Import the available solver components
from app.solver.utils import Box, ContainerSpace, PlacedBox
from app.solver.optimal_solver import OptimalSolver


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def small_container():
    """Small container for basic tests"""
    return ContainerSpace(
        length=100.0,
        width=80.0,
        height=60.0,
        max_weight=1000.0,
        door_width=80.0,
        door_height=60.0
    )


@pytest.fixture
def standard_container():
    """Standard 20ft container dimensions"""
    return ContainerSpace(
        length=590.0,  # cm
        width=235.0,
        height=239.0,
        max_weight=28000.0,
        door_width=235.0,
        door_height=239.0
    )


@pytest.fixture
def uniform_boxes():
    """10 identical boxes"""
    boxes = []
    for i in range(10):
        boxes.append(Box(
            id=i,
            sku_id=i,
            instance_index=0,
            length=20.0,
            width=15.0,
            height=10.0,
            weight=5.0,
            fragile=False,
            max_stack=999,
            stacking_group=None,
            priority=1,
            allowed_rotations=[True] * 6
        ))
    return boxes


@pytest.fixture
def mixed_boxes():
    """Mix of different box sizes"""
    return [
        # Large boxes
        Box(id=0, sku_id=0, instance_index=0, length=40, width=30, height=30, weight=20,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=1, sku_id=1, instance_index=0, length=40, width=30, height=30, weight=20,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        # Medium boxes
        Box(id=2, sku_id=2, instance_index=0, length=25, width=20, height=20, weight=10,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=3, sku_id=3, instance_index=0, length=25, width=20, height=20, weight=10,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=4, sku_id=4, instance_index=0, length=25, width=20, height=20, weight=10,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        # Small boxes
        Box(id=5, sku_id=5, instance_index=0, length=15, width=10, height=10, weight=3,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=6, sku_id=6, instance_index=0, length=15, width=10, height=10, weight=3,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=7, sku_id=7, instance_index=0, length=15, width=10, height=10, weight=3,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=8, sku_id=8, instance_index=0, length=15, width=10, height=10, weight=3,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
        Box(id=9, sku_id=9, instance_index=0, length=15, width=10, height=10, weight=3,
            fragile=False, max_stack=999, stacking_group=None, priority=1, allowed_rotations=[True]*6),
    ]


# =============================================================================
# BASIC TESTS
# =============================================================================

def test_basic_import():
    """Verify basic solver components can be imported"""
    assert Box is not None
    assert ContainerSpace is not None
    assert PlacedBox is not None
    assert OptimalSolver is not None


def test_box_creation():
    """Test basic box creation"""
    box = Box(
        id=0,
        sku_id=1,
        instance_index=0,
        length=10.0,
        width=20.0,
        height=30.0,
        weight=5.0,
        fragile=False,
        max_stack=999,
        stacking_group=None,
        priority=1,
        allowed_rotations=[True] * 6
    )
    assert box.volume == 10 * 20 * 30
    assert box.weight == 5.0


def test_container_creation():
    """Test basic container creation"""
    container = ContainerSpace(
        length=100.0,
        width=80.0,
        height=60.0,
        max_weight=1000.0,
        door_width=80.0,
        door_height=60.0
    )
    assert container.volume == 100 * 80 * 60
    assert container.max_weight == 1000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
