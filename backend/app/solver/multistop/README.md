# Multi-Stop Load Planning Module

**Production-grade multi-stop logistics optimization for LoadOpt**

---

## Quick Links

- 📖 **Quick Start**: See [MULTISTOP_QUICKSTART.md](../../../../MULTISTOP_QUICKSTART.md)
- 🏗️ **Architecture**: See [MULTISTOP_ARCHITECTURE.md](../../../../MULTISTOP_ARCHITECTURE.md)
- 🎨 **Visual Guide**: See [MULTISTOP_VISUAL_GUIDE.md](../../../../MULTISTOP_VISUAL_GUIDE.md)
- 📊 **Summary**: See [MULTISTOP_SUMMARY.md](../../../../MULTISTOP_SUMMARY.md)

---

## What This Module Does

Optimizes container loading for multi-stop delivery routes, ensuring:
- ✅ Boxes for earlier stops are accessible (near door)
- ✅ Minimal rehandling at each stop
- ✅ Safety constraints satisfied (fragile, weight, stacking)
- ✅ Operationally executable plans

---

## Module Structure

```
multistop/
├── __init__.py              # Public API exports
├── models.py                # Data models (Stop, Trip, VirtualSKU, Plans)
├── preprocessor.py          # Virtual SKU splitting, priority calculation
├── placement_engine.py      # Zone-based 3D placement
├── validator.py             # Accessibility analysis, rehandling detection
├── optimizer.py             # Main orchestrator
├── examples.py              # 6 complete worked examples
└── README.md                # This file
```

---

## Basic Usage

```python
from backend.app.solver.multistop import quick_optimize
from backend.app.solver.domain.models import Box, Container
from backend.app.solver.multistop.models import Trip, Stop

# 1. Define container
container = Container(
    length=589, width=235, height=239,
    max_weight=28000, door_width=235, door_height=239
)

# 2. Define SKU catalog
sku_catalog = {
    1: Box(id=1, sku_id=1, instance_index=0,
           length=50, width=40, height=30, weight=10)
}

# 3. Define stops
stops = [
    Stop(stop_number=1, location_id="A", location_name="Store A",
         sku_requirements={1: 10}),
    Stop(stop_number=2, location_id="B", location_name="Store B",
         sku_requirements={1: 5})
]

# 4. Create trip
trip = Trip(trip_id="TRIP-001", stops=stops, container=container)

# 5. Optimize
result = quick_optimize(trip, sku_catalog, verbose=True)

# 6. Use results
print(f"Utilization: {result.overall_utilization_pct:.1f}%")
print(f"Rehandling: {result.total_rehandling_events} events")
```

---

## Key Features

### Virtual SKU Splitting
Automatically handles SKUs appearing at multiple stops by creating Virtual SKUs

### Priority-Based Placement
Multi-factor priority ensures LIFO ordering while handling fragile, heavy, and time-critical items

### Zone-Based Loading
Divides container into zones per stop (earlier stops near door, later stops in back)

### Accessibility Analysis
Detects and quantifies rehandling requirements at each stop

### Multiple Strategies
- STRICT_LIFO: Zero rehandling
- MINIMAL_REHANDLING: Configurable tolerance
- OPTIMIZED: Balance utilization vs rehandling

---

## Examples

Run the examples:

```bash
cd backend/app/solver/multistop
python examples.py
```

Or import specific examples:

```python
from backend.app.solver.multistop.examples import (
    example_1_simple_two_stop,
    example_2_complex_overlap,
    example_3_fragile_early_stop,
    example_4_strict_lifo,
    example_5_heavy_concentration,
    example_6_pickup_delivery
)

# Run a single example
result = example_2_complex_overlap()

# Or run all examples
from backend.app.solver.multistop.examples import run_all_examples
results = run_all_examples()
```

---

## Configuration

### Custom Priority Weights

```python
from backend.app.solver.multistop.preprocessor import PriorityWeights
from backend.app.solver.multistop.optimizer import MultiStopOptimizer

weights = PriorityWeights(
    stop_priority_base=2000,
    fragile_bonus=1000,
    heavy_item_bonus=300
)

optimizer = MultiStopOptimizer(priority_weights=weights)
result = optimizer.optimize(trip, sku_catalog)
```

### Zoning Strategies

```python
optimizer = MultiStopOptimizer(
    use_proportional_zones=True,    # Volume-proportional (recommended)
    allow_zone_overflow=True,       # Allow cross-zone placement
    accessibility_weight=0.8        # High accessibility priority
)
```

---

