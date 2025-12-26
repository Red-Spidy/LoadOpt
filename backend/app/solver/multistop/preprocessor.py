"""
Pre-Processing Engine for Multi-Stop Load Planning

Handles:
1. Splitting SKUs across multiple stops into Virtual SKUs
2. Computing priority scores based on stop order, fragility, weight, SLA
3. Assigning delivery_order to boxes for placement algorithm
4. Creating box instances from SKU specifications

This is the critical first step that transforms the trip specification
into a format suitable for the 3D bin-packing algorithm.
"""

from typing import List, Dict, Tuple, Set
from dataclasses import dataclass

from app.solver.utils import Box
from .models import Trip, Stop, VirtualSKU, StopType


@dataclass
class PriorityWeights:
    """
    Configurable weights for priority score calculation.

    These weights determine the relative importance of different factors
    when deciding load order. Higher weight = more important.
    """
    # Stop-based weights
    stop_priority_base: float = 1000.0  # Earlier stops get higher priority
    stop_priority_multiplier: float = 100.0  # Penalty per stop number

    # Physical property weights
    fragile_bonus: float = 500.0  # Fragile items loaded first (near door)
    heavy_weight_threshold: float = 50.0  # kg
    heavy_item_bonus: float = 200.0  # Heavy items lower/earlier
    non_stackable_penalty: float = 300.0  # Non-stackable must go on floor

    # SLA and criticality weights
    time_critical_bonus: float = 800.0  # Time-critical stops prioritized
    sla_priority_weight: float = 100.0  # User-defined priority amplifier

    # Weight distribution factor
    weight_factor: float = 1.0  # Linear weight factor (kg)


