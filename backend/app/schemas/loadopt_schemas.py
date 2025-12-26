"""
Pydantic schemas for LoadOpt API
Request and response models for TMS integration
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class UnitEnum(str, Enum):
    """Supported measurement units"""
    cm = "cm"
    m = "m"
    inch = "inch"
    kg = "kg"
    lb = "lb"


class AlgorithmEnum(str, Enum):
    """Available solver algorithms"""
    heuristic = "heuristic"
    layer = "layer"
    layer_rotated = "layer_rotated"
    optimal = "optimal"


class OptimizationLevel(str, Enum):
    """Optimization quality levels"""
    fast = "fast"
    balanced = "balanced"
    thorough = "thorough"


class UnloadSequence(str, Enum):
    """Unloading sequence strategy"""
    LIFO = "LIFO"  # Last In First Out
    FIFO = "FIFO"  # First In First Out
    ANY = "ANY"


# ========== REQUEST SCHEMAS ==========

class Dimensions(BaseModel):
    """Dimensional measurements"""
    length: float = Field(..., gt=0, description="Length dimension")
    width: float = Field(..., gt=0, description="Width dimension")
    height: float = Field(..., gt=0, description="Height dimension")
    unit: UnitEnum = Field(default=UnitEnum.cm, description="Unit of measurement")


class Weight(BaseModel):
    """Weight measurement"""
    value: float = Field(..., gt=0, description="Weight value")
    unit: UnitEnum = Field(default=UnitEnum.kg, description="Unit of measurement")


class Door(BaseModel):
    """Container door specifications"""
    width: float = Field(..., gt=0, description="Door width")
    height: float = Field(..., gt=0, description="Door height")


class AxleLimits(BaseModel):
    """Axle weight distribution limits"""
    front_axle_limit: Optional[float] = Field(None, description="Maximum front axle weight")
    rear_axle_limit: Optional[float] = Field(None, description="Maximum rear axle weight")
    unit: UnitEnum = Field(default=UnitEnum.kg, description="Unit of measurement")


class Container(BaseModel):
    """Container specifications"""
    type: Optional[str] = Field(None, description="Container type (e.g., 40FT_HC, 20FT)")
    dimensions: Dimensions = Field(..., description="Container dimensions")
    weight_limit: Weight = Field(..., description="Maximum payload weight")
    door: Optional[Door] = Field(None, description="Door dimensions")
    axle_limits: Optional[AxleLimits] = Field(None, description="Axle weight constraints")


class ItemConstraints(BaseModel):
    """Constraints for individual items"""
    stackable: bool = Field(default=True, description="Can other items be placed on top")
    fragile: bool = Field(default=False, description="Is the item fragile")
    max_stack_height: int = Field(default=10, ge=1, description="Maximum stacking count")
    allowed_rotations: List[bool] = Field(
        default=[True, True, False, False, False, False],
        min_items=6,
        max_items=6,
        description="Allowed rotations: [0°, 90°, 180°, 270°, flip-x, flip-y]"
    )
    keep_upright: bool = Field(default=True, description="Must remain in upright position")


class Delivery(BaseModel):
    """Delivery sequence information"""
    stop_number: int = Field(..., ge=1, description="Delivery stop number (1-based)")
    priority: int = Field(default=1, ge=1, description="Loading priority (1=highest)")
    unload_sequence: UnloadSequence = Field(default=UnloadSequence.LIFO, description="Unloading strategy")


class Item(BaseModel):
    """Individual item/SKU to be loaded"""
    sku: str = Field(..., description="Unique SKU identifier")
    description: Optional[str] = Field(None, description="Item description")
    dimensions: Dimensions = Field(..., description="Item dimensions")
    weight: Weight = Field(..., description="Item weight")
    quantity: int = Field(..., ge=1, description="Number of items")
    constraints: Optional[ItemConstraints] = Field(default_factory=ItemConstraints, description="Loading constraints")
    delivery: Delivery = Field(..., description="Delivery information")


class Objectives(BaseModel):
    """Optimization objectives"""
    maximize_utilization: bool = Field(default=True, description="Maximize space utilization")
    minimize_center_of_gravity_deviation: bool = Field(default=True, description="Balance weight distribution")
    respect_delivery_sequence: bool = Field(default=True, description="Ensure LIFO/FIFO compliance")
    prefer_stable_stacking: bool = Field(default=True, description="Prioritize stability")


class SolverOptions(BaseModel):
    """Solver configuration options"""
    algorithm: AlgorithmEnum = Field(default=AlgorithmEnum.heuristic, description="Optimization algorithm")
    max_execution_time_seconds: int = Field(default=30, ge=1, le=300, description="Solver timeout")
    optimization_level: OptimizationLevel = Field(default=OptimizationLevel.balanced, description="Quality vs speed")
    objectives: Optional[Objectives] = Field(default_factory=Objectives, description="Optimization goals")


class Metadata(BaseModel):
    """Request metadata for tracking"""
    tms_order_id: Optional[str] = Field(None, description="TMS order reference")
    client_id: Optional[str] = Field(None, description="Client identifier")
    timestamp: Optional[str] = Field(None, description="Request timestamp (ISO 8601)")


class LoadOptimizationRequest(BaseModel):
    """Complete load optimization request"""
    request_id: str = Field(..., description="Unique request identifier for tracing")
    container: Container = Field(..., description="Container specifications")
    items: List[Item] = Field(..., min_items=1, description="Items to be loaded")
    solver_options: Optional[SolverOptions] = Field(default_factory=SolverOptions, description="Solver configuration")
    metadata: Optional[Metadata] = Field(default_factory=Metadata, description="Additional metadata")

    @validator('items')
    def validate_items(cls, v):
        """Ensure at least one item exists"""
        if not v:
            raise ValueError("At least one item must be provided")
        return v


# ========== RESPONSE SCHEMAS ==========

class Position(BaseModel):
    """3D position coordinates"""
    x: float = Field(..., description="X coordinate (length)")
    y: float = Field(..., description="Y coordinate (width)")
    z: float = Field(..., description="Z coordinate (height)")
    unit: UnitEnum = Field(default=UnitEnum.cm, description="Unit of measurement")


class Placement(BaseModel):
    """Single item placement in container"""
    placement_id: int = Field(..., description="Unique placement identifier")
    sku: str = Field(..., description="SKU identifier")
    position: Position = Field(..., description="Bottom-front-left corner position")
    dimensions: Dimensions = Field(..., description="Item dimensions after rotation")
    rotation: int = Field(..., ge=0, le=5, description="Rotation index (0-5)")
    rotation_description: str = Field(..., description="Human-readable rotation")
    load_order: int = Field(..., description="Loading sequence number")
    delivery_stop: int = Field(..., description="Delivery stop number")
    weight: float = Field(..., description="Item weight")
    support_area_percentage: float = Field(..., ge=0, le=100, description="Bottom surface support %")


class Utilization(BaseModel):
    """Space and weight utilization metrics"""
    volume_used_cm3: float = Field(..., description="Volume occupied by items")
    volume_total_cm3: float = Field(..., description="Total container volume")
    volume_percentage: float = Field(..., ge=0, le=100, description="Volume utilization %")
    weight_used_kg: float = Field(..., description="Total weight of loaded items")
    weight_limit_kg: float = Field(..., description="Container weight limit")
    weight_percentage: float = Field(..., ge=0, le=100, description="Weight utilization %")


class CenterOfGravity(BaseModel):
    """Center of gravity coordinates"""
    x: float = Field(..., description="CG X coordinate")
    y: float = Field(..., description="CG Y coordinate")
    z: float = Field(..., description="CG Z coordinate")
    unit: UnitEnum = Field(default=UnitEnum.cm, description="Unit of measurement")
    deviation_from_center: float = Field(..., description="Distance from geometric center")


class AxleWeights(BaseModel):
    """Axle weight distribution"""
    front_axle_kg: float = Field(..., description="Weight on front axle")
    rear_axle_kg: float = Field(..., description="Weight on rear axle")
    within_limits: bool = Field(..., description="Are axle weights within limits?")


class Statistics(BaseModel):
    """Optimization statistics"""
    total_items_requested: int = Field(..., description="Total items in request")
    items_placed: int = Field(..., description="Successfully placed items")
    items_failed: int = Field(..., description="Failed to place items")
    utilization: Utilization = Field(..., description="Utilization metrics")
    center_of_gravity: Optional[CenterOfGravity] = Field(None, description="CG information")
    axle_weights: Optional[AxleWeights] = Field(None, description="Axle weight distribution")
    loading_time_estimate_minutes: Optional[int] = Field(None, description="Estimated loading time")


class Validation(BaseModel):
    """Validation results"""
    all_constraints_met: bool = Field(..., description="All constraints satisfied?")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")
    errors: List[str] = Field(default_factory=list, description="Error messages")


class OptimizationResult(BaseModel):
    """Optimization result data"""
    placements: List[Placement] = Field(..., description="All item placements")
    statistics: Statistics = Field(..., description="Optimization statistics")
    validation: Validation = Field(..., description="Validation results")
    visualization_url: Optional[str] = Field(None, description="URL for 3D visualization")


class SolverMetadata(BaseModel):
    """Solver execution metadata"""
    algorithm_used: str = Field(..., description="Algorithm that was used")
    optimization_level: str = Field(..., description="Optimization level applied")
    iterations: int = Field(..., description="Number of iterations performed")
    version: str = Field(..., description="Solver version")


class LoadOptimizationResponse(BaseModel):
    """Successful optimization response"""
    status: str = Field(default="success", description="Response status")
    request_id: str = Field(..., description="Original request ID")
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")
    result: OptimizationResult = Field(..., description="Optimization results")
    solver_metadata: SolverMetadata = Field(..., description="Solver metadata")


class ErrorDetail(BaseModel):
    """Error details"""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class ErrorResponse(BaseModel):
    """Error response"""
    status: str = Field(default="error", description="Response status")
    request_id: str = Field(..., description="Original request ID")
    error: ErrorDetail = Field(..., description="Error information")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current server time")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime")


class VersionResponse(BaseModel):
    """Version information response"""
    api_version: str = Field(..., description="API version")
    solver_version: str = Field(..., description="Solver version")
    supported_algorithms: List[str] = Field(..., description="Available algorithms")
    capabilities: Dict[str, bool] = Field(..., description="Feature flags")
