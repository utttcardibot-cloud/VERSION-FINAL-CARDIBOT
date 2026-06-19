from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.database.session import get_db
from app.models.openai_usage import OpenAIUsage
from app.services.redis_service import redis_client
router = APIRouter(
    prefix="/usage",
    tags=["Usage"]
)

MONTHLY_BUDGET_USD = 50

def count_active_anonymous_sessions():
    count = 0
    cursor = 0

    while True:
        cursor, keys = redis_client.scan(
            cursor=cursor,
            match="anon_session:*",
            count=100
        )
        count += len(keys)

        if cursor == 0:
            break

    return count

@router.get("/global")
def global_stats(db: Session = Depends(get_db)):

    total_requests = db.execute(select(func.count(OpenAIUsage.id)))
    total_tokens = db.execute(select(func.sum(OpenAIUsage.total_tokens)))
    total_cost = db.execute(select(func.sum(OpenAIUsage.estimated_cost)))

    # 🔥 ANÓNIMOS ACTIVOS
    active_anonymous = count_active_anonymous_sessions()

    return {
        "total_requests": total_requests.scalar() or 0,
        "total_tokens": total_tokens.scalar() or 0,
        "total_cost_usd": float(total_cost.scalar() or 0),

        
        "usuarios_activos_anonimos": active_anonymous
    }

@router.get("/today")
def today_stats(db: Session = Depends(get_db)):

    today = datetime.utcnow().date()

    result = db.execute(
        select(
            func.count(OpenAIUsage.id),
            func.sum(OpenAIUsage.total_tokens),
            func.sum(OpenAIUsage.estimated_cost)
        ).where(
            func.date(OpenAIUsage.created_at) == today
        )
    )

    requests, tokens, cost = result.first()

    return {
        "date": str(today),
        "total_requests": requests or 0,
        "total_tokens": tokens or 0,
        "total_cost_usd": float(cost or 0)
    }
@router.get("/monthly")
def monthly_stats(db: Session = Depends(get_db)):

    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)

    total_requests = db.execute(
        select(func.count(OpenAIUsage.id))
        .where(OpenAIUsage.created_at >= start_of_month)
    )

    total_tokens = db.execute(
        select(func.sum(OpenAIUsage.total_tokens))
        .where(OpenAIUsage.created_at >= start_of_month)
    )

    total_cost = db.execute(
        select(func.sum(OpenAIUsage.estimated_cost))
        .where(OpenAIUsage.created_at >= start_of_month)
    )

    return {
        "month": f"{now.year}-{now.month}",
        "total_requests": total_requests.scalar() or 0,
        "total_tokens": total_tokens.scalar() or 0,
        "total_cost_usd": float(total_cost.scalar() or 0)
    }


@router.get("/daily")
def daily_usage(
    db: Session = Depends(get_db),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None)
):

    query = select(
        func.date(OpenAIUsage.created_at).label("day"),
        func.sum(OpenAIUsage.total_tokens).label("tokens"),
        func.sum(OpenAIUsage.estimated_cost).label("cost"),
        func.count(OpenAIUsage.id).label("requests")
    )

    if start_date:
        query = query.where(OpenAIUsage.created_at >= start_date)

    if end_date:
        query = query.where(OpenAIUsage.created_at <= end_date)

    query = query.group_by(
        func.date(OpenAIUsage.created_at)
    ).order_by(
        func.date(OpenAIUsage.created_at)
    )

    result = db.execute(query)
    rows = result.all()

    return [
        {
            "date": str(row[0]),
            "total_tokens": row[1],
            "total_cost_usd": float(row[2] or 0),
            "total_requests": row[3]
        }
        for row in rows
    ]


@router.get("/top-users")
def top_users(db: Session = Depends(get_db)):

    result = db.execute(
        select(
            OpenAIUsage.user_id,
            func.sum(OpenAIUsage.total_tokens).label("tokens"),
            func.count(OpenAIUsage.id).label("requests"),
            func.sum(OpenAIUsage.estimated_cost).label("cost")
        )
        .group_by(OpenAIUsage.user_id)
        .order_by(func.sum(OpenAIUsage.total_tokens).desc())
    )

    rows = result.all()

    return [
        {
            "user_id": row[0],
            "total_tokens": row[1],
            "total_requests": row[2],
            "total_cost_usd": float(row[3] or 0)
        }
        for row in rows
    ]


@router.get("/by-endpoint")
def usage_by_endpoint(db: Session = Depends(get_db)):

    result = db.execute(
        select(
            OpenAIUsage.endpoint,
            func.sum(OpenAIUsage.total_tokens).label("tokens"),
            func.sum(OpenAIUsage.estimated_cost).label("cost"),
            func.count(OpenAIUsage.id).label("requests")
        )
        .group_by(OpenAIUsage.endpoint)
        .order_by(func.sum(OpenAIUsage.total_tokens).desc())
    )

    rows = result.all()

    return [
        {
            "endpoint": row[0],
            "total_tokens": row[1],
            "total_cost_usd": float(row[2] or 0),
            "total_requests": row[3]
        }
        for row in rows
    ]


@router.get("/by-model")
def usage_by_model(db: Session = Depends(get_db)):

    result = db.execute(
        select(
            OpenAIUsage.model,
            func.sum(OpenAIUsage.total_tokens).label("tokens"),
            func.sum(OpenAIUsage.estimated_cost).label("cost"),
            func.count(OpenAIUsage.id).label("requests")
        )
        .group_by(OpenAIUsage.model)
        .order_by(func.sum(OpenAIUsage.total_tokens).desc())
    )

    rows = result.all()

    return [
        {
            "model": row[0],
            "total_tokens": row[1],
            "total_cost_usd": float(row[2] or 0),
            "total_requests": row[3]
        }
        for row in rows
    ]


@router.get("/budget-alert")
def budget_alert(db: Session = Depends(get_db)):

    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)

    result = db.execute(
        select(func.sum(OpenAIUsage.estimated_cost))
        .where(OpenAIUsage.created_at >= start_of_month)
    )

    total_cost = float(result.scalar() or 0)

    percentage_used = (
        (total_cost / MONTHLY_BUDGET_USD) * 100
        if MONTHLY_BUDGET_USD > 0
        else 0
    )

    return {
        "monthly_budget_usd": MONTHLY_BUDGET_USD,
        "current_spent_usd": total_cost,
        "percentage_used": round(percentage_used, 2),
        "alert": percentage_used >= 80
    }
