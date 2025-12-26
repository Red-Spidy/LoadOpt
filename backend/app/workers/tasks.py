from celery import Task
from datetime import datetime
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.models import Plan, Container, SKU, Placement, PlanStatus, DeliveryGroup
from app.solver.optimal_solver import OptimalSolver
from app.solver.utils import Box, ContainerSpace


class DatabaseTask(Task):
    """Base task with database session management"""
    _db = None
    
    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db
    
    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()


def convert_sku_to_boxes(skus, delivery_groups: dict) -> list:
    """Convert SKU models to Box objects
    
    Args:
        skus: List of SKU models
        delivery_groups: Dict mapping group_id to DeliveryGroup model
    """
    boxes = []
    for sku in skus:
        # Get delivery order from group (lower order = first delivery = load last)
        delivery_order = 999  # Default: no specific order
        if sku.delivery_group_id and sku.delivery_group_id in delivery_groups:
            delivery_order = delivery_groups[sku.delivery_group_id].delivery_order
        
        # Debug: Print SKU attributes to diagnose type issues
        if len(boxes) == 0:  # Only print once for debugging
            print(f"DEBUG SKU attributes:")
            print(f"  id={sku.id} (type={type(sku.id)})")
            print(f"  length={sku.length} (type={type(sku.length)})")
            print(f"  width={sku.width} (type={type(sku.width)})")
            print(f"  height={sku.height} (type={type(sku.height)})")
            print(f"  weight={sku.weight} (type={type(sku.weight)})")
            print(f"  priority={sku.priority} (type={type(sku.priority)})")
            print(f"  allowed_rotations={sku.allowed_rotations} (type={type(sku.allowed_rotations)})")
            print(f"  delivery_order={delivery_order} (type={type(delivery_order)})")
        
        for i in range(sku.quantity):
            box = Box(
                id=len(boxes),
                sku_id=sku.id,
                instance_index=i,
                length=float(sku.length),
                width=float(sku.width),
                height=float(sku.height),
                weight=float(sku.weight),
                fragile=bool(sku.fragile),
                max_stack=int(sku.max_stack),
                stacking_group=sku.stacking_group,
                priority=int(sku.priority),
                allowed_rotations=sku.allowed_rotations if isinstance(sku.allowed_rotations, list) else [True] * 6,
                delivery_order=int(delivery_order)
            )
            boxes.append(box)
    return boxes


def convert_container_model(container) -> ContainerSpace:
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


