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

from app.solver.utils import (
    Box, 
    ContainerSpace as Container, 
    PlacedBox, 
    PlacementPoint,
    CollisionDetector,
    StackingValidator,
    SpatialGrid
)
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
        1. Calculate total volume needed per stop (using actual dimensions)
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
        # Calculate volume needed per stop using ACTUAL BOX DIMENSIONS (not cached volume property)
        # This ensures we account for box orientation and true space requirements
        stop_volumes = {}
        stop_max_dimensions = {}  # Track largest box dimensions per stop
        total_volume = 0.0

        for stop_num in range(1, trip.num_stops + 1):
            boxes = boxes_by_stop.get(stop_num, [])
            # CRITICAL FIX: Use actual dimensions, not just volume property
            # Large boxes need more X-axis space even if volume is similar
            volume = sum(b.length * b.width * b.height for b in boxes)
            stop_volumes[stop_num] = volume
            total_volume += volume
            
            # Track largest box dimensions for minimum zone size
            if boxes:
                max_length = max(b.length for b in boxes)
                max_width = max(b.width for b in boxes)
                stop_max_dimensions[stop_num] = (max_length, max_width)
            else:
                stop_max_dimensions[stop_num] = (0, 0)

        # Calculate proportions with MINIMUM zone sizes for lateral packing
        stop_proportions = {}
        min_zone_lengths = {}  # Minimum X-axis length per stop
        
        for stop_num, volume in stop_volumes.items():
            proportion = volume / total_volume if total_volume > 0 else 1.0 / trip.num_stops
            # Add buffer for lateral packing
            # Cap at 2x to prevent excessive over-allocation
            buffered_proportion = min(proportion * 1.5, proportion + 0.5)
            stop_proportions[stop_num] = buffered_proportion
            
            # CRITICAL: Ensure minimum zone size is at least 5x largest box dimension
            # This allows lateral packing of at least 4-5 boxes side by side
            max_length, max_width = stop_max_dimensions[stop_num]
            min_zone_lengths[stop_num] = max(max_length * 5, max_width * 5, 300.0)

        # PATCH 4: Normalize proportions to eliminate unused X-space
        total_prop = sum(stop_proportions.values())
        if total_prop > 0:
            for k in stop_proportions:
                stop_proportions[k] /= total_prop

        # Allocate X-axis from BACK TO FRONT
        # Later stops (higher number) go in back (lower X)
        # Earlier stops (lower number) go near door (higher X)
        zones = {}
        current_x = 0.0
        remaining_length = container.length

        # Process stops in REVERSE order (latest stop first, at back)
        stop_nums = list(range(trip.num_stops, 0, -1))
        for i, stop_num in enumerate(stop_nums):
            is_last_zone = (i == len(stop_nums) - 1)
            
            if is_last_zone:
                # Last zone gets ALL remaining space (no artificial limits)
                zone_length = remaining_length
            else:
                # Use minimum zone size OR proportional, whichever is larger
                proportion = stop_proportions[stop_num]
                zone_length_proportional = container.length * proportion
                zone_length = max(zone_length_proportional, min_zone_lengths[stop_num])
                
                # Don't exceed remaining space
                zone_length = min(zone_length, remaining_length)

            x_min = current_x
            x_max = min(current_x + zone_length, container.length)
            remaining_length -= (x_max - x_min)

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
        
        # FIX 4: Validate that zones respect stop ordering in X
        # Later stops (higher stop_num) must be deeper (lower X)
        for stop_num in range(1, trip.num_stops):
            later_zone = zones[stop_num + 1]
            earlier_zone = zones[stop_num]
            # Later zone's maximum X must not exceed earlier zone's minimum X
            if later_zone.x_max > earlier_zone.x_min + 1.0:  # 1cm tolerance
                # Zone construction violated monotonicity - this should not happen with correct algorithm
                # but guard against it anyway
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Zone ordering violation: Stop {stop_num + 1} zone [{later_zone.x_min:.0f}, {later_zone.x_max:.0f}] "
                    f"overlaps Stop {stop_num} zone [{earlier_zone.x_min:.0f}, {earlier_zone.x_max:.0f}]"
                )

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
        use_proportional_zones: bool = True,
        collision_tolerance_cm: float = 0.1,
        min_zone_length_cm: float = 80.0,
        non_adjacent_stop_separation_cm: float = 50.0
    ):
        """
        Initialize placement engine.

        Args:
            container: The container
            trip: The trip specification
            use_proportional_zones: If True, use volume-proportional zoning;
                                   if False, use equal sequential zoning
            collision_tolerance_cm: Tolerance for collision detection (default 0.1cm = 1mm)
            min_zone_length_cm: Minimum zone length before fallback to sequential (default 80cm)
            non_adjacent_stop_separation_cm: Minimum separation for non-adjacent stops (default 50cm)
        """
        self.container = container
        self.trip = trip
        self.use_proportional_zones = use_proportional_zones
        self.collision_tolerance_cm = collision_tolerance_cm
        self.min_zone_length_cm = min_zone_length_cm
        self.non_adjacent_stop_separation_cm = non_adjacent_stop_separation_cm

        # Will be set during placement
        self.zones: Dict[int, StopZone] = {}
        self.placements: List[PlacedBox] = []
        
        # Initialize SpatialGrid for O(1) collision detection (like single-stop solver)
        self.spatial_grid: Optional[SpatialGrid] = None
        try:
            # Use 10cm cells (same as single-stop solver)
            self.spatial_grid = SpatialGrid(cell_size=10.0)
        except Exception:
            # Fallback to linear collision detection if grid fails
            self.spatial_grid = None
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
        # Group boxes by delivery_order (which IS the stop number)
        # CLARIFICATION: box.delivery_order = stop.stop_number
        # Lower delivery_order = unloaded earlier = should be near door (high X)
        import logging
        logger = logging.getLogger(__name__)
        
        boxes_by_stop: Dict[int, List[Box]] = {}
        for box in boxes:
            stop_num = box.delivery_order  # delivery_order IS the stop number
            if stop_num not in boxes_by_stop:
                boxes_by_stop[stop_num] = []
            boxes_by_stop[stop_num].append(box)

        # CRITICAL FIX: Sort boxes by volume (largest first) within each stop
        # Like single-stop solver, this ensures large boxes get placed early
        # when there are more extreme points and ground-level space available
        for stop_num in boxes_by_stop:
            boxes_by_stop[stop_num].sort(
                key=lambda b: b.length * b.width * b.height,
                reverse=True
            )

        # Debug: Log box grouping
        logger.warning(f"Placement Engine: Grouping boxes by delivery_order")
        for stop_num, box_list in sorted(boxes_by_stop.items()):
            logger.warning(f"  Stop {stop_num}: {len(box_list)} boxes")

        # Create zones
        if self.use_proportional_zones:
            self.zones = ZoneStrategy.proportional_zoning(
                self.container, self.trip, boxes_by_stop
            )
            
            # Bug #12 Fix: Validate minimum zone sizes
            has_small_zone = any(
                (zone.x_max - zone.x_min) < self.min_zone_length_cm
                for zone in self.zones.values()
            )
            
            if has_small_zone:
                logger.warning(f"Proportional zoning created zones smaller than {self.min_zone_length_cm}cm, falling back to sequential zoning")
                self.zones = ZoneStrategy.strict_sequential_zoning(
                    self.container, self.trip
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
        self.placements = []  # Initialize/reset self.placements for this run
        load_order = 0

        for box in boxes:
            placement = self._place_single_box(
                box,
                load_order,
                allow_zone_overflow,
                accessibility_weight
            )

            if placement:
                self.placements.append(placement)  # Update self.placements immediately!
                
                # Add to spatial grid for O(1) collision detection (like single-stop solver)
                if self.spatial_grid:
                    self.spatial_grid.add_box(placement)
                
                load_order += 1
                self._update_extreme_points(placement)

        return self.placements

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
        
        Enhanced with single-stop principles:
        - Try target zone first with strict validation
        - Only overflow to adjacent zones if permitted
        - Apply strong penalties for zone violations
        - Prioritize same-stop grouping

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

            # Get extreme points, prioritizing target zone
            sorted_eps = self._sort_extreme_points_by_zone(target_zone)
            
            # Limit search for efficiency (single-stop pattern)
            max_points_to_try = min(200, len(sorted_eps))

            for ep in sorted_eps[:max_points_to_try]:
                # CRITICAL: Validate extreme point space availability (prevents placing in occupied space)
                # This is the PRIMARY protection against overlaps and height violations
                if length > ep.available_length:
                    continue
                if width > ep.available_width:
                    continue
                if height > ep.available_height:
                    continue
                
                # DOUBLE CHECK: Explicit container bounds validation (belt and suspenders)
                # This catches any EP generation bugs
                if ep.x < 0 or ep.y < 0 or ep.z < 0:
                    continue
                if ep.x + length > self.container.length + 0.01:  # 0.01cm tolerance for rounding
                    continue
                if ep.y + width > self.container.width + 0.01:
                    continue
                if ep.z + height > self.container.height + 0.01:  # CRITICAL: Height check
                    continue

                # Check if can enter door
                if not self.container.can_enter_door(width, height):
                    continue
                
                # Zone overflow check: Use simple distance-based check
                # Allow reasonable overflow for natural packing without artificial gaps
                if not allow_zone_overflow:
                    # Calculate how much the box extends beyond zone boundaries
                    x_overflow_start = max(0, target_zone.x_min - ep.x)
                    x_overflow_end = max(0, (ep.x + length) - target_zone.x_max)
                    total_x_overflow = x_overflow_start + x_overflow_end
                    
                    # Allow up to 50% of box length to overflow (increased from 30%)
                    max_overflow = length * 0.5
                    
                    if total_x_overflow > max_overflow:
                        continue  # Too much overflow, skip this placement
                
                # If allowing overflow, only permit overflow to ADJACENT zones
                elif not self._is_overflow_to_adjacent_zone_only(ep, length, width, target_stop):
                    continue

                # Create candidate placement with quantized coordinates to prevent floating-point issues
                candidate = PlacedBox(
                    box=box,
                    x=round(ep.x, 1),  # Quantize to 0.1cm precision
                    y=round(ep.y, 1),
                    z=round(ep.z, 1),
                    rotation=rotation,
                    length=length,
                    width=width,
                    height=height,
                    load_order=load_order
                )

                # Validate placement (comprehensive checks including stop adjacency)
                if not self._is_valid_placement(candidate):
                    continue

                # Score placement (multi-factor with zone compliance emphasis)
                score = self._score_placement(
                    candidate,
                    target_zone,
                    accessibility_weight
                )

                if score < best_score:
                    best_score = score
                    best_placement = candidate
                    
                    # Early exit for excellent placements (ground level, in zone, well-positioned)
                    if (ep.z == 0 and  # Ground level
                        score < 500.0 and  # Good score
                        target_zone.contains_point(ep.x + length/2, ep.y + width/2, ep.z)):
                        break
            
            # If found good placement, don't try more rotations
            if best_placement and best_score < 1000.0:
                break

        return best_placement
    
    def _is_overflow_to_adjacent_zone_only(
        self, 
        point: PlacementPoint, 
        length: float, 
        width: float, 
        target_stop: int
    ) -> bool:
        """
        Check if overflow is only to adjacent zones (stop ± 1).
        
        Prevents non-adjacent stop mixing when overflow is allowed.
        
        Args:
            point: Placement point
            length: Box length after rotation
            width: Box width after rotation
            target_stop: Target stop number
            
        Returns:
            True if overflow is acceptable (adjacent only or none), False otherwise
        """
        target_zone = self.zones.get(target_stop)
        if not target_zone:
            return False
        
        # Calculate box bounds
        box_x_min = point.x
        box_x_max = point.x + length
        box_y_min = point.y
        box_y_max = point.y + width
        
        # Check which zones this box would overlap
        overlapping_zones = []
        for stop_num, zone in self.zones.items():
            # Check X overlap
            x_overlap = not (box_x_max <= zone.x_min or box_x_min >= zone.x_max)
            # Check Y overlap  
            y_overlap = not (box_y_max <= zone.y_min or box_y_min >= zone.y_max)
            
            if x_overlap and y_overlap:
                overlapping_zones.append(stop_num)
        
        # Allow if only overlaps target zone
        if len(overlapping_zones) == 1 and overlapping_zones[0] == target_stop:
            return True
        
        # Allow if overlaps target zone and adjacent zones only
        for zone_num in overlapping_zones:
            if zone_num != target_stop:
                # Check if adjacent (differ by 1)
                if abs(zone_num - target_stop) > 1:
                    return False  # Non-adjacent zone overlap - reject
        
        return True  # All overlaps are with target or adjacent zones

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

        Checks (in optimized order - cheapest first):
        1. Container fit (fast boundary check)
        2. PRODUCTION-GRADE: Unload monotonicity (critical multi-stop rule)
        3. Collision detection (O(k) with nearby placements)
        4. Adequate support (70% overlap)
        5. Stacking rules (fragile, max_stack, groups)

        Returns:
            True if valid, False otherwise
        """
        # Fast check: Container fit using proven CollisionDetector
        if not CollisionDetector.check_container_fit(candidate, self.container, tolerance=0.01):
            return False
        
        # PRODUCTION-GRADE: Unload monotonicity rule (ALWAYS enforced, regardless of mode)
        # This single rule dominates all adjacency/accessibility heuristics
        if self._violates_unload_monotonicity(candidate):
            return False
        
        # CRITICAL: Check collisions against ALL placements like single-stop solver does
        # The nearby optimization with 10cm margin can miss collisions with larger boxes (40-120cm)
        # This is O(1) with spatial grid, O(n) without - but ALWAYS CORRECT
        if self.spatial_grid:
            # Use spatial grid for O(1) collision detection
            if self.spatial_grid.check_collision(candidate):
                return False
        else:
            # Fallback: Check against ALL placements (no filtering)
            for placed in self.placements:
                if self._boxes_collide(candidate, placed):
                    return False
        
        # Get nearby placements for support/stacking validation (not collision)
        nearby_placements = self._get_nearby_placements(candidate)

        # Check support (if not on ground) - uses nearby_placements (sufficient for support calc)
        if candidate.z > 0.1:  # Not on floor
            if not self._has_adequate_support(candidate, nearby_placements):
                return False

        # Check stacking rules - uses nearby_placements (sufficient for stacking calc)
        if not self._check_stacking_rules(candidate, nearby_placements):
            return False

        return True

    def _get_nearby_placements(self, candidate: PlacedBox, margin: float = 10.0) -> List[PlacedBox]:
        """
        Get placements that could potentially collide with candidate.
        Uses SpatialGrid for O(1) lookup if available, otherwise falls back to linear bounding box check.
        
        This follows the single-stop pattern of spatial optimization.
        
        Args:
            candidate: Box to check
            margin: Extra margin for bounding box (default 10cm) - only used in linear fallback
            
        Returns:
            List of potentially colliding placements
        """
        # Use SpatialGrid if available (O(1) average case - like single-stop solver)
        if self.spatial_grid:
            return self.spatial_grid.get_potential_collisions(candidate)
        
        # Fallback to linear bounding box check (O(n))
        nearby = []
        
        # Expanded bounding box
        x_min = candidate.x - margin
        x_max = candidate.max_x + margin
        y_min = candidate.y - margin
        y_max = candidate.max_y + margin
        z_min = candidate.z - margin
        z_max = candidate.max_z + margin
        
        for placed in self.placements:
            # Quick bounding box overlap check
            if not (placed.max_x < x_min or placed.x > x_max or
                    placed.max_y < y_min or placed.y > y_max or
                    placed.max_z < z_min or placed.z > z_max):
                nearby.append(placed)
        
        return nearby
    
    def _boxes_collide(self, box1: PlacedBox, box2: PlacedBox, tolerance: float = None) -> bool:
        """Check if two boxes collide using AABB (Axis-Aligned Bounding Box)
        
        Uses the battle-tested CollisionDetector from utils.py with proper tolerance.
        
        Args:
            box1: First placed box
            box2: Second placed box
            tolerance: Small tolerance for floating point comparisons (uses 0.01cm if None)
        
        Returns:
            True if boxes collide/overlap, False if they're separated
        """
        if tolerance is None:
            # Use same tight tolerance as single-stop solver (0.01cm = 0.1mm)
            tolerance = 0.01
        
        # Use proven collision detection from utils.py
        return CollisionDetector.check_collision_fast(box1, box2, tolerance)

    def _has_adequate_support(
        self,
        candidate: PlacedBox,
        nearby_placements: List[PlacedBox] = None,
        required_support: float = 0.7
    ) -> bool:
        """
        Check if box has adequate support below it.
        Uses the proven StackingValidator from utils.py.

        Args:
            candidate: Box to check
            nearby_placements: Nearby boxes to check (for efficiency)
            required_support: Fraction of base area that must be supported

        Returns:
            True if adequately supported
        """
        # Use nearby_placements if provided, otherwise all placements
        placements_to_check = nearby_placements if nearby_placements is not None else self.placements
        
        # Use proven support validation from utils.py
        return StackingValidator.check_support(candidate, placements_to_check, tolerance=0.1)

    def _check_stacking_rules(self, candidate: PlacedBox, nearby_placements: List[PlacedBox] = None) -> bool:
        """
        Check stacking rules for placement.
        Uses the proven StackingValidator from utils.py and SpatialGrid when available.

        Rules:
        - Can't place on top of fragile boxes
        - Respect max_stack limits
        - Respect stacking groups
        - Check load bearing capacity

        Args:
            candidate: Box to check
            nearby_placements: Nearby boxes to check (for efficiency)

        Returns:
            True if stacking rules satisfied
        """
        # Use nearby_placements if provided, otherwise all placements
        placements_to_check = nearby_placements if nearby_placements is not None else self.placements

        # Find boxes directly below using SpatialGrid if available (like single-stop solver)
        if self.spatial_grid and candidate.z > 0.1:
            boxes_below = self.spatial_grid.get_boxes_below(candidate, tolerance=0.1)
        else:
            # Fallback to linear search
            boxes_below = []
            for placed in placements_to_check:
                if abs(placed.max_z - candidate.z) < 0.1:
                    if candidate.overlaps_xy(placed):
                        boxes_below.append(placed)

        # Use proven stacking validation from utils.py
        if not StackingValidator.check_stacking_rules(candidate, boxes_below):
            return False
        
        # Check max_stack limits using utils.py
        for below in boxes_below:
            count = StackingValidator.count_boxes_above(below, placements_to_check + [candidate])
            if count > below.box.max_stack:
                return False

        return True

    def _score_placement(
        self,
        candidate: PlacedBox,
        target_zone: StopZone,
        accessibility_weight: float
    ) -> float:
        """
        Score a placement candidate with comprehensive multi-stop aware metrics.

        Lower score = better placement.

        Components (in priority order):
        1. Zone compliance (CRITICAL for multi-stop)
        2. Stop separation (prevent non-adjacent mixing)
        3. Height penalty (prefer ground, but allow elevated X-expansion)
        4. X-progression bonus (encourage progressive X-filling to prevent walls)
        5. Repeated footprint penalty (discourage vertical stacking when X-space available)
        6. Position optimization (prefer back-left within zone)
        7. Accessibility penalty (multi-stop specific)
        8. Compactness bonus (reduce gaps within same stop)

        Returns:
            Score (lower is better)
        """
        score = 0.0
        
        # 1. ZONE COMPLIANCE (Most critical for multi-stop)
        center_x = candidate.x + candidate.length / 2
        center_y = candidate.y + candidate.width / 2
        center_z = candidate.z + candidate.height / 2
        
        in_zone = target_zone.contains_point(center_x, center_y, center_z)
        
        if not in_zone:
            # Calculate how far outside zone the box is
            x_distance_outside = 0.0
            if center_x < target_zone.x_min:
                x_distance_outside = target_zone.x_min - center_x
            elif center_x > target_zone.x_max:
                x_distance_outside = center_x - target_zone.x_max
            
            # Progressive penalty based on distance (not massive flat penalty)
            # Small overflow (< 30% box length) gets moderate penalty
            # Large overflow gets heavy penalty
            if x_distance_outside < candidate.length * 0.3:
                score += 2000.0 + x_distance_outside * 50.0  # Moderate penalty for small overflow
            else:
                score += 5000.0 + x_distance_outside * 100.0  # Heavy penalty for large overflow
        else:
            # Small bonus for being well within zone (not on edge)
            zone_center_x = (target_zone.x_min + target_zone.x_max) / 2
            distance_from_center = abs(center_x - zone_center_x)
            zone_width = target_zone.x_max - target_zone.x_min
            if distance_from_center < zone_width * 0.3:
                score -= 50.0  # Bonus for central placement
        
        # 2. STOP SEPARATION (Prevent non-adjacent mixing)
        candidate_stop = candidate.box.delivery_order
        nearby_stops = set()
        
        for placed in self.placements:
            # Check if nearby (YZ overlap + close in X)
            y_overlap = not (candidate.max_y <= placed.y or candidate.y >= placed.max_y)
            z_overlap = not (candidate.max_z <= placed.z or candidate.z >= placed.max_z)
            x_distance = min(abs(candidate.x - placed.max_x), abs(candidate.max_x - placed.x))
            
            if y_overlap and z_overlap and x_distance < 150.0:
                nearby_stops.add(placed.box.delivery_order)
        
        # Penalize non-adjacent stops in proximity
        for nearby_stop in nearby_stops:
            if nearby_stop != candidate_stop:
                stop_gap = abs(candidate_stop - nearby_stop)
                if stop_gap > 1:  # Non-adjacent stops
                    score += 3000.0 * stop_gap  # Heavy penalty, scales with gap
        
        # 3. HEIGHT PENALTY (Modified: prefer ground, but allow elevated X-expansion)
        # Reduce height penalty to allow lateral expansion above ground
        # Original penalty (50.0) was too harsh, preventing elevated lateral packing
        score += candidate.z * 15.0  # Reduced from 50.0
        
        # 4. X-PROGRESSION BONUS (NEW: Encourage progressive X-filling)
        # Reward filling X-axis progressively rather than stacking vertically
        # This prevents "wall" formation that blocks container depth
        max_x_in_zone = 0.0
        for placed in self.placements:
            if placed.box.delivery_order == candidate_stop:
                max_x_in_zone = max(max_x_in_zone, placed.max_x)
        
        # If this box extends X further than existing same-stop boxes, reward it
        if candidate.max_x > max_x_in_zone:
            x_extension = candidate.max_x - max_x_in_zone
            score -= x_extension * 2.0  # Bonus for extending X
        
        # 5. REPEATED FOOTPRINT PENALTY (NEW: Discourage vertical walls)
        # Penalize placing multiple boxes at same X,Y footprint (vertical stacking)
        # when lateral X space is available
        footprint_repeats = 0
        for placed in self.placements:
            if placed.box.delivery_order == candidate_stop:
                # Check if same X,Y footprint
                x_overlap = abs(candidate.x - placed.x) < 5.0
                y_overlap = abs(candidate.y - placed.y) < 5.0
                if x_overlap and y_overlap:
                    footprint_repeats += 1
        
        # If repeating footprint AND lateral space available, penalize
        if footprint_repeats > 0:
            available_x_space = target_zone.x_max - max_x_in_zone
            if available_x_space > candidate.length:
                # Penalize repeated stacking when lateral space exists
                score += footprint_repeats * 200.0  # Penalty scales with repetitions
        
        # 6. POSITION OPTIMIZATION (Single-stop principle: prefer organized placement)
        # Prefer positions that match stop sequence (earlier stops toward door)
        # Earlier stops (low delivery_order) should have high X values
        expected_x_ratio = 1.0 - (candidate_stop / max(len(self.zones), 1))
        actual_x_ratio = center_x / self.container.length
        position_deviation = abs(expected_x_ratio - actual_x_ratio)
        score += position_deviation * 1000.0
        
        # Prefer back-left within zone
        score += (candidate.y) * 5.0  # Slight preference for left side
        
        # 7. ACCESSIBILITY PENALTY - REMOVED
        # Now redundant - monotonicity rule enforces unload feasibility as hard constraint
        # Accessibility is a consequence of correct placement, not a scoring factor
        
        # 8. COMPACTNESS BONUS (Single-stop principle: reduce gaps)
        # Reward placements that are close to existing placements in same zone
        min_distance_to_same_stop = float('inf')
        for placed in self.placements:
            if placed.box.delivery_order == candidate_stop:
                distance = ((candidate.x - placed.x)**2 + 
                           (candidate.y - placed.y)**2 + 
                           (candidate.z - placed.z)**2) ** 0.5
                min_distance_to_same_stop = min(min_distance_to_same_stop, distance)
        
        if min_distance_to_same_stop < float('inf'):
            # Bonus for being close to same-stop boxes (promotes grouping)
            if min_distance_to_same_stop < 100.0:
                score -= 100.0  # Strong bonus for adjacent placement
            elif min_distance_to_same_stop < 200.0:
                score -= 50.0   # Moderate bonus

        return score

    def _violates_unload_monotonicity(self, candidate: PlacedBox) -> bool:
        """
        Production-grade unload blocking rule (ALWAYS enforced).
        
        MONOTONIC X-ENVELOPE INVARIANT (CORRECTED):
        For all stops S and T where S < T: max_x(S) >= max_x(T) when YZ overlaps
        
        CRITICAL: Compare FRONT FACES (max_x), not origins (x).
        Blocking is determined by which box extends closer to the door.
        
        In plain terms:
        - Later-stop items MUST NOT extend closer to door than earlier-stop items
        - If a later-stop box's front face (max_x) extends beyond an earlier-stop box's front face
          AND they overlap in YZ, it blocks the unload corridor
        - This is THE fundamental multi-stop constraint
        
        This single rule dominates:
        - _check_stop_adjacency (REMOVED)
        - _check_same_stop_blocking (REMOVED)  
        - accessibility penalties (REMOVED)
        - All ad-hoc blocking heuristics (REMOVED)
        
        Args:
            candidate: Box being placed
            
        Returns:
            True if placement would violate unload monotonicity (REJECT)
            False if placement is valid (ALLOW)
        """
        cand_stop = candidate.box.delivery_order
        
        for placed in self.placements:
            placed_stop = placed.box.delivery_order
            
            # Only later stops can block earlier ones
            # Candidate is a LATER stop (higher number) trying to extend in FRONT of earlier stop
            if cand_stop > placed_stop:
                # CORRECTED: Compare front faces (max_x), not origins (x)
                # Later-stop box must NOT extend closer to door than earlier-stop box
                if candidate.max_x > placed.max_x + 1.0:  # 1cm tolerance for rounding
                    # Check YZ overlap - if overlaps, candidate blocks unload corridor
                    if candidate.overlaps_yz(placed):
                        # REJECT: Later stop cannot extend beyond earlier stop's front face
                        return True
        
        return False

    def _check_same_stop_blocking(self, candidate: PlacedBox, nearby_placements: List[PlacedBox]) -> bool:
        """
        Bug #7 Fix: Prevent same-stop boxes from blocking each other during placement.
        
        CORRECTED LOGIC:
        - Allow vertical stacking (same X, different Z) ✓
        - Prevent horizontal blocking (different X, same Z, overlapping YZ) ✗
        
        Args:
            candidate: Box being placed
            nearby_placements: Boxes in spatial proximity
            
        Returns:
            True if no same-stop blocking detected, False if violation
        """
        candidate_stop = candidate.box.delivery_order
        
        for placed in nearby_placements:
            # Only check same-stop boxes
            if placed.box.delivery_order != candidate_stop:
                continue
            
            # Safety check for None values
            if placed.x is None or candidate.x is None:
                continue
            
            # Check YZ overlap first (required for blocking)
            y_overlap = not (placed.max_y <= candidate.y or placed.y >= candidate.max_y)
            z_overlap = not (placed.max_z <= candidate.z or placed.z >= candidate.max_z)
            
            if not (y_overlap and z_overlap):
                continue  # No overlap, can't block
            
            # CRITICAL: Check if they're at SAME height level
            # Only boxes at same Z level can block each other horizontally
            # Different Z levels = vertical stacking, which is ALLOWED
            same_z_level = abs(placed.z - candidate.z) < 0.1
            
            if not same_z_level:
                continue  # Different heights - vertical stacking is OK
            
            # Now check horizontal blocking (same Z level, YZ overlap)
            # BUG 1 FIX: Only block if candidate would permanently trap another same-stop box
            # i.e., candidate is closer to door AND overlaps YZ at same Z
            # Do NOT symmetrically forbid both directions - same-stop items can coexist
            
            # Only reject if candidate is closer to door (higher X) than placed box
            if candidate.x > placed.x:
                return False  # Candidate would block same-stop box from door
        
        return True
    
    def _check_stop_adjacency(self, candidate: PlacedBox, nearby_placements: List[PlacedBox]) -> bool:
        """
        Validate stop adjacency: prevent non-adjacent stops from mixing.
        
        Key Rule: Items from Stop 1 should NOT be placed near Stop 3 items,
        because unloading Stop 1 would require removing Stop 2 items as well.
        
        Args:
            candidate: Box being placed
            nearby_placements: Boxes in spatial proximity
            
        Returns:
            True if adjacency is valid, False if violation detected
        """
        candidate_stop = candidate.box.delivery_order
        
        # Define "nearby" as overlapping in YZ plane with X distance < 200cm
        for placed in nearby_placements:
            placed_stop = placed.box.delivery_order
            
            # Skip if same stop
            if placed_stop == candidate_stop:
                continue
            
            # Check if stops are adjacent (differ by 1)
            stop_gap = abs(candidate_stop - placed_stop)
            
            # If stops are NOT adjacent (gap > 1), check spatial proximity
            if stop_gap > 1:
                # Check Y-Z overlap
                y_overlap = not (candidate.max_y <= placed.y or candidate.y >= placed.max_y)
                z_overlap = not (candidate.max_z <= placed.z or candidate.z >= placed.max_z)
                
                # BUG 3 FIX: Only apply adjacency rule when at same Z level
                # Vertical coexistence (different Z) is allowed even for non-adjacent stops
                same_z_level = abs(candidate.z - placed.z) < 0.1
                
                if y_overlap and z_overlap and same_z_level:
                    # Check X distance
                    x_distance = min(abs(candidate.x - placed.max_x), abs(candidate.max_x - placed.x))
                    
                    # Bug #10 Fix: Use configurable separation threshold
                    # If too close in X direction, this is a violation
                    if x_distance < self.non_adjacent_stop_separation_cm:
                        return False
        
        return True
    
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
                # BUG 4 FIX: Later stops are deeper in container (LOWER X)
                # Placed box blocks if it's closer to door (LOWER X) than candidate
                if placed.x < candidate.x:
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

        Creates new extreme points with CORRECT available space calculation:
        - Above the box: constrain to box surface if elevated, else full container
        - To the right: lateral packing on elevated surfaces (like single-stop)
        - To the front: lateral packing on elevated surfaces (like single-stop)
        - ZONE-AWARE: Available space respects zone boundaries to prevent gaps

        Also removes points that are now inside the placed box.
        """
        # Determine which zone this box belongs to
        box_zone = self.zones.get(placed.box.delivery_order)
        
        # Remove invalidated points
        self.extreme_points = [
            ep for ep in self.extreme_points
            if not (
                placed.x <= ep.x < placed.max_x and
                placed.y <= ep.y < placed.max_y and
                placed.z <= ep.z < placed.max_z
            )
        ]

        # Add new extreme points with CORRECT available space
        new_points = []
        
        # Point above (z+) - Always valid to place on top of a box
        if placed.max_z < self.container.height:
            # BUG 2 FIX: For elevated points, use supporting footprint (union of boxes below)
            if placed.z > 0.1:
                # Elevated point - use the union of supporting boxes' footprint
                support_boxes = [p for p in self.placements if abs(p.max_z - placed.z) < 0.1]
                if support_boxes:
                    avail_length = max(p.length for p in support_boxes)
                    avail_width = max(p.width for p in support_boxes)
                else:
                    avail_length = placed.length
                    avail_width = placed.width
            else:
                # Ground level - advertise full container space (zone checked during placement)
                avail_length = self.container.length - placed.x
                avail_width = self.container.width - placed.y
            
            new_points.append(PlacementPoint(
                x=placed.x,
                y=placed.y,
                z=placed.max_z,
                available_length=avail_length,
                available_width=avail_width,
                available_height=self.container.height - placed.max_z,
                source="above"
            ))
        
        # Point to the right (x+) - LATERAL PACKING FIX
        if placed.max_x < self.container.length:
            if placed.z < 0.1:
                # Ground level - advertise PHYSICAL space, NOT zone-constrained
                # Zone compliance is handled by placement validation (soft constraint)
                # This allows natural lateral packing without artificial boundaries
                avail_length = self.container.length - placed.max_x
                
                # Only create EP if there's meaningful space available (>5cm)
                if avail_length > 5.0:
                    new_points.append(PlacementPoint(
                        x=placed.max_x,
                        y=placed.y,
                        z=0,
                        available_length=avail_length,
                        available_width=self.container.width - placed.y,
                        available_height=self.container.height,
                        source="right_ground"
                    ))
            else:
                # ELEVATED - Allow lateral packing (multiple boxes side-by-side)
                # The next box will share support from the boxes below
                # Calculate available space based on supporting boxes
                support_boxes = [p for p in self.placements if abs(p.max_z - placed.z) < 0.1]
                if support_boxes:
                    # PATCH 5: Use actual maximum width from ALL support boxes
                    max_width = max(p.width for p in support_boxes)
                    
                    # Elevated - constrain by container, not zone (support geometry is the real constraint)
                    avail_length = self.container.length - placed.max_x
                    
                    # Only create EP if there's meaningful space
                    if avail_length > 5.0:
                        new_points.append(PlacementPoint(
                            x=placed.max_x,
                            y=placed.y,
                            z=placed.z,
                            available_length=avail_length,
                            available_width=max_width,  # Use maximum support width
                            available_height=self.container.height - placed.z,
                            source="right_elevated"
                        ))
        
        # Point to the front (y+) - LATERAL PACKING FIX
        if placed.max_y < self.container.width:
            if placed.z < 0.1:
                # Ground level - advertise PHYSICAL space without zone constraints
                avail_length = self.container.length - placed.x
                
                # Only create EP if there's meaningful space
                if avail_length > 5.0:
                    new_points.append(PlacementPoint(
                        x=placed.x,
                        y=placed.max_y,
                        z=0,
                        available_length=avail_length,
                        available_width=self.container.width - placed.max_y,
                        available_height=self.container.height,
                        source="front_ground"
                    ))
            else:
                # ELEVATED - Allow lateral packing
                support_boxes = [p for p in self.placements if abs(p.max_z - placed.z) < 0.1]
                if support_boxes:
                    # PATCH 5: Use actual maximum length from ALL support boxes
                    avail_length = max(p.length for p in support_boxes)
                    
                    # Only create EP if there's meaningful space
                    if avail_length > 5.0:
                        new_points.append(PlacementPoint(
                            x=placed.x,
                            y=placed.max_y,
                            z=placed.z,
                            available_length=avail_length,  # Use maximum support length
                            available_width=self.container.width - placed.max_y,
                            available_height=self.container.height - placed.z,
                            source="front_elevated"
                        ))

        # Filter and add valid new points
        for np in new_points:
            if self.container.contains_point(np.x, np.y, np.z):
                # Quantize to prevent duplicates
                np_quantized = np.quantize(0.1)
                
                # PATCH 6: Check for duplicates including available space dimensions
                is_duplicate = False
                for existing_ep in self.extreme_points:
                    if (abs(existing_ep.x - np_quantized.x) < 0.01 and
                        abs(existing_ep.y - np_quantized.y) < 0.01 and
                        abs(existing_ep.z - np_quantized.z) < 0.01 and
                        abs(existing_ep.available_length - np_quantized.available_length) < 0.01 and
                        abs(existing_ep.available_width - np_quantized.available_width) < 0.01):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
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
