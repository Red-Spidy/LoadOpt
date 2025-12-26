from typing import List, Tuple, Optional, Dict, Set
from app.solver.utils import (
    Box, ContainerSpace, PlacementPoint, PlacedBox,
    BoxRotation, CollisionDetector, StackingValidator, WeightDistribution,
    SpatialGrid
)
import heapq
import numpy as np
from functools import lru_cache


class HeuristicSolver:
    """
    Optimized heuristic solver using:
    - First Fit Decreasing (FFD) with priority weighting
    - Extreme Points placement strategy with O(1) duplicate detection
    - Spatial grid for O(1) collision detection (vs O(n) linear scan)
    - Best Fit for rotation selection with symmetry pruning
    - Heap-based point management for efficient sorting
    - Cached dimension calculations
    - Future space awareness scoring (Optimization #2)
    - Adaptive extreme point limit (Optimization #3)
    """
    
    def __init__(self, boxes: List[Box], container: ContainerSpace,
                 use_spatial_grid: bool = True, existing_placements: List[PlacedBox] = None):
        self.boxes = boxes
        self.container = container
        self.placements: List[PlacedBox] = existing_placements if existing_placements else []
        self._existing_count = len(self.placements)  # Track how many are pre-existing
        self.placement_points: List[Tuple[float, float, float, PlacementPoint]] = []  # Heap
        self._points_set: Set[Tuple[float, float, float]] = set()  # Quantized floats (Optimization #10)
        self._invalid_points: Set[Tuple[float, float, float]] = set()  # Lazy deletion tombstones
        self._points_fragmentation: float = 0.0  # Track fragmentation ratio
        
        # Adaptive spatial grid cell size based on box dimensions (Optimization #9)
        cell_size = self._calculate_adaptive_cell_size(boxes, container)
        
        # Spatial indexing for fast collision detection - O(1) vs O(n)
        self.use_spatial_grid = use_spatial_grid
        self.spatial_grid = SpatialGrid(
            container.length, container.width, container.height,
            cell_size=cell_size
        ) if use_spatial_grid else None
        
        # If we have existing placements, add them to the spatial grid
        if self.spatial_grid and existing_placements:
            for p in existing_placements:
                self.spatial_grid.add_box(p)
        
        # Precompute container volume
        self._container_volume = container.length * container.width * container.height
        
        # Precompute box volumes for faster sorting
        self._box_volumes: Dict[int, float] = {id(b): b.volume for b in boxes}

        # Current total weight for quick limit checking
        self._total_weight = 0.0

        # Track placed box IDs for O(1) lookup instead of O(n) set creation
        self._placed_box_ids: Set[int] = set()

        # Cache minimum useful dimension (updated as boxes are placed)
        self._min_useful_dim: float = min(min(b.length, b.width, b.height) for b in boxes) if boxes else 30.0
        self._remaining_box_count: int = len(boxes)
        
        # Ground column reservation: compute tall SKU threshold (Commercial Fix)
        self._max_box_height: float = max(b.height for b in boxes) if boxes else 0.0
        self._max_box_length: float = max(b.length for b in boxes) if boxes else 0.0
        self._max_box_width: float = max(b.width for b in boxes) if boxes else 0.0
        self._tall_height_threshold: float = 0.8 * self._max_box_height
        
        # Adaptive max points based on problem size (Optimization #3)
        # Increased limits for better space exploration
        n_boxes = len(boxes)
        if n_boxes <= 30:
            self._max_points = 300  # More points for thorough search
        elif n_boxes <= 60:
            self._max_points = 200
        elif n_boxes <= 100:
            self._max_points = 150
        else:
            self._max_points = 100  # Still reasonable for large problems
        
        # Initialize with corner point
        origin = PlacementPoint(
            x=0, y=0, z=0,
            available_length=container.length,
            available_width=container.width,
            available_height=container.height
        )
        heapq.heappush(self.placement_points, (0, 0, 0, origin))
        self._points_set.add(self._quantize_point(0, 0, 0))
    
    @staticmethod
    def _calculate_adaptive_cell_size(boxes: List[Box], container: ContainerSpace) -> float:
        """Calculate optimal cell size based on box dimensions (Optimization #9)"""
        if not boxes:
            return 50.0
        
        # Use median of all box dimensions
        all_dims = []
        for b in boxes:
            all_dims.extend([b.length, b.width, b.height])
        all_dims.sort()
        median_dim = all_dims[len(all_dims) // 2]
        
        # Cell size = 1.5-2x median, bounded
        cell_size = median_dim * 1.8
        container_min = min(container.length, container.width, container.height)
        
        return max(30.0, min(cell_size, container_min / 5))
    
    @staticmethod
    def _quantize_point(x: float, y: float, z: float, precision: float = 0.01) -> Tuple[float, float, float]:
        """Quantize point coordinates for better precision (Optimization #10)"""
        return (round(x / precision) * precision, 
                round(y / precision) * precision, 
                round(z / precision) * precision)
    
    def solve(self, box_order: List[int] = None) -> Tuple[List[PlacedBox], dict]:
        """
        Run optimized heuristic solver
        
        Args:
            box_order: Optional custom order of box indices for metaheuristic integration
        
        Returns:
            (placements, stats)
        
        Sorting Logic:
        - Items are placed from BACK to FRONT of container (X=0 to X=length)
        - Higher delivery_order (loaded later = unloaded later) is placed FIRST (at back)
        - Lower delivery_order (loaded first = unloaded first) is placed LAST (near door)
        - Within same delivery_order: sort by priority (desc), then volume (desc)
        """
        # Sort boxes: high delivery_order first (back of truck), then priority (desc), then volume (desc)
        # This ensures first delivery items (low delivery_order) are placed near the door
        if box_order is not None:
            sorted_boxes = [self.boxes[i] for i in box_order if i < len(self.boxes)]
        else:
            sorted_boxes = sorted(
                self.boxes,
                key=lambda b: (-b.delivery_order, b.priority, self._box_volumes.get(id(b), b.volume)),
                reverse=True
            )
        
        placed_count = 0
        failed_count = 0
        
        for box in sorted_boxes:
            if self._place_box_optimized(box):
                placed_count += 1
            else:
                failed_count += 1
        
        # Calculate statistics
        stats = self._calculate_stats()
        stats['placed_count'] = placed_count
        stats['failed_count'] = failed_count
        
        # Return only the NEW placements (not the existing ones)
        new_placements = self.placements[self._existing_count:]
        return new_placements, stats
    
    def _place_box_optimized(self, box: Box) -> bool:
        """Try to place a single box using optimized algorithms"""
        # Quick weight check before trying placements
        if self._total_weight + box.weight > self.container.max_weight:
            return False
        
        best_placement = None
        best_score = float('inf')
        
        # Get unique rotations (prunes symmetric duplicates for cubes)
        rotations = BoxRotation.get_unique_rotations(box)
        
        # Pre-check door entry for each rotation
        valid_rotations = []
        for rotation in rotations:
            length, width, height = BoxRotation.get_dimensions(
                box.length, box.width, box.height, rotation
            )
            if width <= self.container.door_width and height <= self.container.door_height:
                valid_rotations.append((rotation, length, width, height))
        
        if not valid_rotations:
            return False
        
        # Create a copy of points to iterate (heap is modified during iteration)
        points_to_try = []
        temp_heap = list(self.placement_points)
        heapq.heapify(temp_heap)
        
        # Adaptive point limit (Optimization #3)
        max_points = min(len(temp_heap), self._max_points)
        for _ in range(max_points):
            if not temp_heap:
                break
            _, _, _, point = heapq.heappop(temp_heap)
            points_to_try.append(point)
        
        # First pass: try limited points
        for point in points_to_try:
            for rotation, length, width, height in valid_rotations:
                # Quick bounds check
                if (length > point.available_length or
                    width > point.available_width or
                    height > point.available_height):
                    continue
                
                # Create placement
                placed = PlacedBox(
                    box=box,
                    x=point.x,
                    y=point.y,
                    z=point.z,
                    rotation=rotation,
                    length=length,
                    width=width,
                    height=height,
                    load_order=len(self.placements)
                )
                
                # 🔒 GROUND COLUMN RESERVATION RULE (COMMERCIAL FIX)
                # Reserve ground space for remaining tall boxes that could use it
                if placed.z == 0 and box.height < self._tall_height_threshold:
                    tall_boxes_remaining = any(
                        b.height >= self._tall_height_threshold
                        for b in self.boxes
                        if id(b) not in self._placed_box_ids
                    )
                    
                    if tall_boxes_remaining:
                        # Only forbid if this ground position could be used by a tall box
                        if (placed.x + self._max_box_length <= self.container.length and
                            placed.y + self._max_box_width <= self.container.width):
                            continue
                
                # Validate placement (optimized order - cheapest checks first)
                if not self._validate_placement_optimized(placed):
                    continue
                
                # Improved placement scoring (Optimization #2)
                score = self._calculate_placement_score(placed, point)
                
                if score < best_score:
                    best_score = score
                    best_placement = placed
                    
                    # If we found a ground-level back corner placement, accept immediately
                    if point.z == 0 and point.x < self.container.length * 0.1:
                        break
            
            if best_placement and best_placement.z == 0 and best_placement.x < self.container.length * 0.1:
                break
        
        # If no placement found and we didn't try all points, try remaining points
        if not best_placement and len(temp_heap) > 0:
            remaining_points = []
            while temp_heap:
                _, _, _, point = heapq.heappop(temp_heap)
                remaining_points.append(point)
            
            for point in remaining_points:
                for rotation, length, width, height in valid_rotations:
                    if (length > point.available_length or
                        width > point.available_width or
                        height > point.available_height):
                        continue
                    
                    placed = PlacedBox(
                        box=box,
                        x=point.x, y=point.y, z=point.z,
                        rotation=rotation,
                        length=length, width=width, height=height,
                        load_order=len(self.placements)
                    )
                    
                    # 🔒 GROUND COLUMN RESERVATION RULE (COMMERCIAL FIX)
                    if placed.z == 0 and box.height < self._tall_height_threshold:
                        tall_boxes_remaining = any(
                            b.height >= self._tall_height_threshold
                            for b in self.boxes
                            if id(b) not in self._placed_box_ids
                        )
                        
                        if tall_boxes_remaining:
                            # Only forbid if this ground position could be used by a tall box
                            if (placed.x + self._max_box_length <= self.container.length and
                                placed.y + self._max_box_width <= self.container.width):
                                continue
                    
                    if not self._validate_placement_optimized(placed):
                        continue
                    
                    score = self._calculate_placement_score(placed, point)
                    if score < best_score:
                        best_score = score
                        best_placement = placed
                        break
                
                if best_placement:
                    break
        
        if best_placement:
            self.placements.append(best_placement)
            self._total_weight += best_placement.box.weight
            self._placed_box_ids.add(id(best_placement.box))
            self._remaining_box_count -= 1

            # Update min useful dimension if needed
            if self._remaining_box_count > 0:
                # Only recalculate every 10 boxes for efficiency
                if self._remaining_box_count % 10 == 0:
                    self._min_useful_dim = min(
                        (min(b.length, b.width, b.height) for b in self.boxes
                         if id(b) not in self._placed_box_ids),
                        default=30.0
                    )

            if self.spatial_grid:
                self.spatial_grid.add_box(best_placement)

            self._update_placement_points_optimized(best_placement)
            return True

        return False
    
    def _calculate_placement_score(self, placed: PlacedBox, point: PlacementPoint) -> float:
        """
        Improved placement scoring with future space awareness (Optimization #2)
        
        Considers:
        - Height level (ground strongly preferred)
        - Position (based on delivery_order: high order->back, low order->front)
        - Remaining space quality (avoid narrow gaps)
        - Weight distribution contribution
        """
        # Base score: strongly prefer ground level
        z_penalty = point.z * 10000
        
        # Position score: depends on delivery_order
        # High delivery_order (last delivery) should go to BACK (low X)
        # Low delivery_order (first delivery) should go to FRONT/DOOR (high X)
        # We invert X preference for low delivery_order boxes
        # Use strong multiplier (100) to make delivery zone separation a priority
        if placed.box.delivery_order <= 1:
            # First delivery - prefer HIGH X (near door)
            # Invert: use (container_length - x) so high X gives low score
            position_score = (self.container.length - point.x) * 100 + point.y
        else:
            # Later deliveries - prefer LOW X (at back)
            position_score = point.x * 100 + point.y
        
        # Future space awareness: penalize placements that create narrow gaps
        gap_penalty = 0.0
        remaining_x = self.container.length - placed.max_x
        remaining_y = self.container.width - placed.max_y

        # Use cached min_useful_dim instead of recalculating (O(1) vs O(n))
        if 0 < remaining_x < self._min_useful_dim * 0.5:
            gap_penalty += 200  # Narrow X gap (reduced penalty)
        if 0 < remaining_y < self._min_useful_dim * 0.5:
            gap_penalty += 100  # Narrow Y gap (reduced penalty)
        
        # Prefer placements that leave rectangular free space
        # Reward if placement aligns with container edges or other boxes
        alignment_bonus = 0.0
        if abs(placed.max_x - self.container.length) < 1.0:
            alignment_bonus -= 100  # Flush with back wall
        if abs(placed.max_y - self.container.width) < 1.0:
            alignment_bonus -= 50   # Flush with side wall
        
        # Check alignment with existing boxes
        for existing in self.placements[-5:]:  # Check recent placements
            if abs(placed.max_x - existing.max_x) < 1.0:
                alignment_bonus -= 30  # Aligned X edges
            if abs(placed.max_y - existing.max_y) < 1.0:
                alignment_bonus -= 20  # Aligned Y edges
        
        return z_penalty + position_score + gap_penalty + alignment_bonus
    
    def _validate_placement_optimized(self, placed: PlacedBox) -> bool:
        """Validate a placement with optimized check order"""
        # Check container fit (fast)
        if not CollisionDetector.check_container_fit(placed, self.container):
            return False
        
        # Check collisions using spatial grid (O(1) average) or linear (O(n))
        if self.spatial_grid:
            if self.spatial_grid.check_collision(placed):
                return False
        else:
            for existing in self.placements:
                if CollisionDetector.check_collision_fast(placed, existing):
                    return False
        
        # Check support using spatial grid if available
        if self.spatial_grid:
            if not StackingValidator.check_support_with_grid(placed, self.spatial_grid):
                return False
        else:
            if not StackingValidator.check_support(placed, self.placements):
                return False
        
        # Check stacking rules
        if placed.z > 0.1:  # Not on ground
            if self.spatial_grid:
                below_boxes = self.spatial_grid.get_boxes_below(placed)
            else:
                below_boxes = [p for p in self.placements 
                              if abs(p.max_z - placed.z) < 0.1]
            
            if not StackingValidator.check_stacking_rules(placed, below_boxes):
                return False
            
            for below in below_boxes:
                count = StackingValidator.count_boxes_above(below, self.placements + [placed])
                if count > below.box.max_stack:
                    return False
        
        return True
    
    def _update_placement_points_optimized(self, placed: PlacedBox):
        """
        Update placement points using lazy deletion (tombstones).

        Optimization: Instead of rebuilding heap after each placement,
        mark blocked points as invalid. Only rebuild when fragmentation > 50%.
        Expected improvement: 2-3x faster point management.
        """
        # Mark blocked points as invalid (lazy deletion)
        for item in self.placement_points:
            z, x, y, point = item
            if self._point_blocked(point, placed):
                key = self._quantize_point(point.x, point.y, point.z)
                self._invalid_points.add(key)

        # Calculate fragmentation ratio
        total_points = len(self.placement_points)
        invalid_count = len(self._invalid_points)
        self._points_fragmentation = invalid_count / max(1, total_points)

        # Rebuild heap only if fragmentation is high (>50%)
        if self._points_fragmentation > 0.5:
            new_heap = []
            for item in self.placement_points:
                z, x, y, point = item
                key = self._quantize_point(point.x, point.y, point.z)
                if key not in self._invalid_points:
                    new_heap.append(item)

            self.placement_points = new_heap
            heapq.heapify(self.placement_points)
            self._invalid_points.clear()
            self._points_fragmentation = 0.0

            # Update point set
            self._points_set = {self._quantize_point(p[3].x, p[3].y, p[3].z) for p in self.placement_points}
        else:
            # Just update the set to exclude invalid points
            self._points_set = {
                self._quantize_point(p[3].x, p[3].y, p[3].z)
                for p in self.placement_points
                if self._quantize_point(p[3].x, p[3].y, p[3].z) not in self._invalid_points
            }
        
        # Add new extreme points
        new_points = []
        
        # Point above (z+) - Always valid to place on top of a box
        # Use quantized coordinates to prevent floating point gaps
        if placed.max_z < self.container.height:
            qx, qy, qz = self._quantize_point(placed.x, placed.y, placed.max_z)
            key = (qx, qy, qz)
            if key not in self._points_set:
                # Calculate ACTUAL available space on top of this box
                # For elevated points, available space is limited by the supporting box dimensions
                if placed.z > 0.1:
                    # Elevated point - constrain to the box's surface area
                    avail_length = placed.length
                    avail_width = placed.width
                else:
                    # Ground level - use container remaining space
                    avail_length = self.container.length - qx
                    avail_width = self.container.width - qy
                
                new_points.append(PlacementPoint(
                    x=qx,
                    y=qy,
                    z=qz,
                    available_length=avail_length,
                    available_width=avail_width,
                    available_height=self.container.height - qz
                ))
                self._points_set.add(key)
        
        # Lateral points - Create both at ground level AND on elevated surfaces
        # When elevated, boxes must have support from the box below

        # Point to the right (x+)
        if placed.max_x < self.container.length:
            if placed.z < 0.1:
                # Ground level - full remaining space
                qx, qy, qz = self._quantize_point(placed.max_x, placed.y, 0)
                key = (qx, qy, qz)
                if key not in self._points_set:
                    new_points.append(PlacementPoint(
                        x=qx,
                        y=qy,
                        z=qz,
                        available_length=self.container.length - qx,
                        available_width=self.container.width - qy,
                        available_height=self.container.height - qz
                    ))
                    self._points_set.add(key)
            else:
                # Elevated - create point at same level if supported by box below
                # The box placed next to this one at the same level will share support
                qx, qy, qz = self._quantize_point(placed.max_x, placed.y, placed.z)
                key = (qx, qy, qz)
                if key not in self._points_set:
                    # Calculate available space constrained by supporting box
                    # Get the supporting box to determine available surface
                    support_boxes = self._get_boxes_at_level(placed.z)
                    avail_length = self._calculate_available_length(qx, qy, placed.z, support_boxes)
                    # FIXED: Calculate width based on support, not limited by previous box
                    avail_width = self._calculate_available_width(qx, qy, placed.z, support_boxes)
                    
                    new_points.append(PlacementPoint(
                        x=qx,
                        y=qy,
                        z=qz,
                        available_length=avail_length,
                        available_width=avail_width,
                        available_height=self.container.height - qz
                    ))
                    self._points_set.add(key)

        # Point to the front (y+)
        if placed.max_y < self.container.width:
            if placed.z < 0.1:
                # Ground level - full remaining space
                qx, qy, qz = self._quantize_point(placed.x, placed.max_y, 0)
                key = (qx, qy, qz)
                if key not in self._points_set:
                    new_points.append(PlacementPoint(
                        x=qx,
                        y=qy,
                        z=qz,
                        available_length=self.container.length - qx,
                        available_width=self.container.width - qy,
                        available_height=self.container.height - qz
                    ))
                    self._points_set.add(key)
            else:
                # Elevated - create point at same level if supported
                qx, qy, qz = self._quantize_point(placed.x, placed.max_y, placed.z)
                key = (qx, qy, qz)
                if key not in self._points_set:
                    support_boxes = self._get_boxes_at_level(placed.z)
                    # FIXED: Calculate length based on support, not limited by previous box
                    avail_length = self._calculate_available_length(qx, qy, placed.z, support_boxes)
                    avail_width = self._calculate_available_width(qx, qy, placed.z, support_boxes)
                    
                    new_points.append(PlacementPoint(
                        x=qx,
                        y=qy,
                        z=qz,
                        available_length=avail_length,
                        available_width=avail_width,
                        available_height=self.container.height - qz
                    ))
                    self._points_set.add(key)
        
        # Corner point (x+, y+)
        if placed.max_x < self.container.length and placed.max_y < self.container.width:
            if placed.z < 0.1:
                # Ground level - helps fill gaps
                qx, qy, qz = self._quantize_point(placed.max_x, placed.max_y, 0)
                key = (qx, qy, qz)
                if key not in self._points_set:
                    new_points.append(PlacementPoint(
                        x=qx,
                        y=qy,
                        z=qz,
                        available_length=self.container.length - qx,
                        available_width=self.container.width - qy,
                        available_height=self.container.height - qz
                    ))
                    self._points_set.add(key)
            else:
                # Elevated corner point
                qx, qy, qz = self._quantize_point(placed.max_x, placed.max_y, placed.z)
                key = (qx, qy, qz)
                if key not in self._points_set:
                    support_boxes = self._get_boxes_at_level(placed.z)
                    avail_length = self._calculate_available_length(qx, qy, placed.z, support_boxes)
                    avail_width = self._calculate_available_width(qx, qy, placed.z, support_boxes)
                    
                    new_points.append(PlacementPoint(
                        x=qx,
                        y=qy,
                        z=qz,
                        available_length=avail_length,
                        available_width=avail_width,
                        available_height=self.container.height - qz
                    ))
                    self._points_set.add(key)
        
        # Add new points to heap
        for point in new_points:
            heapq.heappush(self.placement_points, (point.z, point.x, point.y, point))
    
    def _point_blocked(self, point: PlacementPoint, placed: PlacedBox) -> bool:
        """Check if a point is blocked by a placed box"""
        return (point.x >= placed.x and point.x < placed.max_x and
                point.y >= placed.y and point.y < placed.max_y and
                point.z >= placed.z and point.z < placed.max_z)
    
    def _get_boxes_at_level(self, z: float, tolerance: float = 0.1) -> List[PlacedBox]:
        """Get all boxes at a specific Z level (boxes whose top surface is at this level)"""
        return [p for p in self.placements if abs(p.max_z - z) < tolerance]
    
    def _calculate_available_length(self, x: float, y: float, z: float, 
                                     support_boxes: List[PlacedBox]) -> float:
        """
        Calculate available length (X direction) from point (x, y, z) 
        constrained by supporting boxes below.
        
        Returns the maximum distance we can extend in the X direction
        while maintaining support from boxes below.
        """
        if not support_boxes:
            return 0.0
        
        # Find supporting boxes that:
        # 1. Overlap with the Y coordinate (can provide support at this Y)
        # 2. Start at or before X (box extends through this X position)
        relevant_boxes = [b for b in support_boxes 
                         if b.y <= y < b.max_y and b.x <= x < b.max_x]
        
        if not relevant_boxes:
            return 0.0
        
        # The available length is limited by the nearest edge of supporting boxes
        # We can extend until the minimum max_x among all supporting boxes at this Y
        max_extent = min(b.max_x for b in relevant_boxes)
        
        return max(0.0, max_extent - x)
    
    def _calculate_available_width(self, x: float, y: float, z: float, 
                                    support_boxes: List[PlacedBox]) -> float:
        """
        Calculate available width (Y direction) from point (x, y, z) 
        constrained by supporting boxes below.
        
        Returns the maximum distance we can extend in the Y direction
        while maintaining support from boxes below.
        """
        if not support_boxes:
            return 0.0
        
        # Find supporting boxes that:
        # 1. Overlap with the X coordinate (can provide support at this X)
        # 2. Start at or before Y (box extends through this Y position)
        relevant_boxes = [b for b in support_boxes 
                         if b.x <= x < b.max_x and b.y <= y < b.max_y]
        
        if not relevant_boxes:
            return 0.0
        
        # The available width is limited by the nearest edge of supporting boxes
        max_extent = min(b.max_y for b in relevant_boxes)
        
        return max(0.0, max_extent - y)
    
    def _calculate_stats(self) -> dict:
        """Calculate statistics for the solution (optimized with numpy)"""
        if not self.placements:
            return {
                'utilization_pct': 0.0,
                'total_weight': 0.0,
                'weight_distribution': None,
                'is_valid': True,
                'validation_errors': []
            }
        
        # Calculate volume utilization
        used_volume = sum(p.volume for p in self.placements)
        utilization = (used_volume / self._container_volume) * 100
        
        # Calculate weight distribution
        cog = WeightDistribution.calculate_cog(self.placements)
        front_axle, rear_axle = WeightDistribution.calculate_axle_loads(
            self.placements, self.container.length
        )
        
        weight_dist = {
            'front_axle': front_axle,
            'rear_axle': rear_axle,
            'center_of_gravity': {'x': cog[0], 'y': cog[1], 'z': cog[2]}
        }
        
        # Validate
        errors = []
        
        # Check axle limits
        if self.container.front_axle_limit and front_axle > self.container.front_axle_limit:
            errors.append(f"Front axle overloaded: {front_axle:.1f}kg > {self.container.front_axle_limit:.1f}kg")
        
        if self.container.rear_axle_limit and rear_axle > self.container.rear_axle_limit:
            errors.append(f"Rear axle overloaded: {rear_axle:.1f}kg > {self.container.rear_axle_limit:.1f}kg")
        
        # Check balance (CoG should be roughly centered)
        if abs(cog[1] - self.container.width / 2) > self.container.width * 0.2:
            errors.append("Load is unbalanced (side-to-side)")
        
        return {
            'utilization_pct': round(utilization, 2),
            'total_weight': round(self._total_weight, 2),
            'weight_distribution': weight_dist,
            'is_valid': len(errors) == 0,
            'validation_errors': errors
        }


class LayerBuildingHeuristic:
    """
    Layer-building heuristic for homogeneous loads.
    Creates horizontal layers of boxes for better stability.
    Automatically detects uniform boxes and uses grid packing for optimal results.
    """
    
    def __init__(self, boxes: List[Box], container: ContainerSpace):
        self.boxes = boxes
        self.container = container
        self.layers: List[List[PlacedBox]] = []
    
    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """Build layers from bottom up - auto-detect uniform boxes for grid packing"""
        # Check if boxes are uniform (same or similar dimensions)
        if self._are_boxes_uniform():
            return self._solve_grid_packing()
        
        # Group boxes by similar heights
        height_groups = self._group_by_height()
        
        current_z = 0.0
        all_placements = []
        load_order = 0
        
        for target_height, group_boxes in height_groups:
            if current_z + target_height > self.container.height:
                break
            
            layer_placements = self._fill_layer(group_boxes, current_z, load_order, all_placements)
            if layer_placements:
                all_placements.extend(layer_placements)
                load_order += len(layer_placements)
                current_z += target_height
        
        # Use standard heuristic for remaining boxes
        remaining = [b for b in self.boxes if id(b) not in {id(p.box) for p in all_placements}]
        if remaining:
            # Pass existing placements so HeuristicSolver knows about already-placed boxes
            solver = HeuristicSolver(remaining, self.container, existing_placements=all_placements)
            extra_placements, _ = solver.solve()
            
            # Adjust load orders
            for p in extra_placements:
                p.load_order = load_order
                load_order += 1
            
            all_placements.extend(extra_placements)
        
        return all_placements, self._calculate_stats(all_placements)
    
    def _are_boxes_uniform(self, tolerance: float = 2.0) -> bool:
        """Check if all boxes have same/similar dimensions (within tolerance)"""
        if len(self.boxes) < 2:
            return True
        
        first = self.boxes[0]
        ref_dims = sorted([first.length, first.width, first.height])
        
        for box in self.boxes[1:]:
            box_dims = sorted([box.length, box.width, box.height])
            for d1, d2 in zip(ref_dims, box_dims):
                if abs(d1 - d2) > tolerance:
                    return False
        return True
    
    def _solve_grid_packing(self) -> Tuple[List[PlacedBox], dict]:
        """Grid-based packing for uniform boxes - respects delivery groups for easy unloading"""
        if not self.boxes:
            return [], self._calculate_stats([])
        
        # Group boxes by delivery_order for zone-based packing
        from collections import defaultdict
        delivery_groups = defaultdict(list)
        for box in self.boxes:
            delivery_groups[box.delivery_order].append(box)
        
        # Sort groups: LOW delivery_order first (placed first = near door = high X)
        # delivery_order=1 means FIRST delivery = unload FIRST = should be NEAR DOOR (high X)
        # delivery_order=2 means SECOND delivery = unload SECOND = should be at BACK (low X)
        sorted_group_keys = sorted(delivery_groups.keys())  # Ascending: 1, 2, 3...
        
        # Find best rotation for grid packing
        sample_box = self.boxes[0]
        best_rot = 0
        best_dims = (sample_box.length, sample_box.width, sample_box.height)
        
        for rot in range(6):
            if rot < len(sample_box.allowed_rotations) and sample_box.allowed_rotations[rot]:
                dims = BoxRotation.get_dimensions(sample_box.length, sample_box.width, sample_box.height, rot)
                if dims[1] <= self.container.door_width and dims[2] <= self.container.door_height:
                    # Prefer rotation that maximizes boxes per row (along X axis)
                    if dims[0] <= best_dims[0]:
                        best_rot = rot
                        best_dims = dims
        
        box_l, box_w, box_h = best_dims
        nx = int(self.container.length / box_l)
        ny = int(self.container.width / box_w)
        nz = int(self.container.height / box_h)
        
        if nx == 0 or ny == 0 or nz == 0:
            # Fall back to standard heuristic
            solver = HeuristicSolver(self.boxes, self.container)
            return solver.solve()
        
        placements = []
        load_order = 0
        
        # Current position tracking - start from BACK of container
        # X goes from container.length towards 0 (back to front/door)
        current_x_start = int(self.container.length / box_l) - 1  # Start at back (highest X index)
        
        for group_key in sorted_group_keys:
            group_boxes = delivery_groups[group_key]
            boxes_remaining = len(group_boxes)
            box_idx = 0
            
            # Fill this group's zone from back to front
            # Each group gets contiguous X positions
            while boxes_remaining > 0 and current_x_start >= 0:
                # Fill columns at current X position (all Y and Z)
                for iz in range(nz):
                    for iy in range(ny):
                        if box_idx >= len(group_boxes):
                            break
                        
                        box = group_boxes[box_idx]
                        x = current_x_start * box_l
                        y = iy * box_w
                        z = iz * box_h
                        
                        placements.append(PlacedBox(
                            box=box,
                            x=x, y=y, z=z,
                            rotation=best_rot,
                            length=box_l,
                            width=box_w,
                            height=box_h,
                            load_order=load_order
                        ))
                        load_order += 1
                        box_idx += 1
                        boxes_remaining -= 1
                    if box_idx >= len(group_boxes):
                        break
                
                current_x_start -= 1  # Move towards front for next column
        
        # Try to fit remaining boxes with standard heuristic
        placed_box_ids = {id(p.box) for p in placements}
        remaining = [b for b in self.boxes if id(b) not in placed_box_ids]
        if remaining and placements:
            solver = HeuristicSolver(remaining, self.container, existing_placements=placements)
            extra_placements, _ = solver.solve()
            for i, p in enumerate(extra_placements):
                p.load_order = load_order + i
            placements.extend(extra_placements)
        
        return placements, self._calculate_stats(placements)
    
    def _group_by_height(self) -> List[Tuple[float, List[Box]]]:
        """Group boxes by similar heights, considering best rotation for each box"""
        tolerance = 5.0  # cm
        groups: Dict[float, List[Box]] = {}
        
        for box in sorted(self.boxes, key=lambda b: b.height, reverse=True):
            # Find the best height to use for this box (smallest that fits)
            best_height = box.height
            for rot in range(6):
                if rot < len(box.allowed_rotations) and box.allowed_rotations[rot]:
                    l, w, h = BoxRotation.get_dimensions(box.length, box.width, box.height, rot)
                    # Check if this rotation fits through door
                    if w <= self.container.door_width and h <= self.container.door_height:
                        if h < best_height:
                            best_height = h
            
            placed = False
            for height in groups:
                if abs(best_height - height) < tolerance:
                    groups[height].append(box)
                    placed = True
                    break
            if not placed:
                groups[best_height] = [box]
        
        return sorted(groups.items(), key=lambda x: -x[0])
    
    def _fill_layer(self, boxes: List[Box], z: float, start_order: int, existing_placements: List[PlacedBox] = None) -> List[PlacedBox]:
        """Fill a single layer with best rotation selection and collision detection.
        Respects delivery_order: high delivery_order placed at back (high X), low at front (near door).
        """
        if existing_placements is None:
            existing_placements = []
        
        placements = []
        load_order = start_order
        
        # Sort by delivery_order descending - last delivery first (at back)
        remaining_boxes = sorted(boxes, key=lambda b: (-b.delivery_order, -b.priority, -b.volume))
        
        # Use a more sophisticated 2D bin packing approach
        # Fill from BACK to FRONT (high X to low X) so first-delivery items end up near door
        x = self.container.length  # Start at back
        y = 0.0
        row_height = 0.0
        
        while remaining_boxes:
            best_box = None
            best_rot = 0
            best_dims = None
            best_score = float('inf')
            best_idx = -1
            
            # Find the best box and rotation for current position
            for idx, box in enumerate(remaining_boxes):
                for rot in range(6):
                    if rot >= len(box.allowed_rotations) or not box.allowed_rotations[rot]:
                        continue
                    
                    l, w, h = BoxRotation.get_dimensions(box.length, box.width, box.height, rot)
                    
                    # 🔒 FOUNDATION PRESERVATION RULE (SURGICAL FIX)
                    # At ground level (z == 0), prevent smaller boxes from blocking vertical columns for taller boxes
                    if z == 0 and remaining_boxes:
                        max_height_in_group = remaining_boxes[0].height  # tallest remaining (list is sorted)
                        if h < max_height_in_group:
                            actual_x = x - l
                            # Only skip if this position could support a taller box
                            if actual_x >= 0 and actual_x + max_height_in_group <= self.container.length:
                                continue
                    
                    # Check door entry
                    if w > self.container.door_width or h > self.container.door_height:
                        continue
                    
                    # Try current position (placing from back: x - l is the actual x position)
                    actual_x = x - l
                    if actual_x >= 0 and y + w <= self.container.width + 0.01:
                        # Score: prefer boxes that fit well (less wasted space)
                        waste = actual_x * 0.3 + abs(row_height - w) * 0.2
                        
                        # Prefer larger boxes first
                        waste -= (l * w) * 0.001
                        
                        if waste < best_score:
                            candidate = PlacedBox(
                                box=box, x=actual_x, y=y, z=z,
                                rotation=rot, length=l, width=w, height=h,
                                load_order=load_order
                            )
                            # Quick collision check
                            has_collision = False
                            for existing in placements:
                                if CollisionDetector.check_collision_fast(candidate, existing):
                                    has_collision = True
                                    break
                            if not has_collision:
                                for existing in existing_placements:
                                    if CollisionDetector.check_collision_fast(candidate, existing):
                                        has_collision = True
                                        break
                            if not has_collision:
                                best_score = waste
                                best_box = box
                                best_rot = rot
                                best_dims = (l, w, h)
                                best_idx = idx
            
            if best_box is not None:
                # Place the best box
                l, w, h = best_dims
                actual_x = x - l
                placements.append(PlacedBox(
                    box=best_box, x=actual_x, y=y, z=z,
                    rotation=best_rot, length=l, width=w, height=h,
                    load_order=load_order
                ))
                remaining_boxes.pop(best_idx)
                load_order += 1
                x = actual_x  # Move x position towards front
                row_height = max(row_height, w)
            else:
                # Move to next row (reset x to back of container)
                if row_height > 0:
                    x = self.container.length
                    y += row_height
                    row_height = 0
                    
                    if y >= self.container.width:
                        break  # Layer is full
                else:
                    # No progress possible, skip smallest box
                    if remaining_boxes:
                        remaining_boxes.pop()
                    else:
                        break
        
        return placements
    
    def _calculate_stats(self, placements: List[PlacedBox]) -> dict:
        """Calculate statistics"""
        if not placements:
            return {'utilization_pct': 0.0, 'placed_count': 0, 'failed_count': len(self.boxes)}
        
        container_volume = self.container.length * self.container.width * self.container.height
        used_volume = sum(p.volume for p in placements)
        
        return {
            'utilization_pct': round((used_volume / container_volume) * 100, 2),
            'placed_count': len(placements),
            'failed_count': len(self.boxes) - len(placements),
            'total_weight': sum(p.box.weight for p in placements),
            'is_valid': True,
            'validation_errors': []
        }


class LayerBuildingHeuristicRotated:
    """
    Layer-building heuristic with rotation support (Optimization #4).
    Tries all rotations when filling each layer for better space utilization.
    """
    
    def __init__(self, boxes: List[Box], container: ContainerSpace):
        self.boxes = boxes
        self.container = container
    
    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """Build layers using best rotation for each box"""
        # Group boxes by similar heights (considering rotations)
        height_groups = self._group_by_height_with_rotations()
        
        current_z = 0.0
        all_placements = []
        load_order = 0
        placed_box_ids = set()
        
        for target_height, group_boxes in height_groups:
            if current_z + target_height > self.container.height:
                break
            
            # Filter out already placed boxes
            available_boxes = [
                (box, rot) for box, rot in group_boxes 
                if id(box) not in placed_box_ids
            ]
            
            if not available_boxes:
                continue
            
            layer_placements = self._fill_layer_with_rotation(
                available_boxes, current_z, load_order, all_placements
            )
            
            if layer_placements:
                for p in layer_placements:
                    placed_box_ids.add(id(p.box))
                all_placements.extend(layer_placements)
                load_order += len(layer_placements)
                current_z += target_height
        
        # Use standard heuristic for remaining boxes
        remaining = [b for b in self.boxes if id(b) not in placed_box_ids]
        if remaining:
            solver = HeuristicSolver(remaining, self.container, existing_placements=all_placements)
            extra_placements, _ = solver.solve()
            
            for p in extra_placements:
                p.load_order = load_order
                load_order += 1
            
            all_placements.extend(extra_placements)
        
        return all_placements, self._calculate_stats(all_placements)
    
    def _group_by_height_with_rotations(self) -> List[Tuple[float, List[Tuple[Box, int]]]]:
        """Group boxes by height, considering all valid rotations"""
        tolerance = 5.0  # cm
        groups: Dict[float, List[Tuple[Box, int]]] = {}
        
        for box in self.boxes:
            # Get valid rotations for this box
            for rot_id in range(6):
                if rot_id >= len(box.allowed_rotations) or not box.allowed_rotations[rot_id]:
                    continue
                    
                l, w, h = BoxRotation.get_dimensions(box.length, box.width, box.height, rot_id)
                
                # Only use rotations that fit in container and through door
                if (l <= self.container.length and w <= self.container.width and 
                    h <= self.container.height and w <= self.container.door_width and 
                    h <= self.container.door_height):
                    
                    # Add to best matching height group
                    placed = False
                    for group_height in list(groups.keys()):
                        if abs(h - group_height) < tolerance:
                            groups[group_height].append((box, rot_id))
                            placed = True
                            break
                    if not placed:
                        groups[h] = [(box, rot_id)]
                    break  # Only add each box once to best height group
        
        # Sort by height descending (fill tallest layers first)
        return sorted(groups.items(), key=lambda x: -x[0])
    
    def _fill_layer_with_rotation(self, boxes_with_rot: List[Tuple[Box, int]], 
                                   z: float, start_order: int, existing_placements: List[PlacedBox] = None) -> List[PlacedBox]:
        """Fill a single layer using specified rotations with collision detection"""
        if existing_placements is None:
            existing_placements = []
            
        placements = []
        x = 0.0
        y = 0.0
        row_height = 0.0
        load_order = start_order
        
        # Sort by rotated volume descending for better packing
        sorted_boxes = sorted(
            boxes_with_rot,
            key=lambda br: br[0].volume,
            reverse=True
        )
        
        used_boxes = set()
        
        for box, rot_id in sorted_boxes:
            if id(box) in used_boxes:
                continue
            
            length, width, height = BoxRotation.get_dimensions(box.length, box.width, box.height, rot_id)
            
            placed_this_box = False
            
            # Try to place in current row
            if x + length <= self.container.length + 0.01 and y + width <= self.container.width + 0.01:
                candidate = PlacedBox(
                    box=box, x=x, y=y, z=z,
                    rotation=rot_id,
                    length=length, width=width, height=height,
                    load_order=load_order
                )
                # Check collisions
                has_collision = False
                for existing in placements:
                    if CollisionDetector.check_collision_fast(candidate, existing):
                        has_collision = True
                        break
                if not has_collision:
                    for existing in existing_placements:
                        if CollisionDetector.check_collision_fast(candidate, existing):
                            has_collision = True
                            break
                
                if not has_collision:
                    placements.append(candidate)
                    used_boxes.add(id(box))
                    load_order += 1
                    x += length
                    row_height = max(row_height, width)
                    placed_this_box = True
            
            if not placed_this_box:
                # Start new row
                x = 0
                y += row_height
                row_height = 0
                
                if y + width <= self.container.width + 0.01 and x + length <= self.container.length + 0.01:
                    candidate = PlacedBox(
                        box=box, x=x, y=y, z=z,
                        rotation=rot_id,
                        length=length, width=width, height=height,
                        load_order=load_order
                    )
                    has_collision = False
                    for existing in placements:
                        if CollisionDetector.check_collision_fast(candidate, existing):
                            has_collision = True
                            break
                    if not has_collision:
                        for existing in existing_placements:
                            if CollisionDetector.check_collision_fast(candidate, existing):
                                has_collision = True
                                break
                    
                    if not has_collision:
                        placements.append(candidate)
                        used_boxes.add(id(box))
                        load_order += 1
                        x += length
                        row_height = max(row_height, width)
        
        return placements
    
    def _calculate_stats(self, placements: List[PlacedBox]) -> dict:
        """Calculate statistics"""
        if not placements:
            return {'utilization_pct': 0.0, 'placed_count': 0, 'failed_count': len(self.boxes)}
        
        container_volume = self.container.length * self.container.width * self.container.height
        used_volume = sum(p.volume for p in placements)
        
        return {
            'utilization_pct': round((used_volume / container_volume) * 100, 2),
            'placed_count': len(placements),
            'failed_count': len(self.boxes) - len(placements),
            'total_weight': sum(p.box.weight for p in placements),
            'is_valid': True,
            'validation_errors': []
        }
