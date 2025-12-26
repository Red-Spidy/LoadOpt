# LoadOpt Solver Architecture

## Overview

LoadOpt is a commercial-grade 3D container loading optimizer that packs rectangular boxes into trucks/containers while maximizing volume utilization and respecting real-world logistics constraints.

## Design Philosophy

The solver follows these key principles:

1. **Progressive Deepening**: Start with fast heuristics, refine with metaheuristics
2. **Separated Concerns**: Validators, spatial indexing, and solvers are independent modules
3. **Learn from Experience**: Pattern caching improves performance on similar problems
4. **Full Explainability**: Every placement decision can be traced and explained

## Architecture

```
app/solver/
├── __init__.py              # Package exports
├── orchestrator.py          # Main LoadOptSolver entry point
├── bridge.py                # API integration layer
│
├── domain/
│   └── models.py            # Core domain models (Box, Container, PlacedBox)
│
├── validators/
│   └── __init__.py          # Rule validation system
│
├── spatial/
│   └── __init__.py          # Spatial indexing (Grid, Extreme Points)
│
├── engine/
│   ├── __init__.py          # Module exports
│   └── placement.py         # Core placement engine
│
├── solvers/
│   ├── __init__.py          # Module exports
│   ├── core.py              # Multi-phase solver, Fast Heuristic, Layer Building
│   ├── metaheuristics.py    # Genetic Algorithm, Simulated Annealing
│   ├── lns.py               # Large Neighborhood Search
│   └── local_search.py      # Local Re-packing, Position Optimization
│
└── memory/
    └── __init__.py          # Pattern caching and learning
```

## Solving Pipeline

The solver uses a multi-phase approach where each phase can be skipped if quality thresholds are met:

```
┌─────────────────┐
│ Fast Heuristic  │  ~100ms
│ (Greedy BLF)    │  Target: 70%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Layer Building  │  ~500ms
│ (Height layers) │  Target: 75%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Genetic Algo    │  ~5s
│ (Population)    │  Target: 85%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Simulated Ann.  │  ~3s
│ (Local search)  │  Target: 88%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LNS             │  ~5s
│ (Destroy/Repair)│  Target: 90%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Local Re-pack   │  ~1s
│ (k-box subsets) │  Final polish
└─────────────────┘
```

## Key Components

### Domain Models (`domain/models.py`)

**Box**: Represents a physical box with:
- Dimensions (L×W×H)
- Weight
- Rotation constraints
- Fragility flag
- Stacking group
- Delivery order

**Container**: Represents the loading space:
- Internal dimensions
- Weight limits
- Axle weight limits
- Obstacles (wheel wells, etc.)

**PlacedBox**: A box with assigned position:
- (x, y, z) coordinates
- Actual dimensions after rotation
- Support area percentage

### Validators (`validators/__init__.py`)

Each validator checks one constraint type:

| Validator | Checks |
|-----------|--------|
| `GeometryValidator` | Box fits in container bounds |
| `SupportValidator` | Box has ≥70% floor/support contact |
| `StackingValidator` | Fragile items not crushed, group rules |
| `WeightValidator` | Container and axle limits |
| `DeliveryOrderValidator` | LIFO access for delivery stops |

Validators are composable:
```python
validator = CompositeValidator([
    GeometryValidator(container),
    SupportValidator(min_support=0.70),
    StackingValidator(),
    WeightValidator(container),
])
```

### Spatial Indexing (`spatial/__init__.py`)

**SpatialGrid**: O(1) collision detection using 3D grid cells
- 50mm default cell size
- Query occupied cells efficiently
- Track which boxes occupy each cell

**ExtremePointManager**: Manages candidate positions
- Extreme Points algorithm for placement candidates
- Heap-based priority ordering
- Automatic pruning of dominated points

**VolumeTracker**: Real-time utilization tracking
- Layer-by-layer volume analysis
- Identify gaps and unused regions

### Placement Engine (`engine/placement.py`)

**PlacementScorer**: Multi-criteria placement scoring:
- **Height Penalty**: Prefer lower positions
- **Gap Penalty**: Minimize wasted space
- **Alignment Bonus**: Reward wall/box alignment
- **Support Bonus**: Prefer well-supported positions
- **Future Space Penalty**: Don't block good future positions

**PlacementEngine**: Core placement logic:
- Try all rotations at all extreme points
- Validate each candidate
- Score and rank candidates
- Execute best placement

### Solvers

**FastHeuristicSolver**: Greedy best-fit decreasing
- Sort by volume/height
- Place at best-scoring position
- O(n² × p) where p = positions

**LayerBuildingSolver**: Layer-based packing
- Build horizontal layers
- Fill each layer before starting next
- Good for uniform box sizes

**GeneticAlgorithmSolver**: Population-based optimization
- Chromosome = box ordering permutation
- Ordered crossover (OX)
- Adaptive mutation rate
- Fitness caching for speed

