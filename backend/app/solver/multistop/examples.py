"""
Multi-Stop Load Planning Examples

Demonstrates the multi-stop optimizer with various real-world scenarios.

SCENARIOS COVERED:
1. Simple 2-stop delivery (unique SKUs per stop)
2. Complex 3-stop with SKU overlap
3. Split quantities (same SKU at multiple stops)
4. Fragile items at early stop
5. Heavy concentrated load
6. Time-critical delivery
7. Strict zero-rehandling requirement
8. Pickup + delivery route
"""

from typing import Dict
from app.solver.utils import Box, ContainerSpace as Container
from .models import Trip, Stop, StopType, UnloadStrategy
from .optimizer import MultiStopOptimizer, quick_optimize


# =============================================================================
# EXAMPLE 1: Simple 2-Stop Route
# =============================================================================

def example_1_simple_two_stop():
    """
    SCENARIO: Simple 2-stop delivery
    - Stop 1: 10 boxes of SKU A (small)
    - Stop 2: 15 boxes of SKU B (large)
    - No overlap, clean separation

    EXPECTED RESULT:
    - SKU A near door (high X)
    - SKU B in back (low X)
    - Zero rehandling
    - High utilization
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Simple 2-Stop Route")
    print("="*70)

    # Container: Standard 20ft container
    container = Container(
        length=589,  # cm (20ft)
        width=235,
        height=239,
        max_weight=28000,  # kg
        door_width=235,
        door_height=239,
        name="20ft Container"
    )

    # SKU Catalog
    sku_catalog = {
        1: Box(  # SKU A - Small boxes
            id=1,
            sku_id=1,
            instance_index=0,
            length=50,
            width=40,
            height=30,
            weight=10,
            name="Small Box A",
            color="#3B82F6"
        ),
        2: Box(  # SKU B - Large boxes
            id=2,
            sku_id=2,
            instance_index=0,
            length=100,
            width=80,
            height=60,
            weight=25,
            name="Large Box B",
            color="#10B981"
        )
    }

    # Define stops
    stops = [
        Stop(
            stop_number=1,
            location_id="CUST-001",
            location_name="Customer A - Downtown",
            sku_requirements={1: 10}  # 10 of SKU A
        ),
        Stop(
            stop_number=2,
            location_id="CUST-002",
            location_name="Customer B - Warehouse District",
            sku_requirements={2: 15}  # 15 of SKU B
        )
    ]

    # Create trip
    trip = Trip(
        trip_id="TRIP-001",
        stops=stops,
        container=container,
        unload_strategy=UnloadStrategy.MINIMAL_REHANDLING
    )

    # Optimize
    result = quick_optimize(trip, sku_catalog, verbose=True)

    # Analysis
    print("\n📊 ANALYSIS:")
    print(f"   Valid plan: {result.is_valid}")
    print(f"   Utilization: {result.overall_utilization_pct:.1f}%")
    print(f"   Rehandling events: {result.total_rehandling_events}")

    return result


# =============================================================================
# EXAMPLE 2: Complex 3-Stop with SKU Overlap
# =============================================================================

def example_2_complex_overlap():
    """
    SCENARIO: 3-stop route with overlapping SKUs
    - Stop 1: SKU A (qty 5), SKU B (qty 3)
    - Stop 2: SKU A (qty 2), SKU C (qty 4)
    - Stop 3: SKU B (qty 2), SKU C (qty 5)

    CHALLENGE:
    - SKU A appears at stops 1 and 2
    - SKU B appears at stops 1 and 3
    - SKU C appears at stops 2 and 3

    EXPECTED:
    - Virtual SKUs created for each SKU-stop combination
    - Stop 1 items near door
    - Stop 3 items in back
    - Minimal rehandling due to proper priority sorting
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Complex 3-Stop with SKU Overlap")
    print("="*70)

    container = Container(
        length=589,
        width=235,
        height=239,
        max_weight=28000,
        door_width=235,
        door_height=239,
        name="20ft Container"
    )

    sku_catalog = {
        10: Box(
            id=10, sku_id=10, instance_index=0,
            length=60, width=50, height=40, weight=15,
            name="Product A", color="#3B82F6"
        ),
        20: Box(
            id=20, sku_id=20, instance_index=0,
            length=80, width=60, height=50, weight=20,
            name="Product B", color="#10B981"
        ),
        30: Box(
            id=30, sku_id=30, instance_index=0,
            length=70, width=55, height=45, weight=18,
            name="Product C", color="#F59E0B"
        )
    }

    stops = [
        Stop(
            stop_number=1,
            location_id="LOC-A",
            location_name="First Delivery",
            sku_requirements={10: 5, 20: 3}
        ),
        Stop(
            stop_number=2,
            location_id="LOC-B",
            location_name="Second Delivery",
            sku_requirements={10: 2, 30: 4}
        ),
        Stop(
            stop_number=3,
            location_id="LOC-C",
            location_name="Third Delivery",
            sku_requirements={20: 2, 30: 5}
        )
    ]

    trip = Trip(
        trip_id="TRIP-002",
        stops=stops,
        container=container,
        unload_strategy=UnloadStrategy.MINIMAL_REHANDLING
    )

    result = quick_optimize(trip, sku_catalog, verbose=True)

    # Detailed analysis
    print("\n📊 SKU DISTRIBUTION ANALYSIS:")
    metadata = result.solver_metadata['preprocessor']
    print(f"   Multi-stop SKUs: {metadata['multi_stop_skus']}")
    print(f"   Virtual SKUs created: {metadata['total_virtual_skus']}")

    return result


