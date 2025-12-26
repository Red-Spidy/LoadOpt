# LoadOpt API - Testing & TMS Integration Guide

## **Quick Start - Local Testing**

### **1. Start the API Server**

```powershell
# Navigate to backend directory
cd c:\Users\karan.dhillon\loadopt\backend

# Install dependencies (if not already installed)
pip install fastapi uvicorn pydantic

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Application startup complete.
```

---

### **2. Verify Server is Running**

Open browser: `http://localhost:8000`

You should see:
```json
{
  "message": "LoadOpt 3D Load Planning API",
  "version": "1.0.0",
  "environment": "development",
  "docs": "/docs"
}
```

---

### **3. View Interactive API Documentation**

Open: `http://localhost:8000/docs`

This provides:
- ✅ All available endpoints
- ✅ Request/response schemas
- ✅ Interactive testing interface
- ✅ Example payloads

---

## **API Endpoints**

### **Core Endpoints**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/loadopt/plan` | Execute load optimization |
| `POST` | `/api/v1/loadopt/validate` | Validate without optimizing |
| `GET` | `/api/v1/loadopt/health` | Health check |
| `GET` | `/api/v1/loadopt/version` | Version & capabilities |

---

## **Testing with Postman**

### **Method 1: Using Postman GUI**

1. **Open Postman**
2. **Create New Request:**
   - Method: `POST`
   - URL: `http://localhost:8000/api/v1/loadopt/plan`
3. **Set Headers:**
   - `Content-Type: application/json`
4. **Set Body:**
   - Select "raw" → "JSON"
   - Paste contents from `postman_sample_request.json`
5. **Click Send**
6. **View Response** (should return 200 OK with placement data)

---

### **Method 2: Using Postman with File**

1. Open Postman
2. Click **Import** button
3. Select **File** tab
4. Browse to: `c:\Users\karan.dhillon\loadopt\postman_sample_request.json`
5. Or drag-and-drop the file
6. Postman will auto-populate the request

---

### **Method 3: Using curl (Command Line)**

```powershell
# Test optimization endpoint
curl -X POST "http://localhost:8000/api/v1/loadopt/plan" `
  -H "Content-Type: application/json" `
  -d "@postman_sample_request.json"

# Test health check
curl http://localhost:8000/api/v1/loadopt/health

# Test version info
curl http://localhost:8000/api/v1/loadopt/version
```

---

## **Sample Request Payload**

**File:** `postman_sample_request.json`

**Key Components:**

```json
{
  "request_id": "TMS-ORDER-12345-20251226",
  "container": {
    "type": "40FT_HC",
    "dimensions": {"length": 1203, "width": 235, "height": 269, "unit": "cm"},
    "weight_limit": {"value": 28000, "unit": "kg"},
    "door": {"width": 234, "height": 259}
  },
  "items": [
    {
      "sku": "PALLET-EURO-A",
      "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"},
      "weight": {"value": 300, "unit": "kg"},
      "quantity": 8,
      "delivery": {"stop_number": 1, "priority": 1}
    }
  ],
  "solver_options": {
    "algorithm": "heuristic",
    "max_execution_time_seconds": 30
  }
}
```

---

## **Sample Response**

**Success (200 OK):**

```json
{
  "status": "success",
  "request_id": "TMS-ORDER-12345-20251226",
  "execution_time_ms": 1250,
  "result": {
    "placements": [
      {
        "placement_id": 1,
        "sku": "PALLET-EURO-A",
        "position": {"x": 0.0, "y": 0.0, "z": 0.0, "unit": "cm"},
        "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"},
        "rotation": 0,
        "rotation_description": "Original orientation (L×W×H)",
        "load_order": 1,
        "delivery_stop": 1,
        "weight": 300.0,
        "support_area_percentage": 100.0
      }
    ],
    "statistics": {
      "total_items_requested": 88,
      "items_placed": 88,
      "items_failed": 0,
      "utilization": {
        "volume_used_cm3": 2450000,
        "volume_total_cm3": 7600000,
        "volume_percentage": 32.2,
        "weight_used_kg": 4025,
        "weight_limit_kg": 28000,
        "weight_percentage": 14.4
      }
    },
    "validation": {
      "all_constraints_met": true,
      "warnings": [],
      "errors": []
    }
  },
  "solver_metadata": {
    "algorithm_used": "heuristic",
    "optimization_level": "balanced",
    "iterations": 1,
    "version": "1.0.0"
  }
}
```

---

## **Error Responses**

### **Weight Exceeded (400 Bad Request):**

```json
{
  "status": "error",
  "request_id": "TMS-ORDER-12345",
  "error": {
    "code": "WEIGHT_LIMIT_EXCEEDED",
    "message": "Total item weight exceeds container weight limit",
    "details": {
      "total_weight_requested": 30500.0,
      "container_weight_limit": 28000.0,
      "excess_weight": 2500.0
    }
  }
}
```

### **Internal Error (500):**