## Output Structure

```python
result: MultiStopLoadPlan
├── placements: List[PlacedBox]
│   └── (x, y, z, rotation, box details)
├── unload_plans: Dict[int, UnloadPlan]
│   ├── boxes_to_unload
│   ├── rehandling_events
│   ├── accessibility_score
│   └── estimated_time_minutes
├── stop_metrics: Dict[int, StopMetrics]
│   ├── volume_used
│   ├── weight_loaded
│   └── utilization_pct
├── validation_errors: List[str]
├── validation_warnings: List[str]
└── solver_metadata: Dict
```

---

## Algorithm Overview

```
Phase 1: PREPROCESSING
  ├─ Split multi-stop SKUs → Virtual SKUs
  ├─ Compute priority scores (stop + fragility + weight + SLA)
  └─ Generate box instances

Phase 2: PLACEMENT
  ├─ Create stop-based zones
  ├─ Place boxes in priority order
  └─ Use extreme point algorithm

Phase 3: VALIDATION
  ├─ Analyze accessibility
  ├─ Detect rehandling
  └─ Generate unload plans

Phase 4: OUTPUT
  └─ Build MultiStopLoadPlan
```

---

## Performance

| Boxes | Stops | Time    |
|-------|-------|---------|
| 50    | 2     | < 1s    |
| 100   | 3     | 2-5s    |
| 200   | 5     | 10-20s  |
| 500   | 10    | 30-60s  |

---

## Testing

Run tests with examples:

```bash
# All examples
python examples.py

# Specific scenario
python -c "from examples import example_2_complex_overlap; example_2_complex_overlap()"
```

---

## Integration

### With Existing LoadOpt API

```python
# In your API endpoint
from backend.app.solver.multistop import quick_optimize

@router.post("/optimize-multistop")
async def optimize_route(trip_data: dict, sku_catalog: dict):
    trip = Trip(**trip_data)
    skus = {int(k): Box(**v) for k, v in sku_catalog.items()}
    result = quick_optimize(trip, skus, verbose=False)
    return result.to_dict()
```

### With Database Models

```python
def convert_db_to_multistop(db_project, delivery_stops):
    # Convert DB models to solver models
    container = Container(
        length=db_project.container.length,
        # ... etc
    )

    sku_catalog = {
        db_sku.id: Box(
            id=db_sku.id,
            sku_id=db_sku.id,
            # ... etc
        )
        for db_sku in db_project.skus
    }

    stops = [
        Stop(
            stop_number=i,
            location_id=stop['location_id'],
            # ... etc
        )
        for i, stop in enumerate(delivery_stops, 1)
    ]

    trip = Trip(trip_id=db_project.id, stops=stops, container=container)
    return trip, sku_catalog
```

---

## Troubleshooting

### Low Utilization
- Check door size constraints
- Try `allow_zone_overflow=True`
- Use equal zones instead of proportional

### Excessive Rehandling
- Increase `accessibility_weight`
- Use `STRICT_LIFO` strategy
- Disable zone overflow

### Validation Errors
- Check SKU catalog completeness
- Verify stop requirements
- Review fragile/stacking constraints

---

## Design Principles

1. **Deterministic**: Same input always produces same output
2. **Explainable**: Every decision has operational rationale
3. **Auditable**: Can trace all placements and priorities
4. **Realistic**: Designed for actual warehouse execution
5. **Extensible**: Clear architecture for enhancements

---

## Future Extensions

- [ ] Machine learning for priority weight optimization
- [ ] Real-time replanning for route changes
- [ ] Multi-vehicle fleet optimization
- [ ] Time window constraints
- [ ] Driver skill adaptation
- [ ] Integration with route optimization

---

## Documentation

- **Architecture**: [../../../../MULTISTOP_ARCHITECTURE.md](../../../../MULTISTOP_ARCHITECTURE.md)
- **Visual Guide**: [../../../../MULTISTOP_VISUAL_GUIDE.md](../../../../MULTISTOP_VISUAL_GUIDE.md)
- **Quick Start**: [../../../../MULTISTOP_QUICKSTART.md](../../../../MULTISTOP_QUICKSTART.md)
- **Summary**: [../../../../MULTISTOP_SUMMARY.md](../../../../MULTISTOP_SUMMARY.md)

---

## Support

For questions, issues, or feature requests:
1. Review documentation (links above)
2. Check examples (`examples.py`)
3. Review code comments in source files

---

## License

Part of LoadOpt - Multi-Stop Load Planning System
Version 1.0.0 | 2025-12-17