class MultiStopPreprocessor:
    """
    Preprocesses trip data into optimized box list with priorities.

    WORKFLOW:
    1. Analyze trip to find SKUs appearing at multiple stops
    2. Create Virtual SKUs for each SKU-stop combination
    3. Compute priority scores using multi-factor algorithm
    4. Generate box instances with proper delivery_order and priorities
    5. Return sorted box list ready for 3D placement

    WHY THIS APPROACH:
    - Virtual SKUs allow tracking which boxes go to which stops
    - Priority scores encode operational reality (LIFO, fragility, weight)
    - Deterministic and explainable (no black box)
    - Auditable by operations teams
    """

    def __init__(self, weights: PriorityWeights = None):
        """
        Initialize preprocessor with configurable weights.

        Args:
            weights: Priority calculation weights (uses defaults if None)
        """
        self.weights = weights or PriorityWeights()

    def preprocess_trip(
        self,
        trip: Trip,
        sku_catalog: Dict[int, Box]
    ) -> Tuple[List[Box], List[VirtualSKU], Dict[str, any]]:
        """
        Preprocess a trip into a prioritized box list.

        Args:
            trip: Trip specification with stops
            sku_catalog: Mapping of sku_id -> Box template

        Returns:
            Tuple of:
            - List[Box]: All box instances, sorted by priority (high to low)
            - List[VirtualSKU]: Virtual SKUs created
            - Dict: Preprocessing metadata and statistics

        Raises:
            ValueError: If SKU catalog missing required SKUs
        """
        # Step 1: Validate that all required SKUs exist
        self._validate_sku_catalog(trip, sku_catalog)

        # Step 2: Create Virtual SKUs by splitting multi-stop SKUs
        virtual_skus = self._create_virtual_skus(trip, sku_catalog)

        # Step 3: Compute priority scores for each virtual SKU
        self._compute_priority_scores(trip, virtual_skus)

        # Step 4: Generate box instances from virtual SKUs
        boxes = self._generate_box_instances(virtual_skus)

        # Step 5: Sort boxes by priority (highest first)
        boxes.sort(key=lambda b: b.priority, reverse=True)

        # Step 6: Collect metadata
        metadata = self._collect_metadata(trip, virtual_skus, boxes)

        return boxes, virtual_skus, metadata

    def _validate_sku_catalog(self, trip: Trip, sku_catalog: Dict[int, Box]):
        """
        Validate that all SKUs in trip exist in catalog.

        Raises:
            ValueError: If any required SKU is missing
        """
        required_skus = trip.all_sku_ids
        missing_skus = required_skus - set(sku_catalog.keys())

        if missing_skus:
            raise ValueError(
                f"SKU catalog missing required SKUs: {sorted(missing_skus)}"
            )

    def _create_virtual_skus(
        self,
        trip: Trip,
        sku_catalog: Dict[int, Box]
    ) -> List[VirtualSKU]:
        """
        Create Virtual SKUs by splitting real SKUs across stops.

        LOGIC:
        - For each SKU, find all stops where it appears
        - Create one Virtual SKU per (SKU, Stop) combination
        - Virtual SKU gets quantity specific to that stop

        Example:
            SKU #10 appears at:
            - Stop 1: qty 5
            - Stop 3: qty 2
            Creates:
            - VirtualSKU(sku=10, stop=1, qty=5)
            - VirtualSKU(sku=10, stop=3, qty=2)

        Returns:
            List of Virtual SKUs
        """
        virtual_skus = []

        for stop in trip.stops:
            for sku_id, quantity in stop.sku_requirements.items():
                base_box = sku_catalog[sku_id]

                # Use original_delivery_order if available, otherwise fall back to stop_number
                delivery_order = stop.original_delivery_order if stop.original_delivery_order is not None else stop.stop_number

                virtual_sku = VirtualSKU(
                    virtual_id=f"V{sku_id}_S{stop.stop_number}",
                    original_sku_id=sku_id,
                    stop_number=delivery_order,  # Use original delivery_order for box matching
                    quantity=quantity,
                    base_box=base_box,
                    priority_score=0.0  # Computed next
                )
                virtual_skus.append(virtual_sku)

        return virtual_skus

    def _compute_priority_scores(
        self,
        trip: Trip,
        virtual_skus: List[VirtualSKU]
    ):
        """
        Compute priority scores for each Virtual SKU.

        PRIORITY FORMULA:
        ================

        Priority = StopPriority
                 + FragilityBonus
                 + HeavyItemBonus
                 + NonStackablePenalty
                 + TimeCriticalBonus
                 + SLAPriority
                 + WeightFactor

        RATIONALE:
        ----------

        1. **StopPriority** (MOST IMPORTANT):
           - Earlier stops MUST be near the door (high X position in container)
           - Formula: base - (stop_number * multiplier)
           - Stop 1: 1000 - (1 * 100) = 900
           - Stop 2: 1000 - (2 * 100) = 800
           - Stop 3: 1000 - (3 * 100) = 700
           - NOTE: These scores are used for TIE-BREAKING only
           - PRIMARY sort key is delivery_order (see core.py)
           - LIFO: High delivery_order loads first (back) → unloads last
           - Example: Stop 3 boxes placed first (deep in truck)

        2. **FragilityBonus**:
           - Fragile items can't have weight on top
           - Load them first so they end up accessible/on top
           - Bonus: +500

        3. **HeavyItemBonus**:
           - Heavy items should be low and stable
           - Loading earlier puts them deeper/lower
           - Bonus: +200 if weight > threshold

        4. **NonStackablePenalty**:
           - Non-stackable items MUST be on floor
           - Penalty ensures they're placed early (on floor)
           - Penalty: +300 (higher priority = earlier placement)

        5. **TimeCriticalBonus**:
           - Time-critical stops need easy access
           - Bonus: +800

        6. **SLAPriority**:
           - User-defined priority from box
           - Amplified by weight

        7. **WeightFactor**:
           - Linear factor based on weight
           - Helps with weight distribution

        This multi-factor approach is:
        - Deterministic (same input = same output)
        - Explainable (each factor has clear operational meaning)
        - Tunable (weights can be adjusted per customer)
        """
        w = self.weights

        for vsku in virtual_skus:
            box = vsku.base_box
            stop = trip.get_stop(vsku.stop_number)

            # Start with base score
            score = 0.0

            # 1. STOP PRIORITY (most important - determines LIFO order)
            # Earlier stops get HIGHER priority (loaded LAST, near door)
            stop_priority = w.stop_priority_base - (vsku.stop_number * w.stop_priority_multiplier)
            score += stop_priority

            # 2. FRAGILITY BONUS
            # Fragile items loaded later (higher priority) so they're on top/accessible
            if box.fragile:
                score += w.fragile_bonus

            # 3. HEAVY ITEM BONUS
            # Heavy items loaded earlier (higher priority) so they're low/stable
            if box.weight >= w.heavy_weight_threshold:
                score += w.heavy_item_bonus

            # 4. NON-STACKABLE PENALTY (actually a bonus to prioritize early)
            # Non-stackable must be on floor, so load early
            if box.max_stack == 0:
                score += w.non_stackable_penalty

            # 5. TIME CRITICAL BONUS
            # Time-critical stops need easy access
            if stop and stop.is_time_critical:
                score += w.time_critical_bonus

            # 6. SLA PRIORITY
            # User-defined priority (amplified)
            score += box.priority * w.sla_priority_weight

            # 7. WEIGHT FACTOR
            # Linear weight contribution
            score += box.weight * w.weight_factor

            # Store computed score
            vsku.priority_score = score

    def _generate_box_instances(
        self,
        virtual_skus: List[VirtualSKU]
    ) -> List[Box]:
        """
        Generate individual Box instances from Virtual SKUs.

        Each Virtual SKU with quantity N generates N box instances,
        each with the computed priority and delivery_order.

        Args:
            virtual_skus: List of Virtual SKUs

        Returns:
            List of Box instances
        """
        boxes = []
        global_box_id = 1

        for vsku in virtual_skus:
            for instance_idx in range(vsku.quantity):
                # Create a new box instance based on the template
                box = Box(
                    id=global_box_id,
                    sku_id=vsku.original_sku_id,
                    instance_index=instance_idx,
                    length=vsku.base_box.length,
                    width=vsku.base_box.width,
                    height=vsku.base_box.height,
                    weight=vsku.base_box.weight,
                    fragile=vsku.base_box.fragile,
                    max_stack=vsku.base_box.max_stack,
                    stacking_group=vsku.base_box.stacking_group,
                    allowed_rotations=vsku.base_box.allowed_rotations.copy(),
                    priority=int(vsku.priority_score),  # Use computed priority
                    delivery_order=vsku.stop_number,  # CRITICAL: which stop
                    load_bearing_capacity=vsku.base_box.load_bearing_capacity,
                    color=vsku.base_box.color,
                    name=vsku.base_box.name or f"SKU-{vsku.original_sku_id}"
                )
                boxes.append(box)
                global_box_id += 1

        return boxes

    def _collect_metadata(
        self,
        trip: Trip,
        virtual_skus: List[VirtualSKU],
        boxes: List[Box]
    ) -> Dict[str, any]:
        """
        Collect preprocessing statistics and metadata.

        Returns:
            Dictionary with preprocessing information
        """
        # Analyze stop distribution
        stop_distribution = {}
        for stop in trip.stops:
            stop_boxes = [b for b in boxes if b.delivery_order == stop.stop_number]
            stop_distribution[stop.stop_number] = {
                'location': stop.location_name,
                'box_count': len(stop_boxes),
                'total_weight': sum(b.weight for b in stop_boxes),
                'total_volume': sum(b.volume for b in stop_boxes),
                'fragile_count': sum(1 for b in stop_boxes if b.fragile),
                'unique_skus': len(set(b.sku_id for b in stop_boxes))
            }

        # Identify multi-stop SKUs
        sku_stop_map = trip.get_sku_stop_map()
        multi_stop_skus = {
            sku_id: stops for sku_id, stops in sku_stop_map.items()
            if len(stops) > 1
        }

        return {
            'total_boxes': len(boxes),
            'total_virtual_skus': len(virtual_skus),
            'unique_real_skus': len(trip.all_sku_ids),
            'multi_stop_skus': multi_stop_skus,
            'stop_distribution': stop_distribution,
            'priority_range': {
                'min': min(b.priority for b in boxes) if boxes else 0,
                'max': max(b.priority for b in boxes) if boxes else 0,
                'avg': sum(b.priority for b in boxes) / len(boxes) if boxes else 0
            },
            'weights_used': {
                'stop_priority_base': self.weights.stop_priority_base,
                'stop_priority_multiplier': self.weights.stop_priority_multiplier,
                'fragile_bonus': self.weights.fragile_bonus,
                'heavy_item_bonus': self.weights.heavy_item_bonus,
                'time_critical_bonus': self.weights.time_critical_bonus
            }
        }


