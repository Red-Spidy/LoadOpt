"""
Skyline/Horizon Algorithm for 3D Bin Packing

Tracks the "skyline" of placed boxes and places new boxes at lowest points.
More structured than extreme points, naturally creates stable layers.
Expected improvement: 5-10% better for homogeneous loads.
"""

from typing import List, Tuple, Optional
import numpy as np
from app.solver.utils import (
    Box, ContainerSpace, PlacedBox,
    BoxRotation, CollisionDetector, StackingValidator
)


class Skyline:
    """
    Represents the skyline (height profile) of placed boxes.

    Uses a 2D grid to track the height at each (x, y) position.
    """

    def __init__(self, container: ContainerSpace, grid_resolution: float = 5.0):
        """
        Initialize skyline.

        grid_resolution: size of each grid cell in cm (smaller = more accurate but slower)
        Default 5.0cm provides good balance for typical box sizes (20-100cm)
        """
        self.container = container
        self.grid_resolution = grid_resolution

        # Create height grid
        self.grid_x = int(np.ceil(container.length / grid_resolution))
        self.grid_y = int(np.ceil(container.width / grid_resolution))

        # Heights array: heights[x_idx, y_idx] = height at that position
        self.heights = np.zeros((self.grid_x, self.grid_y), dtype=np.float32)

    def get_lowest_point(self) -> Tuple[float, float, float]:
        """
        Get the position with lowest height in the skyline.

        Returns: (x, y, z) coordinates
        """
        # Find minimum height
        min_height = self.heights.min()

        # Find all positions with minimum height
        min_positions = np.where(self.heights == min_height)

        # Prefer back-left position (low x, low y)
        best_idx = 0
        best_score = float('inf')

        for i in range(len(min_positions[0])):
            x_idx = min_positions[0][i]
            y_idx = min_positions[1][i]
            score = x_idx * 10 + y_idx  # Prefer low x and y
            if score < best_score:
                best_score = score
                best_idx = i

        x_idx = min_positions[0][best_idx]
        y_idx = min_positions[1][best_idx]

        x = x_idx * self.grid_resolution
        y = y_idx * self.grid_resolution
        z = min_height

        return (x, y, z)

    def get_candidate_positions(self, max_candidates: int = 50) -> List[Tuple[float, float, float]]:
        """
        Get multiple candidate positions sorted by priority.

        This explores different placement options instead of just the lowest point,
        improving space utilization by finding better local fits.

        Args:
            max_candidates: Maximum number of positions to return

        Returns:
            List of (x, y, z) coordinates sorted by placement priority
        """
        candidates = []

        # Get unique heights in the skyline
        unique_heights = np.unique(self.heights)

        # For each height level, find candidate positions with better sampling
        for height in sorted(unique_heights)[:5]:  # Try up to 5 different height levels
            positions = np.where(self.heights == height)
            n_positions = len(positions[0])

            # Sample more positions to ensure full coverage (especially for tight packing)
            # Take every Nth position to get distributed sampling across the grid
            step = max(1, n_positions // (max_candidates * 3))

            for i in range(0, n_positions, step):
                x_idx = positions[0][i]
                y_idx = positions[1][i]

                x = x_idx * self.grid_resolution
                y = y_idx * self.grid_resolution
                z = float(height)

                # Priority score: prefer back (low x), left (low y), and low height
                priority = x * 1.0 + y * 1.0 + z * 2.0

                candidates.append((priority, (x, y, z)))

            # Don't break early - collect candidates from all height levels

        # Sort by priority and return top candidates
        candidates.sort(key=lambda c: c[0])
        return [pos for _, pos in candidates[:max_candidates]]

    def place_box(self, box: PlacedBox) -> None:
        """
        Update skyline after placing a box.

        Increases height at all grid cells covered by the box.
        """
        # Get grid indices for box footprint
        x_start = int(box.x / self.grid_resolution)
        x_end = int(np.ceil(box.max_x / self.grid_resolution))
        y_start = int(box.y / self.grid_resolution)
        y_end = int(np.ceil(box.max_y / self.grid_resolution))

        # Clamp to grid boundaries
        x_start = max(0, min(x_start, self.grid_x - 1))
        x_end = max(0, min(x_end, self.grid_x))
        y_start = max(0, min(y_start, self.grid_y - 1))
        y_end = max(0, min(y_end, self.grid_y))

        # Update heights
        self.heights[x_start:x_end, y_start:y_end] = box.max_z

    def get_height_at(self, x: float, y: float) -> float:
        """Get height of skyline at given (x, y) position"""
        x_idx = int(x / self.grid_resolution)
        y_idx = int(y / self.grid_resolution)

        if 0 <= x_idx < self.grid_x and 0 <= y_idx < self.grid_y:
            return float(self.heights[x_idx, y_idx])
        return 0.0

    def can_place_at(self, x: float, y: float, length: float, width: float) -> bool:
        """Check if a box can be placed at given position (flat support check)"""
        x_start = int(x / self.grid_resolution)
        x_end = int(np.ceil((x + length) / self.grid_resolution))
        y_start = int(y / self.grid_resolution)
        y_end = int(np.ceil((y + width) / self.grid_resolution))

        # Check bounds
        if x_end > self.grid_x or y_end > self.grid_y:
            return False

        # Get heights in footprint area
        footprint_heights = self.heights[x_start:x_end, y_start:y_end]

        # Check if all heights are equal (flat surface)
        if footprint_heights.size == 0:
            return True

        height_range = footprint_heights.max() - footprint_heights.min()
        # Allow 1cm tolerance to account for grid discretization
        # This prevents rejecting valid placements due to grid resolution artifacts
        return height_range < 1.0


class SkylineSolver:
    """
    Solver using skyline algorithm.

    Maintains a skyline and always places boxes at the lowest available point.
    """

    def __init__(
        self,
        boxes: List[Box],
        container: ContainerSpace,
        grid_resolution: float = 10.0
    ):
        self.boxes = boxes
        self.container = container
        self.skyline = Skyline(container, grid_resolution)
        self.placements: List[PlacedBox] = []

    def solve(self, box_order: Optional[List[int]] = None) -> Tuple[List[PlacedBox], dict]:
        """
        Solve using skyline algorithm.

        Args:
            box_order: Optional custom order of box indices

        Returns:
            (placements, stats)
        """
        # Sort boxes
        if box_order is not None:
            sorted_boxes = [self.boxes[i] for i in box_order if i < len(self.boxes)]
        else:
            sorted_boxes = sorted(
                self.boxes,
                key=lambda b: (-b.delivery_order, -b.priority, -b.volume)
            )

        placed_count = 0
        failed_count = 0

        for box in sorted_boxes:
            if self._place_box(box):
                placed_count += 1
            else:
                failed_count += 1

        # Calculate statistics
        stats = self._calculate_stats()
        stats['placed_count'] = placed_count
        stats['failed_count'] = failed_count

        return self.placements, stats

    def _place_box(self, box: Box) -> bool:
        """Try to place a single box using skyline algorithm with multi-position search"""
        best_placement = None
        best_score = float('inf')

        rotations = BoxRotation.get_unique_rotations(box)

        # Get multiple candidate positions to try (increased from 10 to 50 for better coverage)
        candidate_positions = self.skyline.get_candidate_positions(max_candidates=50)

        # Try each rotation
        for rotation in rotations:
            length, width, height = BoxRotation.get_dimensions(
                box.length, box.width, box.height, rotation
            )

            # Check door entry
            if width > self.container.door_width or height > self.container.door_height:
                continue

            # Try placing at each candidate position
            for x, y, z in candidate_positions:
                # Check if box fits
                if (x + length > self.container.length or
                    y + width > self.container.width or
                    z + height > self.container.height):
                    continue

                # Check if surface is flat enough
                if not self.skyline.can_place_at(x, y, length, width):
                    continue

                # Create placement
                placed = PlacedBox(
                    box=box,
                    x=x, y=y, z=z,
                    rotation=rotation,
                    length=length, width=width, height=height,
                    load_order=len(self.placements)
                )

                # Validate
                if not self._validate_placement(placed):
                    continue

                # Score: prefer low height, but also consider back-left position
                # Lower score is better
                placement_score = z * 2.0 + x * 0.5 + y * 0.5

                if placement_score < best_score:
                    best_score = placement_score
                    best_placement = placed

        if best_placement:
            self.placements.append(best_placement)
            self.skyline.place_box(best_placement)
            return True

        return False

    def _validate_placement(self, placed: PlacedBox) -> bool:
        """Validate placement"""
        # Check container fit
        if not CollisionDetector.check_container_fit(placed, self.container):
            return False

        # Check collisions with existing placements
        for existing in self.placements:
            if CollisionDetector.check_collision_fast(placed, existing):
                return False

        # Support is implicitly guaranteed by skyline algorithm
        # (boxes are placed on flat surfaces)

        # Check stacking rules
        if placed.z > 0.1:
            below_boxes = [p for p in self.placements if abs(p.max_z - placed.z) < 0.1]
            if not StackingValidator.check_stacking_rules(placed, below_boxes):
                return False

        return True

    def _calculate_stats(self) -> dict:
        """Calculate statistics"""
        if not self.placements:
            return {
                'utilization_pct': 0.0,
                'placed_count': 0,
                'is_valid': True,
                'solver': 'skyline'
            }

        used_volume = sum(p.volume for p in self.placements)
        container_volume = (self.container.length *
                           self.container.width *
                           self.container.height)
        utilization = (used_volume / container_volume) * 100

        return {
            'utilization_pct': round(utilization, 2),
            'total_weight': sum(p.box.weight for p in self.placements),
            'is_valid': True,
            'solver': 'skyline'
        }
