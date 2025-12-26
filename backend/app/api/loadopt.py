"""
LoadOpt API Routes
REST endpoints for load optimization and TMS integration
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import time
from datetime import datetime

from app.schemas.loadopt_schemas import (
    LoadOptimizationRequest,
    LoadOptimizationResponse,
    ErrorResponse,
    HealthResponse,
    VersionResponse,
    Placement,
    Position,
    Dimensions as DimensionsSchema,
    Utilization,
    CenterOfGravity,
    AxleWeights,
    Statistics,
    Validation,
    OptimizationResult,
    SolverMetadata,
    UnitEnum
)
from app.solver.heuristic import HeuristicSolver, LayerBuildingHeuristic, LayerBuildingHeuristicRotated
from app.solver.utils import Box, ContainerSpace

router = APIRouter()

# Service start time for uptime tracking
SERVICE_START_TIME = time.time()
API_VERSION = "1.0.0"
SOLVER_VERSION = "1.0.0"


def convert_request_to_solver_objects(request: LoadOptimizationRequest):
    """
    Convert API request objects to solver objects
    
    Args:
        request: LoadOptimizationRequest from API
        
    Returns:
        tuple: (boxes, container) as solver objects
    """
    boxes = []
    
    # Convert items to Box objects
    for item in request.items:
        for _ in range(item.quantity):
            # Handle unit conversion if needed (assuming cm and kg as base)
            length = item.dimensions.length
            width = item.dimensions.width
            height = item.dimensions.height
            weight = item.weight.value
            
            # Simple unit conversion (extend as needed)
            if item.dimensions.unit == UnitEnum.m:
                length *= 100
                width *= 100
                height *= 100
            elif item.dimensions.unit == UnitEnum.inch:
                length *= 2.54
                width *= 2.54
                height *= 2.54
                
            if item.weight.unit == UnitEnum.lb:
                weight *= 0.453592
            
            # Create Box object
            box = Box(
                sku=item.sku,
                length=length,
                width=width,
                height=height,
                weight=weight,
                priority=item.delivery.priority if item.delivery else 1,
                delivery_order=item.delivery.stop_number if item.delivery else 1,
                stackable=item.constraints.stackable if item.constraints else True,
                fragile=item.constraints.fragile if item.constraints else False,
                max_stack=item.constraints.max_stack_height if item.constraints else 10,
                allowed_rotations=(
                    item.constraints.allowed_rotations 
                    if item.constraints and item.constraints.allowed_rotations 
                    else [True] * 6
                )
            )
            boxes.append(box)
    
    # Convert container
    container_dims = request.container.dimensions
    container_length = container_dims.length
    container_width = container_dims.width
    container_height = container_dims.height
    max_weight = request.container.weight_limit.value
    
    # Unit conversion for container
    if container_dims.unit == UnitEnum.m:
        container_length *= 100
        container_width *= 100
        container_height *= 100
    elif container_dims.unit == UnitEnum.inch:
        container_length *= 2.54
        container_width *= 2.54
        container_height *= 2.54
        
    if request.container.weight_limit.unit == UnitEnum.lb:
        max_weight *= 0.453592
    
    # Door dimensions
    door_width = container_width
    door_height = container_height
    if request.container.door:
        door_width = request.container.door.width
        door_height = request.container.door.height
        if container_dims.unit == UnitEnum.m:
            door_width *= 100
            door_height *= 100
        elif container_dims.unit == UnitEnum.inch:
            door_width *= 2.54
            door_height *= 2.54
    
    # Axle limits
    front_axle_limit = None
    rear_axle_limit = None
    if request.container.axle_limits:
        front_axle_limit = request.container.axle_limits.front_axle_limit
        rear_axle_limit = request.container.axle_limits.rear_axle_limit
        if request.container.axle_limits.unit == UnitEnum.lb:
            if front_axle_limit:
                front_axle_limit *= 0.453592
            if rear_axle_limit:
                rear_axle_limit *= 0.453592
    
    container = ContainerSpace(
        length=container_length,
        width=container_width,
        height=container_height,
        max_weight=max_weight,
        door_width=door_width,
        door_height=door_height,
        front_axle_limit=front_axle_limit,
        rear_axle_limit=rear_axle_limit
    )
    
    return boxes, container


def convert_placements_to_response(placements: List, stats: dict, request_id: str, 
                                   execution_time_ms: int, algorithm: str) -> LoadOptimizationResponse:
    """
    Convert solver results to API response format
    
    Args:
        placements: List of PlacedBox objects from solver
        stats: Statistics dictionary from solver
        request_id: Original request ID
        execution_time_ms: Execution time in milliseconds
        algorithm: Algorithm used
        
    Returns:
        LoadOptimizationResponse
    """
    # Convert placements
    placement_list = []
    for idx, placed in enumerate(placements):
        rotation_descriptions = [
            "Original orientation (L×W×H)",
            "Rotated 90° (W×L×H)",
            "Rotated 180° (L×W×H)",
            "Rotated 270° (W×L×H)",
            "Flipped on X-axis",
            "Flipped on Y-axis"
        ]
        
        placement = Placement(
            placement_id=idx + 1,
            sku=placed.box.sku,
            position=Position(
                x=round(placed.x, 2),
                y=round(placed.y, 2),
                z=round(placed.z, 2),
                unit=UnitEnum.cm
            ),
            dimensions=DimensionsSchema(
                length=round(placed.length, 2),
                width=round(placed.width, 2),
                height=round(placed.height, 2),
                unit=UnitEnum.cm
            ),
            rotation=placed.rotation,
            rotation_description=rotation_descriptions[placed.rotation] if placed.rotation < 6 else "Custom",
            load_order=placed.load_order,
            delivery_stop=placed.box.delivery_order,
            weight=round(placed.box.weight, 2),
            support_area_percentage=round(stats.get('support_area_percentage', 100.0), 2)
        )
        placement_list.append(placement)
    
    # Build utilization
    utilization = Utilization(
        volume_used_cm3=round(stats.get('volume_used', 0), 2),
        volume_total_cm3=round(stats.get('volume_total', 1), 2),
        volume_percentage=round(stats.get('utilization_pct', 0), 2),
        weight_used_kg=round(stats.get('total_weight', 0), 2),
        weight_limit_kg=round(stats.get('weight_limit', 10000), 2),
        weight_percentage=round(stats.get('weight_pct', 0), 2)
    )
    
    # Center of gravity
    cg = None
    if 'center_of_gravity' in stats:
        cg_data = stats['center_of_gravity']
        cg = CenterOfGravity(
            x=round(cg_data.get('x', 0), 2),
            y=round(cg_data.get('y', 0), 2),
            z=round(cg_data.get('z', 0), 2),
            unit=UnitEnum.cm,
            deviation_from_center=round(cg_data.get('deviation', 0), 2)
        )
    
    # Axle weights
    axle_weights = None
    if 'axle_weights' in stats:
        aw_data = stats['axle_weights']
        axle_weights = AxleWeights(
            front_axle_kg=round(aw_data.get('front', 0), 2),
            rear_axle_kg=round(aw_data.get('rear', 0), 2),
            within_limits=aw_data.get('within_limits', True)
        )
    
    # Statistics
    statistics = Statistics(
        total_items_requested=stats.get('total_boxes', 0),
        items_placed=stats.get('placed_count', len(placements)),
        items_failed=stats.get('failed_count', 0),
        utilization=utilization,
        center_of_gravity=cg,
        axle_weights=axle_weights,
        loading_time_estimate_minutes=stats.get('loading_time_estimate', None)
    )
    
    # Validation
    warnings = stats.get('warnings', [])
    errors = stats.get('errors', [])
    validation = Validation(
        all_constraints_met=len(errors) == 0,
        warnings=warnings,
        errors=errors
    )
    
    # Build result
    result = OptimizationResult(
        placements=placement_list,
        statistics=statistics,
        validation=validation,
        visualization_url=f"http://localhost:8000/api/v1/loadopt/visualize/{request_id}"
    )
    
    # Solver metadata
    solver_metadata = SolverMetadata(
        algorithm_used=algorithm,
        optimization_level=stats.get('optimization_level', 'balanced'),
        iterations=stats.get('iterations', 1),
        version=SOLVER_VERSION
    )
    
    # Build response
    response = LoadOptimizationResponse(
        status="success",
        request_id=request_id,
        execution_time_ms=execution_time_ms,
        result=result,
        solver_metadata=solver_metadata
    )
    
    return response


@router.post(
    "/loadopt/plan",
    response_model=LoadOptimizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Optimize Load Plan",
    description="Execute 3D load optimization and return placement plan"
)
async def optimize_load(request: LoadOptimizationRequest):
    """
    **Optimize Load Plan**
    
    Execute 3D bin packing optimization for the given container and items.
    Returns detailed placement coordinates, utilization metrics, and validation results.
    
    **Algorithm Options:**
    - `heuristic`: Fast extreme-points based placement (recommended)
    - `layer`: Layer-building approach for homogeneous loads
    - `layer_rotated`: Layer-building with rotation support
    
    **Example Usage:**
    ```json
    {
      "request_id": "TMS-ORDER-12345",
      "container": {
        "dimensions": {"length": 1200, "width": 240, "height": 240, "unit": "cm"},
        "weight_limit": {"value": 28000, "unit": "kg"},
        "door": {"width": 240, "height": 240}
      },
      "items": [
        {
          "sku": "PALLET-A",
          "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"},
          "weight": {"value": 300, "unit": "kg"},
          "quantity": 10,
          "delivery": {"stop_number": 1, "priority": 1}
        }
      ],
      "solver_options": {
        "algorithm": "heuristic",
        "max_execution_time_seconds": 30
      }
    }
    ```
    """
    start_time = time.time()
    
    try:
        # Convert request to solver objects
        boxes, container = convert_request_to_solver_objects(request)
        
        # Validate weight before solving
        total_weight = sum(box.weight for box in boxes)
        if total_weight > container.max_weight:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "status": "error",
                    "request_id": request.request_id,
                    "error": {
                        "code": "WEIGHT_LIMIT_EXCEEDED",
                        "message": "Total item weight exceeds container weight limit",
                        "details": {
                            "total_weight_requested": round(total_weight, 2),
                            "container_weight_limit": round(container.max_weight, 2),
                            "excess_weight": round(total_weight - container.max_weight, 2)
                        }
                    }
                }
            )
        
        # Select solver algorithm
        algorithm = request.solver_options.algorithm if request.solver_options else "heuristic"
        
        if algorithm == "layer":
            solver = LayerBuildingHeuristic(boxes, container)
        elif algorithm == "layer_rotated":
            solver = LayerBuildingHeuristicRotated(boxes, container)
        else:  # heuristic (default)
            solver = HeuristicSolver(boxes, container)
        
        # Run solver
        placements, stats = solver.solve()
        
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Convert to response format
        response = convert_placements_to_response(
            placements=placements,
            stats=stats,
            request_id=request.request_id,
            execution_time_ms=execution_time_ms,
            algorithm=algorithm
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "request_id": request.request_id,
                "error": {
                    "code": "SOLVER_ERROR",
                    "message": f"Optimization failed: {str(e)}",
                    "details": {
                        "execution_time_ms": execution_time_ms,
                        "exception_type": type(e).__name__
                    }
                }
            }
        )


@router.post(
    "/loadopt/validate",
    response_model=LoadOptimizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate Load Plan",
    description="Validate container, items, and constraints without optimization"
)
async def validate_load(request: LoadOptimizationRequest):
    """
    **Validate Load Plan**
    
    Perform validation checks on container and items without running optimization.
    Useful for pre-flight checks before optimization.
    
    **Validation Checks:**
    - Total weight vs container limit
    - Individual item dimensions vs container dimensions
    - Door accessibility
    - Constraint consistency
    """
    start_time = time.time()
    
    try:
        boxes, container = convert_request_to_solver_objects(request)
        
        warnings = []
        errors = []
        
        # Weight validation
        total_weight = sum(box.weight for box in boxes)
        if total_weight > container.max_weight:
            errors.append(f"Total weight ({total_weight:.2f} kg) exceeds container limit ({container.max_weight:.2f} kg)")
        
        # Dimension validation
        for box in boxes:
            if box.length > container.length or box.width > container.width or box.height > container.height:
                errors.append(f"SKU {box.sku} dimensions exceed container dimensions")
        
        # Door validation
        if container.door_width or container.door_height:
            for box in boxes:
                if box.width > container.door_width or box.height > container.door_height:
                    warnings.append(f"SKU {box.sku} may not fit through door opening")
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Create validation-only response
        validation = Validation(
            all_constraints_met=len(errors) == 0,
            warnings=warnings,
            errors=errors
        )
        
        utilization = Utilization(
            volume_used_cm3=0,
            volume_total_cm3=container.length * container.width * container.height,
            volume_percentage=0,
            weight_used_kg=total_weight,
            weight_limit_kg=container.max_weight,
            weight_percentage=round((total_weight / container.max_weight) * 100, 2)
        )
        
        statistics = Statistics(
            total_items_requested=len(boxes),
            items_placed=0,
            items_failed=0,
            utilization=utilization
        )
        
        result = OptimizationResult(
            placements=[],
            statistics=statistics,
            validation=validation
        )
        
        solver_metadata = SolverMetadata(
            algorithm_used="validation_only",
            optimization_level="n/a",
            iterations=0,
            version=SOLVER_VERSION
        )
        
        response = LoadOptimizationResponse(
            status="success",
            request_id=request.request_id,
            execution_time_ms=execution_time_ms,
            result=result,
            solver_metadata=solver_metadata
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "status": "error",
                "request_id": request.request_id,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"Validation failed: {str(e)}",
                    "details": {}
                }
            }
        )


@router.get(
    "/loadopt/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Service health check for monitoring"
)
async def health_check():
    """
    **Health Check**
    
    Returns service status and uptime information.
    Used by monitoring systems and TMS to verify service availability.
    """
    uptime_seconds = time.time() - SERVICE_START_TIME
    
    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        timestamp=datetime.utcnow().isoformat() + "Z",
        uptime_seconds=round(uptime_seconds, 2)
    )


@router.get(
    "/loadopt/version",
    response_model=VersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Version Information",
    description="API and solver version information"
)
async def version_info():
    """
    **Version Information**
    
    Returns API version, solver version, and capabilities.
    """
    return VersionResponse(
        api_version=API_VERSION,
        solver_version=SOLVER_VERSION,
        supported_algorithms=["heuristic", "layer", "layer_rotated"],
        capabilities={
            "multi_stop_delivery": True,
            "weight_distribution": True,
            "rotation_support": True,
            "fragile_handling": True,
            "axle_limits": True,
            "async_optimization": False  # Not implemented yet
        }
    )