```json
{
  "status": "error",
  "request_id": "TMS-ORDER-12345",
  "error": {
    "code": "SOLVER_ERROR",
    "message": "Optimization failed: ...",
    "details": {}
  }
}
```

---

## **TMS Integration Flow**

### **Architecture**

```
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│              │   HTTP    │              │  Solver   │              │
│     TMS      │  ──────>  │  LoadOpt API │  ──────>  │  Heuristic   │
│   System     │  <──────  │  (FastAPI)   │  <──────  │   Engine     │
│              │   JSON    │              │  Results  │              │
└──────────────┘           └──────────────┘           └──────────────┘
```

### **Integration Steps**

1. **TMS Prepares Request:**
   - Extract order details from TMS database
   - Map SKUs to dimensions/weights
   - Determine delivery sequence
   - Build JSON payload

2. **TMS Calls LoadOpt API:**
   ```
   POST http://loadopt-server:8000/api/v1/loadopt/plan
   Content-Type: application/json
   Authorization: Bearer <token>
   
   { ... JSON payload ... }
   ```

3. **LoadOpt Processes:**
   - Validates constraints
   - Runs 3D bin packing algorithm
   - Calculates utilization, CG, weight distribution
   - Returns placement coordinates

4. **TMS Receives Response:**
   - Parse JSON response
   - Store placements in TMS database
   - Display loading instructions to warehouse
   - Generate 3D visualization (optional)

5. **TMS Uses Results:**
   - Print loading manifests
   - Show load order on handheld devices
   - Track loading progress
   - Verify weight distribution before dispatch

---

## **Configuration for TMS Integration**

### **Option 1: Internal Network**

TMS and LoadOpt on same network:
```
http://loadopt-server.internal:8000/api/v1/loadopt/plan
```

### **Option 2: Cloud Deployment**

LoadOpt hosted on cloud:
```
https://api.loadopt.yourcompany.com/api/v1/loadopt/plan
```

### **Option 3: Docker Deployment**

```yaml
# docker-compose.yml
services:
  loadopt-api:
    image: loadopt:latest
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://...
```

---

## **Authentication (Production)**

For production TMS integration, add authentication:

### **JWT Token Authentication**

```python
# In TMS:
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {jwt_token}"
}

response = requests.post(
    "http://loadopt-server:8000/api/v1/loadopt/plan",
    headers=headers,
    json=payload
)
```

### **API Key Authentication**

```python
# In TMS:
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your-api-key-here"
}
```

---

## **Performance Considerations**

| Items Count | Expected Time | Recommendation |
|-------------|---------------|----------------|
| < 50 items  | < 2 seconds   | Synchronous API call |
| 50-200 items | 2-10 seconds | Synchronous with timeout |
| > 200 items | > 10 seconds | Use async endpoint (future) |

---

## **Testing Checklist**

### **✅ Local Testing**

- [ ] Server starts without errors
- [ ] Health check returns "healthy"
- [ ] Sample request returns 200 OK
- [ ] Response contains placements
- [ ] Utilization percentage is calculated
- [ ] Invalid request returns 400 error
- [ ] Excessive weight returns error

### **✅ TMS Integration Testing**

- [ ] TMS can reach LoadOpt API endpoint
- [ ] TMS can parse JSON response
- [ ] Placement coordinates map correctly
- [ ] Load order sequence is correct
- [ ] Delivery stops are respected
- [ ] Weight limits are enforced
- [ ] Error handling works properly

---

## **Common Issues & Solutions**

### **Issue: Server won't start**

```
ModuleNotFoundError: No module named 'app.solver.utils'
```

**Solution:**
```powershell
cd c:\Users\karan.dhillon\loadopt\backend
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --reload
```

---

### **Issue: Connection refused**

```
curl: (7) Failed to connect to localhost port 8000
```

**Solution:**
- Check if server is running: `netstat -an | findstr 8000`
- Restart server
- Check firewall settings

---

### **Issue: Validation errors**

```
422 Unprocessable Entity: field required
```

**Solution:**
- Ensure all required fields are present
- Check JSON syntax is valid
- Verify data types match schema
- Use `/docs` endpoint to see required fields

---

## **Next Steps**

1. **Start Server Locally** → Test with Postman
2. **Validate JSON Schema** → Ensure TMS can generate compatible payloads
3. **Test Error Handling** → Send invalid requests
4. **Performance Testing** → Test with large item counts
5. **TMS Integration** → Update TMS to call LoadOpt API
6. **Production Deployment** → Deploy to server, add authentication

---

## **Support & Documentation**

- **API Docs (Interactive):** `http://localhost:8000/docs`
- **ReDoc (Alternative):** `http://localhost:8000/redoc`
- **OpenAPI Schema:** `http://localhost:8000/api/v1/openapi.json`
- **Health Check:** `http://localhost:8000/api/v1/loadopt/health`

---

## **Contact**

For TMS integration support, provide:
- Request ID from the API call
- Complete JSON request payload
- Error response (if any)
- TMS system details
