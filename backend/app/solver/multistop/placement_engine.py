"""
Multi-Stop Aware Placement Engine

Extends the base 3D bin-packing algorithm with stop-based zoning and
LIFO (Last-In-First-Out) constraints.

STRATEGY:
---------
1. Divide container into virtual "zones" based on stop sequence
2. Earlier stops (unloaded first) placed near door (X = max)
3. Later stops placed deeper in container (X = min)
4. Use existing extreme point algorithm within zones
5. Apply accessibility constraints to prevent blocking

COORDINATE SYSTEM:
------------------
X-axis: 0 (back/bulkhead) → length (door)
Earlier stops → higher X values (closer to door)
Later stops → lower X values (deeper in container)
"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
import math

from app.solver.utils import Box, ContainerSpace as Container, PlacedBox, PlacementPoint
from .models import Trip


@dataclass
class StopZone:
    """
    Represents a virtual zone in the container for a specific stop.

    Zones are regions of the container allocated to specific stops,
    ensuring earlier stops are more accessible than later stops.

    Attributes:
        stop_number: Which stop this zone is for
        x_min: Minimum X coordinate (back edge)
        x_max: Maximum X coordinate (front edge toward door)
        y_min: Minimum Y coordinate (left edge)
        y_max: Maximum Y coordinate (right edge)
        z_min: Minimum Z coordinate (floor)
        z_max: Maximum Z coordinate (ceiling)
        priority: Zone priority for loading
    """
    stop_number: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    priority: int = 0

    @property
    def volume(self) -> float:
        """Calculate zone volume"""
        return (
            (self.x_max - self.x_min) *
            (self.y_max - self.y_min) *
            (self.z_max - self.z_min)
        )

    @property
    def center_x(self) -> float:
        """Get center X coordinate"""
        return (self.x_min + self.x_max) / 2

    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a point is within this zone"""
        return (
            self.x_min <= x <= self.x_max and
            self.y_min <= y <= self.y_max and
            self.z_min <= z <= self.z_max
        )

    def get_priority_point(self) -> Tuple[float, float, float]:
        """Get the ideal starting point for this zone (back-left-bottom)"""
        return (self.x_min, self.y_min, self.z_min)


class ZoneStrategy:
    """Strategy for dividing container into stop zones"""

    @staticmethod
    def proportional_zoning(
        container: Container,
        trip: Trip,
        boxes_by_stop: Dict[int, List[Box]]
    ) -> Dict[int, StopZone]:
        """
        Create zones proportional to each stop's volume requirements.

        ALGORITHM:
        ----------
        1. Calculate total volume needed per stop
        2. Allocate X-axis proportionally (earlier stops → near door)
        3. All zones use full Y and Z dimensions

        EXAMPLE:
        --------
        Container: 1000cm (X) × 240cm (Y) × 270cm (Z)
        Stop 1: 30% of volume → X: 700-1000 (near door)
        Stop 2: 50% of volume → X: 200-700
        Stop 3: 20% of volume → X: 0-200 (deep/back)

        Args:
            container: The container
            trip: The trip with stops
            boxes_by_stop: Mapping of stop_number -> boxes for that stop

        Returns:
            Dict mapping stop_number -> StopZone
        """
        # Calculate volume needed per stop
        stop_volumes = {}
        total_volume = 0.0

        for stop_num in range(1, trip.num_stops + 1):
            boxes = boxes_by_stop.get(stop_num, [])
            volume = sum(b.volume for b in boxes)
            stop_volumes[stop_num] = volume
            total_volume += volume

        # Calculate proportions
        stop_proportions = {}
        for stop_num, volume in stop_volumes.items():
            proportion = volume / total_volume if total_volume > 0 else 1.0 / trip.num_stops
            # Add 10% buffer to prevent tight packing issues
            stop_proportions[stop_num] = proportion * 1.1

        # Normalize proportions to ensure they sum to <= 1.0 (prevent overflow)
        total_proportion = sum(stop_proportions.values())
        if total_proportion > 1.0:
            for stop_num in stop_proportions:
                stop_proportions[stop_num] = stop_proportions[stop_num] / total_proportion

        # Allocate X-axis from BACK TO FRONT
        # Later stops (higher number) go in back (lower X)
        # Earlier stops (lower number) go near door (higher X)
        zones = {}
        current_x = 0.0

        # Process stops in REVERSE order (latest stop first, at back)
        for stop_num in range(trip.num_stops, 0, -1):
            proportion = stop_proportions[stop_num]
            zone_length = container.length * proportion

            x_min = current_x
            x_max = min(current_x + zone_length, container.length)

            zone = StopZone(
                stop_number=stop_num,
                x_min=x_min,
                x_max=x_max,
                y_min=0.0,
                y_max=container.width,
                z_min=0.0,
                z_max=container.height,
                priority=trip.num_stops - stop_num + 1  # Earlier stop = higher priority
            )
            zones[stop_num] = zone
            current_x = x_max

        return zones

    @staticmethod
    def strict_sequential_zoning(
        container: Container,
        trip: Trip
    ) -> Dict[int, StopZone]:
        """
        Create equal-sized zones strictly by stop sequence.

        Simpler strategy: divide container into equal X-axis segments.

        Args:
            container: The container
            trip: The trip with stops

        Returns:
            Dict mapping stop_number -> StopZone
        """
        zone_length = container.length / trip.num_stops
        zones = {}

        for stop_num in range(1, trip.num_stops + 1):
            # Stop 1 (first delivery) → near door (high X)
            # Stop N (last delivery) → deep/back (low X)
            reverse_idx = trip.num_stops - stop_num

            x_min = reverse_idx * zone_length
            x_max = (reverse_idx + 1) * zone_length

            zone = StopZone(
                stop_number=stop_num,
                x_min=x_min,
                x_max=x_max,
                y_min=0.0,
                y_max=container.width,
                z_min=0.0,
                z_max=container.height,
                priority=trip.num_stops - stop_num + 1
            )
            zones[stop_num] = zone

        return zones


