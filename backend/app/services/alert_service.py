"""
Fraud Alert management service: listing, acknowledgment, and resolution.
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone
from fastapi import HTTPException, status
from backend.app.models.alert import FraudAlert
from backend.app.schemas.alert import AlertUpdate

def get_alerts(
    db: Session,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[int, List[FraudAlert]]:
    query = db.query(FraudAlert)
    if status_filter:
        query = query.filter(FraudAlert.status == status_filter.upper())
    total = query.count()
    items = query.order_by(desc(FraudAlert.created_at)).offset(offset).limit(limit).all()
    return total, items

def update_alert_status(
    db: Session,
    alert_id: int,
    alert_update: AlertUpdate,
    username: str
) -> FraudAlert:
    alert = db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert #{alert_id} not found."
        )
    
    alert.status = alert_update.status
    alert.acknowledged_by = username
    alert.acknowledged_at = datetime.now(timezone.utc)
    if alert_update.notes:
        alert.notes = alert_update.notes
    alert.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(alert)
    return alert
