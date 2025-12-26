"""
Tabu Search Solver for 3D Bin Packing

Uses memory-based search to avoid cycles and escape local optima.
Expected improvement: 5-10% better than Simulated Annealing.
"""

from typing import List, Tuple, Set, Deque
from collections import deque
import random
from app.solver.utils import Box, ContainerSpace, PlacedBox
from app.solver.heuristic import HeuristicSolver


class TabuSearchSolver:
    """
    Tabu Search solver with adaptive tabu tenure and aspiration criteria.

    Key features:
    - Tabu list prevents cycling back to recent solutions
    - Aspiration criterion allows tabu moves if they improve best solution
    - Adaptive tabu tenure based on search progress
    - Diversification when stuck in local optimum
    """

    def __init__(
        self,
        boxes: List[Box],
        container: ContainerSpace,
        max_iterations: int = 500,
        tabu_tenure: int = 20,
        diversification_threshold: int = 50
    ):
        self.boxes = boxes
        self.container = container
        self.max_iterations = max_iterations
        self.tabu_tenure = tabu_tenure
        self.diversification_threshold = diversification_threshold

        # Tabu list stores recent moves
        self.tabu_list: Deque[Tuple[int, int]] = deque(maxlen=tabu_tenure)

        # Best solution tracking
        self.best_solution = None
        self.best_fitness = float('-inf')
        self.best_placements = []
        self.best_stats = {}

        # Iteration tracking
        self.iterations_without_improvement = 0

    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """Run Tabu Search algorithm"""
        # Initialize with greedy solution
        current_solution = self._initialize_solution()
        current_placements, current_stats = self._evaluate_order(current_solution)
        current_fitness = self._calculate_fitness(current_stats)

        self.best_solution = current_solution.copy()
        self.best_fitness = current_fitness
        self.best_placements = current_placements
        self.best_stats = current_stats

        for iteration in range(self.max_iterations):
            # Generate candidate neighbors
            neighbors = self._generate_neighbors(current_solution)

            # Find best non-tabu neighbor (or use aspiration criterion)
            best_neighbor = None
            best_neighbor_fitness = float('-inf')
            best_neighbor_placements = None
            best_neighbor_stats = None
            best_move = None

            for neighbor, move in neighbors:
                # Check if move is tabu
                is_tabu = move in self.tabu_list

                # Evaluate neighbor
                placements, stats = self._evaluate_order(neighbor)
                fitness = self._calculate_fitness(stats)

                # Aspiration criterion: accept tabu move if it's better than best
                if fitness > best_neighbor_fitness:
                    if not is_tabu or fitness > self.best_fitness:
                        best_neighbor = neighbor
                        best_neighbor_fitness = fitness
                        best_neighbor_placements = placements
                        best_neighbor_stats = stats
                        best_move = move

            # Move to best neighbor
            if best_neighbor is not None:
                current_solution = best_neighbor
                current_fitness = best_neighbor_fitness
                current_placements = best_neighbor_placements
                current_stats = best_neighbor_stats

                # Add move to tabu list
                if best_move:
                    self.tabu_list.append(best_move)

                # Update best solution
                if current_fitness > self.best_fitness:
                    self.best_solution = current_solution.copy()
                    self.best_fitness = current_fitness
                    self.best_placements = current_placements
                    self.best_stats = current_stats
                    self.iterations_without_improvement = 0
                else:
                    self.iterations_without_improvement += 1
            else:
                self.iterations_without_improvement += 1

            # Diversification: restart from random solution if stuck
            if self.iterations_without_improvement >= self.diversification_threshold:
                current_solution = self._diversify()
                current_placements, current_stats = self._evaluate_order(current_solution)
                current_fitness = self._calculate_fitness(current_stats)
                self.iterations_without_improvement = 0
                self.tabu_list.clear()  # Clear tabu list for fresh start

            # Adaptive tabu tenure
            if iteration % 50 == 0:
                self._adapt_tabu_tenure()

        self.best_stats['solver'] = 'tabu_search'
        self.best_stats['iterations'] = self.max_iterations
        self.best_stats['best_fitness'] = self.best_fitness

        return self.best_placements, self.best_stats

    def _initialize_solution(self) -> List[int]:
        """Initialize with greedy solution based on delivery order, priority, and volume"""
        solution = list(range(len(self.boxes)))
        solution.sort(key=lambda i: (
            -self.boxes[i].delivery_order,
            -self.boxes[i].priority,
            -self.boxes[i].volume
        ))
        return solution

    def _generate_neighbors(self, solution: List[int]) -> List[Tuple[List[int], Tuple[int, int]]]:
        """
        Generate neighbor solutions using various operators.

        Returns: List of (neighbor_solution, move) tuples
        """
        neighbors = []
        n = len(solution)

        # Swap operator (sample for efficiency)
        num_swaps = min(20, n * (n - 1) // 4)
        for _ in range(num_swaps):
            i, j = random.sample(range(n), 2)
            neighbor = solution.copy()
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
            move = (min(i, j), max(i, j))  # Normalized move representation
            neighbors.append((neighbor, move))

        # Insert operator
        num_inserts = min(15, n)
        for _ in range(num_inserts):
            i = random.randint(0, n - 1)
            j = random.randint(0, n - 1)
            if i != j:
                neighbor = solution.copy()
                item = neighbor.pop(i)
                neighbor.insert(j, item)
                move = (i, j)
                neighbors.append((neighbor, move))

        # Reverse operator
        num_reverses = min(10, n)
        for _ in range(num_reverses):
            i = random.randint(0, n - 2)
            j = random.randint(i + 2, n)
            neighbor = solution.copy()
            neighbor[i:j] = reversed(neighbor[i:j])
            move = (i, j)
            neighbors.append((neighbor, move))

        return neighbors

    def _diversify(self) -> List[int]:
        """Create diversified solution by partially randomizing"""
        solution = self.best_solution.copy()
        n = len(solution)

        # Randomize a portion of the solution (30-50%)
        num_to_shuffle = random.randint(n // 3, n // 2)
        indices = random.sample(range(n), num_to_shuffle)

        # Extract and shuffle selected elements
        elements = [solution[i] for i in sorted(indices, reverse=True)]
        for i in sorted(indices, reverse=True):
            solution.pop(i)

        random.shuffle(elements)

        # Reinsert at random positions
        for element in elements:
            pos = random.randint(0, len(solution))
            solution.insert(pos, element)

        return solution

    def _adapt_tabu_tenure(self):
        """Adapt tabu tenure based on search progress"""
        if self.iterations_without_improvement > 30:
            # Increase tenure when stuck (more restrictive)
            new_tenure = min(30, self.tabu_tenure + 5)
        elif self.iterations_without_improvement < 10:
            # Decrease tenure when improving (more flexible)
            new_tenure = max(10, self.tabu_tenure - 2)
        else:
            new_tenure = self.tabu_tenure

        if new_tenure != self.tabu_tenure:
            self.tabu_tenure = new_tenure
            self.tabu_list = deque(self.tabu_list, maxlen=new_tenure)

    def _evaluate_order(self, order: List[int]) -> Tuple[List[PlacedBox], dict]:
        """Evaluate a box ordering"""
        ordered_boxes = [self.boxes[i] for i in order if i < len(self.boxes)]
        solver = HeuristicSolver(ordered_boxes, self.container, use_spatial_grid=True)
        return solver.solve()

    def _calculate_fitness(self, stats: dict) -> float:
        """Calculate fitness from stats"""
        if not stats:
            return 0.0

        utilization = stats.get('utilization_pct', 0) / 100.0
        placed_ratio = stats.get('placed_count', 0) / max(1, len(self.boxes))

        fitness = utilization * 0.6 + placed_ratio * 0.4

        if not stats.get('is_valid', True):
            fitness *= 0.85

        return fitness
