"""
Multi-Stop Data Models

Core data structures for multi-stop load planning, including stops, trips,
virtual SKUs, and unload plans.

These models extend the base domain models to support multi-stop scenarios.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Any
from enum import Enum, auto
import hashlib

from app.solver.utils import Box, ContainerSpace as Container, PlacedBox


class StopType(Enum):
    """Type of stop in the route"""
    DELIVERY = auto()       # Standard delivery stop
    PICKUP = auto()         # Pickup at intermediate location
    CROSS_DOCK = auto()     # Cross-dock transfer
    RETURN = auto()         # Return pickup


class UnloadStrategy(Enum):
    """Strategy for handling unloading"""
    STRICT_LIFO = auto()        # Strict Last-In-First-Out, zero rehandling
    MINIMAL_REHANDLING = auto()  # Allow minimal rehandling (configurable cost)
    OPTIMIZED = auto()          # Optimize for space utilization with bounded rehandling


@dataclass
class Stop:
    """
    Represents a single stop in a multi-stop delivery route.

    Each stop has a sequence number, location identifier, and the set of
    SKUs/quantities to be delivered or picked up at this location.

    Attributes:
        stop_number: Sequential order in the route (1 = first stop)
        location_id: Unique location identifier
        location_name: Human-readable location name
        sku_requirements: Dict mapping sku_id -> quantity to deliver/pickup
        stop_type: Type of stop (delivery, pickup, etc.)
        time_window_start: Optional earliest delivery time
        time_window_end: Optional latest delivery time
        is_time_critical: If True, prioritize accessibility
        service_time_minutes: Expected time to unload/load at this stop
        notes: Additional instructions or constraints
        original_delivery_order: Original delivery_order from database (preserved for box matching)
    """
    stop_number: int
    location_id: str
    location_name: str
    sku_requirements: Dict[int, int]  # sku_id -> quantity
    stop_type: StopType = StopType.DELIVERY
    time_window_start: Optional[float] = None
    time_window_end: Optional[float] = None
    is_time_critical: bool = False
    service_time_minutes: float = 30.0
    notes: str = ""
    original_delivery_order: Optional[int] = None  # Original delivery_order from database

    def __post_init__(self):
        """Validate stop parameters"""
        if self.stop_number < 1:
            raise ValueError(f"Stop number must be >= 1, got {self.stop_number}")
        if not self.sku_requirements:
            raise ValueError(f"Stop {self.stop_number} must have at least one SKU requirement")
        for sku_id, qty in self.sku_requirements.items():
            if qty <= 0:
                raise ValueError(f"SKU quantity must be positive: SKU {sku_id} = {qty}")

    @property
    def total_items(self) -> int:
        """Total number of items at this stop"""
        return sum(self.sku_requirements.values())

    @property
    def unique_skus(self) -> Set[int]:
        """Set of unique SKU IDs at this stop"""
        return set(self.sku_requirements.keys())

    def has_sku(self, sku_id: int) -> bool:
        """Check if this stop requires a specific SKU"""
        return sku_id in self.sku_requirements

    def get_quantity(self, sku_id: int) -> int:
        """Get quantity required for a SKU (0 if not at this stop)"""
        return self.sku_requirements.get(sku_id, 0)


@dataclass
class Trip:
    """
    Represents a complete multi-stop trip with ordered sequence of stops.

    The trip defines the route, constraints, and overall logistics requirements.

    Attributes:
        trip_id: Unique trip identifier
        stops: Ordered list of stops (stop 1 = first delivery)
        container: The container being loaded
        unload_strategy: How to handle unloading constraints
        max_rehandling_events: Maximum total rehandling events allowed
        rehandling_cost_per_item: Cost penalty per rehandled item
        require_stable_load: If True, enforce additional stability rules
        driver_instructions: Special instructions for the driver
    """
    trip_id: str
    stops: List[Stop]
    container: Container
    unload_strategy: UnloadStrategy = UnloadStrategy.MINIMAL_REHANDLING
    max_rehandling_events: int = 5
    rehandling_cost_per_item: float = 10.0
    require_stable_load: bool = True
    driver_instructions: str = ""

    def __post_init__(self):
        """Validate trip and renumber stops if needed"""
        if not self.stops:
            raise ValueError("Trip must have at least one stop")

        # Ensure stops are numbered sequentially starting from 1
        for i, stop in enumerate(self.stops, start=1):
            if stop.stop_number != i:
                stop.stop_number = i

        # Sort by stop number to ensure order
        self.stops.sort(key=lambda s: s.stop_number)

    @property
    def num_stops(self) -> int:
        """Number of stops in this trip"""
        return len(self.stops)

    @property
    def total_items(self) -> int:
        """Total items across all stops"""
        return sum(stop.total_items for stop in self.stops)

    @property
    def all_sku_ids(self) -> Set[int]:
        """All unique SKU IDs across all stops"""
        all_skus = set()
        for stop in self.stops:
            all_skus.update(stop.unique_skus)
        return all_skus

    def get_stop(self, stop_number: int) -> Optional[Stop]:
        """Get stop by number"""
        for stop in self.stops:
            if stop.stop_number == stop_number:
                return stop
        return None

    def get_sku_stop_map(self) -> Dict[int, List[int]]:
        """
        Get mapping of SKU ID to list of stop numbers where it appears.

        Returns:
            Dict mapping sku_id -> [stop_numbers] ordered by stop sequence
        """
        sku_map: Dict[int, List[int]] = {}
        for stop in self.stops:
            for sku_id in stop.unique_skus:
                if sku_id not in sku_map:
                    sku_map[sku_id] = []
                sku_map[sku_id].append(stop.stop_number)
        return sku_map


@dataclass
class VirtualSKU:
    """
    Virtual SKU representing a portion of a real SKU assigned to a specific stop.

    When a SKU appears at multiple stops, we create virtual SKUs to track
    which boxes go to which stops. This enables proper placement and unload planning.

    Example:
        Real SKU #42 appears at stops 1 (qty=5) and 3 (qty=3)
        We create:
        - VirtualSKU(original_sku_id=42, stop_number=1, quantity=5)
        - VirtualSKU(original_sku_id=42, stop_number=3, quantity=3)

    Attributes:
        virtual_id: Unique ID for this virtual SKU
        original_sku_id: The real SKU ID this is derived from
        stop_number: Which stop this portion is assigned to
        quantity: How many boxes of this SKU go to this stop
        base_box: Template box with dimensions/properties
        priority_score: Computed priority for load ordering
    """
    virtual_id: str
    original_sku_id: int
    stop_number: int
    quantity: int
    base_box: Box
    priority_score: float = 0.0

    def __post_init__(self):
        """Generate virtual ID if not provided"""
        if not self.virtual_id:
            self.virtual_id = f"V{self.original_sku_id}_S{self.stop_number}"

    @property
    def is_early_stop(self) -> bool:
        """True if this is for stop 1"""
        return self.stop_number == 1

    @property
    def total_volume(self) -> float:
        """Total volume of all boxes in this virtual SKU"""
        return self.base_box.volume * self.quantity

    @property
    def total_weight(self) -> float:
        """Total weight of all boxes in this virtual SKU"""
        return self.base_box.weight * self.quantity

    def __hash__(self):
        return hash(self.virtual_id)

    def __eq__(self, other):
        if not isinstance(other, VirtualSKU):
            return False
        return self.virtual_id == other.virtual_id


@dataclass
class RehandlingEvent:
    """
    Represents a single rehandling operation at a stop.

    Rehandling occurs when a box for a later stop must be temporarily
    removed to access boxes for the current stop.

    Attributes:
        stop_number: Stop where rehandling occurs
        box_id: ID of box being rehandled
        original_sku_id: SKU of the rehandled box
        destination_stop: Where the rehandled box is actually going
        reason: Why this rehandling was necessary
        estimated_time_seconds: Expected time cost
    """
    stop_number: int
    box_id: int
    original_sku_id: int
    destination_stop: int
    reason: str
    estimated_time_seconds: float = 60.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stop_number': self.stop_number,
            'box_id': self.box_id,
            'original_sku_id': self.original_sku_id,
            'destination_stop': self.destination_stop,
            'reason': self.reason,
            'estimated_time_seconds': self.estimated_time_seconds
        }


@dataclass
class UnloadPlan:
    """
    Plan for unloading boxes at a specific stop.

    Defines which boxes to remove, in what order, and any rehandling required.

    Attributes:
        stop_number: Which stop this plan is for
        boxes_to_unload: List of PlacedBoxes to remove (in order)
        rehandling_events: List of rehandling operations needed
        is_feasible: Whether unload can be performed as planned
        accessibility_score: 0-100, how easy it is to access these boxes
        warnings: List of warnings or concerns
    """
    stop_number: int
    boxes_to_unload: List[PlacedBox]
    rehandling_events: List[RehandlingEvent] = field(default_factory=list)
    is_feasible: bool = True
    accessibility_score: float = 100.0
    warnings: List[str] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        """Number of boxes to unload"""
        return len(self.boxes_to_unload)

    @property
    def rehandling_count(self) -> int:
        """Number of rehandling events"""
        return len(self.rehandling_events)

    @property
    def total_weight(self) -> float:
        """Total weight being unloaded"""
        return sum(b.box.weight for b in self.boxes_to_unload)

    @property
    def estimated_time_minutes(self) -> float:
        """Estimated unload time including rehandling"""
        base_time = self.total_items * 1.0  # 1 minute per box
        rehandling_time = sum(e.estimated_time_seconds for e in self.rehandling_events) / 60.0
        return base_time + rehandling_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stop_number': self.stop_number,
            'boxes_to_unload': [
                {
                    'box_id': b.box.id,
                    'sku_id': b.box.sku_id,
                    'position': {'x': b.x, 'y': b.y, 'z': b.z},
                    'weight': b.box.weight
                } for b in self.boxes_to_unload
            ],
            'rehandling_events': [e.to_dict() for e in self.rehandling_events],
            'is_feasible': self.is_feasible,
            'accessibility_score': round(self.accessibility_score, 2),
            'total_items': self.total_items,
            'rehandling_count': self.rehandling_count,
            'estimated_time_minutes': round(self.estimated_time_minutes, 2),
            'warnings': self.warnings
        }


@dataclass
class StopMetrics:
    """
    Metrics and analytics for a specific stop's portion of the load.

    Attributes:
        stop_number: Which stop these metrics are for
        items_loaded: Number of boxes for this stop
        volume_used: Volume occupied by this stop's boxes
        weight_loaded: Weight of this stop's boxes
        utilization_pct: Percentage of container used by this stop
        avg_accessibility: Average accessibility score for boxes
        fragile_count: Number of fragile boxes for this stop
    """
    stop_number: int
    items_loaded: int = 0
    volume_used: float = 0.0
    weight_loaded: float = 0.0
    utilization_pct: float = 0.0
    avg_accessibility: float = 0.0
    fragile_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stop_number': self.stop_number,
            'items_loaded': self.items_loaded,
            'volume_used': round(self.volume_used, 2),
            'weight_loaded': round(self.weight_loaded, 2),
            'utilization_pct': round(self.utilization_pct, 2),
            'avg_accessibility': round(self.avg_accessibility, 2),
            'fragile_count': self.fragile_count
        }


@dataclass
class MultiStopLoadPlan:
    """
    Complete load plan for a multi-stop trip.

    Contains all placements, unload plans for each stop, rehandling analysis,
    and validation results.

    This is the primary output of the multi-stop optimizer.

    Attributes:
        trip: The trip this plan is for
        placements: All box placements
        unload_plans: Unload plan for each stop
        stop_metrics: Metrics for each stop
        total_rehandling_events: Total rehandling operations
        total_rehandling_cost: Total cost of rehandling
        overall_utilization_pct: Container utilization
        is_valid: Whether plan passes all validations
        validation_errors: List of validation errors
        validation_warnings: List of warnings
        solve_time_seconds: Time to generate this plan
        solver_metadata: Additional solver information
    """
    trip: Trip
    placements: List[PlacedBox]
    unload_plans: Dict[int, UnloadPlan]  # stop_number -> UnloadPlan
    stop_metrics: Dict[int, StopMetrics]  # stop_number -> StopMetrics
    total_rehandling_events: int = 0
    total_rehandling_cost: float = 0.0
    overall_utilization_pct: float = 0.0
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    solve_time_seconds: float = 0.0
    solver_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Calculate aggregate metrics"""
        self.total_rehandling_events = sum(
            plan.rehandling_count for plan in self.unload_plans.values()
        )

        if self.placements and self.trip.container:
            used_volume = sum(p.volume for p in self.placements)
            self.overall_utilization_pct = (used_volume / self.trip.container.volume) * 100

        self.total_rehandling_cost = (
            self.total_rehandling_events * self.trip.rehandling_cost_per_item
        )

    def get_boxes_for_stop(self, stop_number: int) -> List[PlacedBox]:
        """Get all placed boxes destined for a specific stop"""
        return [
            p for p in self.placements
            if p.box.delivery_order == stop_number
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            'trip_id': self.trip.trip_id,
            'placements': [p.to_dict() for p in self.placements],
            'unload_plans': {
                stop_num: plan.to_dict()
                for stop_num, plan in self.unload_plans.items()
            },
            'stop_metrics': {
                stop_num: metrics.to_dict()
                for stop_num, metrics in self.stop_metrics.items()
            },
            'total_rehandling_events': self.total_rehandling_events,
            'total_rehandling_cost': round(self.total_rehandling_cost, 2),
            'overall_utilization_pct': round(self.overall_utilization_pct, 2),
            'is_valid': self.is_valid,
            'validation_errors': self.validation_errors,
            'validation_warnings': self.validation_warnings,
            'solve_time_seconds': round(self.solve_time_seconds, 3),
            'solver_metadata': self.solver_metadata
        }
