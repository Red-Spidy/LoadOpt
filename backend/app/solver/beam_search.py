"""
Beam Search Solver for 3D Bin Packing

Explores multiple promising paths simultaneously while pruning less promising ones.
Expected improvement: 10-20% better than greedy, 5-10x faster than exhaustive search.
"""

from typing import List, Tuple, Optional
import heapq
from dataclasses import dataclass
from app.solver.utils import (
    Box, ContainerSpace, PlacedBox, PlacementPoint,
    BoxRotation, CollisionDetector, StackingValidator, SpatialGrid
)


@dataclass
class BeamState:
    """Represents a partial packing solution in beam search"""
    placements: List[PlacedBox]
    remaining_boxes: List[Box]
    spatial_grid: SpatialGrid
    fitness: float
    load_order: int

    def __lt__(self, other):
        """Compare states by fitness (for heap)"""
        return self.fitness > other.fitness  # Higher fitness is better


class BeamSearchSolver:
    """
    Beam Search solver that maintains K best partial solutions at each level.

    Algorithm:
    1. Start with empty container
    2. For each level (box position), expand K best states
    3. For each state, try placing each remaining box
    4. Keep only K best resulting states
    5. Repeat until all boxes placed or no valid states
    """

    def __init__(
        self,
        boxes: List[Box],
        container: ContainerSpace,
        beam_width: int = 10,
        max_boxes_per_state: int = 10,
        max_positions_per_box: int = 5
    ):
        self.boxes = boxes
        self.container = container
        self.beam_width = beam_width
        self.max_boxes_per_state = max_boxes_per_state  # Limit boxes tried per state
        self.max_positions_per_box = max_positions_per_box  # Limit positions tried per box

    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """Run beam search"""
        # Initialize beam with empty state
        initial_grid = SpatialGrid(
            self.container.length,
            self.container.width,
            self.container.height
        )

        initial_state = BeamState(
            placements=[],
            remaining_boxes=self.boxes.copy(),
            spatial_grid=initial_grid,
            fitness=0.0,
            load_order=0
        )

        beam = [initial_state]

        # Beam search main loop
        for level in range(len(self.boxes)):
            if not beam:
                break

            new_beam = []

            # Expand each state in current beam
            for state in beam:
                if not state.remaining_boxes:
                    new_beam.append(state)
                    continue

                # Select boxes to try (prioritize by heuristic)
                boxes_to_try = self._select_boxes(
                    state.remaining_boxes,
                    self.max_boxes_per_state
                )

                # Try placing each selected box
                for box in boxes_to_try:
                    # Get promising placement positions
                    positions = self._get_placement_positions(
                        box, state, self.max_positions_per_box
                    )

                    # Try each position with each rotation
                    for position in positions:
                        rotations = BoxRotation.get_unique_rotations(box)

                        for rotation in rotations:
                            new_state = self._try_placement(
                                state, box, position, rotation
                            )

                            if new_state:
                                new_beam.append(new_state)

            # Keep only beam_width best states
            if len(new_beam) > self.beam_width:
                new_beam.sort(key=lambda s: s.fitness, reverse=True)
                beam = new_beam[:self.beam_width]
            else:
                beam = new_beam

        # Return best state
        if beam:
            best_state = max(beam, key=lambda s: s.fitness)
            stats = self._calculate_stats(best_state.placements)
            return best_state.placements, stats

        return [], {'utilization_pct': 0, 'placed_count': 0, 'is_valid': False}

    def _select_boxes(self, remaining: List[Box], max_count: int) -> List[Box]:
        """Select most promising boxes to try"""
        # Sort by delivery order (high first), then priority, then volume
        sorted_boxes = sorted(
            remaining,
            key=lambda b: (-b.delivery_order, -b.priority, -b.volume)
        )
        return sorted_boxes[:max_count]

    def _get_placement_positions(
        self,
        box: Box,
        state: BeamState,
        max_positions: int
    ) -> List[Tuple[float, float, float]]:
        """Get promising placement positions for a box"""
        positions = [(0, 0, 0)]  # Always try origin

        # Add positions based on existing placements
        for placed in state.placements[-10:]:  # Only consider recent placements
            # Try placing next to existing boxes
            candidates = [
                (placed.max_x, placed.y, placed.z),  # Right
                (placed.x, placed.max_y, placed.z),  # Front
                (placed.x, placed.y, placed.max_z),  # Top
            ]
            positions.extend(candidates)

        # Score positions (prefer ground level, back-left corner)
        scored_positions = []
        for x, y, z in positions:
            # Quick bounds check
            if (x < self.container.length and
                y < self.container.width and
                z < self.container.height):
                score = z * 10000 + x * 10 + y
                scored_positions.append((score, (x, y, z)))

        # Sort by score and return top positions
        scored_positions.sort()
        return [pos for score, pos in scored_positions[:max_positions]]

    def _try_placement(
        self,
        state: BeamState,
        box: Box,
        position: Tuple[float, float, float],
        rotation: int
    ) -> Optional[BeamState]:
        """Try placing a box and return new state if valid"""
        x, y, z = position

        # Get rotated dimensions
        length, width, height = BoxRotation.get_dimensions(
            box.length, box.width, box.height, rotation
        )

        # Check bounds
        if (x + length > self.container.length or
            y + width > self.container.width or
            z + height > self.container.height):
            return None

        # Check door entry
        if width > self.container.door_width or height > self.container.door_height:
            return None

        # Create placement
        placed = PlacedBox(
            box=box,
            x=x, y=y, z=z,
            rotation=rotation,
            length=length, width=width, height=height,
            load_order=state.load_order
        )

        # Validate placement
        if state.spatial_grid.check_collision(placed):
            return None

        # Check support
        if not StackingValidator.check_support_with_grid(placed, state.spatial_grid):
            return None

        # Check stacking rules
        if z > 0.1:
            below_boxes = state.spatial_grid.get_boxes_below(placed)
            if not StackingValidator.check_stacking_rules(placed, below_boxes):
                return None

        # Create new state
        new_grid = self._copy_spatial_grid(state.spatial_grid)
        new_grid.add_box(placed)

        new_placements = state.placements.copy()
        new_placements.append(placed)

        new_remaining = [b for b in state.remaining_boxes if b.id != box.id]

        new_fitness = self._calculate_state_fitness(new_placements, new_remaining)

        new_state = BeamState(
            placements=new_placements,
            remaining_boxes=new_remaining,
            spatial_grid=new_grid,
            fitness=new_fitness,
            load_order=state.load_order + 1
        )

        return new_state

    def _copy_spatial_grid(self, grid: SpatialGrid) -> SpatialGrid:
        """Create a copy of spatial grid"""
        new_grid = SpatialGrid(
            grid.grid_x * grid.cell_size,
            grid.grid_y * grid.cell_size,
            grid.grid_z * grid.cell_size,
            cell_size=grid.cell_size
        )

        # Copy all placements
        for box_id, placed in grid.boxes.items():
            new_grid.add_box(placed)

        return new_grid

    def _calculate_state_fitness(
        self,
        placements: List[PlacedBox],
        remaining: List[Box]
    ) -> float:
        """Calculate fitness of a partial solution"""
        if not placements:
            return 0.0

        # Volume utilization
        placed_volume = sum(p.volume for p in placements)
        container_volume = (self.container.length *
                           self.container.width *
                           self.container.height)
        utilization = placed_volume / container_volume

        # Progress ratio
        progress = len(placements) / len(self.boxes)

        # Remaining capacity for remaining boxes
        remaining_volume = sum(b.volume for b in remaining)
        remaining_capacity = container_volume - placed_volume
        capacity_ratio = remaining_capacity / max(1, remaining_volume) if remaining else 1.0

        # Combined fitness
        fitness = utilization * 0.5 + progress * 0.3 + min(1.0, capacity_ratio) * 0.2

        return fitness

    def _calculate_stats(self, placements: List[PlacedBox]) -> dict:
        """Calculate statistics for final solution"""
        if not placements:
            return {'utilization_pct': 0, 'placed_count': 0, 'is_valid': False}

        used_volume = sum(p.volume for p in placements)
        container_volume = (self.container.length *
                           self.container.width *
                           self.container.height)
        utilization = (used_volume / container_volume) * 100

        return {
            'utilization_pct': round(utilization, 2),
            'placed_count': len(placements),
            'failed_count': len(self.boxes) - len(placements),
            'total_weight': sum(p.box.weight for p in placements),
            'is_valid': True,
            'solver': 'beam_search',
            'beam_width': self.beam_width
        }
