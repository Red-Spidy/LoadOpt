from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass, field
import numpy as np
from functools import lru_cache


@dataclass
class Box:
    """Represents a box/SKU instance"""
    id: int
    sku_id: int
    instance_index: int
    length: float
    width: float
    height: float
    weight: float
    fragile: bool
    max_stack: int
    stacking_group: Optional[str]
    priority: int
    allowed_rotations: List[bool]
    delivery_order: int = 999  # Lower = first delivery = load last (near door)
    name: Optional[str] = None
    color: Optional[str] = None
    load_bearing_capacity: Optional[float] = None
    
    @property
    def volume(self) -> float:
        """Calculate box volume - cached property"""
        return self.length * self.width * self.height
    
    def get_unique_rotations(self) -> List[int]:
        """
        Get list of unique allowed rotations for this box.
        Filters out redundant rotations for boxes with equal dimensions.
        
        Returns:
            List of rotation indices (0-5) that are allowed and unique
        """
        if not self.allowed_rotations or len(self.allowed_rotations) < 6:
            return [0]  # Only original orientation
        
        unique_rotations = []
        seen_dimensions = set()
        
        for rotation_idx in range(6):
            if not self.allowed_rotations[rotation_idx]:
                continue
            
            dims = self.get_rotated_dimensions(rotation_idx)
            # Round to avoid floating point comparison issues
            dims_tuple = tuple(round(d, 2) for d in dims)
            
            if dims_tuple not in seen_dimensions:
                seen_dimensions.add(dims_tuple)
                unique_rotations.append(rotation_idx)
        
        return unique_rotations if unique_rotations else [0]
    
    def get_rotated_dimensions(self, rotation: int) -> Tuple[float, float, float]:
        """
        Get box dimensions after applying rotation.
        
        Rotations:
        0: Original (L, W, H)
        1: 90° rotation (W, L, H)
        2: 180° rotation (L, W, H) - same as 0
        3: 270° rotation (W, L, H) - same as 1
        4: Flip on side (H, W, L)
        5: Flip end (L, H, W)
        
        Args:
            rotation: Rotation index (0-5)
            
        Returns:
            Tuple of (length, width, height) after rotation
        """
        if rotation == 0 or rotation == 2:
            return (self.length, self.width, self.height)
        elif rotation == 1 or rotation == 3:
            return (self.width, self.length, self.height)
        elif rotation == 4:
            return (self.height, self.width, self.length)
        elif rotation == 5:
            return (self.length, self.height, self.width)
        else:
            return (self.length, self.width, self.height)
    
    def __hash__(self):
        return hash((self.id, self.sku_id, self.instance_index))


@dataclass
class ContainerSpace:
    """Represents the container/truck space"""
    length: float
    width: float
    height: float
    max_weight: float
    door_width: float
    door_height: float
    front_axle_limit: Optional[float] = None
    rear_axle_limit: Optional[float] = None
    obstacles: List[dict] = None
    
    @property
    def volume(self) -> float:
        """Calculate container volume"""
        return self.length * self.width * self.height

    def can_enter_door(self, width: float, height: float) -> bool:
        """Check if dimensions can pass through door"""
        return width <= self.door_width and height <= self.door_height
    
    def contains_point(self, x: float, y: float, z: float) -> bool:
        """Check if a point is within container bounds"""
        return (0 <= x <= self.length and 
                0 <= y <= self.width and 
                0 <= z <= self.height)