@celery_app.task(base=DatabaseTask, bind=True, name='app.workers.tasks.optimize_plan')
def optimize_plan(self, plan_id: int):
    """
    Celery task to optimize a loading plan
    
    Args:
        plan_id: The ID of the plan to optimize
    """
    db = self.db
    
    try:
        # Get plan
        plan = db.query(Plan).filter(Plan.id == plan_id).first()
        if not plan:
            return {'error': 'Plan not found'}
        
        # Update status
        plan.status = PlanStatus.RUNNING
        plan.job_id = self.request.id
        db.commit()
        
        # Get data
        container = db.query(Container).filter(Container.id == plan.container_id).first()
        skus = db.query(SKU).filter(SKU.project_id == plan.project_id).all()
        
        # Get delivery groups for this project
        groups = db.query(DeliveryGroup).filter(DeliveryGroup.project_id == plan.project_id).all()
        delivery_groups = {g.id: g for g in groups}
        
        if not container or not skus:
            plan.status = PlanStatus.FAILED
            plan.validation_errors = ['Container or SKUs not found']
            db.commit()
            return {'error': 'Container or SKUs not found'}
        
        # Convert to solver objects
        boxes = convert_sku_to_boxes(skus, delivery_groups)
        container_space = convert_container_model(container)

        n_boxes = len(boxes)

        # Check if this is a multi-stop problem (any boxes have specific delivery groups)
        has_delivery_groups = any(box.delivery_order < 999 for box in boxes)

        if has_delivery_groups and len(groups) > 0:
            # Use unified multi-stop solver for delivery route optimization
            print(f"Using unified multi-stop solver for {n_boxes} boxes, {len(groups)} delivery groups...")
            print("RUNNING COMPREHENSIVE 7-PHASE MULTI-ALGORITHM OPTIMIZATION")
            self.update_state(state='PROGRESS', meta={'status': f'Starting multi-algorithm solver for {n_boxes} boxes...'})

            from app.solver.unified_multistop import run_unified_solver
            result = run_unified_solver(
                container=container_space,
                boxes=boxes,
                delivery_groups=list(groups),
                plan=plan,
                verbose=True,
                multi_algorithm=True  # Enable comprehensive multi-algorithm approach
            )

            placements = []
            used_boxes = set()  # Track which (sku_id, instance_index, delivery_order) combinations are used
            for idx, p_data in enumerate(result['placements']):
                # Create a unique key for this placement
                placement_key = (p_data['sku_id'], p_data['instance_index'], p_data.get('delivery_order'))
                
                # Skip duplicate placements (same box placed twice)
                if placement_key in used_boxes:
                    print(f"Warning: Skipping duplicate placement for SKU {p_data['sku_id']}, instance {p_data['instance_index']}, delivery_order {p_data.get('delivery_order')}")
                    continue
                
                # Reconstruct PlacedBox-like object for database saving
                # Match by sku_id, instance_index, AND delivery_order to avoid cross-stop mismatches
                box = next((b for b in boxes 
                           if b.sku_id == p_data['sku_id'] 
                           and b.instance_index == p_data['instance_index']
                           and b.delivery_order == p_data.get('delivery_order', b.delivery_order)), None)
                if box:
                    from app.solver.utils import PlacedBox
                    placed = PlacedBox(
                        box=box,
                        x=p_data['x'],
                        y=p_data['y'],
                        z=p_data['z'],
                        rotation=p_data['rotation'],
                        length=p_data['length'],
                        width=p_data['width'],
                        height=p_data['height'],
                        load_order=p_data.get('load_order', idx)
                    )
                    placements.append(placed)
                    used_boxes.add(placement_key)
                else:
                    print(f"Warning: No matching box found for SKU {p_data['sku_id']}, instance {p_data['instance_index']}, delivery_order {p_data.get('delivery_order')}")

            stats = {
                'utilization_pct': result['utilization_pct'],
                'total_weight': result['total_weight'],
                'is_valid': result['is_valid'],
                'validation_errors': result['validation_errors'],
                'weight_distribution': result.get('weight_distribution'),
                'solutions_tested': result.get('solutions_tested', 0)
            }
        else:
            # Use OptimalSolver for single-stop pure packing optimization
            print(f"Using OptimalSolver for {n_boxes} boxes (single-stop optimization)...")
            self.update_state(state='PROGRESS', meta={'status': f'Starting optimal search for {n_boxes} boxes...'})

            solver = OptimalSolver(boxes, container_space)
            placements, stats = solver.solve()
        
        # Save results
        plan.utilization_pct = stats['utilization_pct']
        plan.total_weight = stats.get('total_weight', sum(p.box.weight for p in placements))
        plan.items_placed = len(placements)
        plan.weight_distribution = stats.get('weight_distribution')
        plan.is_valid = stats.get('is_valid', True)
        plan.validation_errors = stats.get('validation_errors', [])
        plan.status = PlanStatus.DONE
        plan.completed_at = datetime.utcnow()
        
        # Delete old placements
        db.query(Placement).filter(Placement.plan_id == plan.id).delete()
        
        # Save new placements
        for placed in placements:
            placement = Placement(
                plan_id=plan.id,
                sku_id=placed.box.sku_id,
                instance_index=placed.box.instance_index,
                x=placed.x,
                y=placed.y,
                z=placed.z,
                rotation=placed.rotation,
                length=placed.length,
                width=placed.width,
                height=placed.height,
                load_order=placed.load_order,
                delivery_order=placed.box.delivery_order if hasattr(placed.box, 'delivery_order') else None
            )
            db.add(placement)
        
        db.commit()
        
        return {
            'status': 'success',
            'plan_id': plan_id,
            'utilization': stats['utilization_pct'],
            'items_placed': len(placements),
            'items_total': plan.items_total,
            'solutions_tested': stats.get('solutions_tested', 0)
        }
        
    except Exception as e:
        # Update plan as failed
        if plan:
            plan.status = PlanStatus.FAILED
            plan.validation_errors = [str(e)]
            db.commit()
        
        raise