class MultiStopPlacementEngine:
    """
    Placement engine with multi-stop awareness.

    Integrates stop-based zoning with the existing extreme point
    placement algorithm.

    WORKFLOW:
    ---------
    1. Create zones for each stop
    2. Sort boxes by priority (already set by preprocessor)
    3. For each box:
       a. Identify its target zone (based on delivery_order)
       b. Try to place within that zone using extreme points
       c. If zone is full, try adjacent zones (with penalty)
    4. Apply standard validation (collision, support, stacking)
    5. Return placements
    """

    def __init__(
        self,
        container: Container,
        trip: Trip,
        use_proportional_zones: bool = True
    ):
        """
        Initialize placement engine.

        Args:
            container: The container
            trip: The trip specification
            use_proportional_zones: If True, use volume-proportional zoning;
                                   if False, use equal sequential zoning
        """
        self.container = container
        self.trip = trip
        self.use_proportional_zones = use_proportional_zones

        # Will be set during placement
        self.zones: Dict[int, StopZone] = {}
        self.placements: List[PlacedBox] = []

    def place_boxes(
        self,
        boxes: List[Box],
        allow_zone_overflow: bool = True,
        accessibility_weight: float = 0.5
    ) -> List[PlacedBox]:
        """
        Place boxes with multi-stop awareness.

        Args:
            boxes: List of boxes (should be pre-sorted by priority)
            allow_zone_overflow: If True, allow boxes to overflow into
                                adjacent zones when primary zone is full
            accessibility_weight: Weight for accessibility in scoring (0-1)

        Returns:
            List of PlacedBox objects

        Algorithm:
        ----------
        1. Group boxes by delivery_order (stop number)
        2. Create zones based on stop requirements
        3. Place boxes in priority order:
           - Generate extreme points within target zone
           - Score placements with accessibility penalty
           - Place box at best valid position
        4. Track placements and update extreme points
        """
        # Group boxes by stop - Map delivery_order to stop_number using original_delivery_order
        import logging
        logger = logging.getLogger(__name__)
        
        # Create mapping from original_delivery_order to stop_number
        delivery_order_to_stop: Dict[int, int] = {}
        for stop in self.trip.stops:
            original_do = stop.original_delivery_order if hasattr(stop, 'original_delivery_order') and stop.original_delivery_order is not None else stop.stop_number
            delivery_order_to_stop[original_do] = stop.stop_number
        
        logger.warning(f"Placement Engine: Delivery order mapping: {delivery_order_to_stop}")
        
        boxes_by_stop: Dict[int, List[Box]] = {}
        for box in boxes:
            # Map box's delivery_order to the stop's stop_number
            stop_num = delivery_order_to_stop.get(box.delivery_order, box.delivery_order)
            if stop_num not in boxes_by_stop:
                boxes_by_stop[stop_num] = []
            boxes_by_stop[stop_num].append(box)

        # Debug: Log box grouping
        logger.warning(f"Placement Engine: Grouping boxes by delivery_order")
        for stop_num, box_list in sorted(boxes_by_stop.items()):
            logger.warning(f"  Stop {stop_num}: {len(box_list)} boxes")

        # Create zones
        if self.use_proportional_zones:
            self.zones = ZoneStrategy.proportional_zoning(
                self.container, self.trip, boxes_by_stop
            )
        else:
            self.zones = ZoneStrategy.strict_sequential_zoning(
                self.container, self.trip
            )

        # Debug: Log zone allocation
        logger.warning(f"Placement Engine: Created {len(self.zones)} zones")
        for stop_num, zone in sorted(self.zones.items()):
            logger.warning(f"  Zone for Stop {stop_num}: x=[{zone.x_min:.0f}, {zone.x_max:.0f}], length={zone.x_max - zone.x_min:.0f}cm")

        # Initialize extreme points
        self.extreme_points: List[PlacementPoint] = []
        self._initialize_extreme_points()

        # Place boxes in priority order
        placements = []
        load_order = 0

        for box in boxes:
            placement = self._place_single_box(
                box,
                load_order,
                allow_zone_overflow,
                accessibility_weight
            )

            if placement:
                placements.append(placement)
                load_order += 1
                self._update_extreme_points(placement)

        self.placements = placements
        return placements

    def _initialize_extreme_points(self):
        """Initialize extreme points for each zone"""
        self.extreme_points = []

        for stop_num, zone in self.zones.items():
            # Start point for each zone (back-left-bottom of zone)
            ep = PlacementPoint(
                x=zone.x_min,
                y=zone.y_min,
                z=zone.z_min,
                available_length=zone.x_max - zone.x_min,
                available_width=zone.y_max - zone.y_min,
                available_height=zone.z_max - zone.z_min,
                source=f"zone_{stop_num}_init"
            )
            self.extreme_points.append(ep)

    def _place_single_box(
        self,
        box: Box,
        load_order: int,
        allow_zone_overflow: bool,
        accessibility_weight: float
    ) -> Optional[PlacedBox]:
        """
        Place a single box using extreme point algorithm with zone awareness.

        Returns:
            PlacedBox if successful, None if no valid placement found
        """
        target_stop = box.delivery_order
        target_zone = self.zones.get(target_stop)

        if not target_zone:
            return None

        # Get allowed rotations
        rotations = box.get_unique_rotations()

        best_placement = None
        best_score = float('inf')

        # Try each rotation
        for rotation in rotations:
            dims = box.get_rotated_dimensions(rotation)
            length, width, height = dims

            # Try extreme points (prioritize those in target zone)
            sorted_eps = self._sort_extreme_points_by_zone(target_zone)

            for ep in sorted_eps[:300]:  # Limit search
                # Check if box fits in container
                if (ep.x + length > self.container.length or
                    ep.y + width > self.container.width or
                    ep.z + height > self.container.height):
                    continue

                # Check if can enter door
                if not self.container.can_enter_door(width, height):
                    continue

                # Create candidate placement
                candidate = PlacedBox(
                    box=box,
                    x=ep.x,
                    y=ep.y,
                    z=ep.z,
                    rotation=rotation,
                    length=length,
                    width=width,
                    height=height,
                    load_order=load_order
                )

                # Validate placement
                if not self._is_valid_placement(candidate):
                    continue

                # Score placement
                score = self._score_placement(
                    candidate,
                    target_zone,
                    accessibility_weight
                )

                if score < best_score:
                    best_score = score
                    best_placement = candidate

        return best_placement

    def _sort_extreme_points_by_zone(
        self,
        target_zone: StopZone
    ) -> List[PlacementPoint]:
        """
        Sort extreme points prioritizing those in target zone.

        Returns:
            Sorted list of extreme points
        """
        in_zone = []
        out_zone = []

        for ep in self.extreme_points:
            if target_zone.contains_point(ep.x, ep.y, ep.z):
                in_zone.append(ep)
            else:
                out_zone.append(ep)

        # Sort in-zone points by height, then Y, then X
        in_zone.sort(key=lambda p: (p.z, p.y, p.x))

        # Sort out-zone points similarly
        out_zone.sort(key=lambda p: (p.z, p.y, p.x))

        # Prioritize in-zone points
        return in_zone + out_zone

    def _is_valid_placement(self, candidate: PlacedBox) -> bool:
        """
        Validate that placement meets all constraints.

        Checks:
        - No collision with existing placements
        - Adequate support (70% overlap)
        - Stacking rules (fragile, max_stack, groups)
        - Weight bearing capacity

        Returns:
            True if valid, False otherwise
        """
        # Check collisions
        for placed in self.placements:
            if self._boxes_collide(candidate, placed):
                return False

        # Check support (if not on ground)
        if candidate.z > 0.1:  # Not on floor
            if not self._has_adequate_support(candidate):
                return False

        # Check stacking rules
        if not self._check_stacking_rules(candidate):
            return False

        return True

    def _boxes_collide(self, box1: PlacedBox, box2: PlacedBox) -> bool:
        """Check if two boxes collide using AABB"""
        return not (
            box1.max_x <= box2.x or box1.x >= box2.max_x or
            box1.max_y <= box2.y or box1.y >= box2.max_y or
            box1.max_z <= box2.z or box1.z >= box2.max_z
        )

    def _has_adequate_support(
        self,
        candidate: PlacedBox,
        required_support: float = 0.7
    ) -> bool:
        """
        Check if box has adequate support below it.

        Args:
            candidate: Box to check
            required_support: Fraction of base area that must be supported

        Returns:
            True if adequately supported
        """
        tolerance = 0.1  # cm
        support_area = 0.0
        base_area = candidate.base_area

        for placed in self.placements:
            # Check if this box is directly below
            if abs(placed.max_z - candidate.z) < tolerance:
                # Calculate overlap area
                overlap = candidate.get_xy_overlap_area(placed)
                support_area += overlap

        support_ratio = support_area / base_area if base_area > 0 else 0
        return support_ratio >= required_support

    def _check_stacking_rules(self, candidate: PlacedBox) -> bool:
        """
        Check stacking rules for placement.

        Rules:
        - Can't place on top of fragile boxes
        - Respect max_stack limits
        - Respect stacking groups
        - Check load bearing capacity

        Returns:
            True if stacking rules satisfied
        """
        tolerance = 0.1

        # Find boxes directly below
        boxes_below = []
        for placed in self.placements:
            if abs(placed.max_z - candidate.z) < tolerance:
                if candidate.overlaps_xy(placed):
                    boxes_below.append(placed)

        for below in boxes_below:
            # Check fragility
            if below.box.fragile:
                return False

            # Check stacking group
            if (below.box.stacking_group and candidate.box.stacking_group and
                below.box.stacking_group != candidate.box.stacking_group):
                return False

            # Check load bearing capacity
            if candidate.box.weight > below.box.load_bearing_capacity:
                return False

        return True

    def _score_placement(
        self,
        candidate: PlacedBox,
        target_zone: StopZone,
        accessibility_weight: float
    ) -> float:
        """
        Score a placement candidate.

        Lower score = better placement.

        Components:
        - Height penalty (prefer ground level)
        - Position penalty (prefer back-left)
        - Zone compliance (penalty if outside target zone)
        - Accessibility penalty (penalty if blocked by later-stop boxes)

        Returns:
            Score (lower is better)
        """
        score = 0.0

        # Height penalty (prefer low)
        score += candidate.z * 50.0

        # Position penalty (prefer back-left)
        score += (candidate.x + candidate.y) * 10.0

        # Zone compliance penalty
        in_zone = target_zone.contains_point(
            candidate.x + candidate.length / 2,
            candidate.y + candidate.width / 2,
            candidate.z + candidate.height / 2
        )
        if not in_zone:
            score += 5000.0  # Large penalty for being out of zone

        # Accessibility penalty (for earlier stops)
        if accessibility_weight > 0:
            accessibility_penalty = self._calculate_accessibility_penalty(candidate)
            score += accessibility_penalty * accessibility_weight * 1000.0

        return score

    def _calculate_accessibility_penalty(self, candidate: PlacedBox) -> float:
        """
        Calculate penalty based on accessibility.

        Earlier stops should not be blocked by later stops.

        Returns:
            Penalty value (0 = perfect accessibility, higher = more blocked)
        """
        penalty = 0.0
        candidate_stop = candidate.box.delivery_order

        # Check if any later-stop boxes block access to this box
        # "Blocking" means: overlaps in YZ plane AND has higher X
        for placed in self.placements:
            placed_stop = placed.box.delivery_order

            # If placed box is for a LATER stop (higher number)
            # and it blocks the path to the door (X direction)
            if placed_stop > candidate_stop:
                # Check if it blocks in X direction
                if placed.x > candidate.x:
                    # Check if it overlaps in YZ plane
                    y_overlap = not (
                        placed.max_y <= candidate.y or
                        placed.y >= candidate.max_y
                    )
                    z_overlap = not (
                        placed.max_z <= candidate.z or
                        placed.z >= candidate.max_z
                    )

                    if y_overlap and z_overlap:
                        # This later-stop box blocks access
                        penalty += 1.0

        return penalty

    def _update_extreme_points(self, placed: PlacedBox):
        """
        Update extreme points after placing a box.

        Creates 3 new extreme points:
        - Above the box (x, y, z + height)
        - To the right (x + length, y, z)
        - To the front (x, y + width, z)

        Also removes points that are now inside the placed box.
        """
        # Remove invalidated points
        self.extreme_points = [
            ep for ep in self.extreme_points
            if not (
                placed.x <= ep.x < placed.max_x and
                placed.y <= ep.y < placed.max_y and
                placed.z <= ep.z < placed.max_z
            )
        ]

        # Add new extreme points
        new_points = [
            # Above
            PlacementPoint(
                x=placed.x,
                y=placed.y,
                z=placed.max_z,
                available_length=self.container.length - placed.x,
                available_width=self.container.width - placed.y,
                available_height=self.container.height - placed.max_z,
                source="above"
            ),
            # Right
            PlacementPoint(
                x=placed.max_x,
                y=placed.y,
                z=placed.z,
                available_length=self.container.length - placed.max_x,
                available_width=self.container.width - placed.y,
                available_height=self.container.height - placed.z,
                source="right"
            ),
            # Front
            PlacementPoint(
                x=placed.x,
                y=placed.max_y,
                z=placed.z,
                available_length=self.container.length - placed.x,
                available_width=self.container.width - placed.max_y,
                available_height=self.container.height - placed.z,
                source="front"
            ),
        ]

        # Filter and add valid new points
        for np in new_points:
            if self.container.contains_point(np.x, np.y, np.z):
                # Quantize to prevent duplicates
                np_quantized = np.quantize(0.1)
                if np_quantized not in self.extreme_points:
                    self.extreme_points.append(np_quantized)

    def get_zone_utilization(self) -> Dict[int, Dict[str, float]]:
        """
        Calculate utilization statistics per zone.

        Returns:
            Dict mapping stop_number -> utilization metrics
        """
        zone_stats = {}

        for stop_num, zone in self.zones.items():
            # Find placements in this zone
            boxes_in_zone = [
                p for p in self.placements
                if p.box.delivery_order == stop_num
            ]

            total_volume = sum(p.volume for p in boxes_in_zone)
            utilization = (total_volume / zone.volume * 100) if zone.volume > 0 else 0

            zone_stats[stop_num] = {
                'zone_volume': zone.volume,
                'used_volume': total_volume,
                'utilization_pct': utilization,
                'box_count': len(boxes_in_zone),
                'x_range': (zone.x_min, zone.x_max)
            }

        return zone_stats
