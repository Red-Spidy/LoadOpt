# LoadOpt API Reference

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication

All endpoints except `/auth/login` and `/auth/signup` require authentication.

Add the JWT token to requests:
```
Authorization: Bearer <token>
```

## Authentication Endpoints

### POST /auth/signup
Create a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "password123",
  "full_name": "John Doe"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "full_name": "John Doe",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2024-01-01T00:00:00"
}
```

### POST /auth/login
Login and receive access token.

**Request Body:** (form-urlencoded)
```
username=username
password=password123
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

### GET /auth/me
Get current user information.

**Response:** `200 OK`
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "full_name": "John Doe",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2024-01-01T00:00:00"
}
```

## Project Endpoints

### GET /projects/
List all projects for the current user.

**Query Parameters:**
- `skip` (optional): Number of records to skip (default: 0)
- `limit` (optional): Maximum number of records (default: 100)

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "name": "My Project",
    "description": "Project description",
    "owner_id": 1,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": null
  }
]
```

### POST /projects/
Create a new project.

**Request Body:**
```json
{
  "name": "My Project",
  "description": "Optional description"
}
```

**Response:** `201 Created`

### GET /projects/{id}
Get project details including SKUs, containers, and plans.

**Response:** `200 OK`
```json
{
  "id": 1,
  "name": "My Project",
  "description": "Project description",
  "owner_id": 1,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": null,
  "skus": [...],
  "containers": [...],
  "plans": [...]
}
```

### PUT /projects/{id}
Update project details.

**Request Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description"
}
```

**Response:** `200 OK`

### DELETE /projects/{id}
Delete a project and all related data.

**Response:** `204 No Content`

## SKU Endpoints

### GET /skus/project/{project_id}
List all SKUs in a project.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "project_id": 1,
    "name": "Box A",
    "sku_code": "SKU001",
    "length": 100,
    "width": 50,
    "height": 30,
    "weight": 10,
    "quantity": 5,
    "allowed_rotations": [true, true, true, true, true, true],
    "fragile": false,
    "max_stack": 999,
    "stacking_group": null,
    "priority": 1,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

### POST /skus/
Create a new SKU.

**Request Body:**
```json
{
  "project_id": 1,
  "name": "Box A",
  "sku_code": "SKU001",
  "length": 100,
  "width": 50,
  "height": 30,
  "weight": 10,
  "quantity": 5,
  "allowed_rotations": [true, true, true, true, true, true],
  "fragile": false,
  "max_stack": 999,
  "stacking_group": null,
  "priority": 1
}
```

**Response:** `201 Created`

### POST /skus/bulk?project_id={id}
Bulk import SKUs from CSV file.

**Request:** Multipart form-data with CSV file

**CSV Format:**
```csv
name,length,width,height,weight,quantity,fragile,max_stack,stacking_group,priority
Box A,100,50,30,10,5,false,999,,1
Box B,80,60,40,15,3,true,0,,2
```

**Response:** `200 OK` - Array of created SKUs

### GET /skus/{id}
Get SKU by ID.

**Response:** `200 OK`

### PUT /skus/{id}
Update SKU.

**Request Body:**
```json
{
  "name": "Updated Box A",
  "quantity": 10
}
```

**Response:** `200 OK`

### DELETE /skus/{id}
Delete SKU.

**Response:** `204 No Content`

## Container Endpoints

### GET /containers/project/{project_id}
List all containers in a project.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "project_id": 1,
    "name": "Standard Container",
    "inner_length": 1200,
    "inner_width": 240,
    "inner_height": 260,
    "door_width": 230,
    "door_height": 250,
    "max_weight": 25000,
    "front_axle_limit": 7000,
    "rear_axle_limit": 11000,
    "obstacles": [],
    "created_at": "2024-01-01T00:00:00"
  }
]
```

### POST /containers/
Create a new container.

**Request Body:**
```json
{
  "project_id": 1,
  "name": "Standard Container",
  "inner_length": 1200,
  "inner_width": 240,
  "inner_height": 260,
  "door_width": 230,
  "door_height": 250,
  "max_weight": 25000,
  "front_axle_limit": 7000,
  "rear_axle_limit": 11000,
  "obstacles": [
    {
      "x": 0,
      "y": 0,
      "z": 0,
      "length": 50,
      "width": 50,
      "height": 100
    }
  ]
}
```

**Response:** `201 Created`

### GET /containers/{id}
Get container by ID.

**Response:** `200 OK`

### PUT /containers/{id}
Update container.

**Response:** `200 OK`

### DELETE /containers/{id}
Delete container.

**Response:** `204 No Content`

## Plan Endpoints

### GET /plans/project/{project_id}
List all plans in a project.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "project_id": 1,
    "container_id": 1,
    "name": "Optimization 1",
    "solver_mode": "FAST",
    "status": "DONE",
    "utilization_pct": 78.5,
    "total_weight": 15600,
    "items_placed": 45,
    "items_total": 50,
    "weight_distribution": {
      "front_axle": 6800,
      "rear_axle": 8800,
      "center_of_gravity": {"x": 580, "y": 120, "z": 95}
    },
    "is_valid": true,
    "validation_errors": [],
    "job_id": null,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:30",
    "completed_at": "2024-01-01T00:00:30"
  }
]
```

### POST /plans/
Create a new plan and start optimization.

**Request Body:**
```json
{
  "project_id": 1,
  "container_id": 1,
  "name": "Optimization 1",
  "solver_mode": "FAST"
}
```

**Solver Modes:**
- `FAST` - Quick heuristic (<1s)
- `IMPROVED` - Genetic Algorithm (10-30s)
- `OPTIMAL` - Simulated Annealing (30-60s)

**Response:** `201 Created`

### GET /plans/{id}
Get plan with all placements.

**Response:** `200 OK`
```json
{
  "id": 1,
  "project_id": 1,
  "container_id": 1,
  "name": "Optimization 1",
  "solver_mode": "FAST",
  "status": "DONE",
  "utilization_pct": 78.5,
  "total_weight": 15600,
  "items_placed": 45,
  "items_total": 50,
  "weight_distribution": {...},
  "is_valid": true,
  "validation_errors": [],
  "created_at": "2024-01-01T00:00:00",
  "placements": [
    {
      "id": 1,
      "plan_id": 1,
      "sku_id": 1,
      "instance_index": 0,
      "x": 0,
      "y": 0,
      "z": 0,
      "rotation": 0,
      "length": 100,
      "width": 50,
      "height": 30,
      "load_order": 0
    }
  ]
}
```

### POST /plans/{id}/optimize
Re-run optimization on existing plan.

**Response:** `200 OK`

### PUT /plans/{id}
Update plan metadata.

**Request Body:**
```json
{
  "name": "Updated Name",
  "solver_mode": "IMPROVED"
}
```

**Response:** `200 OK`

### DELETE /plans/{id}
Delete plan.

**Response:** `204 No Content`

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid input"
}
```

### 401 Unauthorized
```json
{
  "detail": "Could not validate credentials"
}
```

### 404 Not Found
```json
{
  "detail": "Project not found"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "length"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt"
    }
  ]
}
```

## Rate Limiting

No rate limiting is currently implemented, but it's recommended for production.

## Pagination

List endpoints support pagination via `skip` and `limit` query parameters:
```
GET /api/v1/projects/?skip=20&limit=10
```
