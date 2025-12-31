from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import io
import csv

from app.core.database import get_db
from app.api.dependencies import get_current_active_user
from app.models.models import User, Plan, Project, Container, SKU, Placement, PlanStatus, SolverMode
from app.schemas.schemas import (
    PlanCreate, Plan as PlanSchema, PlanWithPlacements, 
    PlanUpdate, Placement as PlacementSchema, SolverModeEnum
)

# Always import solver utils for convert functions
from app.solver.utils import Box, ContainerSpace
from app.solver.optimal_solver import OptimalSolver

# Try to import Celery, fallback to background tasks if not available
try:
    from app.workers.tasks import optimize_plan as optimize_plan_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

router = APIRouter()


def verify_project_access(project_id: int, user_id: int, db: Session) -> Project:
    """Verify user has access to project"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.owner_id == user_id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


def convert_sku_to_boxes(skus: List[SKU]) -> List[Box]:
    """Convert SKU models to Box objects"""
    boxes = []
    for sku in skus:
        for i in range(sku.quantity):
            box = Box(
                id=len(boxes),
                sku_id=sku.id,
                instance_index=i,
                length=sku.length,
                width=sku.width,
                height=sku.height,
                weight=sku.weight,
                fragile=sku.fragile,
                max_stack=sku.max_stack,
                stacking_group=sku.stacking_group,
                priority=sku.priority,
                allowed_rotations=sku.allowed_rotations
            )
            boxes.append(box)
    return boxes


def convert_container_model(container: Container) -> ContainerSpace:
    """Convert Container model to ContainerSpace object"""
    return ContainerSpace(
        length=container.inner_length,
        width=container.inner_width,
        height=container.inner_height,
        max_weight=container.max_weight,
        door_width=container.door_width,
        door_height=container.door_height,
        front_axle_limit=container.front_axle_limit,
        rear_axle_limit=container.rear_axle_limit,
        obstacles=container.obstacles or []
    )


@router.post("/", response_model=PlanSchema, status_code=status.HTTP_201_CREATED)
def create_plan(
    plan_in: PlanCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create new loading plan"""
    # Verify project access
    verify_project_access(plan_in.project_id, current_user.id, db)
    
    # Verify container exists
    container = db.query(Container).filter(
        Container.id == plan_in.container_id,
        Container.project_id == plan_in.project_id
    ).first()
    
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Container not found"
        )
    
    # Get SKUs for the project
    skus = db.query(SKU).filter(SKU.project_id == plan_in.project_id).all()
    total_items = sum(sku.quantity for sku in skus)
    
    # Auto-detect multi-stop based on delivery groups
    unique_delivery_groups = set(
        sku.delivery_group_id for sku in skus 
        if sku.delivery_group_id is not None
    )
    has_multiple_stops = len(unique_delivery_groups) > 1
    
    # Set defaults based on detection if not explicitly provided
    solver_mode = plan_in.solver_mode
    use_advanced_multistop = plan_in.use_advanced_multistop
    
    if solver_mode is None:
        # Auto-select: FAST for multi-stop (uses heuristic), OPTIMAL for single-stop
        solver_mode = SolverModeEnum.FAST if has_multiple_stops else SolverModeEnum.OPTIMAL
    
    if use_advanced_multistop is None:
        # Auto-enable for multiple stops
        use_advanced_multistop = has_multiple_stops
    
    # CRITICAL: Force FAST mode when multi-stop is enabled
    # OPTIMAL solver doesn't support zone-based multi-stop placement
    if use_advanced_multistop:
        solver_mode = SolverModeEnum.FAST
        print(f"⚠️  Multi-stop enabled - forcing FAST solver mode (was: {plan_in.solver_mode})")
    
    # Create plan
    plan = Plan(
        project_id=plan_in.project_id,
        container_id=plan_in.container_id,
        name=plan_in.name,
        solver_mode=solver_mode,
        use_advanced_multistop=use_advanced_multistop,
        unload_strategy=plan_in.unload_strategy,
        max_rehandling_events=plan_in.max_rehandling_events,
        rehandling_cost_per_event=plan_in.rehandling_cost_per_event,
        status=PlanStatus.PENDING,
        items_total=total_items
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    # Run solver based on mode
    if CELERY_AVAILABLE:
        # Use Celery for async optimization
        task = optimize_plan_task.delay(plan.id)
        plan.job_id = task.id
        db.commit()
    else:
        # Fallback to background tasks
        background_tasks.add_task(run_solver_sync, plan.id)
    
    return plan


def run_solver_sync(plan_id: int):
    """Run solver synchronously with unified multi-stop support"""
    # Get fresh DB session
    from app.core.database import SessionLocal
    from app.models.models import DeliveryGroup
    from app.solver.unified_multistop import run_unified_solver
    import json
    db = SessionLocal()

    try:
        plan = db.query(Plan).filter(Plan.id == plan_id).first()
        if not plan:
            print(f"Plan {plan_id} not found")
            return

        # Update status
        plan.status = PlanStatus.RUNNING
        db.commit()

        # Get data
        container = db.query(Container).filter(Container.id == plan.container_id).first()
        skus = db.query(SKU).filter(SKU.project_id == plan.project_id).all()

        # Get delivery groups for this project
        delivery_groups_list = db.query(DeliveryGroup).filter(
            DeliveryGroup.project_id == plan.project_id
        ).order_by(DeliveryGroup.delivery_order).all()
        delivery_groups = {g.id: g for g in delivery_groups_list}

        if not container or not skus:
            print(f"Missing data: container={bool(container)}, skus={len(skus)}")
            plan.status = PlanStatus.FAILED
            plan.validation_errors = ['Container or SKUs not found']
            db.commit()
            return

        # Convert to solver objects with delivery groups
        boxes = []
        for sku in skus:
            # Get delivery order from group (lower order = first delivery = load last)
            delivery_order = 999  # Default: no specific order
            if sku.delivery_group_id and sku.delivery_group_id in delivery_groups:
                delivery_order = delivery_groups[sku.delivery_group_id].delivery_order

            for i in range(sku.quantity):
                box = Box(
                    id=len(boxes),
                    sku_id=sku.id,
                    instance_index=i,
                    length=sku.length,
                    width=sku.width,
                    height=sku.height,
                    weight=sku.weight,
                    fragile=sku.fragile,
                    max_stack=sku.max_stack,
                    stacking_group=sku.stacking_group,
                    priority=sku.priority,
                    allowed_rotations=sku.allowed_rotations,
                    delivery_order=delivery_order
                )
                boxes.append(box)

        container_space = convert_container_model(container)

        # Check if this is a multi-stop problem (any boxes have specific delivery groups)
        has_delivery_groups = any(box.delivery_order < 999 for box in boxes)

        if has_delivery_groups and len(delivery_groups_list) > 0:
            # Use unified multi-stop solver for delivery route optimization
            print(f"Running unified multi-stop solver for {len(boxes)} boxes, {len(delivery_groups_list)} delivery groups...")

            result = run_unified_solver(
                container=container_space,
                boxes=boxes,
                delivery_groups=delivery_groups_list,
                plan=plan,
                verbose=True
            )
        else:
            # Use OptimalSolver for pure packing optimization (includes skyline improvements)
            print(f"Running OptimalSolver for {len(boxes)} boxes (single-stop optimization)...")

            solver = OptimalSolver(boxes, container_space)
            placements, stats = solver.solve()

            # Convert to unified result format
            result = {
                'placements': [
                    {
                        'x': p.x,
                        'y': p.y,
                        'z': p.z,
                        'rotation': p.rotation,
                        'sku_id': p.box.sku_id,
                        'instance_index': p.box.instance_index,
                        'length': p.length,
                        'width': p.width,
                        'height': p.height,
                        'load_order': p.load_order,
                        'delivery_order': p.box.delivery_order if hasattr(p.box, 'delivery_order') else None
                    }
                    for p in placements
                ],
                'utilization_pct': stats.get('utilization_pct', 0.0),
                'items_placed': len(placements),
                'items_total': len(boxes),
                'total_weight': stats.get('total_weight', 0.0),
                'is_valid': stats.get('is_valid', True),
                'validation_errors': stats.get('validation_errors', []),
                'weight_distribution': stats.get('weight_distribution'),
                'solver_type': 'optimal',
                'total_rehandling_events': 0,
                'total_rehandling_cost': 0.0,
                'unload_plans': None,
                'stop_metrics': None
            }

        print(f"Solver completed ({result.get('solver_type', 'unknown')}): "
              f"{result['items_placed']}/{result['items_total']} placed, "
              f"{result['utilization_pct']:.1f}% utilization, "
              f"{result.get('total_rehandling_events', 0)} rehandling events")

        # Save results
        plan.utilization_pct = result.get('utilization_pct', 0.0)
        plan.total_weight = result.get('total_weight', sum(
            p['length'] * p['width'] * p['height'] * 0.001  # Rough estimate if not provided
            for p in result.get('placements', [])
        ))
        plan.items_placed = result['items_placed']
        plan.is_valid = result.get('is_valid', True)
        plan.validation_errors = result.get('validation_errors', [])

        # Multi-stop specific results
        plan.total_rehandling_events = result.get('total_rehandling_events', 0)
        plan.total_rehandling_cost = result.get('total_rehandling_cost', 0.0)
        plan.unload_plans = json.dumps(result.get('unload_plans', {})) if result.get('unload_plans') else None
        plan.stop_metrics = json.dumps(result.get('stop_metrics', {})) if result.get('stop_metrics') else None

        plan.status = PlanStatus.DONE
        plan.completed_at = datetime.utcnow()

        # Delete old placements
        db.query(Placement).filter(Placement.plan_id == plan.id).delete()

        # Save placements
        for placed_dict in result.get('placements', []):
            placement = Placement(
                plan_id=plan.id,
                sku_id=placed_dict['sku_id'],
                instance_index=placed_dict['instance_index'],
                x=placed_dict['x'],
                y=placed_dict['y'],
                z=placed_dict['z'],
                rotation=placed_dict['rotation'],
                length=placed_dict['length'],
                width=placed_dict['width'],
                height=placed_dict['height'],
                load_order=placed_dict.get('load_order'),
                delivery_order=placed_dict.get('delivery_order')
            )
            db.add(placement)

        db.commit()
        print(f"Saved {len(result.get('placements', []))} placements to database")

    except Exception as e:
        import traceback
        print(f"Error in solver: {e}")
        print(traceback.format_exc())
        plan.status = PlanStatus.FAILED
        plan.validation_errors = [str(e)]
        db.commit()
    finally:
        db.close()


@router.get("/{plan_id}", response_model=PlanWithPlacements)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get plan by ID with placements"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Verify project access
    verify_project_access(plan.project_id, current_user.id, db)
    
    return plan


@router.get("/project/{project_id}", response_model=List[PlanSchema])
def list_plans_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all plans in a project"""
    # Verify project access
    verify_project_access(project_id, current_user.id, db)
    
    plans = db.query(Plan).filter(Plan.project_id == project_id).all()
    return plans


@router.put("/{plan_id}", response_model=PlanSchema)
def update_plan(
    plan_id: int,
    plan_in: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update plan"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Verify project access
    verify_project_access(plan.project_id, current_user.id, db)
    
    update_data = plan_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)
    
    db.commit()
    db.refresh(plan)
    
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete plan"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Verify project access
    verify_project_access(plan.project_id, current_user.id, db)
    
    db.delete(plan)
    db.commit()
    
    return None


@router.post("/{plan_id}/optimize", response_model=PlanSchema)
def optimize_plan(
    plan_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Re-run optimization on an existing plan"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Verify project access
    verify_project_access(plan.project_id, current_user.id, db)
    
    # Reset plan
    plan.status = PlanStatus.PENDING
    plan.utilization_pct = 0.0
    plan.total_weight = 0.0
    plan.items_placed = 0
    plan.weight_distribution = None
    plan.validation_errors = []
    
    # Delete old placements
    db.query(Placement).filter(Placement.plan_id == plan_id).delete()
    
    db.commit()
    
    # Run solver
    if CELERY_AVAILABLE:
        task = optimize_plan_task.delay(plan.id)
        plan.job_id = task.id
        db.commit()
    else:
        background_tasks.add_task(run_solver_sync, plan.id)
    
    return plan


@router.get("/{plan_id}/export/csv")
def export_plan_csv(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export plan placements as CSV"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Verify project access
    verify_project_access(plan.project_id, current_user.id, db)
    
    # Get placements with SKU data
    placements = db.query(Placement).filter(Placement.plan_id == plan_id).all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Load Order', 'SKU ID', 'SKU Name', 'Instance', 
        'X (cm)', 'Y (cm)', 'Z (cm)',
        'Length (cm)', 'Width (cm)', 'Height (cm)',
        'Rotation', 'Weight (kg)'
    ])
    
    # Write data
    for placement in placements:
        sku = db.query(SKU).filter(SKU.id == placement.sku_id).first()
        writer.writerow([
            placement.load_order if placement.load_order else '',
            placement.sku_id,
            sku.name if sku else 'Unknown',
            placement.instance_index + 1,
            f"{placement.x:.2f}",
            f"{placement.y:.2f}",
            f"{placement.z:.2f}",
            f"{placement.length:.2f}",
            f"{placement.width:.2f}",
            f"{placement.height:.2f}",
            placement.rotation,
            f"{sku.weight:.2f}" if sku else '0'
        ])
    
    # Add summary
    output.write('\n')
    writer.writerow(['Summary'])
    writer.writerow(['Total Items', plan.items_total])
    writer.writerow(['Items Placed', plan.items_placed])
    writer.writerow(['Utilization', f"{plan.utilization_pct:.2f}%"])
    writer.writerow(['Total Weight', f"{plan.total_weight:.2f} kg"])
    
    # Return as downloadable file
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=plan_{plan_id}_export.csv"
        }
    )


@router.get("/{plan_id}/export/summary")
def export_plan_summary(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get plan summary for export/reporting"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    # Verify project access
    project = verify_project_access(plan.project_id, current_user.id, db)
    container = db.query(Container).filter(Container.id == plan.container_id).first()
    
    # Get SKU counts
    placements = db.query(Placement).filter(Placement.plan_id == plan_id).all()
    sku_counts = {}
    for placement in placements:
        if placement.sku_id not in sku_counts:
            sku_counts[placement.sku_id] = 0
        sku_counts[placement.sku_id] += 1
    
    sku_details = []
    for sku_id, count in sku_counts.items():
        sku = db.query(SKU).filter(SKU.id == sku_id).first()
        if sku:
            sku_details.append({
                'sku_name': sku.name,
                'sku_code': sku.sku_code,
                'quantity_requested': sku.quantity,
                'quantity_placed': count,
                'dimensions': f"{sku.length}×{sku.width}×{sku.height} cm",
                'weight_each': sku.weight,
                'total_weight': sku.weight * count
            })
    
    return {
        'plan': {
            'id': plan.id,
            'name': plan.name,
            'status': plan.status,
            'solver_mode': plan.solver_mode,
            'created_at': plan.created_at,
            'completed_at': plan.completed_at
        },
        'project': {
            'id': project.id,
            'name': project.name
        },
        'container': {
            'id': container.id,
            'name': container.name,
            'dimensions': f"{container.inner_length}×{container.inner_width}×{container.inner_height} cm",
            'max_weight': container.max_weight
        },
        'results': {
            'utilization_pct': plan.utilization_pct,
            'total_weight': plan.total_weight,
            'items_placed': plan.items_placed,
            'items_total': plan.items_total,
            'is_valid': plan.is_valid,
            'validation_errors': plan.validation_errors
        },
        'weight_distribution': plan.weight_distribution,
        'sku_breakdown': sku_details
    }
