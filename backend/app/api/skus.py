from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import csv
import io

from app.core.database import get_db
from app.api.dependencies import get_current_active_user, verify_project_access
from app.models.models import User, SKU, Project
from app.schemas.schemas import SKUCreate, SKU as SKUSchema, SKUUpdate

router = APIRouter()


@router.post("/", response_model=SKUSchema, status_code=status.HTTP_201_CREATED)
def create_sku(
    sku_in: SKUCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create new SKU"""
    # Verify project access
    verify_project_access(sku_in.project_id, current_user.id, db)
    
    sku = SKU(**sku_in.dict())
    db.add(sku)
    db.commit()
    db.refresh(sku)
    
    return sku


@router.post("/bulk", response_model=List[SKUSchema])
async def create_skus_bulk(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bulk import SKUs from CSV"""
    # Verify project access
    verify_project_access(project_id, current_user.id, db)
    
    # Read CSV
    content = await file.read()
    csv_text = content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(csv_text))
    
    skus = []
    for row in csv_reader:
        sku = SKU(
            project_id=project_id,
            name=row['name'],
            sku_code=row.get('sku_code'),
            length=float(row['length']),
            width=float(row['width']),
            height=float(row['height']),
            weight=float(row['weight']),
            quantity=int(row.get('quantity', 1)),
            fragile=row.get('fragile', 'false').lower() == 'true',
            max_stack=int(row.get('max_stack', 999)),
            stacking_group=row.get('stacking_group'),
            priority=int(row.get('priority', 1))
        )
        db.add(sku)
        skus.append(sku)
    
    db.commit()
    
    for sku in skus:
        db.refresh(sku)
    
    return skus


@router.get("/{sku_id}", response_model=SKUSchema)
def get_sku(
    sku_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get SKU by ID"""
    sku = db.query(SKU).filter(SKU.id == sku_id).first()
    
    if not sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found"
        )
    
    # Verify project access
    verify_project_access(sku.project_id, current_user.id, db)
    
    return sku


@router.get("/project/{project_id}", response_model=List[SKUSchema])
def list_skus_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all SKUs in a project"""
    # Verify project access
    verify_project_access(project_id, current_user.id, db)
    
    skus = db.query(SKU).filter(SKU.project_id == project_id).all()
    return skus


@router.put("/{sku_id}", response_model=SKUSchema)
def update_sku(
    sku_id: int,
    sku_in: SKUUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update SKU"""
    sku = db.query(SKU).filter(SKU.id == sku_id).first()
    
    if not sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found"
        )
    
    # Verify project access
    verify_project_access(sku.project_id, current_user.id, db)
    
    update_data = sku_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sku, field, value)
    
    db.commit()
    db.refresh(sku)
    
    return sku


@router.patch("/{sku_id}/quantity", response_model=SKUSchema)
def update_sku_quantity(
    sku_id: int,
    quantity: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Quick update for SKU quantity only"""
    if quantity < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be at least 1"
        )

    sku = db.query(SKU).filter(SKU.id == sku_id).first()

    if not sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found"
        )

    # Verify project access
    verify_project_access(sku.project_id, current_user.id, db)

    sku.quantity = quantity
    db.commit()
    db.refresh(sku)

    return sku


@router.delete("/{sku_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sku(
    sku_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete SKU"""
    sku = db.query(SKU).filter(SKU.id == sku_id).first()

    if not sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU not found"
        )

    # Verify project access
    verify_project_access(sku.project_id, current_user.id, db)

    db.delete(sku)
    db.commit()

    return None
