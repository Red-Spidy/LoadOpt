from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import DeliveryGroup, SKU, User
from app.schemas.schemas import (
    DeliveryGroup as DeliveryGroupSchema,
    DeliveryGroupCreate,
    DeliveryGroupUpdate,
    DeliveryGroupWithSKUs,
)
from app.api.dependencies import get_current_active_user, verify_project_access

router = APIRouter()


@router.get("/project/{project_id}", response_model=List[DeliveryGroupSchema])
def list_delivery_groups(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all delivery groups for a project, ordered by delivery_order"""
    verify_project_access(project_id, current_user.id, db)
    return db.query(DeliveryGroup).filter(
        DeliveryGroup.project_id == project_id
    ).order_by(DeliveryGroup.delivery_order).all()


@router.get("/{group_id}", response_model=DeliveryGroupWithSKUs)
def get_delivery_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get delivery group with its SKUs"""
    group = db.query(DeliveryGroup).filter(DeliveryGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Delivery group not found")
    verify_project_access(group.project_id, current_user.id, db)
    return group


@router.post("/", response_model=DeliveryGroupSchema, status_code=status.HTTP_201_CREATED)
def create_delivery_group(
    group_in: DeliveryGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new delivery group"""
    verify_project_access(group_in.project_id, current_user.id, db)
    
    group = DeliveryGroup(**group_in.dict())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.put("/{group_id}", response_model=DeliveryGroupSchema)
def update_delivery_group(
    group_id: int,
    group_in: DeliveryGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update a delivery group"""
    group = db.query(DeliveryGroup).filter(DeliveryGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Delivery group not found")
    verify_project_access(group.project_id, current_user.id, db)
    
    update_data = group_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)
    
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_delivery_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a delivery group (SKUs will have their group_id set to null)"""
    group = db.query(DeliveryGroup).filter(DeliveryGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Delivery group not found")
    verify_project_access(group.project_id, current_user.id, db)
    
    # Set SKUs group_id to null instead of deleting them
    db.query(SKU).filter(SKU.delivery_group_id == group_id).update(
        {"delivery_group_id": None}
    )
    
    db.delete(group)
    db.commit()


@router.post("/{group_id}/assign-skus", response_model=DeliveryGroupSchema)
def assign_skus_to_group(
    group_id: int,
    sku_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Assign multiple SKUs to a delivery group"""
    group = db.query(DeliveryGroup).filter(DeliveryGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Delivery group not found")
    verify_project_access(group.project_id, current_user.id, db)
    
    # Update SKUs
    db.query(SKU).filter(
        SKU.id.in_(sku_ids),
        SKU.project_id == group.project_id
    ).update({"delivery_group_id": group_id}, synchronize_session=False)
    
    db.commit()
    db.refresh(group)
    return group


@router.post("/{group_id}/remove-skus", response_model=DeliveryGroupSchema)
def remove_skus_from_group(
    group_id: int,
    sku_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Remove SKUs from a delivery group"""
    group = db.query(DeliveryGroup).filter(DeliveryGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Delivery group not found")
    verify_project_access(group.project_id, current_user.id, db)
    
    # Set group_id to null for these SKUs
    db.query(SKU).filter(
        SKU.id.in_(sku_ids),
        SKU.delivery_group_id == group_id
    ).update({"delivery_group_id": None}, synchronize_session=False)
    
    db.commit()
    db.refresh(group)
    return group
