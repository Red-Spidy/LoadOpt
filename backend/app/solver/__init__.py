"""
LoadOpt Solver Module

Optimized 3D bin packing algorithms for container loading.
"""

# =============================================================================
# LEGACY API (v1.x) - Active
# =============================================================================

from app.solver.utils import (
    Box, ContainerSpace, PlacedBox, PlacementPoint,
    BoxRotation, CollisionDetector, StackingValidator, 
    WeightDistribution, SpatialGrid
)
from app.solver.heuristic import HeuristicSolver, LayerBuildingHeuristic
from app.solver.optimizer import (
    GeneticAlgorithmSolver, SimulatedAnnealingSolver, 
    HybridSolver, FitnessCache
)
from app.solver.optimal_solver import OptimalSolver, BranchAndBoundSolver

# =============================================================================
# VERSION INFO
# =============================================================================

__version__ = '1.0.0'
__author__ = 'LoadOpt Team'

# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    'Box', 'ContainerSpace', 'PlacedBox', 'PlacementPoint',
    # Utilities
    'BoxRotation', 'CollisionDetector', 'StackingValidator', 
    'WeightDistribution', 'SpatialGrid',
    # Solvers
    'HeuristicSolver', 'LayerBuildingHeuristic',
    'GeneticAlgorithmSolver', 'SimulatedAnnealingSolver', 
    'HybridSolver', 'OptimalSolver', 'BranchAndBoundSolver',
    # Caching
    'FitnessCache',
]

# Note: v2.0 solver modules are available in the following files but not yet activated:
# - domain/models.py - New domain models
# - validators/__init__.py - Validation system
# - spatial/__init__.py - Spatial indexing
# - engine/placement.py - Placement engine
# - solvers/*.py - Multi-phase solvers
# - memory/__init__.py - Pattern caching
# - orchestrator.py - Main orchestrator
# - bridge.py - API integration