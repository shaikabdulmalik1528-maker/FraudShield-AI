"""
Fraud Alert notification and acknowledgment endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List

from backend.app.database import get_db
from backend.app.schemas.alert import AlertResponse, AlertUpdate
from backend.app.services.alert_service import get_alerts, update_alert_status
from backend.app.services.auth_service import get_current_user
from backend.app.models.user import User

router = APIRouter(tags=["Fraud Alerts"])

@router.get("/alerts", response_model=List[AlertResponse])
def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status: PENDING, INVESTIGATING, RESOLVED, FALSE_POSITIVE"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    _, items = get_alerts(db=db, status_filter=status, limit=limit, offset=offset)
    return items

@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: int,
    update_data: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update status of a flagged fraud alert (Requires authenticated user)."""
    return update_alert_status(
        db=db,
        alert_id=alert_id,
        alert_update=update_data,
        username=current_user.username
    )
