from __future__ import annotations

from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Rule, Strategy
from app.schemas import StrategyCreate, StrategyResponse, StrategyUpdate


router = APIRouter(prefix="/strategies", tags=["strategies"])


def _rule_id(index: int) -> str:
    return "R{:03d}".format(index)


@router.get("", response_model=List[StrategyResponse])
def list_strategies(db: Session = Depends(get_db)) -> List[Strategy]:
    stmt = select(Strategy).options(selectinload(Strategy.rules)).order_by(Strategy.created_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(strategy_id: str, db: Session = Depends(get_db)) -> Strategy:
    stmt = select(Strategy).options(selectinload(Strategy.rules)).where(Strategy.id == strategy_id)
    strategy = db.scalar(stmt)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")
    return strategy


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)) -> Strategy:
    strategy = Strategy(id=str(uuid4()), name=payload.name)
    for index, rule in enumerate(payload.rules, start=1):
        strategy.rules.append(
            Rule(
                id=rule.id or _rule_id(index),
                title=rule.title,
                description=rule.description,
                severity=rule.severity,
                is_required=rule.is_required,
            )
        )

    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(strategy_id: str, payload: StrategyUpdate, db: Session = Depends(get_db)) -> Strategy:
    stmt = select(Strategy).options(selectinload(Strategy.rules)).where(Strategy.id == strategy_id)
    strategy = db.scalar(stmt)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")

    strategy.name = payload.name
    strategy.rules.clear()
    for index, rule in enumerate(payload.rules, start=1):
        strategy.rules.append(
            Rule(
                id=rule.id or _rule_id(index),
                title=rule.title,
                description=rule.description,
                severity=rule.severity,
                is_required=rule.is_required,
            )
        )

    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: str, db: Session = Depends(get_db)) -> dict:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found.")
    db.delete(strategy)
    db.commit()
    return {"deleted": True}
