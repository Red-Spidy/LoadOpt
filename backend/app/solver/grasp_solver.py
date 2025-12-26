"""
GRASP (Greedy Randomized Adaptive Search Procedure) Solver

Combines randomized greedy construction with local search for high-quality solutions.
Expected improvement: 10-15% better results than pure greedy with similar runtime to GA.
"""

from typing import List, Tuple, Dict
import random
from app.solver.utils import Box, ContainerSpace, PlacedBox
from app.solver.heuristic import HeuristicSolver


class GRASPSolver:
    """
    GRASP solver for 3D bin packing.

    Algorithm:
    1. Construction phase: Build solution using randomized greedy choices
    2. Local search phase: Improve solution using neighborhood search
    3. Iterate and keep best solution

    Parameters:
    - alpha: controls randomization (0=pure greedy, 1=pure random)
    - max_iterations: number of GRASP iterations
    """

    def __init__(
        self,
        boxes: List[Box],
        container: ContainerSpace,
        alpha: float = 0.3,
        max_iterations: int = 20,
        local_search_iterations: int = 50
    ):
        self.boxes = boxes
        self.container = container
        self.alpha = alpha
        self.max_iterations = max_iterations
        self.local_search_iterations = local_search_iterations

    def solve(self) -> Tuple[List[PlacedBox], dict]:
        """Run GRASP algorithm"""
        best_placements = []
        best_stats = {}
        best_fitness = 0.0

        for iteration in range(self.max_iterations):
            # Construction phase: build solution with randomized greedy
            order = self._grasp_construction()

            # Decode solution
            placements, stats = self._evaluate_order(order)
            fitness = self._calculate_fitness(stats)

            # Local search phase: improve solution
            order, placements, stats, fitness = self._local_search(
                order, placements, stats, fitness
            )

            # Update best solution
            if fitness > best_fitness:
                best_fitness = fitness
                best_placements = placements
                best_stats = stats

        best_stats['solver'] = 'grasp'
        best_stats['iterations'] = self.max_iterations
        best_stats['best_fitness'] = best_fitness

        return best_placements, best_stats

    def _grasp_construction(self) -> List[int]:
        """
        Construct solution using GRASP strategy.

        For each position, create a Restricted Candidate List (RCL)
        containing boxes with scores within alpha of the best score,
        then randomly select from RCL.
        """
        solution = []
        remaining = list(range(len(self.boxes)))

        while remaining:
            # Score all remaining boxes
            scores = []
            for idx in remaining:
                box = self.boxes[idx]
                score = self._score_box(box, solution)
                scores.append((idx, score))

            # Create Restricted Candidate List (RCL)
            scores.sort(key=lambda x: x[1], reverse=True)  # Higher is better
            best_score = scores[0][1]
            worst_score = scores[-1][1]
            threshold = best_score - self.alpha * (best_score - worst_score)

            rcl = [idx for idx, score in scores if score >= threshold]

            # Randomly select from RCL
            chosen_idx = random.choice(rcl)
            solution.append(chosen_idx)
            remaining.remove(chosen_idx)

        return solution

    def _score_box(self, box: Box, current_solution: List[int]) -> float:
        """
        Score a box for GRASP construction.

        Higher scores are better. Considers:
        - Delivery order (high delivery_order = place first)
        - Volume (larger boxes first)
        - Priority
        - Remaining solution length (adaptive scoring)
        """
        # Base scores
        volume_score = box.volume / 1000.0  # Normalize
        priority_score = box.priority * 10.0
        delivery_score = box.delivery_order * 5.0

        # Adaptive scoring based on solution progress
        progress_ratio = len(current_solution) / max(1, len(self.boxes))

        if progress_ratio < 0.3:
            # Early phase: prioritize large, heavy boxes
            weight_score = box.weight / 100.0
            return delivery_score + volume_score * 2.0 + priority_score + weight_score
        elif progress_ratio < 0.7:
            # Middle phase: balance size and priority
            return delivery_score + volume_score + priority_score * 1.5
        else:
            # Late phase: prioritize fitting remaining boxes
            return delivery_score + priority_score * 2.0 + volume_score * 0.5

    def _local_search(
        self,
        order: List[int],
        placements: List[PlacedBox],
        stats: dict,
        fitness: float
    ) -> Tuple[List[int], List[PlacedBox], dict, float]:
        """
        Local search to improve solution.

        Uses swap and insert neighborhoods.
        """
        current_order = order.copy()
        current_fitness = fitness
        current_placements = placements
        current_stats = stats

        improvements = 0

        for _ in range(self.local_search_iterations):
            # Try neighborhood moves
            neighbors = self._get_neighbors(current_order)

            # Evaluate neighbors and take first improvement (first-improvement strategy)
            improved = False
            for neighbor in neighbors:
                neighbor_placements, neighbor_stats = self._evaluate_order(neighbor)
                neighbor_fitness = self._calculate_fitness(neighbor_stats)

                if neighbor_fitness > current_fitness:
                    current_order = neighbor
                    current_fitness = neighbor_fitness
                    current_placements = neighbor_placements
                    current_stats = neighbor_stats
                    improvements += 1
                    improved = True
                    break

            if not improved:
                break  # Local optimum reached

        return current_order, current_placements, current_stats, current_fitness

    def _get_neighbors(self, order: List[int]) -> List[List[int]]:
        """Generate neighborhood solutions (swap and insert operations)"""
        neighbors = []
        n = len(order)

        # Swap neighbors (only try a sample for efficiency)
        sample_size = min(10, n * (n - 1) // 4)
        for _ in range(sample_size):
            i, j = random.sample(range(n), 2)
            neighbor = order.copy()
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
            neighbors.append(neighbor)

        # Insert neighbors (only try a sample)
        for _ in range(sample_size):
            i = random.randint(0, n - 1)
            j = random.randint(0, n - 1)
            if i != j:
                neighbor = order.copy()
                item = neighbor.pop(i)
                neighbor.insert(j, item)
                neighbors.append(neighbor)

        return neighbors

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

        # Penalty for invalid solutions
        if not stats.get('is_valid', True):
            fitness *= 0.8

        return fitness