@dataclass
class PlacementPoint:
    """Represents a potential placement point (Extreme Point)"""
    x: float
    y: float
    z: float
    available_length: float
    available_width: float
    available_height: float
    source: Optional[str] = None  # Optional debug info about where this point came from
    
    def __hash__(self):
        return hash((round(self.x, 2), round(self.y, 2), round(self.z, 2)))
    
    def __eq__(self, other):
        if not isinstance(other, PlacementPoint):
            return False
        return (abs(self.x - other.x) < 0.01 and 
                abs(self.y - other.y) < 0.01 and 
                abs(self.z - other.z) < 0.01)
    
    def quantize(self, resolution: float = 1.0):
        """Return a quantized copy of this point to prevent floating-point duplicates"""
        return PlacementPoint(
            x=round(self.x / resolution) * resolution,
            y=round(self.y / resolution) * resolution,
            z=round(self.z / resolution) * resolution,
            available_length=self.available_length,
            available_width=self.available_width,
            available_height=self.available_height,
            source=self.source
        )


@dataclass
class PlacedBox:
    """Represents a placed box"""
    box: Box
    x: float
    y: float
    z: float
    rotation: int  # 0-5
    length: float  # After rotation
    width: float  # After rotation
    height: float  # After rotation
    load_order: int
    
    @property
    def volume(self) -> float:
        return self.length * self.width * self.height
    
    @property
    def base_area(self) -> float:
        """Calculate base area (length × width)"""
        return self.length * self.width
    
    @property
    def max_x(self) -> float:
        return self.x + self.length
    
    @property
    def max_y(self) -> float:
        return self.y + self.width
    
    @property
    def max_z(self) -> float:
        return self.z + self.height
    
    @property
    def center(self) -> Tuple[float, float, float]:
        return (self.x + self.length/2, self.y + self.width/2, self.z + self.height/2)
    
    def overlaps_xy(self, other: 'PlacedBox') -> bool:
        """Check if this box overlaps with another in XY plane"""
        return not (
            self.max_x <= other.x or self.x >= other.max_x or
            self.max_y <= other.y or self.y >= other.max_y
        )
    
    def get_xy_overlap_area(self, other: 'PlacedBox') -> float:
        """Calculate the overlapping area in XY plane"""
        # Calculate overlap dimensions
        overlap_x_min = max(self.x, other.x)
        overlap_x_max = min(self.max_x, other.max_x)
        overlap_y_min = max(self.y, other.y)
        overlap_y_max = min(self.max_y, other.max_y)
        
        # Check if there's actual overlap
        if overlap_x_max <= overlap_x_min or overlap_y_max <= overlap_y_min:
            return 0.0
        
        overlap_length = overlap_x_max - overlap_x_min
        overlap_width = overlap_y_max - overlap_y_min
        
        return overlap_length * overlap_width
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'box_id': self.box.id,
            'sku_id': self.box.sku_id,
            'name': self.box.name if hasattr(self.box, 'name') and self.box.name else f"SKU-{self.box.sku_id}",
            'position': {
                'x': round(self.x, 2),
                'y': round(self.y, 2),
                'z': round(self.z, 2)
            },
            'dimensions': {
                'length': round(self.length, 2),
                'width': round(self.width, 2),
                'height': round(self.height, 2)
            },
            'rotation': self.rotation,
            'load_order': self.load_order,
            'weight': round(self.box.weight, 2),
            'delivery_order': self.box.delivery_order
        }


