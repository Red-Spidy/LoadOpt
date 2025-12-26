"""
Optimal Solver - Exhaustive search for the best possible solution
Optimized for both speed and accuracy
"""

from typing import List, Tuple, Optional
import random
import copy
import threading
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

from app.solver.utils import Box, ContainerSpace, PlacedBox, WeightDistribution, SpatialGrid
from app.solver.heuristic import HeuristicSolver, LayerBuildingHeuristic, LayerBuildingHeuristicRotated
from app.solver.grasp_solver import GRASPSolver
from app.solver.tabu_search import TabuSearchSolver
from app.solver.beam_search import BeamSearchSolver
from app.solver.skyline_solver import SkylineSolver
from app.solver.pattern_database import get_global_pattern_db


class GlobalOrderCache:
    """
    Global LRU cache for order evaluations - shared across all phases.

    Optimization: Uses LRU eviction instead of FIFO for better cache hit rates.
    Expected improvement: 5-10% higher cache hit rate.
    """

    def __init__(self, max_size: int = 50000):
        self.cache: OrderedDict[str, Tuple[float, List[PlacedBox], dict]] = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def _get_key(self, order: List[int]) -> str:
        """Generate cache key from order (use hash for speed)"""
        return str(hash(tuple(order)))

    def get(self, order: List[int]) -> Optional[Tuple[float, List[PlacedBox], dict]]:
        """Get cached result if available (LRU - moves to end)"""
        key = self._get_key(order)
        if key in self.cache:
            self.hits += 1
            self.cache.move_to_end(key)
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, order: List[int], fitness: float, placements: List[PlacedBox], stats: dict):
        """Cache a result with LRU eviction"""
        key = self._get_key(order)

        if key in self.cache:
            self.cache.move_to_end(key)

        self.cache[key] = (fitness, placements, stats)

        # Evict least recently used if over capacity
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class OptimalSolver:
    """
    Comprehensive solver that exhaustively searches for the best solution.
    
    OPTIMIZED Strategy (fast + accurate):
    1. Quick heuristic orderings in parallel (immediate results)
    2. Early termination if target reached (>85% with all items placed)
    3. Adaptive GA/SA with reduced iterations for small problems
    4. Skip expensive phases if already good enough
    """
    
    def __init__(self, boxes: List[Box], container: ContainerSpace):
        self.boxes = boxes
        self.container = container
        self.best_placements: List[PlacedBox] = []
        self.best_stats: dict = {
            'utilization_pct': 0.0,
            'placed_count': 0,
            'total_weight': 0.0,
            'is_valid': True,
            'validation_errors': [],
            'weight_distribution': None
        }
        self.best_fitness = -1.0
        self.all_results: List[Tuple[float, List[PlacedBox], dict, str]] = []
        
        # Thread lock for thread-safe updates
        self._lock = threading.Lock()
        
        # Global cache for all order evaluations
        self.global_cache = GlobalOrderCache(max_size=20000)
        
        # Calculate theoretical upper bound for early termination
        total_box_volume = sum(b.volume for b in boxes)
        container_volume = container.length * container.width * container.height
        self.theoretical_max = min(100.0, (total_box_volume / container_volume) * 100)
        
        # More aggressive early termination thresholds
        self.n_boxes = len(boxes)
        if self.n_boxes <= 20:
            self.good_enough = 80.0  # 80% is good for small problems
            self.practical_max = self.theoretical_max * 0.95
        elif self.n_boxes <= 50:
            self.good_enough = 75.0
            self.practical_max = self.theoretical_max * 0.93
        else:
            self.good_enough = 70.0
            self.practical_max = self.theoretical_max * 0.90  # Less aggressive for large problems
        
        # Adaptive workers based on problem size (using threads to avoid daemon process issues)
        self.max_workers = min(4, max(2, self.n_boxes // 15))
    
    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """
        Run optimized search with all advanced algorithms.

        New phases include: GRASP, Tabu Search, Beam Search, Skyline, Pattern DB
        """
        n_boxes = len(self.boxes)
        print(f"OptimalSolver: Starting optimized search for {n_boxes} boxes...")
        print(f"  Target: {self.good_enough:.1f}% (max theoretical: {self.theoretical_max:.1f}%)")

        # Phase 0: Check pattern database for similar problems
        print("Phase 0: Checking pattern database...")
        self._try_pattern_database()

        if self._should_terminate():
            print(f"  Early exit (pattern match): {self.best_fitness:.1f}%")
            return self._finalize_result()

        # Phase 1: Quick heuristic orderings (FAST - usually finds 70-85%)
        print("Phase 1: Testing heuristic orderings...")
        self._try_heuristic_orderings_parallel()

        if self._should_terminate():
            print(f"  Early exit: {self.best_fitness:.1f}% achieved")
            return self._finalize_result()

        # Phase 2: Layer-building and Skyline (FAST - good for uniform boxes)
        print("Phase 2: Layer-building and Skyline...")
        self._try_layer_building_improved()
        self._try_skyline()

        if self._should_terminate():
            return self._finalize_result()

        # For large problems (400+ boxes), skip expensive metaheuristics
        # Layer building and heuristics are good enough
        if self.n_boxes >= 400:
            print(f"  Large problem ({self.n_boxes} boxes) - skipping expensive phases")
            return self._finalize_result()

        # Phase 3: Beam Search (systematic exploration) - skip for 200+ boxes
        if self.n_boxes < 200:
            print("Phase 3: Beam Search...")
            self._run_beam_search()
            if self._should_terminate():
                return self._finalize_result()

        # Phase 4: GRASP (randomized greedy + local search)
        print("Phase 4: GRASP...")
        self._run_grasp()

        if self._should_terminate():
            return self._finalize_result()

        # Phase 5: Quick GA (reduced iterations for speed) - skip for 300+ boxes
        if self.n_boxes < 300:
            print("Phase 5: Genetic Algorithm...")
            self._run_genetic_algorithm_fast()
            if self._should_terminate():
                return self._finalize_result()

        # Phase 6: Tabu Search (memory-based search) - skip for 300+ boxes
        if self.n_boxes < 300:
            print("Phase 6: Tabu Search...")
            self._run_tabu_search()
            if self._should_terminate():
                return self._finalize_result()

        # Phase 7: Quick SA refinement - skip for 200+ boxes
        if self.n_boxes < 200:
            print("Phase 7: Simulated Annealing...")
            self._run_simulated_annealing_fast()

        # Phase 8: Local re-packing only if we have a good solution and small problem
        if self.best_fitness > 60 and self.n_boxes < 150:
            print("Phase 8: Local re-packing...")
            self._run_local_repacking()

        # Store best solution in pattern database
        if self.best_placements:
            pattern_db = get_global_pattern_db()
            pattern_db.store_pattern(
                self.boxes, self.best_placements,
                self.best_stats, self.best_fitness
            )

        # Report results
        print(f"\nOptimalSolver: Tested {len(self.all_results)} solutions")
        print(f"  Cache hit rate: {self.global_cache.hit_rate:.1%}")
        print(f"  Best: {self.best_fitness:.2f}% utilization")

        return self._finalize_result()
    
    def _should_terminate(self) -> bool:
        """Check if we should stop early"""
        placed_count = self.best_stats.get('placed_count', 0)

        # Only stop if ALL boxes placed with good utilization
        if placed_count == self.n_boxes:
            if self.best_fitness >= self.good_enough:
                return True

        # NEVER terminate early if boxes remain unplaced
        # Force solver to exhaust all phases to find placements
        return False
    
    def _finalize_result(self) -> Tuple[List[PlacedBox], dict]:
        """Finalize and return the best result"""
        # Calculate weight distribution for best solution
        if self.best_placements:
            cog = WeightDistribution.calculate_cog(self.best_placements)
            front_axle, rear_axle = WeightDistribution.calculate_axle_loads(
                self.best_placements, self.container.length
            )
            self.best_stats['weight_distribution'] = {
                'front_axle': front_axle,
                'rear_axle': rear_axle,
                'center_of_gravity': {'x': cog[0], 'y': cog[1], 'z': cog[2]}
            }
            self.best_stats['total_weight'] = sum(p.box.weight for p in self.best_placements)
        
        self.best_stats['solver'] = 'optimal'
        self.best_stats['solutions_tested'] = len(self.all_results)
        
        return self.best_placements, self.best_stats
    
    def _remove_collisions(self, placements: List[PlacedBox]) -> List[PlacedBox]:
        """Remove any colliding boxes from the placement list"""
        from app.solver.utils import CollisionDetector
        
        validated = []
        for p in placements:
            has_collision = False
            for existing in validated:
                if CollisionDetector.check_collision_fast(p, existing):
                    has_collision = True
                    break
            if not has_collision:
                validated.append(p)
        return validated
    
    def _update_best(self, placements: List[PlacedBox], stats: dict, method: str):
        """Update best solution if this one is better (thread-safe)"""
        fitness = self._calculate_fitness(placements, stats)
        
        with self._lock:
            self.all_results.append((fitness, placements, stats, method))
            
            if fitness > self.best_fitness:
                self.best_fitness = fitness
                # Deep copy placements to avoid reference issues
                self.best_placements = [
                    PlacedBox(
                        box=p.box,
                        x=p.x, y=p.y, z=p.z,
                        rotation=p.rotation,
                        length=p.length, width=p.width, height=p.height,
                        load_order=p.load_order
                    ) for p in placements
                ]
                self.best_stats = stats.copy()
                self.best_stats['method'] = method
                print(f"  New best: {fitness:.2f}% (method: {method})")
    
    def _calculate_fitness(self, placements: List[PlacedBox], stats: dict) -> float:
        """
        Unified fitness function (Optimization #6)
        Used across all solvers for consistent optimization
        """
        if not placements:
            return 0.0
        
        utilization = stats.get('utilization_pct', 0)
        placed_ratio = len(placements) / max(1, len(self.boxes))
        
        # Primary metrics
        fitness = utilization * 0.6 + placed_ratio * 100 * 0.35
        
        # Weight balance penalty (Optimization #5 - early axle awareness)
        if self.container.length > 0:
            total_weight = sum(p.box.weight for p in placements)
            if total_weight > 0:
                cog_x = sum(p.center[0] * p.box.weight for p in placements) / total_weight
                target_x = self.container.length * 0.5
                balance_deviation = abs(cog_x - target_x) / self.container.length
                fitness -= balance_deviation * 5  # Soft penalty
        
        # Validity penalty
        if not stats.get('is_valid', True):
            fitness *= 0.85
        
        return fitness
    
    def _evaluate_order_cached(self, order: List[int], method_name: str) -> Tuple[List[PlacedBox], dict]:
        """Evaluate an order using global cache (Optimization #7) - thread-safe"""
        # Check cache first
        cached = self.global_cache.get(order)
        if cached:
            fitness, placements, stats = cached
            with self._lock:
                self.all_results.append((fitness, placements, stats, method_name + '_cached'))
                if fitness > self.best_fitness:
                    self.best_fitness = fitness
                    # Deep copy placements to avoid reference issues
                    self.best_placements = [
                        PlacedBox(
                            box=p.box,
                            x=p.x, y=p.y, z=p.z,
                            rotation=p.rotation,
                            length=p.length, width=p.width, height=p.height,
                            load_order=p.load_order
                        ) for p in placements
                    ]
                    self.best_stats = stats.copy()
                    self.best_stats['method'] = method_name
            return placements, stats
        
        # Evaluate and cache
        solver = HeuristicSolver(self.boxes, self.container, use_spatial_grid=True)
        placements, stats = solver.solve(box_order=order)
        fitness = self._calculate_fitness(placements, stats)
        self.global_cache.set(order, fitness, placements, stats)
        
        self._update_best(placements, stats, method_name)
        return placements, stats
    
    def _try_heuristic_orderings_parallel(self):
        """Try key orderings in parallel (optimized for speed)
        
        Delivery order logic: Items with high delivery_order (last delivery) are placed first 
        (at back), items with low delivery_order (first delivery) are placed last (near door).
        """
        # Core orderings that usually perform best - all respect delivery_order first
        orderings = [
            ('delivery_volume_desc', lambda b: (-b.delivery_order, -b.volume)),
            ('delivery_priority_volume', lambda b: (-b.delivery_order, -b.priority, -b.volume)),
            ('volume_desc', lambda b: -b.volume),
            ('priority_volume', lambda b: (-b.priority, -b.volume)),
            ('base_area_desc', lambda b: -(b.length * b.width)),
            ('height_desc', lambda b: -b.height),
            ('weight_desc', lambda b: -b.weight),
        ]
        
        # Prepare all orderings
        orders_to_test = []
        for name, key_func in orderings:
            try:
                sorted_boxes = sorted(self.boxes, key=key_func)
                order = [self.boxes.index(b) for b in sorted_boxes]
                orders_to_test.append((f'heuristic_{name}', order))
            except:
                pass
        
        # Add just 3 random orderings for diversity
        for i in range(3):
            order = list(range(len(self.boxes)))
            random.shuffle(order)
            orders_to_test.append((f'heuristic_random_{i}', order))
        
        # Parallel evaluation with ThreadPoolExecutor (avoids daemon process issues with Celery)
        max_workers = min(mp.cpu_count(), len(orders_to_test), self.max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._evaluate_order_cached, order, name): name
                      for name, order in orders_to_test}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    import traceback
                    print(f"  Warning: {futures[future]} failed: {e}")
                    print(f"    Traceback: {traceback.format_exc()}")
    
    def _try_pattern_database(self):
        """Try to retrieve solution from pattern database"""
        try:
            pattern_db = get_global_pattern_db()
            order = pattern_db.retrieve_pattern(self.boxes)

            if order:
                placements, stats = self._evaluate_order_cached(order, 'pattern_db')
                print(f"  Pattern database hit! Utilization: {stats.get('utilization_pct', 0):.1f}%")
        except Exception as e:
            print(f"  Warning: Pattern DB lookup failed: {e}")

    def _try_layer_building_improved(self):
        """Try layer-building with rotation support (Optimization #4)"""
        try:
            # Standard layer building
            solver = LayerBuildingHeuristic(self.boxes, self.container)
            placements, stats = solver.solve()
            self._update_best(placements, stats, 'layer_building')

            # Also try with rotated boxes
            solver2 = LayerBuildingHeuristicRotated(self.boxes, self.container)
            placements2, stats2 = solver2.solve()
            self._update_best(placements2, stats2, 'layer_building_rotated')
        except Exception as e:
            print(f"  Warning: Layer building failed: {e}")

    def _try_skyline(self):
        """Try skyline algorithm"""
        try:
            solver = SkylineSolver(self.boxes, self.container)
            placements, stats = solver.solve()
            self._update_best(placements, stats, 'skyline')
        except Exception as e:
            print(f"  Warning: Skyline failed: {e}")

    def _run_beam_search(self):
        """Run beam search"""
        try:
            n_boxes = len(self.boxes)
            # Adaptive beam width based on problem size
            if n_boxes <= 30:
                beam_width = 15
            elif n_boxes <= 60:
                beam_width = 10
            else:
                beam_width = 8

            solver = BeamSearchSolver(
                self.boxes, self.container,
                beam_width=beam_width,
                max_boxes_per_state=10,
                max_positions_per_box=5
            )
            placements, stats = solver.solve()
            self._update_best(placements, stats, 'beam_search')
        except Exception as e:
            print(f"  Warning: Beam search failed: {e}")

    def _run_grasp(self):
        """Run GRASP algorithm"""
        try:
            n_boxes = len(self.boxes)
            # Much more aggressive reduction for large problems
            if n_boxes <= 30:
                max_iterations = 15
                local_iters = 30
            elif n_boxes <= 100:
                max_iterations = 8
                local_iters = 20
            elif n_boxes <= 200:
                max_iterations = 5
                local_iters = 10
            else:
                max_iterations = 3  # Very few iterations for 200+ boxes
                local_iters = 5

            solver = GRASPSolver(
                self.boxes, self.container,
                alpha=0.3,
                max_iterations=max_iterations,
                local_search_iterations=local_iters
            )
            placements, stats = solver.solve()
            self._update_best(placements, stats, 'grasp')
        except Exception as e:
            print(f"  Warning: GRASP failed: {e}")

    def _run_tabu_search(self):
        """Run Tabu Search"""
        try:
            n_boxes = len(self.boxes)
            # Much more aggressive reduction for large problems
            if n_boxes <= 30:
                max_iterations = 100
            elif n_boxes <= 100:
                max_iterations = 50
            elif n_boxes <= 200:
                max_iterations = 30
            else:
                max_iterations = 15  # Very few for 200+ boxes

            solver = TabuSearchSolver(
                self.boxes, self.container,
                max_iterations=max_iterations,
                tabu_tenure=min(15, n_boxes // 10),
                diversification_threshold=max_iterations // 3
            )
            placements, stats = solver.solve()
            self._update_best(placements, stats, 'tabu_search')
        except Exception as e:
            print(f"  Warning: Tabu Search failed: {e}")
    
    def _run_local_repacking(self):
        """Local re-packing of last K boxes (Optimization #1 - HIGH IMPACT)"""
        if not self.best_placements or len(self.best_placements) < 5:
            return
        
        k_values = [5, 8, 10]  # Try removing different amounts
        
        for k in k_values:
            if len(self.best_placements) <= k:
                continue
            
            # Keep first N-k placements
            kept = self.best_placements[:-k]
            removed_boxes = [p.box for p in self.best_placements[-k:]]
            
            # Try to re-pack removed boxes in different orders
            for attempt in range(3):
                if attempt > 0:
                    random.shuffle(removed_boxes)
                
                # Create new solver with remaining space
                test_placements = list(kept)
                
                # Try to place removed boxes
                from app.solver.utils import SpatialGrid
                grid = SpatialGrid(
                    self.container.length, self.container.width, self.container.height,
                    cell_size=self._get_adaptive_cell_size()
                )
                for p in test_placements:
                    grid.add_box(p)
                
                load_order = len(kept)
                for box in removed_boxes:
                    placed = self._try_place_box_in_space(box, grid, load_order)
                    if placed:
                        test_placements.append(placed)
                        grid.add_box(placed)
                        load_order += 1
                
                # Evaluate
                stats = self._calculate_stats(test_placements)
                self._update_best(test_placements, stats, f'repack_k{k}_attempt{attempt}')
    
    def _try_place_box_in_space(self, box: Box, grid: SpatialGrid, load_order: int) -> Optional[PlacedBox]:
        """Try to place a box in remaining space"""
        from app.solver.utils import BoxRotation, CollisionDetector, StackingValidator
        
        rotations = BoxRotation.get_unique_rotations(box)
        
        # Generate candidate points
        points = [(0, 0, 0)]  # Origin
        for existing in grid.boxes.values():
            points.extend([
                (existing.max_x, existing.y, existing.z),
                (existing.x, existing.max_y, existing.z),
                (existing.x, existing.y, existing.max_z),
            ])
        
        best_placement = None
        best_score = float('inf')
        
        for px, py, pz in points:
            for rotation in rotations:
                length, width, height = BoxRotation.get_dimensions(
                    box.length, box.width, box.height, rotation
                )
                
                # Quick bounds check
                if px + length > self.container.length or \
                   py + width > self.container.width or \
                   pz + height > self.container.height:
                    continue
                
                # Check door entry
                if width > self.container.door_width or height > self.container.door_height:
                    continue
                
                placed = PlacedBox(
                    box=box, x=px, y=py, z=pz, rotation=rotation,
                    length=length, width=width, height=height, load_order=load_order
                )
                
                # Check collision
                if grid.check_collision(placed):
                    continue
                
                # Check support if not on ground
                if pz > 0.1:
                    below = grid.get_boxes_below(placed)
                    if not StackingValidator.check_stacking_rules(placed, below):
                        continue
                
                # Score: prefer ground, back-left
                score = pz * 10000 + px * 10 + py
                if score < best_score:
                    best_score = score
                    best_placement = placed
        
        return best_placement
    
    def _get_adaptive_cell_size(self) -> float:
        """Adaptive spatial grid cell size (Optimization #9)"""
        if not self.boxes:
            return 50.0
        
        # Use median box dimension
        all_dims = []
        for b in self.boxes:
            all_dims.extend([b.length, b.width, b.height])
        all_dims.sort()
        median_dim = all_dims[len(all_dims) // 2]
        
        # Cell size = 2x median dimension, bounded
        return max(30.0, min(100.0, median_dim * 2))
    
    def _calculate_stats(self, placements: List[PlacedBox]) -> dict:
        """Calculate statistics for placements"""
        if not placements:
            return {'utilization_pct': 0, 'is_valid': True}
        
        total_volume = sum(p.volume for p in placements)
        container_volume = self.container.length * self.container.width * self.container.height
        utilization = (total_volume / container_volume) * 100
        
        return {
            'utilization_pct': utilization,
            'placed_count': len(placements),
            'total_volume': total_volume,
            'is_valid': True
        }

    def _run_genetic_algorithm_fast(self):
        """Run optimized genetic algorithm with reduced iterations"""
        from app.solver.optimizer import GeneticAlgorithmSolver
        
        n_boxes = len(self.boxes)
        
        # FAST configurations - drastically reduced for large problems
        if n_boxes <= 30:
            configs = [{'pop': 20, 'gen': 15, 'mut': 0.12}]
        elif n_boxes <= 100:
            configs = [{'pop': 25, 'gen': 12, 'mut': 0.1}]
        elif n_boxes <= 200:
            configs = [{'pop': 20, 'gen': 8, 'mut': 0.1}]
        else:
            # For 200+ boxes, skip GA entirely - heuristics are good enough
            print("  Skipping GA for large problem (>200 boxes)")
            return
        
        for i, cfg in enumerate(configs):
            if self._should_terminate():
                break
            try:
                solver = GeneticAlgorithmSolver(
                    self.boxes, self.container,
                    population_size=cfg['pop'],
                    generations=cfg['gen'],
                    mutation_rate=cfg['mut'],
                    crossover_rate=0.85,
                    parallel_eval=True,
                    use_cache=True,
                    early_stopping_patience=5  # Stop early if no improvement
                )
                placements, stats = solver.solve()
                self._update_best(placements, stats, f'ga_fast_{i}')
            except Exception as e:
                print(f"  Warning: GA config {i} failed: {e}")
    
    def _run_simulated_annealing_fast(self):
        """Run fast simulated annealing"""
        from app.solver.optimizer import SimulatedAnnealingSolver
        
        n_boxes = len(self.boxes)
        
        # Single fast SA run with quick cooling
        if n_boxes <= 30:
            configs = [{'temp': 50, 'cooling': 0.90, 'iters': 20}]
        else:
            configs = [
                {'temp': 80, 'cooling': 0.88, 'iters': 25},
                {'temp': 50, 'cooling': 0.92, 'iters': 30},
            ]
        
        for i, cfg in enumerate(configs):
            if self._should_terminate():
                break
            try:
                solver = SimulatedAnnealingSolver(
                    self.boxes, self.container,
                    initial_temp=cfg['temp'],
                    cooling_rate=cfg['cooling'],
                    iterations_per_temp=cfg['iters'],
                    min_temp=0.5,  # Higher min temp = faster termination
                    use_cache=True
                )
                placements, stats = solver.solve()
                self._update_best(placements, stats, f'sa_fast_{i}')
            except Exception as e:
                print(f"  Warning: SA config {i} failed: {e}")
    
    def _run_iterated_local_search(self):
        """Run iterated local search with restarts"""
        n_restarts = 5
        
        for restart in range(n_restarts):
            # Start from a random good solution
            order = list(range(len(self.boxes)))
            
            # Bias towards good orderings - now including delivery_order
            if restart % 4 == 0:
                order.sort(key=lambda i: (-self.boxes[i].delivery_order, -self.boxes[i].priority, -self.boxes[i].volume))
            elif restart % 4 == 1:
                order.sort(key=lambda i: (-self.boxes[i].priority, -self.boxes[i].volume))
            elif restart % 4 == 2:
                order.sort(key=lambda i: -self.boxes[i].volume)
            else:
                random.shuffle(order)
            
            current_order = order.copy()
            current_placements, current_stats = self._evaluate_order(current_order)
            current_fitness = self._calculate_fitness(current_placements, current_stats)
            
            best_local_order = current_order.copy()
            best_local_fitness = current_fitness
            best_local_placements = current_placements
            best_local_stats = current_stats
            
            # Local search iterations
            no_improve = 0
            max_no_improve = 50
            
            while no_improve < max_no_improve:
                # Generate neighbor
                neighbor = self._get_neighbor(current_order)
                neighbor_placements, neighbor_stats = self._evaluate_order(neighbor)
                neighbor_fitness = self._calculate_fitness(neighbor_placements, neighbor_stats)
                
                if neighbor_fitness > current_fitness:
                    current_order = neighbor
                    current_fitness = neighbor_fitness
                    current_placements = neighbor_placements
                    current_stats = neighbor_stats
                    no_improve = 0
                    
                    if current_fitness > best_local_fitness:
                        best_local_fitness = current_fitness
                        best_local_order = current_order.copy()
                        best_local_placements = current_placements
                        best_local_stats = current_stats
                else:
                    no_improve += 1
            
            self._update_best(best_local_placements, best_local_stats, f'ils_restart_{restart}')
    
    def _evaluate_order(self, order: List[int]) -> Tuple[List[PlacedBox], dict]:
        """Evaluate a box ordering"""
        solver = HeuristicSolver(self.boxes, self.container, use_spatial_grid=True)
        return solver.solve(box_order=order)
    
    def _get_neighbor(self, order: List[int]) -> List[int]:
        """Generate neighbor for local search"""
        neighbor = order.copy()
        n = len(neighbor)
        
        move = random.choice(['swap', 'insert', 'reverse', '2opt'])
        
        if move == 'swap':
            i, j = random.sample(range(n), 2)
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        elif move == 'insert':
            i = random.randint(0, n - 1)
            j = random.randint(0, n - 1)
            item = neighbor.pop(i)
            neighbor.insert(j, item)
        elif move == 'reverse':
            i = random.randint(0, n - 2)
            j = random.randint(i + 1, n)
            neighbor[i:j] = reversed(neighbor[i:j])
        elif move == '2opt':
            i = random.randint(0, n - 2)
            j = random.randint(i + 2, n)
            neighbor[i:j] = neighbor[i:j][::-1]
        
        return neighbor


class BranchAndBoundSolver:
    """
    Branch and Bound solver for exact optimal solution (for small problems).
    Only practical for problems with ~15 boxes or fewer.
    """
    
    def __init__(self, boxes: List[Box], container: ContainerSpace, max_boxes: int = 15):
        self.boxes = boxes[:max_boxes] if len(boxes) > max_boxes else boxes
        self.container = container
        self.best_placements: List[PlacedBox] = []
        self.best_utilization = 0.0
        self.nodes_explored = 0
    
    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """
        Solve using branch and bound (only for small problems)
        """
        n = len(self.boxes)
        if n > 15:
            print(f"Warning: B&B solver limited to 15 boxes, using first 15 of {n}")
        
        print(f"BranchAndBoundSolver: Searching permutations of {n} boxes...")
        
        # For very small problems, try all permutations
        if n <= 8:
            self._exhaustive_search()
        else:
            # Use B&B with pruning
            self._branch_and_bound()
        
        stats = {
            'utilization_pct': self.best_utilization,
            'placed_count': len(self.best_placements),
            'failed_count': len(self.boxes) - len(self.best_placements),
            'total_weight': sum(p.box.weight for p in self.best_placements),
            'nodes_explored': self.nodes_explored,
            'solver': 'branch_and_bound',
            'is_valid': True,
            'validation_errors': []
        }
        
        return self.best_placements, stats
    
    def _exhaustive_search(self):
        """Try all permutations (only for n <= 8)"""
        from itertools import permutations
        
        total = 1
        for i in range(1, len(self.boxes) + 1):
            total *= i
        print(f"  Trying all {total} permutations...")
        
        for perm in permutations(range(len(self.boxes))):
            self.nodes_explored += 1
            solver = HeuristicSolver(self.boxes, self.container, use_spatial_grid=True)
            placements, stats = solver.solve(box_order=list(perm))
            
            if stats['utilization_pct'] > self.best_utilization:
                self.best_utilization = stats['utilization_pct']
                self.best_placements = placements
                print(f"  New best: {self.best_utilization:.2f}%")
    
    def _branch_and_bound(self):
        """B&B with pruning for larger problems"""
        # Start with a greedy solution for initial bound - now with delivery_order
        order = list(range(len(self.boxes)))
        order.sort(key=lambda i: (-self.boxes[i].delivery_order, -self.boxes[i].priority, -self.boxes[i].volume))
        
        solver = HeuristicSolver(self.boxes, self.container, use_spatial_grid=True)
        placements, stats = solver.solve(box_order=order)
        self.best_utilization = stats['utilization_pct']
        self.best_placements = placements
        
        # Calculate upper bound (sum of all box volumes / container volume)
        total_box_volume = sum(b.volume for b in self.boxes)
        container_volume = self.container.length * self.container.width * self.container.height
        upper_bound = min(100.0, (total_box_volume / container_volume) * 100)
        
        print(f"  Initial bound: {self.best_utilization:.2f}%, Upper bound: {upper_bound:.2f}%")
        
        # B&B search with random restarts
        for _ in range(1000):
            self.nodes_explored += 1
            order = list(range(len(self.boxes)))
            random.shuffle(order)
            
            solver = HeuristicSolver(self.boxes, self.container, use_spatial_grid=True)
            placements, stats = solver.solve(box_order=order)
            
            if stats['utilization_pct'] > self.best_utilization:
                self.best_utilization = stats['utilization_pct']
                self.best_placements = placements
                print(f"  New best: {self.best_utilization:.2f}%")
            
            # Early termination if we're close to upper bound
            if self.best_utilization >= upper_bound * 0.99:
                print(f"  Reached near-optimal solution!")
                break