**SimulatedAnnealingSolver**: Escape local optima
- Temperature-based acceptance
- Automatic reheating on stagnation
- Multiple move types (swap, reverse, relocate)

**LNSSolver**: Large Neighborhood Search
- Destroy strategies: HIGHEST_Z, GAP_CREATORS, VOID_BLOCKERS
- Repair using layer building
- Adaptive strategy selection

**LocalRepackingSolver**: Final improvement
- K-box subset optimization
- Try optimal arrangements of k boxes
- k ∈ {5, 8, 10, 15}

### Memory System (`memory/__init__.py`)

**PatternSignature**: Creates fingerprints of problems
- SKU distribution signature
- Container signature
- Combined problem signature

**SolverMemory**: Learning from past solutions
- Cache successful patterns
- Retrieve seed orderings for similar problems
- Track best-performing weight configurations

## Usage

### Basic Usage

```python
from app.solver import LoadOptSolver, Box, Container

# Create boxes
boxes = [
    Box(id=1, sku_id='A', length=10, width=10, height=10, weight=5),
    Box(id=2, sku_id='B', length=20, width=15, height=12, weight=8),
]

# Create container
container = Container(
    id='truck',
    name='Standard Truck',
    length=600,  # cm
    width=240,
    height=270,
    max_weight=25000  # kg
)

# Solve
solver = LoadOptSolver()
result = solver.solve(boxes, container)

print(f"Utilization: {result.utilization_pct:.1f}%")
print(f"Boxes placed: {result.boxes_placed}/{result.boxes_total}")
print(f"Solve time: {result.solve_time_seconds:.2f}s")
print(f"Phase used: {result.phase_used}")
```

### With Configuration

```python
from app.solver import SolverConfig

config = SolverConfig(
    max_time_seconds=30.0,
    target_utilization=85.0,
    min_support_percentage=0.80,
    validate_stacking=True,
    validate_delivery_order=True,
    use_genetic_algorithm=True,
    use_simulated_annealing=True,
    use_lns=True,
)

result = solver.solve(boxes, container, config)
```

### Dict-Based API

```python
from app.solver import solve_loading_problem

result = solve_loading_problem(
    boxes=[
        {'length': 10, 'width': 10, 'height': 10, 'weight': 5},
        {'length': 20, 'width': 15, 'height': 12, 'weight': 8},
    ],
    container={'length': 600, 'width': 240, 'height': 270},
    config={'max_time_seconds': 30}
)
```

## Performance Characteristics

| Problem Size | Fast Mode | Standard Mode | Optimal Mode |
|--------------|-----------|---------------|--------------|
| 20 boxes     | <0.1s     | <1s           | <5s          |
| 50 boxes     | <0.2s     | <3s           | <15s         |
| 100 boxes    | <0.5s     | <10s          | <30s         |
| 200 boxes    | <1s       | <30s          | <60s         |
| 500 boxes    | <3s       | <60s          | <120s        |

Expected utilization rates:
- **Fast**: 70-80%
- **Standard**: 80-88%
- **Optimal**: 85-95%

## Constraint Handling

### Rotation Constraints

Boxes can have restricted rotations:
```python
box = Box(
    ...,
    can_rotate=True,
    allowed_rotations=[
        Rotation.ORIGINAL,      # LWH (standing)
        Rotation.ROTATE_Z90,    # WHL
    ]
)
```

### Fragility

Fragile boxes are placed on top:
```python
box = Box(..., fragile=True)
```

### Stacking Groups

Only same-group items can be stacked:
```python
box = Box(..., stacking_group="electronics")
```

### Delivery Order

First delivery = load last (near door):
```python
box = Box(..., delivery_order=1)  # First stop
```

## Extending the Solver

### Custom Validators

```python
from app.solver.validators import Validator

class CustomValidator(Validator):
    def validate(self, box, position, rotation, container, placements):
        # Custom validation logic
        return True, "OK"
```

### Custom Scoring

```python
from app.solver.engine import ScoringWeights

weights = ScoringWeights(
    height_penalty=5000.0,      # Less height penalty
    gap_penalty=1000.0,         # More gap penalty
    alignment_bonus=200.0,      # Reward alignment
    support_bonus=500.0,        # Reward support
)
```

## Troubleshooting

### Low Utilization

1. Check box dimensions match container
2. Enable all rotations if possible
3. Try optimal mode with more time
4. Check for conflicting constraints

### Boxes Not Placed

1. Check validation errors in result
2. Review stacking/fragility constraints
3. Check weight limits
4. Verify delivery order isn't too restrictive

### Slow Performance

1. Reduce max_time_seconds
2. Use fast or standard mode
3. Disable LNS for faster results
4. Check for excessive constraint checking