class SpatialGrid:
    """3D spatial grid for fast collision detection - O(1) lookups instead of O(n)"""
    
    def __init__(self, length: float, width: float, height: float, cell_size: float = 50.0):
        self.cell_size = cell_size
        self.grid_x = int(np.ceil(length / cell_size)) + 1
        self.grid_y = int(np.ceil(width / cell_size)) + 1
        self.grid_z = int(np.ceil(height / cell_size)) + 1
        self.cells: Dict[Tuple[int, int, int], Set[int]] = {}
        self.boxes: Dict[int, PlacedBox] = {}
        self._box_cells: Dict[int, Set[Tuple[int, int, int]]] = {}
    
    def _get_cell_range(self, placed: PlacedBox) -> List[Tuple[int, int, int]]:
        """Get all cells that a box occupies"""
        cells = []
        min_x = int(placed.x / self.cell_size)
        max_x = int(placed.max_x / self.cell_size)
        min_y = int(placed.y / self.cell_size)
        max_y = int(placed.max_y / self.cell_size)
        min_z = int(placed.z / self.cell_size)
        max_z = int(placed.max_z / self.cell_size)
        
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                for z in range(min_z, max_z + 1):
                    cells.append((x, y, z))
        return cells
    
    def add_box(self, placed: PlacedBox) -> None:
        """Add a box to the spatial grid"""
        box_id = id(placed)
        self.boxes[box_id] = placed
        cells = self._get_cell_range(placed)
        self._box_cells[box_id] = set(cells)
        
        for cell in cells:
            if cell not in self.cells:
                self.cells[cell] = set()
            self.cells[cell].add(box_id)
    
    def remove_box(self, placed: PlacedBox) -> None:
        """Remove a box from the spatial grid"""
        box_id = id(placed)
        if box_id in self._box_cells:
            for cell in self._box_cells[box_id]:
                if cell in self.cells:
                    self.cells[cell].discard(box_id)
            del self._box_cells[box_id]
            del self.boxes[box_id]
    
    def get_potential_collisions(self, placed: PlacedBox) -> List[PlacedBox]:
        """Get boxes that could potentially collide with the given box"""
        cells = self._get_cell_range(placed)
        potential_ids = set()
        
        for cell in cells:
            if cell in self.cells:
                potential_ids.update(self.cells[cell])
        
        return [self.boxes[bid] for bid in potential_ids if bid in self.boxes]
    
    def check_collision(self, placed: PlacedBox) -> bool:
        """Check if a box collides with any existing box - O(1) average case"""
        for existing in self.get_potential_collisions(placed):
            if CollisionDetector.check_collision_fast(placed, existing):
                return True
        return False
    
    def get_boxes_below(self, placed: PlacedBox, tolerance: float = 0.1) -> List[PlacedBox]:
        """Get boxes directly below the given box"""
        result = []
        for existing in self.get_potential_collisions(placed):
            if abs(existing.max_z - placed.z) < tolerance:
                # Check XY overlap
                if (existing.x < placed.max_x and existing.max_x > placed.x and
                    existing.y < placed.max_y and existing.max_y > placed.y):
                    result.append(existing)
        return result


class BoxRotation:
    """Handle box rotations (6 possible orientations) with caching"""
    
    _rotation_cache: Dict[Tuple[float, float, float, int], Tuple[float, float, float]] = {}
    
    @staticmethod
    def get_rotations(box, container=None) -> List[Tuple[float, float, float]]:
        """Get all 6 rotation dimension tuples for a box"""
        l, w, h = box.length, box.width, box.height
        all_rotations = [
            (l, w, h),   # 0
            (l, h, w),   # 1
            (w, l, h),   # 2
            (w, h, l),   # 3
            (h, l, w),   # 4
            (h, w, l),   # 5
        ]
        # Filter by allowed rotations
        result = []
        for i, dims in enumerate(all_rotations):
            if i < len(box.allowed_rotations) and box.allowed_rotations[i]:
                result.append(dims)
        return result if result else [all_rotations[0]]
    
    @staticmethod
    def get_dimensions(length: float, width: float, height: float, rotation: int) -> Tuple[float, float, float]:
        """Get dimensions after rotation - with caching"""
        key = (length, width, height, rotation)
        if key in BoxRotation._rotation_cache:
            return BoxRotation._rotation_cache[key]
        
        rotations = [
            (length, width, height),   # 0
            (length, height, width),   # 1
            (width, length, height),   # 2
            (width, height, length),   # 3
            (height, length, width),   # 4
            (height, width, length),   # 5
        ]
        result = rotations[rotation]
        BoxRotation._rotation_cache[key] = result
        return result
    
    @staticmethod
    def get_allowed_rotations(box: Box) -> List[int]:
        """Get list of allowed rotation indices"""
        return [i for i, allowed in enumerate(box.allowed_rotations) if allowed]
    
    @staticmethod
    def get_unique_rotations(box: Box) -> List[int]:
        """Get unique rotations (avoiding symmetric duplicates for cubes/rectangular prisms)"""
        allowed = BoxRotation.get_allowed_rotations(box)
        if not allowed:
            return [0]
        
        # Track unique dimension combinations
        seen = set()
        unique = []
        for rot in allowed:
            dims = BoxRotation.get_dimensions(box.length, box.width, box.height, rot)
            # Sort dims to identify symmetric rotations
            key = tuple(sorted(dims))
            if key not in seen:
                seen.add(key)
                unique.append(rot)
        return unique if unique else [0]


