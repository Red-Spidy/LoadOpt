"""
Unified Multi-Stop Solver Bridge

This module provides a unified interface that automatically:
1. Detects whether to use simple or advanced multi-stop optimization
2. Converts between database models and solver models
3. Maintains backward compatibility with existing LoadOpt system

Usage:
    from app.solver.unified_multistop import run_unified_solver

    result = run_unified_solver(
        container=container,
        boxes=boxes,
        delivery_groups=delivery_groups,
        plan=plan
    )
"""

from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import logging

from app.solver.utils import Box, ContainerSpace as Container
from app.solver.multistop.models import Trip, Stop, StopType, UnloadStrategy
from app.solver.multistop.optimizer import MultiStopOptimizer, quick_optimize
from app.models.models import DeliveryGroup as DBDeliveryGroup, Plan as DBPlan

logger = logging.getLogger(__name__)


def convert_to_multistop_trip(
    container: Container,
    delivery_groups: List[DBDeliveryGroup],
    boxes: List[Box],
    plan: DBPlan
) -> Tuple[Trip, Dict[int, Box]]:
    """
    Convert database models to multi-stop Trip and SKU catalog

    Args:
        container: Container model
        delivery_groups: List of DeliveryGroup models
        boxes: List of Box instances
        plan: Plan model with configuration

    Returns:
        Tuple of (Trip, sku_catalog)
    """

    # Group boxes by delivery group to determine requirements
    boxes_by_group = {}
    for box in boxes:
        delivery_order = box.delivery_order if hasattr(box, 'delivery_order') else 999
        if delivery_order not in boxes_by_group:
            boxes_by_group[delivery_order] = []
        boxes_by_group[delivery_order].append(box)

    # Create SKU catalog (unique SKUs)
    sku_catalog = {}
    sku_to_count = {}

    for box in boxes:
        if box.sku_id not in sku_catalog:
            # Use the first instance as template
            sku_catalog[box.sku_id] = Box(
                id=box.sku_id,
                sku_id=box.sku_id,
                instance_index=0,
                length=box.length,
                width=box.width,
                height=box.height,
                weight=box.weight,
                fragile=box.fragile if hasattr(box, 'fragile') else False,
                max_stack=box.max_stack if hasattr(box, 'max_stack') else 999,
                stacking_group=box.stacking_group if hasattr(box, 'stacking_group') else None,
                priority=box.priority if hasattr(box, 'priority') else 1,
                allowed_rotations=box.allowed_rotations if hasattr(box, 'allowed_rotations') else [True]*6,
                delivery_order=box.delivery_order if hasattr(box, 'delivery_order') else 999,
                name=box.name if hasattr(box, 'name') else f"SKU-{box.sku_id}",
                color=box.color if hasattr(box, 'color') else "#3B82F6",
                load_bearing_capacity=box.load_bearing_capacity if hasattr(box, 'load_bearing_capacity') else None
            )

        # Count instances per (SKU, delivery_order)
        key = (box.sku_id, box.delivery_order if hasattr(box, 'delivery_order') else 999)
        sku_to_count[key] = sku_to_count.get(key, 0) + 1

    # Create stops from delivery groups - MERGE groups with same delivery_order
    stops = []
    delivery_group_map = {g.id: g for g in delivery_groups}

    # Sort by delivery_order to ensure proper sequence
    sorted_groups = sorted(delivery_groups, key=lambda g: g.delivery_order)

    # Debug: Print delivery group info
    logger.info(f"Creating stops from {len(sorted_groups)} delivery groups")
    for group in sorted_groups:
        logger.info(f"  Group {group.id}: name={group.name}, delivery_order={group.delivery_order}")

    # Debug: Print box delivery_order distribution
    delivery_order_counts = {}
    for box in boxes:
        do = box.delivery_order if hasattr(box, 'delivery_order') else 999
        delivery_order_counts[do] = delivery_order_counts.get(do, 0) + 1
    logger.info(f"Box delivery_order distribution: {delivery_order_counts}")

    # Group delivery groups by their delivery_order to avoid duplicates
    # Multiple groups can have the same delivery_order - we should merge them into one stop
    groups_by_delivery_order = {}
    for group in sorted_groups:
        if group.delivery_order not in groups_by_delivery_order:
            groups_by_delivery_order[group.delivery_order] = []
        groups_by_delivery_order[group.delivery_order].append(group)

    logger.info(f"Unique delivery_order values: {list(groups_by_delivery_order.keys())}")

    for delivery_order, groups in sorted(groups_by_delivery_order.items()):
        # Calculate SKU requirements for this stop (from boxes, not from groups)
        sku_requirements = {}

        for box in boxes:
            box_delivery_order = box.delivery_order if hasattr(box, 'delivery_order') else 999
            if box_delivery_order == delivery_order:
                sku_requirements[box.sku_id] = sku_requirements.get(box.sku_id, 0) + 1

        # Only create stop if there are SKU requirements
        if not sku_requirements:
            group_names = [g.name for g in groups]
            logger.warning(f"Skipping delivery_order={delivery_order} (groups: {group_names}) - no matching boxes")
            continue

        # Use the first group for metadata
        primary_group = groups[0]
        group_names = [g.name for g in groups]
        location_name = " / ".join(group_names) if len(groups) > 1 else primary_group.name

        logger.info(f"Stop for delivery_order={delivery_order} (groups: {group_names}): {sum(sku_requirements.values())} items, {len(sku_requirements)} SKUs")

        # Create Stop
        # Convert database StopType enum to multistop StopType enum
        if primary_group.stop_type:
            stop_type_map = {
                'DELIVERY': StopType.DELIVERY,
                'PICKUP': StopType.PICKUP,
                'CROSS_DOCK': StopType.CROSS_DOCK,
                'RETURN': StopType.RETURN
            }
            stop_type_str = primary_group.stop_type.value if hasattr(primary_group.stop_type, 'value') else str(primary_group.stop_type)
            multistop_stop_type = stop_type_map.get(stop_type_str, StopType.DELIVERY)
        else:
            multistop_stop_type = StopType.DELIVERY
        
        stop = Stop(
            stop_number=delivery_order,
            location_id=primary_group.location_id or f"LOC-{primary_group.id}",
            location_name=location_name,
            sku_requirements=sku_requirements,
            stop_type=multistop_stop_type,
            is_time_critical=any(g.is_time_critical for g in groups) or False,
            time_window_start=float(primary_group.earliest_time.timestamp()) if primary_group.earliest_time else None,
            time_window_end=float(primary_group.latest_time.timestamp()) if primary_group.latest_time else None,
            notes=primary_group.special_instructions if hasattr(primary_group, 'special_instructions') else "",
            original_delivery_order=delivery_order  # Preserve original for box matching
        )

        stops.append(stop)

    # Handle boxes without delivery group (delivery_order = 999)
    ungrouped_boxes = [b for b in boxes if not hasattr(b, 'delivery_order') or b.delivery_order == 999]
    if ungrouped_boxes:
        sku_requirements = {}
        for box in ungrouped_boxes:
            sku_requirements[box.sku_id] = sku_requirements.get(box.sku_id, 0) + 1

        stops.append(Stop(
            stop_number=999,
            location_id="UNASSIGNED",
            location_name="Unassigned Items",
            sku_requirements=sku_requirements,
            stop_type=StopType.DELIVERY,
            is_time_critical=False
        ))

    # Convert database UnloadStrategy enum to multistop UnloadStrategy enum
    if plan.unload_strategy:
        strategy_map = {
            'STRICT_LIFO': UnloadStrategy.STRICT_LIFO,
            'MINIMAL_REHANDLING': UnloadStrategy.MINIMAL_REHANDLING,
            'OPTIMIZED': UnloadStrategy.OPTIMIZED
        }
        strategy_str = plan.unload_strategy.value if hasattr(plan.unload_strategy, 'value') else str(plan.unload_strategy)
        multistop_strategy = strategy_map.get(strategy_str, UnloadStrategy.MINIMAL_REHANDLING)
    else:
        multistop_strategy = UnloadStrategy.MINIMAL_REHANDLING

    # Create Trip
    trip = Trip(
        trip_id=f"PLAN-{plan.id}",
        stops=stops,
        container=container,
        unload_strategy=multistop_strategy,
        max_rehandling_events=plan.max_rehandling_events if plan.max_rehandling_events else 5,
        rehandling_cost_per_item=plan.rehandling_cost_per_event if plan.rehandling_cost_per_event else 10.0
    )

    return trip, sku_catalog


