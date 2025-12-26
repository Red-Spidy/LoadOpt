from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class StopType(str, enum.Enum):
    """Stop type enumeration for multi-stop routes"""
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"
    CROSS_DOCK = "CROSS_DOCK"
    RETURN = "RETURN"


class UnloadStrategy(str, enum.Enum):
    """Unload strategy enumeration"""
    STRICT_LIFO = "STRICT_LIFO"  # Zero rehandling required
    MINIMAL_REHANDLING = "MINIMAL_REHANDLING"  # Configurable tolerance
    OPTIMIZED = "OPTIMIZED"  # Balance utilization vs rehandling


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    projects = relationship("Project", back_populates="owner")


class Project(Base):
    """Project model"""
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="projects")
    skus = relationship("SKU", back_populates="project", cascade="all, delete-orphan")
    containers = relationship("Container", back_populates="project", cascade="all, delete-orphan")
    plans = relationship("Plan", back_populates="project", cascade="all, delete-orphan")
    delivery_groups = relationship("DeliveryGroup", back_populates="project", cascade="all, delete-orphan")


class DeliveryGroup(Base):
    """Delivery Group - groups SKUs by delivery location (enhanced for multi-stop)"""
    __tablename__ = "delivery_groups"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, default="#3B82F6")  # Hex color for visualization
    delivery_order = Column(Integer, nullable=False)  # 1 = first delivery (load last, near door)

    # Enhanced multi-stop fields (all optional for backward compatibility)
    location_id = Column(String, nullable=True)  # External location identifier
    stop_type = Column(Enum(StopType), default=StopType.DELIVERY, nullable=True)

    # Time constraints (optional)
    earliest_time = Column(DateTime(timezone=True), nullable=True)
    latest_time = Column(DateTime(timezone=True), nullable=True)
    is_time_critical = Column(Boolean, default=False)

    # Operational metadata
    address = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    special_instructions = Column(String, nullable=True)

    # SLA and priority
    sla_priority = Column(Integer, default=1, nullable=True)  # 1-10 scale

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="delivery_groups")
    skus = relationship("SKU", back_populates="delivery_group")


class SKU(Base):
    """SKU (Stock Keeping Unit) model"""
    __tablename__ = "skus"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    delivery_group_id = Column(Integer, ForeignKey("delivery_groups.id"), nullable=True)
    name = Column(String, nullable=False)
    sku_code = Column(String)
    
    # Dimensions (in cm)
    length = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    
    # Weight (in kg)
    weight = Column(Float, nullable=False)
    
    # Quantity
    quantity = Column(Integer, nullable=False, default=1)
    
    # Rotation constraints (6 possible orientations)
    allowed_rotations = Column(JSON, default=[True, True, True, True, True, True])
    
    # Stacking constraints
    fragile = Column(Boolean, default=False)
    max_stack = Column(Integer, default=999)  # Max items that can be stacked on top
    stacking_group = Column(String)  # Items can only stack with same group
    load_bearing_capacity = Column(Float, nullable=True)  # Max weight this can support (kg)

    # Priority
    priority = Column(Integer, default=1)  # Higher = more important
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="skus")
    delivery_group = relationship("DeliveryGroup", back_populates="skus")


class Container(Base):
    """Container/Truck model"""
    __tablename__ = "containers"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    
    # Internal dimensions (in cm)
    inner_length = Column(Float, nullable=False)
    inner_width = Column(Float, nullable=False)
    inner_height = Column(Float, nullable=False)
    
    # Door dimensions (in cm)
    door_width = Column(Float, nullable=False)
    door_height = Column(Float, nullable=False)
    
    # Weight constraints (in kg)
    max_weight = Column(Float, nullable=False)
    
    # Axle limits (in kg)
    front_axle_limit = Column(Float)
    rear_axle_limit = Column(Float)
    
    # Obstacles
    obstacles = Column(JSON, default=[])  # List of {x, y, z, length, width, height}
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="containers")
    plans = relationship("Plan", back_populates="container")


class SolverMode(str, enum.Enum):
    """Solver mode enumeration"""
    FAST = "FAST"
    IMPROVED = "IMPROVED"
    OPTIMAL = "OPTIMAL"


class PlanStatus(str, enum.Enum):
    """Plan status enumeration"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class Plan(Base):
    """Loading plan model"""
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=False)
    name = Column(String, nullable=False)
    
    # Solver configuration
    solver_mode = Column(Enum(SolverMode), default=SolverMode.FAST)
    status = Column(Enum(PlanStatus), default=PlanStatus.PENDING)

    # Multi-stop configuration (optional for backward compatibility)
    use_advanced_multistop = Column(Boolean, default=False, nullable=True)
    unload_strategy = Column(Enum(UnloadStrategy), default=UnloadStrategy.MINIMAL_REHANDLING, nullable=True)
    max_rehandling_events = Column(Integer, default=5, nullable=True)
    rehandling_cost_per_event = Column(Float, default=10.0, nullable=True)  # Cost in minutes

    # Results
    utilization_pct = Column(Float, default=0.0)
    total_weight = Column(Float, default=0.0)
    items_placed = Column(Integer, default=0)
    items_total = Column(Integer, default=0)

    # Multi-stop results (optional)
    total_rehandling_events = Column(Integer, default=0, nullable=True)
    total_rehandling_cost = Column(Float, default=0.0, nullable=True)
    unload_plans = Column(JSON, nullable=True)  # Per-stop unload plans
    stop_metrics = Column(JSON, nullable=True)  # Per-stop metrics
    
    # Weight distribution
    weight_distribution = Column(JSON)  # {front_axle, rear_axle, center_of_gravity: {x, y, z}}
    
    # Validation
    is_valid = Column(Boolean, default=True)
    validation_errors = Column(JSON, default=[])
    
    # Job tracking
    job_id = Column(String)  # Celery task ID
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    project = relationship("Project", back_populates="plans")
    container = relationship("Container", back_populates="plans")
    placements = relationship("Placement", back_populates="plan", cascade="all, delete-orphan")


class Placement(Base):
    """Item placement in a plan"""
    __tablename__ = "placements"
    
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    
    # Instance tracking (for multiple quantities)
    instance_index = Column(Integer, nullable=False)
    
    # Position (in cm)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    z = Column(Float, nullable=False)
    
    # Rotation (0-5 for six orientations)
    rotation = Column(Integer, nullable=False)
    
    # Actual dimensions after rotation
    length = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    
    # Metadata
    load_order = Column(Integer)  # Sequence for loading
    delivery_order = Column(Integer, nullable=True)  # Which stop (for multi-stop routes)

    # Relationships
    plan = relationship("Plan", back_populates="placements")
    sku = relationship("SKU")