class CollisionDetector:
    """Check for collisions between boxes - optimized"""
    
    @staticmethod
    def check_collision_fast(box1: PlacedBox, box2: PlacedBox, tolerance: float = 0.01) -> bool:
        """Fast AABB collision check using cached properties with tolerance for floating point errors"""
        # Two boxes collide if they overlap in ALL three dimensions
        # With tolerance: boxes must be separated by at least 'tolerance' to not collide
        if box1.max_x <= box2.x + tolerance or box2.max_x <= box1.x + tolerance:
            return False  # Separated on X-axis
        if box1.max_y <= box2.y + tolerance or box2.max_y <= box1.y + tolerance:
            return False  # Separated on Y-axis
        if box1.max_z <= box2.z + tolerance or box2.max_z <= box1.z + tolerance:
            return False  # Separated on Z-axis
        return True  # Overlapping in all three dimensions = collision
    
    @staticmethod
    def check_collision(box1: PlacedBox, box2: PlacedBox) -> bool:
        """Check if two boxes collide (legacy interface)"""
        return CollisionDetector.check_collision_fast(box1, box2)
    
    @staticmethod
    def check_container_fit(placed: PlacedBox, container: ContainerSpace, tolerance: float = 0.01) -> bool:
        """Check if box fits within container"""
        return (placed.x >= -tolerance and 
                placed.y >= -tolerance and 
                placed.z >= -tolerance and
                placed.max_x <= container.length + tolerance and
                placed.max_y <= container.width + tolerance and
                placed.max_z <= container.height + tolerance)
    
    @staticmethod
    def check_door_entry(placed: PlacedBox, container: ContainerSpace) -> bool:
        """Check if box can enter through door"""
        # Box must fit through door at entry (x=0 plane)
        return (placed.width <= container.door_width and 
                placed.height <= container.door_height)