# =============================================================================
# EXAMPLE 3: Fragile Items at Early Stop
# =============================================================================

def example_3_fragile_early_stop():
    """
    SCENARIO: Fragile items must be delivered first
    - Stop 1: 5 fragile boxes (cannot have weight on top)
    - Stop 2: 20 regular heavy boxes

    CHALLENGE:
    - Fragile boxes must be accessible and not crushed
    - Heavy boxes should not block fragile boxes

    EXPECTED:
    - Fragile boxes get high priority bonus
    - Placed near door and on top
    - No stacking on fragile boxes
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Fragile Items at Early Stop")
    print("="*70)

    container = Container(
        length=589, width=235, height=239,
        max_weight=28000, door_width=235, door_height=239,
        name="20ft Container"
    )

    sku_catalog = {
        100: Box(
            id=100, sku_id=100, instance_index=0,
            length=50, width=40, height=30, weight=5,
            fragile=True,  # FRAGILE!
            name="Fragile Glassware", color="#EF4444"
        ),
        200: Box(
            id=200, sku_id=200, instance_index=0,
            length=80, width=70, height=60, weight=40,
            name="Heavy Machinery Parts", color="#6B7280"
        )
    }

    stops = [
        Stop(
            stop_number=1,
            location_id="RETAIL-001",
            location_name="Retail Store (Fragile)",
            sku_requirements={100: 5},
            is_time_critical=True  # Extra priority
        ),
        Stop(
            stop_number=2,
            location_id="WAREHOUSE-001",
            location_name="Warehouse (Heavy)",
            sku_requirements={200: 20}
        )
    ]

    trip = Trip(
        trip_id="TRIP-003",
        stops=stops,
        container=container,
        unload_strategy=UnloadStrategy.MINIMAL_REHANDLING
    )

    result = quick_optimize(trip, sku_catalog, verbose=True)

    # Validate fragile handling
    print("\n📦 FRAGILE HANDLING VALIDATION:")
    stop1_plan = result.unload_plans[1]
    print(f"   Stop 1 accessibility: {stop1_plan.accessibility_score:.0f}/100")
    print(f"   Stop 1 rehandling: {stop1_plan.rehandling_count} events")

    return result


# =============================================================================
# EXAMPLE 4: Strict Zero-Rehandling Requirement
# =============================================================================

def example_4_strict_lifo():
    """
    SCENARIO: Customer requires absolute zero rehandling
    - 3 stops with moderate quantities
    - STRICT_LIFO strategy enforced

    CHALLENGE:
    - Must achieve perfect LIFO loading
    - Any blocking = validation failure

    EXPECTED:
    - Strict zone separation
    - May sacrifice some space efficiency for accessibility
    - Zero rehandling events
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: Strict Zero-Rehandling (LIFO)")
    print("="*70)

    container = Container(
        length=589, width=235, height=239,
        max_weight=28000, door_width=235, door_height=239,
        name="20ft Container"
    )

    sku_catalog = {
        1: Box(id=1, sku_id=1, instance_index=0,
               length=60, width=50, height=40, weight=15,
               name="SKU-1", color="#3B82F6"),
        2: Box(id=2, sku_id=2, instance_index=0,
               length=60, width=50, height=40, weight=15,
               name="SKU-2", color="#10B981"),
        3: Box(id=3, sku_id=3, instance_index=0,
               length=60, width=50, height=40, weight=15,
               name="SKU-3", color="#F59E0B")
    }

    stops = [
        Stop(stop_number=1, location_id="A", location_name="Stop A",
             sku_requirements={1: 8}),
        Stop(stop_number=2, location_id="B", location_name="Stop B",
             sku_requirements={2: 10}),
        Stop(stop_number=3, location_id="C", location_name="Stop C",
             sku_requirements={3: 12})
    ]

    trip = Trip(
        trip_id="TRIP-004",
        stops=stops,
        container=container,
        unload_strategy=UnloadStrategy.STRICT_LIFO,  # STRICT MODE
        max_rehandling_events=0  # ZERO tolerance
    )

    # Use optimizer with high accessibility weight
    optimizer = MultiStopOptimizer(
        use_proportional_zones=True,
        allow_zone_overflow=False,  # No overflow!
        accessibility_weight=1.0  # Maximum accessibility priority
    )

    result = optimizer.optimize(trip, sku_catalog, verbose=True)

    print("\n🔒 STRICT LIFO VALIDATION:")
    print(f"   Total rehandling: {result.total_rehandling_events}")
    print(f"   Passes STRICT_LIFO: {result.total_rehandling_events == 0}")

    return result


