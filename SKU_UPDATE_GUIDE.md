# SKU Quantity Update Guide

## ✅ Feature Added!

You can now update SKU quantities without deleting and recreating them!

---

## 🚀 Three Ways to Update SKU Quantity

### Method 1: Quick Quantity Update (NEW - Easiest!)

**Endpoint:** `PATCH /api/v1/skus/{sku_id}/quantity?quantity={new_quantity}`

**Example:**
```bash
# Update SKU #5 to quantity 100
curl -X PATCH "http://localhost:8000/api/v1/skus/5/quantity?quantity=100" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**JavaScript/TypeScript:**
```typescript
import { skusAPI } from '@/services/api';

// Update SKU quantity
await skusAPI.updateQuantity(5, 100);
```

---

### Method 2: Full Update (Update Any Field)

**Endpoint:** `PUT /api/v1/skus/{sku_id}`

**Example:**
```bash
# Update SKU quantity and other fields
curl -X PUT "http://localhost:8000/api/v1/skus/5" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quantity": 100,
    "priority": 2
  }'
```

**JavaScript/TypeScript:**
```typescript
import { skusAPI } from '@/services/api';

// Update quantity and other fields
await skusAPI.update(5, {
  quantity: 100,
  priority: 2,
  fragile: true
});
```

---

### Method 3: Partial Update (Update Multiple Fields)

**Endpoint:** `PUT /api/v1/skus/{sku_id}` (same as Method 2)

**You can update any of these fields:**
```typescript
{
  name?: string;
  sku_code?: string;
  length?: number;
  width?: number;
  height?: number;
  weight?: number;
  quantity?: number;          // ← THIS ONE!
  fragile?: boolean;
  max_stack?: number;
  stacking_group?: string;
  load_bearing_capacity?: number;
  priority?: number;
  delivery_group_id?: number;
  allowed_rotations?: boolean[];
}
```

**Example - Update only quantity:**
```bash
curl -X PUT "http://localhost:8000/api/v1/skus/5" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"quantity": 100}'
```

---

## 📋 Complete Examples

### Example 1: Quick Quantity Change

```bash
# Get your access token first
TOKEN=$(curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=yourname&password=yourpass" | jq -r '.access_token')

# Update SKU quantity
curl -X PATCH "http://localhost:8000/api/v1/skus/5/quantity?quantity=150" \
  -H "Authorization: Bearer $TOKEN"
```

### Example 2: Update Multiple Fields Including Quantity

```bash
curl -X PUT "http://localhost:8000/api/v1/skus/5" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quantity": 150,
    "weight": 25.5,
    "priority": 1,
    "fragile": true,
    "max_stack": 3
  }'
```

### Example 3: Frontend Integration

Create a simple update form in your React component:

```tsx
import { useState } from 'react';
import { skusAPI } from '@/services/api';

function SKUQuantityEditor({ skuId, currentQuantity }) {
  const [quantity, setQuantity] = useState(currentQuantity);
  const [loading, setLoading] = useState(false);

  const handleUpdate = async () => {
    setLoading(true);
    try {
      // Use the new quick update method
      await skusAPI.updateQuantity(skuId, quantity);
      alert('Quantity updated successfully!');
    } catch (error) {
      alert('Failed to update quantity');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="number"
        min="1"
        value={quantity}
        onChange={(e) => setQuantity(parseInt(e.target.value))}
      />
      <button onClick={handleUpdate} disabled={loading}>
        {loading ? 'Updating...' : 'Update Quantity'}
      </button>
    </div>
  );
}
```

---

## 🔍 API Response

All update methods return the updated SKU:

```json
{
  "id": 5,
  "project_id": 1,
  "name": "Air Conditioner",
  "sku_code": "AC-001",
  "length": 120.0,
  "width": 80.0,
  "height": 90.0,
  "weight": 15.0,
  "quantity": 100,           // ← Updated!
  "fragile": false,
  "max_stack": 3,
  "priority": 1,
  "delivery_group_id": 2,
  "created_at": "2025-12-17T10:30:00Z"
}
```

---

## ✨ Benefits

### Before (Old Way):
1. Delete SKU → Lose SKU ID
2. Create new SKU → Get new ID
3. Update all references to new ID
4. Re-assign to delivery groups

### After (New Way):
1. Update quantity → Done! ✅

**Advantages:**
- ✅ SKU ID stays the same
- ✅ All relationships preserved (delivery groups, plans, etc.)
- ✅ History maintained
- ✅ No need to update references
- ✅ Much faster and simpler

---

## 🎯 Quick Reference

| Method | URL | Body | Use Case |
|--------|-----|------|----------|
| **PATCH** | `/skus/{id}/quantity?quantity=X` | None | Quick quantity change only |
| **PUT** | `/skus/{id}` | `{"quantity": X}` | Update quantity (and optionally other fields) |

---

## 🐛 Troubleshooting

### Error: "Quantity must be at least 1"
**Solution:** Quantity cannot be 0 or negative. Use at least 1.

### Error: "SKU not found"
**Solution:** Check the SKU ID exists by listing all SKUs first:
```bash
curl http://localhost:8000/api/v1/skus/project/1 -H "Authorization: Bearer $TOKEN"
```

### Error: "Not authenticated"
**Solution:** Make sure you include the Authorization header with a valid token.

---

## 📚 Additional Resources

- **Full API Documentation:** http://localhost:8000/docs
- **Frontend API Service:** `frontend/src/services/api.ts`
- **Backend SKU Endpoints:** `backend/app/api/skus.py`

---

**No more deleting and recreating!** 🎉

Just update the quantity directly with the new endpoints!
