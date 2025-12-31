"""
Debug script to test LoadOpt API and diagnose placement issues
"""
import json
import requests
import time

API_URL = "http://localhost:8000"

def test_loadopt_api():
    print("=" * 70)
    print("LOADOPT API DEBUG TEST")
    print("=" * 70)
    
    # Load request data
    with open('postman_sample_request.json', 'r') as f:
        request_data = json.load(f)
    
    print(f"\n📦 REQUEST SUMMARY:")
    print(f"   Container: {request_data['container']['type']}")
    print(f"   Dimensions: {request_data['container']['dimensions']['length']}x{request_data['container']['dimensions']['width']}x{request_data['container']['dimensions']['height']} cm")
    
    items = request_data['items']
    total_items = sum(i['quantity'] for i in items)
    print(f"   Total items: {total_items}")
    print(f"   Item types: {len(items)}")
    
    # Check API health
    print(f"\n🔍 Checking API health...")
    try:
        response = requests.get(f"{API_URL}/api/v1/loadopt/health", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ API is healthy: {response.json()}")
        else:
            print(f"   ❌ API health check failed: {response.status_code}")
            return
    except Exception as e:
        print(f"   ❌ Cannot connect to API: {e}")
        print(f"   💡 Make sure Docker containers are running: docker-compose ps")
        return
    
    # Submit optimization request
    print(f"\n🚀 Submitting optimization request...")
    try:
        start_time = time.time()
        response = requests.post(
            f"{API_URL}/api/v1/loadopt/plan",
            json=request_data,
            timeout=60
        )
        elapsed = time.time() - start_time
        
        print(f"   ⏱️  Response time: {elapsed:.2f}s")
        print(f"   📊 Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ OPTIMIZATION SUCCESS!")
            print(f"   Plan ID: {result.get('plan_id', 'N/A')}")
            print(f"   Algorithm: {result.get('algorithm_used', 'N/A')}")
            print(f"   Execution time: {result.get('execution_time_ms', 0):.0f}ms")
            
            # Analyze placements
            placements = result.get('placements', [])
            print(f"\n📦 PLACEMENT ANALYSIS:")
            print(f"   Items placed: {len(placements)}/{total_items} ({len(placements)/total_items*100:.1f}%)")
            
            if len(placements) < total_items:
                print(f"   ⚠️  WARNING: {total_items - len(placements)} items NOT placed!")
                print(f"   💡 This suggests placement constraints are too strict or collision detection issues")
            
            # Check for overlapping boxes (collision detection failure)
            print(f"\n🔍 COLLISION DETECTION CHECK:")
            overlaps = check_for_overlaps(placements)
            if overlaps:
                print(f"   ❌ FOUND {len(overlaps)} OVERLAPPING BOXES!")
                print(f"   This indicates collision detection is failing.")
                for i, (box1, box2) in enumerate(overlaps[:5]):  # Show first 5
                    print(f"   Overlap {i+1}: {box1['sku']} and {box2['sku']}")
            else:
                print(f"   ✅ No overlapping boxes detected")
            
            # Analyze by SKU
            print(f"\n📋 PLACEMENT BY SKU:")
            sku_stats = {}
            for placement in placements:
                sku = placement['sku']
                if sku not in sku_stats:
                    sku_stats[sku] = 0
                sku_stats[sku] += 1
            
            for item in items:
                sku = item['sku']
                qty = item['quantity']
                placed = sku_stats.get(sku, 0)
                status = "✅" if placed == qty else "⚠️"
                print(f"   {status} {sku}: {placed}/{qty} placed ({placed/qty*100:.0f}%)")
            
            # Utilization
            print(f"\n📊 UTILIZATION:")
            print(f"   Volume: {result.get('utilization', {}).get('volume_percent', 0):.1f}%")
            print(f"   Weight: {result.get('utilization', {}).get('weight_percent', 0):.1f}%")
            
            # Validation
            validation = result.get('validation', {})
            print(f"\n✅ VALIDATION:")
            print(f"   Valid: {validation.get('valid', False)}")
            if not validation.get('valid', False):
                print(f"   ⚠️  Validation errors:")
                for error in validation.get('errors', []):
                    print(f"      - {error}")
            
            # Save result for inspection
            with open('last_optimization_result.json', 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n💾 Full result saved to: last_optimization_result.json")
            
        else:
            print(f"\n❌ OPTIMIZATION FAILED!")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.Timeout:
        print(f"   ❌ Request timed out (>60s)")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

def check_for_overlaps(placements):
    """Check if any boxes overlap (indicating collision detection failure)"""
    overlaps = []
    
    for i, box1 in enumerate(placements):
        for box2 in placements[i+1:]:
            if boxes_overlap(box1, box2):
                overlaps.append((box1, box2))
    
    return overlaps

def boxes_overlap(box1, box2):
    """Check if two boxes overlap using AABB collision detection"""
    pos1 = box1['position']
    dim1 = box1['dimensions']
    pos2 = box2['position']
    dim2 = box2['dimensions']
    
    # Calculate bounds
    box1_min_x, box1_max_x = pos1['x'], pos1['x'] + dim1['length']
    box1_min_y, box1_max_y = pos1['y'], pos1['y'] + dim1['width']
    box1_min_z, box1_max_z = pos1['z'], pos1['z'] + dim1['height']
    
    box2_min_x, box2_max_x = pos2['x'], pos2['x'] + dim2['length']
    box2_min_y, box2_max_y = pos2['y'], pos2['y'] + dim2['width']
    box2_min_z, box2_max_z = pos2['z'], pos2['z'] + dim2['height']
    
    # Check for overlap (boxes overlap if they intersect on all 3 axes)
    x_overlap = box1_min_x < box2_max_x and box1_max_x > box2_min_x
    y_overlap = box1_min_y < box2_max_y and box1_max_y > box2_min_y
    z_overlap = box1_min_z < box2_max_z and box1_max_z > box2_min_z
    
    return x_overlap and y_overlap and z_overlap

if __name__ == "__main__":
    test_loadopt_api()
    
    print(f"\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