def run_unified_solver(
    container: Container,
    boxes: List[Box],
    delivery_groups: List[DBDeliveryGroup],
    plan: DBPlan,
    verbose: bool = True,
    multi_algorithm: bool = False
) -> Dict[str, Any]:
    """
    Unified multi-stop solver - runs multiple algorithms and picks the best

    Args:
        container: Container specification
        boxes: List of boxes to place
        delivery_groups: List of delivery groups (stops)
        plan: Plan model with configuration
        verbose: Enable verbose logging
        multi_algorithm: Run comprehensive multi-algorithm approach

    Returns:
        Unified result dictionary with placements and metrics
    """

    logger.info(f"Running unified multi-stop solver for {len(boxes)} boxes across {len(delivery_groups)} stops")
    if multi_algorithm:
        logger.info("COMPREHENSIVE MODE: Running multiple solver algorithms")

    # For multi-stop, convert and use the multi-stop optimizer
    if len(delivery_groups) > 0:
        # Convert to Trip model
        trip, sku_catalog = convert_to_multistop_trip(
            container=container,
            delivery_groups=delivery_groups,
            boxes=boxes,
            plan=plan
        )

        # Run multi-stop optimizer
        multistop_result = quick_optimize(
            trip=trip,
            sku_catalog=sku_catalog,
            verbose=verbose,
            multi_algorithm=multi_algorithm
        )

        # Convert result to unified format
        result = {
            'placements': [
                {
                    'x': p.x,
                    'y': p.y,
                    'z': p.z,
                    'rotation': p.rotation,
                    'length': p.length,
                    'width': p.width,
                    'height': p.height,
                    'sku_id': p.box.sku_id if hasattr(p, 'box') else getattr(p, 'sku_id', 0),
                    'instance_index': p.box.instance_index if hasattr(p, 'box') else getattr(p, 'instance_index', 0),
                    'load_order': p.load_order if hasattr(p, 'load_order') else 0,
                    'delivery_order': p.box.delivery_order if hasattr(p, 'box') else getattr(p, 'delivery_order', 999)
                }
                for p in multistop_result.placements
            ],
            'utilization_pct': multistop_result.overall_utilization_pct,
            'total_weight': sum(p.box.weight for p in multistop_result.placements),
            'is_valid': multistop_result.is_valid,
            'validation_errors': multistop_result.validation_errors,
            'validation': {
                'is_valid': multistop_result.is_valid,
                'errors': multistop_result.validation_errors,
                'warnings': multistop_result.validation_warnings
            }
        }
        return result

    # For single-stop or no delivery groups, run comprehensive algorithm suite
    logger.info("Running comprehensive algorithm suite (7 algorithms)")
    
    from app.solver.heuristic import HeuristicSolver
    from app.solver.skyline_solver import SkylineSolver
    from app.solver.beam_search import BeamSearchSolver
    from app.solver.grasp_solver import GRASPSolver
    from app.solver.tabu_search import TabuSearchSolver
    from app.solver.optimal_solver import OptimalSolver
    
    best_placements = []
    best_utilization = 0.0
    best_algorithm = "none"
    
    # Algorithm 1: Heuristic (Fast)
    if verbose:
        print("Algorithm 1/7: Fast Heuristic...")
    try:
        heuristic = HeuristicSolver(boxes, container)
        heuristic.solve()
        placements = heuristic.placements
        util = (sum(p.volume for p in placements) / (container.length * container.width * container.height)) * 100
        if verbose:
            print(f"  → {len(placements)} items, {util:.1f}% utilization")
        if len(placements) > len(best_placements) or (len(placements) == len(best_placements) and util > best_utilization):
            best_placements = placements
            best_utilization = util
            best_algorithm = "Heuristic"
    except Exception as e:
        logger.warning(f"Heuristic solver failed: {e}")
    
    # Algorithm 2: Skyline
    if verbose:
        print("Algorithm 2/7: Skyline...")
    try:
        skyline = SkylineSolver(boxes, container)
        skyline.solve()
        placements = skyline.placements
        util = (sum(p.volume for p in placements) / (container.length * container.width * container.height)) * 100
        if verbose:
            print(f"  → {len(placements)} items, {util:.1f}% utilization")
        if len(placements) > len(best_placements) or (len(placements) == len(best_placements) and util > best_utilization):
            best_placements = placements
            best_utilization = util
            best_algorithm = "Skyline"
    except Exception as e:
        logger.warning(f"Skyline solver failed: {e}")
    
    # Algorithm 3: Beam Search
    if verbose:
        print("Algorithm 3/7: Beam Search...")
    try:
        beam = BeamSearchSolver(boxes, container, beam_width=5)
        beam.solve()
        placements = beam.placements
        util = (sum(p.volume for p in placements) / (container.length * container.width * container.height)) * 100
        if verbose:
            print(f"  → {len(placements)} items, {util:.1f}% utilization")
        if len(placements) > len(best_placements) or (len(placements) == len(best_placements) and util > best_utilization):
            best_placements = placements
            best_utilization = util
            best_algorithm = "BeamSearch"
    except Exception as e:
        logger.warning(f"Beam Search solver failed: {e}")
    
    # Algorithm 4: GRASP
    if verbose:
        print("Algorithm 4/7: GRASP...")
    try:
        grasp = GRASPSolver(boxes, container, max_iterations=10)
        grasp.solve()
        placements = grasp.placements
        util = (sum(p.volume for p in placements) / (container.length * container.width * container.height)) * 100
        if verbose:
            print(f"  → {len(placements)} items, {util:.1f}% utilization")
        if len(placements) > len(best_placements) or (len(placements) == len(best_placements) and util > best_utilization):
            best_placements = placements
            best_utilization = util
            best_algorithm = "GRASP"
    except Exception as e:
        logger.warning(f"GRASP solver failed: {e}")
    
    # Algorithm 5: Tabu Search
    if verbose:
        print("Algorithm 5/7: Tabu Search...")
    try:
        tabu = TabuSearchSolver(boxes, container, max_iterations=20)
        tabu.solve()
        placements = tabu.placements
        util = (sum(p.volume for p in placements) / (container.length * container.width * container.height)) * 100
        if verbose:
            print(f"  → {len(placements)} items, {util:.1f}% utilization")
        if len(placements) > len(best_placements) or (len(placements) == len(best_placements) and util > best_utilization):
            best_placements = placements
            best_utilization = util
            best_algorithm = "TabuSearch"
    except Exception as e:
        logger.warning(f"Tabu Search solver failed: {e}")
    
    # Algorithm 6 & 7: OptimalSolver (GA, SA, and more)
    if verbose:
        print("Algorithm 6-7/7: OptimalSolver (GA, SA, GRASP, Tabu, Beam, Skyline, Layer)...")
    try:
        optimal = OptimalSolver(boxes, container)
        placements, stats = optimal.solve()
        util = stats.get('utilization_pct', 0)
        if verbose:
            print(f"  → {len(placements)} items, {util:.1f}% utilization")
        if len(placements) > len(best_placements) or (len(placements) == len(best_placements) and util > best_utilization):
            best_placements = placements
            best_utilization = util
            best_algorithm = "OptimalSolver"
    except Exception as e:
        logger.warning(f"OptimalSolver failed: {e}")
    
    if verbose:
        print(f"\n✓ BEST: {best_algorithm} - {len(best_placements)} items, {best_utilization:.1f}% utilization\n")
    
    # Convert result to unified format
    result = {
        'placements': [
            {
                'x': p.x,
                'y': p.y,
                'z': p.z,
                'rotation': p.rotation,
                'length': p.length,
                'width': p.width,
                'height': p.height,
                'sku_id': p.box.sku_id if hasattr(p, 'box') else getattr(p, 'sku_id', 0),
                'instance_index': p.box.instance_index if hasattr(p, 'box') else getattr(p, 'instance_index', 0),
                'load_order': p.load_order if hasattr(p, 'load_order') else 0,
                'delivery_order': p.box.delivery_order if hasattr(p, 'box') else getattr(p, 'delivery_order', 999)
            }
            for p in best_placements
        ],
        'utilization_pct': best_utilization,
        'total_weight': sum(p.box.weight for p in best_placements) if best_placements else 0.0,
        'is_valid': True,
        'validation_errors': [],
        'validation': {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
    }
    
    return result


# Convenience function for backward compatibility
def run_solver_with_multistop(*args, **kwargs):
    """Alias for run_unified_solver for backward compatibility"""
    return run_unified_solver(*args, **kwargs)
