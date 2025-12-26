from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.api.dependencies import get_current_active_user, verify_project_access
from app.models.models import User, Container, Project
from app.schemas.schemas import ContainerCreate, Container as ContainerSchema, ContainerUpdate

router = APIRouter()


@router.post("/", response_model=ContainerSchema, status_code=status.HTTP_201_CREATED)
def create_container(
    container_in: ContainerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create new container"""
    # Verify project access
    verify_project_access(container_in.project_id, current_user.id, db)
    
    container_data = container_in.dict()
    # Convert obstacles to dict list
    container_data['obstacles'] = [obs.dict() for obs in container_in.obstacles]
    
    container = Container(**container_data)
    db.add(container)
    db.commit()
    db.refresh(container)
    
    return container


@router.get("/{container_id}", response_model=ContainerSchema)
def get_container(
    container_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get container by ID"""
    container = db.query(Container).filter(Container.id == container_id).first()
    
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Container not found"
        )
    
    # Verify project access
    verify_project_access(container.project_id, current_user.id, db)
    
    return container


@router.get("/project/{project_id}", response_model=List[ContainerSchema])
def list_containers_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all containers in a project"""
    # Verify project access
    verify_project_access(project_id, current_user.id, db)
    
    containers = db.query(Container).filter(Container.project_id == project_id).all()
    return containers


@router.put("/{container_id}", response_model=ContainerSchema)
def update_container(
    container_id: int,
    container_in: ContainerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update container"""
    container = db.query(Container).filter(Container.id == container_id).first()
    
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Container not found"
        )
    
    # Verify project access
    verify_project_access(container.project_id, current_user.id, db)
    
    update_data = container_in.dict(exclude_unset=True)
    if 'obstacles' in update_data and update_data['obstacles']:
        update_data['obstacles'] = [obs.dict() for obs in container_in.obstacles]
    
    for field, value in update_data.items():
        setattr(container, field, value)
    
    db.commit()
    db.refresh(container)
    
    return container


@router.delete("/{container_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_container(
    container_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete container"""
    container = db.query(Container).filter(Container.id == container_id).first()
    
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Container not found"
        )
    
    # Verify project access
    verify_project_access(container.project_id, current_user.id, db)
    
    db.delete(container)
    db.commit()
    
    return None