def explain_priority_calculation(
    virtual_sku: VirtualSKU,
    stop: Stop,
    weights: PriorityWeights
) -> Dict[str, any]:
    """
    Explain how priority was calculated for a virtual SKU.

    Useful for debugging and auditing.

    Args:
        virtual_sku: The virtual SKU
        stop: The stop it belongs to
        weights: Weights used

    Returns:
        Dictionary breaking down priority components
    """
    box = virtual_sku.base_box
    components = {}

    # Stop priority
    stop_score = weights.stop_priority_base - (virtual_sku.stop_number * weights.stop_priority_multiplier)
    components['stop_priority'] = {
        'value': stop_score,
        'calculation': f"{weights.stop_priority_base} - ({virtual_sku.stop_number} × {weights.stop_priority_multiplier})"
    }

    # Fragility
    if box.fragile:
        components['fragile_bonus'] = {
            'value': weights.fragile_bonus,
            'reason': 'Box is fragile - needs to be accessible'
        }

    # Heavy item
    if box.weight >= weights.heavy_weight_threshold:
        components['heavy_item_bonus'] = {
            'value': weights.heavy_item_bonus,
            'reason': f'Box weight {box.weight}kg exceeds threshold {weights.heavy_weight_threshold}kg'
        }

    # Non-stackable
    if box.max_stack == 0:
        components['non_stackable_penalty'] = {
            'value': weights.non_stackable_penalty,
            'reason': 'Non-stackable items must go on floor (early placement)'
        }

    # Time critical
    if stop.is_time_critical:
        components['time_critical_bonus'] = {
            'value': weights.time_critical_bonus,
            'reason': 'Stop is time-critical'
        }

    # SLA priority
    sla_score = box.priority * weights.sla_priority_weight
    components['sla_priority'] = {
        'value': sla_score,
        'calculation': f"{box.priority} × {weights.sla_priority_weight}"
    }

    # Weight factor
    weight_score = box.weight * weights.weight_factor
    components['weight_factor'] = {
        'value': weight_score,
        'calculation': f"{box.weight} × {weights.weight_factor}"
    }

    total = sum(c['value'] for c in components.values())

    return {
        'virtual_sku_id': virtual_sku.virtual_id,
        'stop_number': virtual_sku.stop_number,
        'components': components,
        'total_priority': total,
        'final_priority': virtual_sku.priority_score
    }
