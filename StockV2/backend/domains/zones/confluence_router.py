from __future__ import annotations
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from .confluence_scanner import ConfluenceScanner

router = APIRouter(tags=["confluence"])
logger = logging.getLogger(__name__)


@router.get("/confluence/scan")
def get_confluence_scan(db: Session = Depends(get_db)):
    """Stocks breaking out with zone backing + stocks sitting just below key resistance."""
    return ConfluenceScanner().scan(db)
