"""
Multi-Stop Load Optimizer - Main Orchestrator

Coordinates all components of multi-stop optimization:
1. Preprocessing (Virtual SKUs, priorities)
2. Placement (Stop-based zoning, 3D packing)
3. Validation (Unload feasibility, rehandling)
4. Output generation

This is the main entry point for multi-stop load planning.
"""

from typing import List, Dict, Optional, Any
import time

from app.solver.utils import Box, ContainerSpace as Container
from .models import (
    Trip, MultiStopLoadPlan, UnloadPlan, StopMetrics,
    UnloadStrategy
)
from .preprocessor import MultiStopPreprocessor, PriorityWeights
from .placement_engine import MultiStopPlacementEngine
from .validator import MultiStopValidator


class MultiStopOptimizer:
    """
    Main optimizer for multi-stop load planning.

    WORKFLOW:
    ---------
    1. **Preprocess**: Convert trip into prioritized box list
       - Split SKUs across stops into Virtual SKUs
       - Compute priority scores (stop order, fragility, weight, SLA)
       - Generate box instances with delivery_order

    2. **Place**: Execute 3D bin-packing with stop awareness
       - Create stop-based zones (LIFO principle)
       - Place boxes using extreme point algorithm
       - Respect accessibility constraints

    3. **Validate**: Check unload feasibility
       - Generate unload plan for each stop
       - Detect rehandling requirements
       - Validate against strategy (STRICT_LIFO, MINIMAL_REHANDLING, etc.)

    4. **Output**: Generate comprehensive load plan
       - Placements with positions and rotations
       - Unload plans with rehandling events
       - Metrics and validation results

    DESIGN PRINCIPLES:
    ------------------
    - **Deterministic**: Same input → same output (no randomness)
    - **Explainable**: Every decision has clear operational rationale
    - **Auditable**: Operations teams can review and understand
    - **Extensible**: Easy to add new constraints or strategies
    """

    def __init__(
        self,
        priority_weights: Optional[PriorityWeights] = None,
        use_proportional_zones: bool = True,
        allow_zone_overflow: bool = True,
        accessibility_weight: float = 0.5
    ):
        """
        Initialize optimizer with configuration.

        Args:
            priority_weights: Weights for priority calculation
            use_proportional_zones: If True, allocate zones by volume;
                                   if False, use equal zones
            allow_zone_overflow: Allow boxes to spill into adjacent zones
            accessibility_weight: Weight for accessibility in placement (0-1)
        """
        self.priority_weights = priority_weights or PriorityWeights()
        self.use_proportional_zones = use_proportional_zones
        self.allow_zone_overflow = allow_zone_overflow
        self.accessibility_weight = accessibility_weight

    def optimize(
        self,
        trip: Trip,
        sku_catalog: Dict[int, Box],
        verbose: bool = False,
        multi_algorithm: bool = False
    ) -> MultiStopLoadPlan:
        """
        Optimize load plan for a multi-stop trip.

        Args:
            trip: Trip specification with stops
            sku_catalog: Mapping of sku_id -> Box template
            verbose: If True, print progress information
            multi_algorithm: If True, run multiple algorithms and pick best

        Returns:
            MultiStopLoadPlan with placements, unload plans, and validation

        Raises:
            ValueError: If inputs are invalid or optimization fails
        """
        start_time = time.time()

        if verbose:
            print(f"\n{'='*70}")
            print(f"MULTI-STOP LOAD OPTIMIZATION")
            if multi_algorithm:
                print(f"MODE: COMPREHENSIVE (7-PHASE MULTI-ALGORITHM)")
            print(f"{'='*70}")
            print(f"Trip: {trip.trip_id}")
            print(f"Stops: {trip.num_stops}")
            print(f"Total items: {trip.total_items}")
            print(f"Strategy: {trip.unload_strategy.name}")
            print(f"{'='*70}\n")

        # PHASE 1: PREPROCESSING
        if verbose:
            print("PHASE 1: Preprocessing...")

        preprocessor = MultiStopPreprocessor(self.priority_weights)
        boxes, virtual_skus, preprocess_metadata = preprocessor.preprocess_trip(
            trip, sku_catalog
        )

        if verbose:
            print(f"  ✓ Created {len(virtual_skus)} virtual SKUs")
            print(f"  ✓ Generated {len(boxes)} box instances")
            print(f"  ✓ Priority range: {preprocess_metadata['priority_range']['min']:.0f} "
                  f"- {preprocess_metadata['priority_range']['max']:.0f}")
            print()

        # PHASE 2: PLACEMENT - Try multiple approaches if multi_algorithm enabled
        if verbose:
            print("PHASE 2: 3D Placement with Stop Zoning...")

        best_placements = []
        best_utilization = 0.0
        approach_used = "default"
        placement_engine = None  # Store the engine for later use
        
        # Configuration matrix for multi-algorithm approach
        if multi_algorithm:
            configs = [
                ("Proportional+Overflow", True, True, 0.5),
                ("Proportional+NoOverflow", True, False, 0.5),
                ("Sequential+Overflow", False, True, 0.5),
                ("Sequential+NoOverflow", False, False, 0.5),
                ("Proportional+HighAccess", True, True, 0.8),
                ("Proportional+LowAccess", True, True, 0.2),
                ("Sequential+HighAccess", False, True, 0.8),
            ]
            
            if verbose:
                print(f"  Running {len(configs)} algorithm configurations...")
            
            for config_name, use_prop, allow_overflow, access_weight in configs:
                if verbose:
                    print(f"    Trying: {config_name}...")
                
                engine = MultiStopPlacementEngine(
                    container=trip.container,
                    trip=trip,
                    use_proportional_zones=use_prop
                )
                
                placements_attempt = engine.place_boxes(
                    boxes=boxes,
                    allow_zone_overflow=allow_overflow,
                    accessibility_weight=access_weight
                )
                
                # Calculate utilization
                total_volume = sum(p.volume for p in placements_attempt)
                container_volume = trip.container.length * trip.container.width * trip.container.height
                utilization = (total_volume / container_volume) * 100 if container_volume > 0 else 0
                
                if verbose:
                    print(f"      → {len(placements_attempt)} boxes, {utilization:.1f}% utilization")
                
                if len(placements_attempt) > len(best_placements) or \
                   (len(placements_attempt) == len(best_placements) and utilization > best_utilization):
                    best_placements = placements_attempt
                    best_utilization = utilization
                    approach_used = config_name
                    placement_engine = engine  # Store the best engine
            
            placements = best_placements
            
            if verbose:
                print(f"\n  ✓ Best approach: {approach_used}")
                print(f"  ✓ Placed {len(placements)} / {len(boxes)} boxes ({best_utilization:.1f}% utilization)")
        else:
            # Single run with default configuration
            placement_engine = MultiStopPlacementEngine(
                container=trip.container,
                trip=trip,
                use_proportional_zones=self.use_proportional_zones
            )

            placements = placement_engine.place_boxes(
                boxes=boxes,
                allow_zone_overflow=self.allow_zone_overflow,
                accessibility_weight=self.accessibility_weight
            )

            if verbose:
                print(f"  ✓ Placed {len(placements)} / {len(boxes)} boxes")

        # Show zone utilization
        if verbose and placements and placement_engine:
            print()

        # PHASE 3: VALIDATION & UNLOAD PLANNING
        if verbose:
            print("PHASE 3: Validation & Unload Planning...")

        validator = MultiStopValidator(trip, trip.container)
        validation, unload_plans, stop_metrics = validator.validate_and_analyze(
            placements
        )

        if verbose:
            print(f"  ✓ Validation: {'PASSED' if validation.is_valid else 'FAILED'}")
            if validation.errors:
                for error in validation.errors:
                    print(f"    ✗ {error}")
            if validation.warnings:
                for warning in validation.warnings:
                    print(f"    ⚠ {warning}")

            total_rehandling = sum(p.rehandling_count for p in unload_plans.values())
            print(f"  ✓ Total rehandling events: {total_rehandling}")

            for stop_num, plan in sorted(unload_plans.items()):
                print(f"    Stop {stop_num}: {plan.total_items} items, "
                      f"{plan.rehandling_count} rehandling, "
                      f"accessibility {plan.accessibility_score:.0f}/100")
            print()

        # PHASE 4: BUILD RESULT
        solve_time = time.time() - start_time

        load_plan = MultiStopLoadPlan(
            trip=trip,
            placements=placements,
            unload_plans=unload_plans,
            stop_metrics=stop_metrics,
            is_valid=validation.is_valid,
            validation_errors=validation.errors,
            validation_warnings=validation.warnings,
            solve_time_seconds=solve_time,
            solver_metadata={
                'preprocessor': preprocess_metadata,
                'zone_utilization': placement_engine.get_zone_utilization(),
                'boxes_failed': len(boxes) - len(placements),
                'priority_weights': {
                    'stop_priority_base': self.priority_weights.stop_priority_base,
                    'stop_priority_multiplier': self.priority_weights.stop_priority_multiplier,
                    'fragile_bonus': self.priority_weights.fragile_bonus,
                    'heavy_item_bonus': self.priority_weights.heavy_item_bonus
                },
                'placement_config': {
                    'use_proportional_zones': self.use_proportional_zones,
                    'allow_zone_overflow': self.allow_zone_overflow,
                    'accessibility_weight': self.accessibility_weight
                }
            }
        )

        if verbose:
            print(f"{'='*70}")
            print(f"OPTIMIZATION COMPLETE")
            print(f"{'='*70}")
            print(f"Utilization: {load_plan.overall_utilization_pct:.1f}%")
            print(f"Items placed: {len(placements)} / {len(boxes)}")
            print(f"Total rehandling: {load_plan.total_rehandling_events} events")
            print(f"Rehandling cost: ${load_plan.total_rehandling_cost:.2f}")
            print(f"Valid: {'YES' if load_plan.is_valid else 'NO'}")
            print(f"Solve time: {solve_time:.2f}s")
            print(f"{'='*70}\n")

        return load_plan

    def optimize_with_alternatives(
        self,
        trip: Trip,
        sku_catalog: Dict[int, Box],
        verbose: bool = False
    ) -> List[MultiStopLoadPlan]:
        """
        Generate multiple alternative load plans with different strategies.

        Tries different configurations and returns all valid plans sorted
        by quality (minimizing rehandling, maximizing utilization).

        Args:
            trip: Trip specification
            sku_catalog: SKU catalog
            verbose: Print progress

        Returns:
            List of MultiStopLoadPlan sorted by quality (best first)
        """
        if verbose:
            print("Generating alternative load plans...\n")

        alternatives = []

        # Configuration 1: Proportional zones, strict accessibility
        config1 = MultiStopOptimizer(
            priority_weights=self.priority_weights,
            use_proportional_zones=True,
            allow_zone_overflow=False,
            accessibility_weight=0.8
        )
        try:
            plan1 = config1.optimize(trip, sku_catalog, verbose=False)
            alternatives.append(('Proportional/Strict', plan1))
        except Exception as e:
            if verbose:
                print(f"Config 1 failed: {e}")

        # Configuration 2: Proportional zones, flexible
        config2 = MultiStopOptimizer(
            priority_weights=self.priority_weights,
            use_proportional_zones=True,
            allow_zone_overflow=True,
            accessibility_weight=0.5
        )
        try:
            plan2 = config2.optimize(trip, sku_catalog, verbose=False)
            alternatives.append(('Proportional/Flexible', plan2))
        except Exception as e:
            if verbose:
                print(f"Config 2 failed: {e}")

        # Configuration 3: Equal zones, high accessibility
        config3 = MultiStopOptimizer(
            priority_weights=self.priority_weights,
            use_proportional_zones=False,
            allow_zone_overflow=True,
            accessibility_weight=0.7
        )
        try:
            plan3 = config3.optimize(trip, sku_catalog, verbose=False)
            alternatives.append(('Equal/Accessible', plan3))
        except Exception as e:
            if verbose:
                print(f"Config 3 failed: {e}")

        # Sort by quality score
        def quality_score(plan: MultiStopLoadPlan) -> float:
            """
            Calculate quality score (higher is better).

            Factors:
            - Utilization (40%)
            - Negative rehandling penalty (30%)
            - Validity (20%)
            - Accessibility (10%)
            """
            score = 0.0

            # Utilization
            score += plan.overall_utilization_pct * 0.4

            # Rehandling penalty
            rehandling_penalty = min(plan.total_rehandling_events * 2.0, 30.0)
            score -= rehandling_penalty * 0.3

            # Validity bonus
            if plan.is_valid:
                score += 20.0

            # Accessibility (average across stops)
            if plan.unload_plans:
                avg_access = sum(
                    p.accessibility_score for p in plan.unload_plans.values()
                ) / len(plan.unload_plans)
                score += avg_access * 0.1

            return score

        alternatives.sort(key=lambda x: quality_score(x[1]), reverse=True)

        if verbose:
            print(f"\nGenerated {len(alternatives)} alternative plans:")
            for i, (name, plan) in enumerate(alternatives, 1):
                print(f"{i}. {name}:")
                print(f"   Utilization: {plan.overall_utilization_pct:.1f}%")
                print(f"   Rehandling: {plan.total_rehandling_events} events")
                print(f"   Valid: {plan.is_valid}")
                print(f"   Quality: {quality_score(plan):.1f}")
                print()

        return [plan for _, plan in alternatives]


def quick_optimize(
    trip: Trip,
    sku_catalog: Dict[int, Box],
    verbose: bool = True,
    multi_algorithm: bool = False
) -> MultiStopLoadPlan:
    """
    Convenience function for quick optimization with defaults.

    Args:
        trip: Trip specification
        sku_catalog: SKU catalog
        verbose: Print progress
        multi_algorithm: Run comprehensive 7-phase multi-algorithm approach

    Returns:
        MultiStopLoadPlan
    """
    optimizer = MultiStopOptimizer()
    return optimizer.optimize(trip, sku_catalog, verbose=verbose, multi_algorithm=multi_algorithm)