class StackingValidator:
    """Validate stacking rules - optimized"""
    
    @staticmethod
    def check_support(box: PlacedBox, placements: List[PlacedBox], tolerance: float = 0.1) -> bool:
        """Check if box has adequate support below it"""
        if box.z < tolerance:  # On ground
            return True
        
        # Find boxes directly below using vectorized operations
        support_area = 0.0
        box_area = box.length * box.width
        
        for placed in placements:
            if placed is box:
                continue
            
            # Check if placed box is directly below (tops must touch bottoms)
            if abs(placed.max_z - box.z) < tolerance:
                # Calculate overlapping area
                overlap_x = max(0, min(box.max_x, placed.max_x) - max(box.x, placed.x))
                overlap_y = max(0, min(box.max_y, placed.max_y) - max(box.y, placed.y))
                support_area += overlap_x * overlap_y
                
                # Early exit if we have enough support (50% minimum - lowered for better packing)
                if support_area >= 0.5 * box_area:
                    return True
        
        # If no support found and box is elevated, reject it
        if support_area == 0 and box.z > tolerance:
            return False

        return support_area >= 0.4 * box_area
    
    @staticmethod
    def check_support_with_grid(box: PlacedBox, grid: SpatialGrid, tolerance: float = 0.1) -> bool:
        """Check support using spatial grid for faster lookups"""
        if box.z < tolerance:
            return True
        
        below_boxes = grid.get_boxes_below(box, tolerance)
        if not below_boxes:
            return False
        
        support_area = 0.0
        box_area = box.length * box.width
        
        for placed in below_boxes:
            overlap_x = max(0, min(box.max_x, placed.max_x) - max(box.x, placed.x))
            overlap_y = max(0, min(box.max_y, placed.max_y) - max(box.y, placed.y))
            support_area += overlap_x * overlap_y

            if support_area >= 0.4 * box_area:
                return True

        return support_area >= 0.4 * box_area
    
    @staticmethod
    def check_stacking_rules(box: PlacedBox, below_boxes: List[PlacedBox]) -> bool:
        """Check stacking compatibility

        Respects max_stack limits instead of blanket fragile rejection.
        If max_stack > 0, items can be placed on top (up to the limit).
        """
        for below in below_boxes:
            # Check max_stack limit (0 = nothing can be stacked on top)
            if below.box.max_stack == 0:
                return False

            # Check stacking group compatibility
            if (box.box.stacking_group and below.box.stacking_group and
                box.box.stacking_group != below.box.stacking_group):
                return False

        return True
    
    @staticmethod
    def count_boxes_above(box: PlacedBox, placements: List[PlacedBox], tolerance: float = 0.1) -> int:
        """Count how many boxes are stacked on top"""
        count = 0
        current_height = box.max_z
        
        for _ in range(len(placements)):  # Max iterations to prevent infinite loop
            found = False
            for placed in placements:
                if abs(placed.z - current_height) < tolerance:
                    if (placed.x < box.max_x and placed.max_x > box.x and
                        placed.y < box.max_y and placed.max_y > box.y):
                        count += 1
                        current_height = placed.max_z
                        found = True
                        break
            if not found:
                break
        
        return count


class WeightDistribution:
    """Calculate weight distribution and center of gravity - optimized with numpy"""
    
    @staticmethod
    def calculate_cog(placements: List[PlacedBox]) -> Tuple[float, float, float]:
        """Calculate center of gravity using numpy for vectorization"""
        if not placements:
            return (0.0, 0.0, 0.0)
        
        n = len(placements)
        weights = np.zeros(n)
        centers_x = np.zeros(n)
        centers_y = np.zeros(n)
        centers_z = np.zeros(n)
        
        for i, p in enumerate(placements):
            weights[i] = p.box.weight
            centers_x[i] = p.x + p.length / 2
            centers_y[i] = p.y + p.width / 2
            centers_z[i] = p.z + p.height / 2
        
        total_weight = weights.sum()
        if total_weight == 0:
            return (0.0, 0.0, 0.0)
        
        cog_x = np.dot(weights, centers_x) / total_weight
        cog_y = np.dot(weights, centers_y) / total_weight
        cog_z = np.dot(weights, centers_z) / total_weight
        
        return (float(cog_x), float(cog_y), float(cog_z))
    
    @staticmethod
    def calculate_axle_loads(placements: List[PlacedBox], container_length: float) -> Tuple[float, float]:
        """Calculate front and rear axle loads using numpy"""
        if not placements:
            return (0.0, 0.0)
        
        front_axle_pos = 0.3 * container_length
        rear_axle_pos = 0.8 * container_length
        wheelbase = rear_axle_pos - front_axle_pos
        
        n = len(placements)
        weights = np.zeros(n)
        center_x = np.zeros(n)
        
        for i, p in enumerate(placements):
            weights[i] = p.box.weight
            center_x[i] = p.x + p.length / 2
        
        total_weight = weights.sum()
        total_moment = np.dot(weights, center_x - front_axle_pos)
        
        rear_load = total_moment / wheelbase
        front_load = total_weight - rear_load
        
        return (max(0.0, float(front_load)), max(0.0, float(rear_load)))