# =============================================================================
# EXAMPLE 5: Heavy Concentrated Load
# =============================================================================

def example_5_heavy_concentration():
    """
    SCENARIO: One stop has all heavy items
    - Stop 1: 30 light boxes
    - Stop 2: 10 very heavy boxes

    CHALLENGE:
    - Heavy boxes should be low and stable
    - But Stop 1 must be accessible (near door)
    - Weight distribution critical

    EXPECTED:
    - Heavy items placed lower despite being Stop 2
    - Careful weight balancing
    - Stop 1 items above/around heavy items
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Heavy Concentrated Load")
    print("="*70)

    container = Container(
        length=589, width=235, height=239,
        max_weight=28000, door_width=235, door_height=239,
        name="20ft Container"
    )

    sku_catalog = {
        1: Box(id=1, sku_id=1, instance_index=0,
               length=40, width=30, height=25, weight=5,
               name="Light Boxes", color="#93C5FD"),
        2: Box(id=2, sku_id=2, instance_index=0,
               length=100, width=80, height=70, weight=150,  # VERY HEAVY
               name="Heavy Machinery", color="#1F2937")
    }

    stops = [
        Stop(stop_number=1, location_id="RETAIL", location_name="Retail Store",
             sku_requirements={1: 30}),
        Stop(stop_number=2, location_id="FACTORY", location_name="Factory",
             sku_requirements={2: 10})
    ]

    trip = Trip(
        trip_id="TRIP-005",
        stops=stops,
        container=container,
        unload_strategy=UnloadStrategy.MINIMAL_REHANDLING,
        require_stable_load=True
    )

    result = quick_optimize(trip, sku_catalog, verbose=True)

    print("\n⚖️ WEIGHT DISTRIBUTION:")
    for stop_num, metrics in result.stop_metrics.items():
        print(f"   Stop {stop_num}: {metrics.weight_loaded:.0f} kg, "
              f"{metrics.items_loaded} items")

    return result


# =============================================================================
# EXAMPLE 6: Pickup + Delivery Route
# =============================================================================

def example_6_pickup_delivery():
    """
    SCENARIO: Mixed pickup and delivery
    - Stop 1: Deliver 10 boxes
    - Stop 2: Pickup 5 boxes (returns)
    - Stop 3: Deliver 15 boxes

    CHALLENGE:
    - Must leave space at Stop 2 for pickups
    - Stop 3 items must not block Stop 1 or pickup area

    EXPECTED:
    - Complex planning considering pickups
    - May need strategic gap for loading returns
    """
    print("\n" + "="*70)
    print("EXAMPLE 6: Pickup + Delivery Route")
    print("="*70)

    container = Container(
        length=589, width=235, height=239,
        max_weight=28000, door_width=235, door_height=239,
        name="20ft Container"
    )

    sku_catalog = {
        1: Box(id=1, sku_id=1, instance_index=0,
               length=50, width=40, height=30, weight=10,
               name="Outbound Delivery", color="#3B82F6"),
        2: Box(id=2, sku_id=2, instance_index=0,
               length=50, width=40, height=30, weight=10,
               name="Return Items", color="#DC2626"),
        3: Box(id=3, sku_id=3, instance_index=0,
               length=60, width=50, height=40, weight=15,
               name="Final Delivery", color="#10B981")
    }

    stops = [
        Stop(stop_number=1, location_id="DEL-1", location_name="First Delivery",
             sku_requirements={1: 10}, stop_type=StopType.DELIVERY),
        Stop(stop_number=2, location_id="PICKUP-1", location_name="Pickup Returns",
             sku_requirements={2: 5}, stop_type=StopType.PICKUP),
        Stop(stop_number=3, location_id="DEL-2", location_name="Final Delivery",
             sku_requirements={3: 15}, stop_type=StopType.DELIVERY)
    ]

    trip = Trip(
        trip_id="TRIP-006",
        stops=stops,
        container=container,
        unload_strategy=UnloadStrategy.OPTIMIZED
    )

    result = quick_optimize(trip, sku_catalog, verbose=True)

    print("\n🔄 PICKUP/DELIVERY ANALYSIS:")
    for stop in trip.stops:
        plan = result.unload_plans[stop.stop_number]
        print(f"   Stop {stop.stop_number} ({stop.stop_type.name}): "
              f"{plan.total_items} items, {plan.estimated_time_minutes:.0f} min")

    return result


# =============================================================================
# RUN ALL EXAMPLES
# =============================================================================

def run_all_examples():
    """Run all example scenarios"""
    examples = [
        ("Simple 2-Stop", example_1_simple_two_stop),
        ("Complex Overlap", example_2_complex_overlap),
        ("Fragile Early", example_3_fragile_early_stop),
        ("Strict LIFO", example_4_strict_lifo),
        ("Heavy Load", example_5_heavy_concentration),
        ("Pickup+Delivery", example_6_pickup_delivery)
    ]

    results = {}

    print("\n" + "="*70)
    print("RUNNING ALL MULTI-STOP EXAMPLES")
    print("="*70)

    for name, example_func in examples:
        try:
            print(f"\n▶️  Running: {name}")
            result = example_func()
            results[name] = result
            print(f"✅ {name} completed successfully")
        except Exception as e:
            print(f"❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "="*70)
    print("SUMMARY OF ALL EXAMPLES")
    print("="*70)

    for name, result in results.items():
        print(f"\n{name}:")
        print(f"  ✓ Utilization: {result.overall_utilization_pct:.1f}%")
        print(f"  ✓ Rehandling: {result.total_rehandling_events} events")
        print(f"  ✓ Valid: {result.is_valid}")
        print(f"  ✓ Time: {result.solve_time_seconds:.2f}s")

    return results


if __name__ == "__main__":
    # Run a single example
    example_2_complex_overlap()

    # Or run all examples
    # run_all_examples()
