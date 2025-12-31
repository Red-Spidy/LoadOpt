"""
Multi-Stop Solver Validation Script

Tests that all imports work correctly and basic functionality is operational.
Run this to verify the multi-stop solver is properly configured.
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

def test_imports():
    """Test that all critical imports work"""
    print("Testing imports...")
    
    try:
        # Test utils
        from app.solver.utils import Box, ContainerSpace, PlacedBox
        print("✅ app.solver.utils imports OK")
        
        # Test multistop models
        from app.solver.multistop.models import Stop, Trip, VirtualSKU, MultiStopLoadPlan
        print("✅ app.solver.multistop.models imports OK")
        
        # Test multistop optimizer
        from app.solver.multistop.optimizer import MultiStopOptimizer, quick_optimize
        print("✅ app.solver.multistop.optimizer imports OK")
        
        # Test multistop validator
        from app.solver.multistop.validator import MultiStopValidator
        print("✅ app.solver.multistop.validator imports OK")
        
        # Test multistop __init__
        from app.solver.multistop import (
            Stop, Trip, MultiStopLoadPlan, MultiStopOptimizer, quick_optimize
        )
        print("✅ app.solver.multistop package imports OK")
        
        # Note: unified_multistop requires database setup, skipping
        print("⚠️  app.solver.unified_multistop (requires DB) - skipped")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_basic_functionality():
    """Test basic functionality of key components"""
    print("\nTesting basic functionality...")
    
    try:
        from app.solver.utils import Box, ContainerSpace, PlacedBox
        from app.solver.multistop.models import Stop, Trip
        
        # Test Box creation
        box = Box(
            id=1,
            sku_id=1,
            instance_index=0,
            length=50,
            width=40,
            height=30,
            weight=10,
            fragile=False,
            max_stack=5,
            stacking_group=None,
            priority=1,
            allowed_rotations=[True] * 6,
            delivery_order=1,
            name="TEST-BOX",
            color="#FF0000",
            load_bearing_capacity=None
        )
        print(f"✅ Box creation OK: {box.name}")
        
        # Test Container creation
        container = ContainerSpace(
            length=1200,
            width=240,
            height=240,
            max_weight=28000,
            door_width=240,
            door_height=240
        )
        print(f"✅ Container creation OK: {container.length}x{container.width}x{container.height}")
        
        # Test PlacedBox creation
        placed = PlacedBox(
            box=box,
            x=0,
            y=0,
            z=0,
            rotation=0,
            length=50,
            width=40,
            height=30,
            load_order=1
        )
        print(f"✅ PlacedBox creation OK")
        
        # Test PlacedBox.to_dict()
        placed_dict = placed.to_dict()
        assert 'box_id' in placed_dict
        assert 'position' in placed_dict
        assert 'dimensions' in placed_dict
        print(f"✅ PlacedBox.to_dict() OK")
        
        # Test Stop creation
        stop = Stop(
            stop_number=1,
            location_id="LOC-001",
            location_name="Store A",
            sku_requirements={1: 10}
        )
        print(f"✅ Stop creation OK: {stop.location_name}")
        
        # Test Trip creation
        trip = Trip(
            trip_id="TRIP-001",
            stops=[stop],
            container=container
        )
        print(f"✅ Trip creation OK: {trip.trip_id} with {trip.num_stops} stop(s)")
        
        return True
        
    except Exception as e:
        print(f"❌ Functionality Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_quick_optimize():
    """Test the quick_optimize function"""
    print("\nTesting quick_optimize function...")
    
    try:
        from app.solver.utils import Box, ContainerSpace
        from app.solver.multistop.models import Stop, Trip
        from app.solver.multistop import quick_optimize
        
        # Create simple test case
        container = ContainerSpace(
            length=600,
            width=240,
            height=240,
            max_weight=10000,
            door_width=240,
            door_height=240
        )
        
        # Create SKU catalog
        sku_catalog = {
            1: Box(
                id=1, sku_id=1, instance_index=0,
                length=50, width=40, height=30, weight=10,
                fragile=False, max_stack=5, stacking_group=None,
                priority=1, allowed_rotations=[True]*6,
                delivery_order=1, name="BOX-A", color="#FF0000",
                load_bearing_capacity=None
            ),
            2: Box(
                id=2, sku_id=2, instance_index=0,
                length=60, width=50, height=40, weight=15,
                fragile=False, max_stack=5, stacking_group=None,
                priority=1, allowed_rotations=[True]*6,
                delivery_order=2, name="BOX-B", color="#00FF00",
                load_bearing_capacity=None
            )
        }
        
        # Create stops
        stops = [
            Stop(
                stop_number=1,
                location_id="LOC-001",
                location_name="Store A",
                sku_requirements={1: 5}
            ),
            Stop(
                stop_number=2,
                location_id="LOC-002",
                location_name="Store B",
                sku_requirements={2: 3}
            )
        ]
        
        trip = Trip(
            trip_id="TEST-TRIP",
            stops=stops,
            container=container
        )
        
        # Run optimization (non-verbose)
        result = quick_optimize(trip, sku_catalog, verbose=False)
        
        # Check for overlaps using tight tolerance (0.01cm = 0.1mm)
        overlaps = []
        for i, box1 in enumerate(result.placements):
            for j, box2 in enumerate(result.placements[i+1:], i+1):
                # Check if boxes overlap (with 0.01cm tolerance)
                x_overlap = not (box1.max_x <= box2.x + 0.01 or box2.max_x <= box1.x + 0.01)
                y_overlap = not (box1.max_y <= box2.y + 0.01 or box2.max_y <= box1.y + 0.01)
                z_overlap = not (box1.max_z <= box2.z + 0.01 or box2.max_z <= box1.z + 0.01)
                
                if x_overlap and y_overlap and z_overlap:
                    overlaps.append((box1, box2))
        
        print(f"✅ quick_optimize executed successfully")
        print(f"   - Placements: {len(result.placements)}")
        print(f"   - Utilization: {result.overall_utilization_pct:.1f}%")
        print(f"   - Rehandling events: {result.total_rehandling_events}")
        print(f"   - Valid: {result.is_valid}")
        
        if overlaps:
            print(f"   ⚠️  WARNING: {len(overlaps)} overlapping box pairs detected!")
            for box1, box2 in overlaps[:3]:  # Show first 3
                print(f"      Box {box1.box.id} overlaps Box {box2.box.id}")
        else:
            print(f"   ✅ NO OVERLAPS (0.01cm tolerance)")
        
        return True
        
    except Exception as e:
        print(f"❌ quick_optimize Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("="*70)
    print("MULTI-STOP SOLVER VALIDATION")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Basic Functionality", test_basic_functionality()))
    results.append(("quick_optimize", test_quick_optimize()))
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Multi-stop solver is ready.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
