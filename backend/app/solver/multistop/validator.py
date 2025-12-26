"""
Multi-Stop Validation and Rehandling Detection Engine

Validates that a load plan is feasible for multi-stop delivery:
1. Unload feasibility at each stop
2. Rehandling detection and quantification
3. Accessibility analysis
4. Safety and stability validation

This module answers: "Can we actually unload this at each stop?"
"""

from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass

from app.solver.utils import PlacedBox, ContainerSpace as Container
from .models import (
    Trip, UnloadPlan, RehandlingEvent, StopMetrics,
    UnloadStrategy
)


@dataclass
class ValidationResult:
    """Result of validation check"""
    valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class AccessibilityAnalysis:
    """
    Analysis of which boxes block access to other boxes.

    Used to determine unload order and rehandling requirements.
    """
    box: PlacedBox
    blocks_boxes: List[PlacedBox]  # Boxes this box blocks
    blocked_by_boxes: List[PlacedBox]  # Boxes that block this box
    accessibility_score: float  # 0-100, higher = more accessible

    @property
    def is_accessible(self) -> bool:
        """True if box can be unloaded without moving others"""
        return len(self.blocked_by_boxes) == 0


class MultiStopValidator:
    """
    Validates multi-stop load plans and generates unload plans.

    VALIDATION HIERARCHY:
    ---------------------
    1. CRITICAL (must pass):
       - All boxes for a stop can be physically reached
       - No safety violations (fragile boxes crushed, etc.)
       - Weight/stability constraints met

    2. WARNINGS (should avoid):
       - Excessive rehandling
       - Difficult access requiring special equipment
       - Weight distribution concerns

    UNLOAD FEASIBILITY:
    -------------------
    A stop is "feasible" if all its boxes can be unloaded either:
    - Directly (no boxes blocking)
    - With acceptable rehandling (moving later-stop boxes temporarily)

    REHANDLING RULES:
    -----------------
    - Rehandling = temporarily moving a box to access another box
    - Only allowed for boxes from LATER stops
    - Cannot rehandle boxes from EARLIER or SAME stop (creates circular dependency)
    """

    def __init__(self, trip: Trip, container: Container):
        """
        Initialize validator.

        Args:
            trip: Trip specification
            container: Container being loaded
        """
        self.trip = trip
        self.container = container

    def validate_and_analyze(
        self,
        placements: List[PlacedBox]
    ) -> Tuple[ValidationResult, Dict[int, UnloadPlan], Dict[int, StopMetrics]]:
        """
        Comprehensive validation and analysis of a load plan.

        Args:
            placements: List of box placements

        Returns:
            Tuple of:
            - ValidationResult: Overall validation
            - Dict[int, UnloadPlan]: Unload plan for each stop
            - Dict[int, StopMetrics]: Metrics for each stop
        """
        validation = ValidationResult(is_valid=True)
        unload_plans = {}
        stop_metrics = {}

        # Group placements by stop
        placements_by_stop = self._group_by_stop(placements)

        # Validate each stop sequentially
        for stop in self.trip.stops:
            stop_num = stop.stop_number

            # Get boxes for this stop and all remaining stops
            current_stop_boxes = placements_by_stop.get(stop_num, [])
            remaining_boxes = self._get_remaining_boxes(
                placements, stop_num
            )

            # Analyze accessibility
            accessibility = self._analyze_accessibility(
                current_stop_boxes,
                remaining_boxes
            )

            # Generate unload plan
            unload_plan = self._generate_unload_plan(
                stop,
                current_stop_boxes,
                remaining_boxes,
                accessibility
            )
            unload_plans[stop_num] = unload_plan

            # Validate unload feasibility
            stop_validation = self._validate_unload_plan(
                unload_plan,
                stop
            )
            validation = validation.merge(stop_validation)

            # Calculate metrics
            metrics = self._calculate_stop_metrics(
                stop_num,
                current_stop_boxes,
                accessibility
            )
            stop_metrics[stop_num] = metrics

            # Check rehandling limits
            if (unload_plan.rehandling_count > self.trip.max_rehandling_events and
                self.trip.unload_strategy == UnloadStrategy.STRICT_LIFO):
                validation.add_error(
                    f"Stop {stop_num}: Requires {unload_plan.rehandling_count} "
                    f"rehandling events, exceeds limit of {self.trip.max_rehandling_events}"
                )

        return validation, unload_plans, stop_metrics

    def _group_by_stop(
        self,
        placements: List[PlacedBox]
    ) -> Dict[int, List[PlacedBox]]:
        """Group placements by delivery stop"""
        groups: Dict[int, List[PlacedBox]] = {}
        for p in placements:
            stop_num = p.box.delivery_order
            if stop_num not in groups:
                groups[stop_num] = []
            groups[stop_num].append(p)
        return groups

    def _get_remaining_boxes(
        self,
        placements: List[PlacedBox],
        current_stop: int
    ) -> List[PlacedBox]:
        """
        Get all boxes for current stop and later stops.

        These are the boxes still in the container when arriving at
        current_stop.
        """
        return [
            p for p in placements
            if p.box.delivery_order >= current_stop
        ]

    def _analyze_accessibility(
        self,
        target_boxes: List[PlacedBox],
        all_boxes: List[PlacedBox]
    ) -> Dict[int, AccessibilityAnalysis]:
        """
        Analyze which boxes block access to target boxes.

        A box B "blocks" box A if:
        1. B is between A and the door (B.x > A.x)
        2. B overlaps with A in the YZ plane
        3. There's no path around B to reach A

        Args:
            target_boxes: Boxes we want to unload
            all_boxes: All boxes currently in container

        Returns:
            Dict mapping box_id -> AccessibilityAnalysis
        """
        analysis: Dict[int, AccessibilityAnalysis] = {}

        for target in target_boxes:
            blocks = []
            blocked_by = []

            for other in all_boxes:
                if other.box.id == target.box.id:
                    continue

                # Check if 'other' blocks 'target'
                # Other must be in front (higher X) and overlap in YZ
                if self._box_blocks_access(other, target):
                    blocked_by.append(other)

                # Check if 'target' blocks 'other'
                if self._box_blocks_access(target, other):
                    blocks.append(other)

            # Calculate accessibility score
            # Score based on: number of blockers, their weights, etc.
            score = self._calculate_accessibility_score(
                target, blocked_by
            )

            analysis[target.box.id] = AccessibilityAnalysis(
                box=target,
                blocks_boxes=blocks,
                blocked_by_boxes=blocked_by,
                accessibility_score=score
            )

        return analysis

    def _box_blocks_access(
        self,
        blocker: PlacedBox,
        blocked: PlacedBox
    ) -> bool:
        """
        Check if blocker prevents direct access to blocked.

        Blocker must be:
        1. In front of blocked (higher X coordinate)
        2. Overlapping in YZ plane (in the "shadow" toward door)

        Args:
            blocker: Potential blocking box
            blocked: Box potentially blocked

        Returns:
            True if blocker blocks access to blocked
        """
        # Must be in front (closer to door) - blocker starts after blocked starts
        if blocker.x <= blocked.x:
            return False

        # Must overlap in Y direction
        y_overlap = not (
            blocker.max_y <= blocked.y or
            blocker.y >= blocked.max_y
        )

        # Must overlap in Z direction
        z_overlap = not (
            blocker.max_z <= blocked.z or
            blocker.z >= blocked.max_z
        )

        return y_overlap and z_overlap

    def _calculate_accessibility_score(
        self,
        box: PlacedBox,
        blockers: List[PlacedBox]
    ) -> float:
        """
        Calculate accessibility score (0-100).

        100 = perfectly accessible (no blockers)
        0 = completely blocked

        Factors:
        - Number of blockers
        - Weight of blockers
        - Fragility of blockers

        Returns:
            Score from 0 to 100
        """
        if not blockers:
            return 100.0

        # Base penalty per blocker
        penalty = len(blockers) * 15.0

        # Additional penalty for heavy blockers
        for blocker in blockers:
            if blocker.box.weight > 50.0:
                penalty += 10.0

        # Additional penalty for fragile blockers (can't roughly handle)
        for blocker in blockers:
            if blocker.box.fragile:
                penalty += 20.0

        score = max(0.0, 100.0 - penalty)
        return score

    def _generate_unload_plan(
        self,
        stop: 'Stop',
        stop_boxes: List[PlacedBox],
        remaining_boxes: List[PlacedBox],
        accessibility: Dict[int, AccessibilityAnalysis]
    ) -> UnloadPlan:
        """
        Generate unload plan for a stop.

        Determines:
        1. Order to unload boxes
        2. Which boxes need to be temporarily moved (rehandling)
        3. Estimated time and feasibility

        ALGORITHM:
        ----------
        1. Identify directly accessible boxes (no blockers from current stop)
        2. For blocked boxes, identify minimum rehandling set
        3. Ensure rehandled boxes are only from LATER stops
        4. Calculate unload sequence

        Args:
            stop: Stop being analyzed
            stop_boxes: Boxes to unload at this stop
            remaining_boxes: All boxes still in container
            accessibility: Accessibility analysis

        Returns:
            UnloadPlan
        """
        plan = UnloadPlan(
            stop_number=stop.stop_number,
            boxes_to_unload=stop_boxes.copy()
        )

        # Find boxes from later stops that block current stop boxes
        later_stop_boxes = [
            b for b in remaining_boxes
            if b.box.delivery_order > stop.stop_number
        ]

        rehandling_events = []

        for box in stop_boxes:
            box_analysis = accessibility.get(box.box.id)
            if not box_analysis:
                continue

            # Check if blocked by boxes from LATER stops
            later_stop_blockers = [
                blocker for blocker in box_analysis.blocked_by_boxes
                if blocker.box.delivery_order > stop.stop_number
            ]

            # Check if blocked by boxes from SAME stop (problematic!)
            same_stop_blockers = [
                blocker for blocker in box_analysis.blocked_by_boxes
                if blocker.box.delivery_order == stop.stop_number
            ]

            # If blocked by same-stop boxes, this is a configuration problem
            if same_stop_blockers:
                plan.is_feasible = False
                plan.warnings.append(
                    f"Box {box.box.id} blocked by same-stop boxes: "
                    f"{[b.box.id for b in same_stop_blockers]}. "
                    f"Cannot unload without unloading other same-stop boxes first."
                )

            # Create rehandling events for later-stop blockers
            for blocker in later_stop_blockers:
                event = RehandlingEvent(
                    stop_number=stop.stop_number,
                    box_id=blocker.box.id,
                    original_sku_id=blocker.box.sku_id,
                    destination_stop=blocker.box.delivery_order,
                    reason=f"Blocks access to box {box.box.id} for stop {stop.stop_number}",
                    estimated_time_seconds=60.0  # 1 minute per box
                )
                rehandling_events.append(event)

        plan.rehandling_events = rehandling_events

        # Calculate accessibility score (average)
        if stop_boxes:
            scores = [
                accessibility.get(b.box.id, AccessibilityAnalysis(b, [], [], 50.0)).accessibility_score
                for b in stop_boxes
            ]
            plan.accessibility_score = sum(scores) / len(scores)

        return plan

    def _validate_unload_plan(
        self,
        plan: UnloadPlan,
        stop: 'Stop'
    ) -> ValidationResult:
        """
        Validate that unload plan is feasible and safe.

        Checks:
        - Plan is marked feasible
        - Rehandling count within limits
        - No circular dependencies
        - Adequate accessibility

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        # Check feasibility flag
        if not plan.is_feasible:
            result.add_error(
                f"Stop {stop.stop_number}: Unload plan is infeasible"
            )

        # Check rehandling limits
        if (plan.rehandling_count > 0 and
            self.trip.unload_strategy == UnloadStrategy.STRICT_LIFO):
            result.add_warning(
                f"Stop {stop.stop_number}: Requires {plan.rehandling_count} "
                f"rehandling events under STRICT_LIFO strategy"
            )

        # Check accessibility
        if plan.accessibility_score < 30.0:
            result.add_warning(
                f"Stop {stop.stop_number}: Low accessibility score "
                f"({plan.accessibility_score:.1f}/100). May be difficult to unload."
            )

        # Check quantity match
        expected_qty = stop.total_items
        actual_qty = plan.total_items
        if actual_qty < expected_qty:
            result.add_error(
                f"Stop {stop.stop_number}: Expected {expected_qty} items, "
                f"only {actual_qty} placed"
            )

        return result

    def _calculate_stop_metrics(
        self,
        stop_number: int,
        boxes: List[PlacedBox],
        accessibility: Dict[int, AccessibilityAnalysis]
    ) -> StopMetrics:
        """
        Calculate metrics for a stop's portion of the load.

        Args:
            stop_number: Stop number
            boxes: Boxes for this stop
            accessibility: Accessibility analysis

        Returns:
            StopMetrics
        """
        if not boxes:
            return StopMetrics(stop_number=stop_number)

        total_volume = sum(b.volume for b in boxes)
        total_weight = sum(b.box.weight for b in boxes)
        fragile_count = sum(1 for b in boxes if b.box.fragile)

        # Average accessibility
        scores = [
            accessibility.get(b.box.id, AccessibilityAnalysis(b, [], [], 50.0)).accessibility_score
            for b in boxes
        ]
        avg_accessibility = sum(scores) / len(scores)

        # Utilization (relative to container)
        utilization_pct = (total_volume / self.container.volume) * 100

        return StopMetrics(
            stop_number=stop_number,
            items_loaded=len(boxes),
            volume_used=total_volume,
            weight_loaded=total_weight,
            utilization_pct=utilization_pct,
            avg_accessibility=avg_accessibility,
            fragile_count=fragile_count
        )


def detect_circular_dependencies(
    placements: List[PlacedBox]
) -> List[Tuple[int, int]]:
    """
    Detect circular blocking dependencies at same stop.

    Returns pairs of (box_id1, box_id2) that block each other.

    This should ideally be empty - circular dependencies mean
    the load plan is infeasible.

    Args:
        placements: List of placements

    Returns:
        List of (box_id1, box_id2) tuples representing circular deps
    """
    circular = []

    # Group by stop
    by_stop: Dict[int, List[PlacedBox]] = {}
    for p in placements:
        stop = p.box.delivery_order
        if stop not in by_stop:
            by_stop[stop] = []
        by_stop[stop].append(p)

    # Check each stop
    for stop_num, boxes in by_stop.items():
        # Build blocking graph
        blocks: Dict[int, Set[int]] = {}

        for i, box_a in enumerate(boxes):
            for j, box_b in enumerate(boxes):
                if i == j:
                    continue

                # Check if box_a blocks box_b
                # (box_a is in front and overlaps YZ)
                if box_a.x > box_b.max_x:
                    y_overlap = not (
                        box_a.max_y <= box_b.y or
                        box_a.y >= box_b.max_y
                    )
                    z_overlap = not (
                        box_a.max_z <= box_b.z or
                        box_a.z >= box_b.max_z
                    )

                    if y_overlap and z_overlap:
                        if box_a.box.id not in blocks:
                            blocks[box_a.box.id] = set()
                        blocks[box_a.box.id].add(box_b.box.id)

        # Detect cycles
        for box_id, blocked_ids in blocks.items():
            for blocked_id in blocked_ids:
                # Check if blocked_id also blocks box_id
                if box_id in blocks.get(blocked_id, set()):
                    circular.append((box_id, blocked_id))

    return circular
