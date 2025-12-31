from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


# ============= Multi-Stop Enums =============

class StopTypeEnum(str, Enum):
    """Stop type enumeration for multi-stop routes"""
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"
    CROSS_DOCK = "CROSS_DOCK"
    RETURN = "RETURN"


class UnloadStrategyEnum(str, Enum):
    """Unload strategy enumeration"""
    STRICT_LIFO = "STRICT_LIFO"
    MINIMAL_REHANDLING = "MINIMAL_REHANDLING"
    OPTIMIZED = "OPTIMIZED"


# ============= Auth Schemas =============

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class User(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============= SKU Schemas =============

class SKUBase(BaseModel):
    name: str
    sku_code: Optional[str] = None
    length: float = Field(gt=0, description="Length in cm")
    width: float = Field(gt=0, description="Width in cm")
    height: float = Field(gt=0, description="Height in cm")
    weight: float = Field(ge=0, description="Weight in kg")
    quantity: int = Field(ge=1, description="Number of items")
    allowed_rotations: List[bool] = [True, True, True, True, True, True]
    fragile: bool = False
    max_stack: int = Field(default=999, ge=0)
    stacking_group: Optional[str] = None
    load_bearing_capacity: Optional[float] = Field(None, ge=0, description="Max weight this can support in kg")
    priority: int = 1
    delivery_group_id: Optional[int] = None


class SKUCreate(SKUBase):
    project_id: int


class SKUUpdate(BaseModel):
    name: Optional[str] = None
    sku_code: Optional[str] = None
    length: Optional[float] = Field(None, gt=0)
    width: Optional[float] = Field(None, gt=0)
    height: Optional[float] = Field(None, gt=0)
    weight: Optional[float] = Field(None, ge=0)
    quantity: Optional[int] = Field(None, ge=1)
    allowed_rotations: Optional[List[bool]] = None
    fragile: Optional[bool] = None
    max_stack: Optional[int] = Field(None, ge=0)
    stacking_group: Optional[str] = None
    load_bearing_capacity: Optional[float] = Field(None, ge=0)
    priority: Optional[int] = None
    delivery_group_id: Optional[int] = None


class SKU(SKUBase):
    id: int
    project_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============= Delivery Group Schemas =============

class DeliveryGroupBase(BaseModel):
    name: str
    color: str = "#3B82F6"
    delivery_order: int = Field(ge=1, description="1 = first delivery (load last, near door)")

    # Enhanced multi-stop fields
    location_id: Optional[str] = None
    stop_type: Optional[StopTypeEnum] = StopTypeEnum.DELIVERY
    earliest_time: Optional[datetime] = None
    latest_time: Optional[datetime] = None
    is_time_critical: bool = False
    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    special_instructions: Optional[str] = None
    sla_priority: int = Field(default=1, ge=1, le=10, description="SLA priority 1-10")


class DeliveryGroupCreate(DeliveryGroupBase):
    project_id: int


class DeliveryGroupUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    delivery_order: Optional[int] = Field(None, ge=1)
    location_id: Optional[str] = None
    stop_type: Optional[StopTypeEnum] = None
    earliest_time: Optional[datetime] = None
    latest_time: Optional[datetime] = None
    is_time_critical: Optional[bool] = None
    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    special_instructions: Optional[str] = None
    sla_priority: Optional[int] = Field(None, ge=1, le=10)


class DeliveryGroup(DeliveryGroupBase):
    id: int
    project_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class DeliveryGroupWithSKUs(DeliveryGroup):
    skus: List[SKU] = []


# ============= Container Schemas =============

class Obstacle(BaseModel):
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float


class ContainerBase(BaseModel):
    name: str
    inner_length: float = Field(gt=0, description="Internal length in cm")
    inner_width: float = Field(gt=0, description="Internal width in cm")
    inner_height: float = Field(gt=0, description="Internal height in cm")
    door_width: float = Field(gt=0, description="Door width in cm")
    door_height: float = Field(gt=0, description="Door height in cm")
    max_weight: float = Field(gt=0, description="Max weight in kg")
    front_axle_limit: Optional[float] = Field(None, ge=0)
    rear_axle_limit: Optional[float] = Field(None, ge=0)
    obstacles: List[Obstacle] = []


class ContainerCreate(ContainerBase):
    project_id: int


class ContainerUpdate(BaseModel):
    name: Optional[str] = None
    inner_length: Optional[float] = Field(None, gt=0)
    inner_width: Optional[float] = Field(None, gt=0)
    inner_height: Optional[float] = Field(None, gt=0)
    door_width: Optional[float] = Field(None, gt=0)
    door_height: Optional[float] = Field(None, gt=0)
    max_weight: Optional[float] = Field(None, gt=0)
    front_axle_limit: Optional[float] = Field(None, ge=0)
    rear_axle_limit: Optional[float] = Field(None, ge=0)
    obstacles: Optional[List[Obstacle]] = None


class Container(ContainerBase):
    id: int
    project_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============= Placement Schemas =============

class PlacementBase(BaseModel):
    sku_id: int
    instance_index: int
    x: float
    y: float
    z: float
    rotation: int = Field(ge=0, le=5)
    length: float
    width: float
    height: float
    load_order: Optional[int] = None
    delivery_order: Optional[int] = None


class PlacementCreate(PlacementBase):
    plan_id: int


class Placement(PlacementBase):
    id: int
    plan_id: int

    class Config:
        from_attributes = True


# ============= Plan Schemas =============

class SolverModeEnum(str, Enum):
    FAST = "FAST"
    IMPROVED = "IMPROVED"
    OPTIMAL = "OPTIMAL"


class PlanStatusEnum(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class WeightDistribution(BaseModel):
    front_axle: float
    rear_axle: float
    center_of_gravity: dict  # {x, y, z}


class PlanBase(BaseModel):
    name: str
    container_id: int
    solver_mode: Optional[SolverModeEnum] = None  # Auto-detect based on stops

    # Multi-stop configuration (optional)
    use_advanced_multistop: Optional[bool] = None  # Auto-detect based on stops
    unload_strategy: Optional[UnloadStrategyEnum] = UnloadStrategyEnum.MINIMAL_REHANDLING
    max_rehandling_events: int = Field(default=5, ge=0)
    rehandling_cost_per_event: float = Field(default=10.0, ge=0.0, description="Cost per rehandling event in minutes")


class PlanCreate(PlanBase):
    project_id: int


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    solver_mode: Optional[SolverModeEnum] = None
    use_advanced_multistop: Optional[bool] = None
    unload_strategy: Optional[UnloadStrategyEnum] = None
    max_rehandling_events: Optional[int] = Field(None, ge=0)
    rehandling_cost_per_event: Optional[float] = Field(None, ge=0.0)


class Plan(PlanBase):
    id: int
    project_id: int
    status: PlanStatusEnum
    utilization_pct: float
    total_weight: float
    items_placed: int
    items_total: Optional[int] = None
    weight_distribution: Optional[dict] = None
    is_valid: bool
    validation_errors: List[str]
    job_id: Optional[str] = None

    # Multi-stop results (optional)
    total_rehandling_events: int = 0
    total_rehandling_cost: float = 0.0
    unload_plans: Optional[Dict] = None
    stop_metrics: Optional[Dict] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlanWithPlacements(Plan):
    placements: List[Placement] = []


# ============= Project Schemas =============

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class Project(ProjectBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectDetail(Project):
    skus: List[SKU] = []
    containers: List[Container] = []
    plans: List[Plan] = []
