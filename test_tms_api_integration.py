"""
Comprehensive TMS API Integration Tests

Tests all LoadOpt APIs for TMS integration:
1. Health check endpoint
2. Version endpoint
3. Validation endpoint
4. Single-stop optimization
5. Multi-stop optimization with automatic detection
6. Error handling and edge cases
"""

import requests
import json
import time
from typing import Dict, Any, List


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TMSAPITester:
    """Comprehensive API tester for TMS integration"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_prefix = "/api/v1"
        self.test_results = []
        
    def print_header(self, title: str):
        """Print a formatted header"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{title.center(80)}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    
    def print_test(self, name: str, passed: bool, message: str = "", details: str = ""):
        """Print test result"""
        status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
        print(f"{status} - {name}")
        if message:
            print(f"  {Colors.YELLOW}→{Colors.RESET} {message}")
        if details and not passed:
            print(f"  {Colors.RED}Details: {details}{Colors.RESET}")
        
        self.test_results.append({
            'name': name,
            'passed': passed,
            'message': message,
            'details': details
        })
    
    def test_health_check(self) -> bool:
        """Test health check endpoint"""
        print(f"\n{Colors.BOLD}Test 1: Health Check Endpoint{Colors.RESET}")
        try:
            response = requests.get(f"{self.base_url}{self.api_prefix}/loadopt/health", timeout=5)
            
            if response.status_code != 200:
                self.print_test("Health Check", False, 
                              f"Expected status 200, got {response.status_code}",
                              response.text)
                return False
            
            data = response.json()
            
            # Validate response structure
            required_fields = ['status', 'version', 'timestamp', 'uptime_seconds']
            missing = [f for f in required_fields if f not in data]
            
            if missing:
                self.print_test("Health Check", False, 
                              f"Missing fields: {missing}",
                              json.dumps(data, indent=2))
                return False
            
            if data['status'] != 'healthy':
                self.print_test("Health Check", False, 
                              f"Service not healthy: {data['status']}")
                return False
            
            self.print_test("Health Check", True, 
                          f"Service healthy, uptime: {data['uptime_seconds']:.2f}s")
            return True
            
        except Exception as e:
            self.print_test("Health Check", False, str(e))
            return False
    
    def test_version_info(self) -> bool:
        """Test version endpoint"""
        print(f"\n{Colors.BOLD}Test 2: Version Information{Colors.RESET}")
        try:
            response = requests.get(f"{self.base_url}{self.api_prefix}/loadopt/version", timeout=5)
            
            if response.status_code != 200:
                self.print_test("Version Info", False, 
                              f"Expected status 200, got {response.status_code}")
                return False
            
            data = response.json()
            
            # Validate response structure
            required_fields = ['api_version', 'solver_version', 'supported_algorithms', 'capabilities']
            missing = [f for f in required_fields if f not in data]
            
            if missing:
                self.print_test("Version Info", False, f"Missing fields: {missing}")
                return False
            
            # Check multi-stop capability
            if not data.get('capabilities', {}).get('multi_stop_delivery', False):
                self.print_test("Version Info", False, 
                              "Multi-stop delivery capability not enabled")
                return False
            
            self.print_test("Version Info", True, 
                          f"API v{data['api_version']}, Solver v{data['solver_version']}")
            print(f"  {Colors.BLUE}Supported algorithms: {', '.join(data['supported_algorithms'])}{Colors.RESET}")
            return True
            
        except Exception as e:
            self.print_test("Version Info", False, str(e))
            return False
    
    def test_single_stop_optimization(self) -> bool:
        """Test single-stop optimization with automatic detection"""
        print(f"\n{Colors.BOLD}Test 3: Single-Stop Optimization (Auto-Detection){Colors.RESET}")
        
        request = {
            "request_id": "TMS-TEST-SINGLE-001",
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
                    "quantity": 5,
                    "delivery": {"stop_number": 1, "priority": 1}
                },
                {
                    "sku": "BOX-B",
                    "dimensions": {"length": 60, "width": 40, "height": 50, "unit": "cm"},
                    "weight": {"value": 25, "unit": "kg"},
                    "quantity": 10,
                    "delivery": {"stop_number": 1, "priority": 2}
                }
            ],
            "solver_options": {
                "algorithm": "heuristic",
                "max_execution_time_seconds": 30
            }
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}{self.api_prefix}/loadopt/plan",
                json=request,
                timeout=60
            )
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                self.print_test("Single-Stop", False, 
                              f"Expected status 200, got {response.status_code}",
                              response.text[:500])
                return False
            
            data = response.json()
            
            # Validate response structure
            if data.get('status') != 'success':
                self.print_test("Single-Stop", False, 
                              f"Status: {data.get('status')}")
                return False
            
            result = data.get('result', {})
            placements = result.get('placements', [])
            
            if not placements:
                self.print_test("Single-Stop", False, "No placements generated")
                return False
            
            # Check for collisions
            collision_found = self._check_collisions(placements)
            if collision_found:
                self.print_test("Single-Stop", False, 
                              "BOX COLLISIONS DETECTED!",
                              collision_found)
                return False
            
            stats = result.get('statistics', {})
            utilization = stats.get('utilization', {}).get('volume_percentage', 0)
            
            self.print_test("Single-Stop", True, 
                          f"{len(placements)} items placed, {utilization:.1f}% utilization, {elapsed:.0f}ms")
            return True
            
        except Exception as e:
            self.print_test("Single-Stop", False, str(e))
            return False
    
    def test_multistop_optimization(self) -> bool:
        """Test multi-stop optimization with automatic detection"""
        print(f"\n{Colors.BOLD}Test 4: Multi-Stop Optimization (Auto-Detection){Colors.RESET}")
        
        request = {
            "request_id": "TMS-TEST-MULTI-001",
            "container": {
                "dimensions": {"length": 1200, "width": 240, "height": 240, "unit": "cm"},
                "weight_limit": {"value": 28000, "unit": "kg"},
                "door": {"width": 240, "height": 240}
            },
            "items": [
                # Stop 1 items (should be near door)
                {
                    "sku": "STOP1-PALLET",
                    "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"},
                    "weight": {"value": 300, "unit": "kg"},
                    "quantity": 3,
                    "delivery": {"stop_number": 1, "priority": 1}
                },
                # Stop 2 items (middle)
                {
                    "sku": "STOP2-BOX",
                    "dimensions": {"length": 80, "width": 60, "height": 70, "unit": "cm"},
                    "weight": {"value": 150, "unit": "kg"},
                    "quantity": 4,
                    "delivery": {"stop_number": 2, "priority": 1}
                },
                # Stop 3 items (back of truck)
                {
                    "sku": "STOP3-CRATE",
                    "dimensions": {"length": 100, "width": 70, "height": 80, "unit": "cm"},
                    "weight": {"value": 200, "unit": "kg"},
                    "quantity": 3,
                    "delivery": {"stop_number": 3, "priority": 1}
                }
            ],
            "solver_options": {
                "algorithm": "heuristic",  # Should auto-switch to multistop
                "max_execution_time_seconds": 60
            }
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}{self.api_prefix}/loadopt/plan",
                json=request,
                timeout=120
            )
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                self.print_test("Multi-Stop", False, 
                              f"Expected status 200, got {response.status_code}",
                              response.text[:500])
                return False
            
            data = response.json()
            
            if data.get('status') != 'success':
                self.print_test("Multi-Stop", False, 
                              f"Status: {data.get('status')}")
                return False
            
            result = data.get('result', {})
            placements = result.get('placements', [])
            
            if not placements:
                self.print_test("Multi-Stop", False, "No placements generated")
                return False
            
            # Verify multi-stop algorithm was used
            solver_metadata = data.get('solver_metadata', {})
            algorithm = solver_metadata.get('algorithm_used', '')
            
            if algorithm != 'multistop':
                self.print_test("Multi-Stop", False, 
                              f"Expected 'multistop' algorithm, got '{algorithm}'")
                return False
            
            # Check for collisions
            collision_found = self._check_collisions(placements)
            if collision_found:
                self.print_test("Multi-Stop", False, 
                              "BOX COLLISIONS DETECTED!",
                              collision_found)
                return False
            
            # Verify stop ordering (Stop 1 should be closest to door)
            stop_positions = {}
            for p in placements:
                stop = p.get('delivery_stop', 1)
                x_pos = p.get('position', {}).get('x', 0)
                if stop not in stop_positions:
                    stop_positions[stop] = []
                stop_positions[stop].append(x_pos)
            
            # Calculate average X position per stop
            avg_x = {stop: sum(positions)/len(positions) 
                    for stop, positions in stop_positions.items()}
            
            # Stop 1 should have higher X (closer to door) than Stop 3
            if len(avg_x) > 1:
                sorted_stops = sorted(avg_x.items(), key=lambda x: x[1], reverse=True)
                print(f"  {Colors.BLUE}Stop positions (X-axis): {sorted_stops}{Colors.RESET}")
            
            stats = result.get('statistics', {})
            utilization = stats.get('utilization', {}).get('volume_percentage', 0)
            
            self.print_test("Multi-Stop", True, 
                          f"{len(placements)} items placed, {utilization:.1f}% utilization, {elapsed:.0f}ms")
            return True
            
        except Exception as e:
            self.print_test("Multi-Stop", False, str(e))
            return False
    
    def test_validation_endpoint(self) -> bool:
        """Test validation endpoint"""
        print(f"\n{Colors.BOLD}Test 5: Validation Endpoint{Colors.RESET}")
        
        request = {
            "request_id": "TMS-TEST-VALIDATE-001",
            "container": {
                "dimensions": {"length": 600, "width": 240, "height": 240, "unit": "cm"},
                "weight_limit": {"value": 5000, "unit": "kg"}
            },
            "items": [
                {
                    "sku": "HEAVY-ITEM",
                    "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"},
                    "weight": {"value": 6000, "unit": "kg"},  # Exceeds container limit
                    "quantity": 1,
                    "delivery": {"stop_number": 1, "priority": 1}  # Added required field
                }
            ]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}{self.api_prefix}/loadopt/validate",
                json=request,
                timeout=30
            )
            
            if response.status_code != 200:
                self.print_test("Validation", False, 
                              f"Expected status 200, got {response.status_code}")
                return False
            
            data = response.json()
            result = data.get('result', {})
            validation = result.get('validation', {})
            
            # Should catch weight violation
            errors = validation.get('errors', [])
            if not errors:
                self.print_test("Validation", False, 
                              "Failed to detect weight limit violation")
                return False
            
            self.print_test("Validation", True, 
                          f"Correctly detected {len(errors)} error(s)")
            print(f"  {Colors.BLUE}Error: {errors[0][:80]}...{Colors.RESET}")
            return True
            
        except Exception as e:
            self.print_test("Validation", False, str(e))
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling"""
        print(f"\n{Colors.BOLD}Test 6: Error Handling{Colors.RESET}")
        
        # Test with invalid container dimensions
        request = {
            "request_id": "TMS-TEST-ERROR-001",
            "container": {
                "dimensions": {"length": -100, "width": 240, "height": 240, "unit": "cm"},
                "weight_limit": {"value": 28000, "unit": "kg"}
            },
            "items": []
        }
        
        try:
            response = requests.post(
                f"{self.base_url}{self.api_prefix}/loadopt/plan",
                json=request,
                timeout=30
            )
            
            # Should return error status (422 for validation or 400 for bad request)
            if response.status_code not in [400, 422]:
                self.print_test("Error Handling", False, 
                              f"Expected error status, got {response.status_code}")
                return False
            
            self.print_test("Error Handling", True, 
                          f"Correctly rejected invalid input (status {response.status_code})")
            return True
            
        except Exception as e:
            self.print_test("Error Handling", False, str(e))
            return False
    
    def test_large_multistop_scenario(self) -> bool:
        """Test larger multi-stop scenario"""
        print(f"\n{Colors.BOLD}Test 7: Large Multi-Stop Scenario (5 stops){Colors.RESET}")
        
        items = []
        for stop in range(1, 6):  # 5 stops
            # Each stop has different items
            items.append({
                "sku": f"STOP{stop}-PALLET",
                "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"},
                "weight": {"value": 250, "unit": "kg"},
                "quantity": 2,
                "delivery": {"stop_number": stop, "priority": 1}
            })
            items.append({
                "sku": f"STOP{stop}-BOX",
                "dimensions": {"length": 60, "width": 40, "height": 50, "unit": "cm"},
                "weight": {"value": 30, "unit": "kg"},
                "quantity": 3,
                "delivery": {"stop_number": stop, "priority": 2}
            })
        
        request = {
            "request_id": "TMS-TEST-LARGE-MULTI-001",
            "container": {
                "dimensions": {"length": 1200, "width": 240, "height": 240, "unit": "cm"},
                "weight_limit": {"value": 28000, "unit": "kg"},
                "door": {"width": 240, "height": 240}
            },
            "items": items,
            "solver_options": {
                "algorithm": "heuristic",
                "max_execution_time_seconds": 120
            }
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}{self.api_prefix}/loadopt/plan",
                json=request,
                timeout=180
            )
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                self.print_test("Large Multi-Stop", False, 
                              f"Expected status 200, got {response.status_code}",
                              response.text[:500])
                return False
            
            data = response.json()
            result = data.get('result', {})
            placements = result.get('placements', [])
            
            # Check for collisions
            collision_found = self._check_collisions(placements)
            if collision_found:
                self.print_test("Large Multi-Stop", False, 
                              "BOX COLLISIONS DETECTED!",
                              collision_found)
                return False
            
            stats = result.get('statistics', {})
            utilization = stats.get('utilization', {}).get('volume_percentage', 0)
            items_placed = stats.get('items_placed', 0)
            items_requested = stats.get('total_items_requested', 0)
            
            self.print_test("Large Multi-Stop", True, 
                          f"{items_placed}/{items_requested} items, {utilization:.1f}% util, {elapsed:.0f}ms")
            return True
            
        except Exception as e:
            self.print_test("Large Multi-Stop", False, str(e))
            return False
    
    def _check_collisions(self, placements: List[Dict]) -> str:
        """Check if any boxes collide/overlap"""
        for i, p1 in enumerate(placements):
            pos1 = p1.get('position', {})
            dim1 = p1.get('dimensions', {})
            
            x1, y1, z1 = pos1.get('x', 0), pos1.get('y', 0), pos1.get('z', 0)
            l1, w1, h1 = dim1.get('length', 0), dim1.get('width', 0), dim1.get('height', 0)
            
            for j, p2 in enumerate(placements[i+1:], i+1):
                pos2 = p2.get('position', {})
                dim2 = p2.get('dimensions', {})
                
                x2, y2, z2 = pos2.get('x', 0), pos2.get('y', 0), pos2.get('z', 0)
                l2, w2, h2 = dim2.get('length', 0), dim2.get('width', 0), dim2.get('height', 0)
                
                # Check for overlap in all 3 dimensions
                x_overlap = not (x1 + l1 <= x2 or x2 + l2 <= x1)
                y_overlap = not (y1 + w1 <= y2 or y2 + w2 <= y1)
                z_overlap = not (z1 + h1 <= z2 or z2 + h2 <= z1)
                
                if x_overlap and y_overlap and z_overlap:
                    return (f"Boxes {i+1} and {j+1} collide! "
                           f"Box{i+1}@[{x1},{y1},{z1}] {l1}x{w1}x{h1} vs "
                           f"Box{j+1}@[{x2},{y2},{z2}] {l2}x{w2}x{h2}")
        
        return ""
    
    def run_all_tests(self):
        """Run all tests"""
        self.print_header("LoadOpt TMS API Integration Test Suite")
        
        print(f"{Colors.BLUE}Target: {self.base_url}{Colors.RESET}")
        print(f"{Colors.BLUE}API Prefix: {self.api_prefix}{Colors.RESET}\n")
        
        tests = [
            self.test_health_check,
            self.test_version_info,
            self.test_single_stop_optimization,
            self.test_multistop_optimization,
            self.test_validation_endpoint,
            self.test_error_handling,
            self.test_large_multistop_scenario
        ]
        
        for test in tests:
            test()
        
        # Summary
        self.print_header("Test Summary")
        
        passed = sum(1 for r in self.test_results if r['passed'])
        failed = sum(1 for r in self.test_results if not r['passed'])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"{Colors.GREEN}Passed: {passed}{Colors.RESET}")
        print(f"{Colors.RED}Failed: {failed}{Colors.RESET}")
        print(f"Success Rate: {(passed/total*100):.1f}%\n")
        
        if failed > 0:
            print(f"{Colors.RED}{Colors.BOLD}FAILED TESTS:{Colors.RESET}")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  {Colors.RED}✗{Colors.RESET} {result['name']}: {result['message']}")
        else:
            print(f"{Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED! ✓{Colors.RESET}")
        
        print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}\n")
        
        return failed == 0


if __name__ == "__main__":
    import sys
    
    # Allow custom base URL
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    tester = TMSAPITester(base_url)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)
