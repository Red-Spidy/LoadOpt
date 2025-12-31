"""Test script to verify no overlapping boxes in multi-stop optimization"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.solver.multistop.optimizer import MultiStopOptimizer
from app.solver.multistop.models import Trip, Stop
from app.solver.utils import Box, ContainerSpace

# Create container
container = ContainerSpace(
    length=1200,
    width=240,
    height=240,
    max_weight=10000,
    door_width=240,
    door_height=240
)

# Create trip with 3 stops
trip = Trip(
    trip_id='TEST-001',
    container=container,
    stops=[
        Stop(stop_number=1, location_id='LOC-A', location_name='Store A', sku_requirements={1001: 15}),
        Stop(stop_number=2, location_id='LOC-B', location_name='Store B', sku_requirements={2001: 15}),
        Stop(stop_number=3, location_id='LOC-C', location_name='Store C', sku_requirements={3001: 15})
    ]
)

# Create many boxes with various sizes
boxes = []
box_id = 0
for stop in [1, 2, 3]:
    for i in range(15):  # 15 boxes per stop
        box_id += 1
        boxes.append(Box(
            id=box_id,
            sku_id=1000 + i,
            instance_index=0,
            length=60 + (i * 3),
            width=40 + (i * 2),
            height=30 + i,
            weight=10 + i,
            fragile=False,
            max_stack=5,
            stacking_group=None,
            priority=100 - (stop * 10) - i,
            allowed_rotations=[True] * 6,
            delivery_order=stop
        ))

print(f'Testing with {len(boxes)} boxes across {trip.num_stops} stops')

# Run optimizer
optimizer = MultiStopOptimizer(container, trip)
result = optimizer.optimize(boxes)

# Check for overlaps
print(f'\nPlaced: {len(result.placements)}/{len(boxes)} boxes')
print(f'Utilization: {result.utilization_percent:.1f}%')

# Manual collision check with tight tolerance (0.01cm = 0.1mm)
overlaps = 0
for i, box1 in enumerate(result.placements):
    for j, box2 in enumerate(result.placements[i+1:], i+1):
        # Check if boxes overlap (with 0.01cm tolerance)
        x_overlap = not (box1.max_x <= box2.x + 0.01 or box2.max_x <= box1.x + 0.01)
        y_overlap = not (box1.max_y <= box2.y + 0.01 or box2.max_y <= box1.y + 0.01)
        z_overlap = not (box1.max_z <= box2.z + 0.01 or box2.max_z <= box1.z + 0.01)
        
        if x_overlap and y_overlap and z_overlap:
            overlaps += 1
            print(f'\nOVERLAP DETECTED:')
            print(f'  Box {box1.box.id} (stop {box1.box.delivery_order}): x=[{box1.x:.2f}, {box1.max_x:.2f}] y=[{box1.y:.2f}, {box1.max_y:.2f}] z=[{box1.z:.2f}, {box1.max_z:.2f}]')
            print(f'  Box {box2.box.id} (stop {box2.box.delivery_order}): x=[{box2.x:.2f}, {box2.max_x:.2f}] y=[{box2.y:.2f}, {box2.max_y:.2f}] z=[{box2.z:.2f}, {box2.max_z:.2f}]')
            
            # Calculate overlap amounts
            x_ovlp = min(box1.max_x, box2.max_x) - max(box1.x, box2.x)
            y_ovlp = min(box1.max_y, box2.max_y) - max(box1.y, box2.y)
            z_ovlp = min(box1.max_z, box2.max_z) - max(box1.z, box2.z)
            print(f'  Overlap amount: X={x_ovlp:.4f}cm, Y={y_ovlp:.4f}cm, Z={z_ovlp:.4f}cm')

if overlaps == 0:
    print('\n✅ NO OVERLAPS DETECTED - All boxes properly placed with 0.01cm tolerance!')
    print('🎉 Multi-stop placement engine is working correctly!')
else:
    print(f'\n❌ FOUND {overlaps} OVERLAPPING BOX PAIRS')
    print('⚠️  Collision detection needs further investigation')
