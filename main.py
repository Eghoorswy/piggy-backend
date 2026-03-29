import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, func, select, cast, Date
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column

# DATABASE
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_iLxsr2hIPp4W@ep-rough-flower-amvyrwrw-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# MODEL
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    amount: Mapped[int] = mapped_column(nullable=False)
    note: Mapped[str] = mapped_column(default="deposit")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# APP
app = FastAPI()

# CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SCHEMA
class Deposit(BaseModel):
    amount: int

GOAL = 100000

# ROUTES

@app.get("/balance")
def get_balance():
    with SessionLocal() as db:
        total = db.execute(select(func.sum(Transaction.amount))).scalar()
        return {"balance": int(total or 0)}


@app.get("/history")
def get_history():
    with SessionLocal() as db:
        txns = db.execute(
            select(Transaction).order_by(Transaction.created_at.desc())
        ).scalars().all()

        return {
            "history": [
                {
                    "amount": t.amount,
                    "date": t.created_at.isoformat()
                }
                for t in txns
            ]
        }


@app.post("/deposit")
def deposit(data: Deposit):
    if data.amount not in [100, 500, 1000]:
        raise HTTPException(status_code=400, detail="Invalid amount")

    with SessionLocal() as db:
        total = db.execute(select(func.sum(Transaction.amount))).scalar() or 0

        if total + data.amount > GOAL:
            raise HTTPException(status_code=400, detail="Goal exceeded")

        txn = Transaction(amount=data.amount)
        db.add(txn)
        db.commit()

        return {
            "message": "Success",
            "new_balance": total + data.amount
        }


@app.delete("/clear")
def clear_history():
    with SessionLocal() as db:
        db.query(Transaction).delete()
        db.commit()
        return {"message": "All transactions deleted"}


@app.get("/analytics")
def get_analytics():
    with SessionLocal() as db:
        total = db.execute(select(func.sum(Transaction.amount))).scalar() or 0
        count = db.execute(select(func.count(Transaction.id))).scalar() or 0

        avg = total / count if count > 0 else 0

        week_ago = datetime.utcnow() - timedelta(days=7)

        daily = db.execute(
            select(
                cast(Transaction.created_at, Date).label("day"),
                func.sum(Transaction.amount).label("daily_total")
            )
            .where(Transaction.created_at >= week_ago)
            .group_by(cast(Transaction.created_at, Date))
            .order_by("day")
        ).all()

        daily_data = [
            {
                "day": str(row.day),
                "amount": int(row.daily_total or 0)
            }
            for row in daily
        ]

        total_last_week = sum(row.daily_total or 0 for row in daily)
        avg_daily = total_last_week / 7 if total_last_week > 0 else 0

        remaining = max(0, GOAL - total)
        days_to_goal = int(remaining / avg_daily) if avg_daily > 0 else None

        recommendations = {
            f"in_{d}_days": int(remaining / d) for d in [30, 60, 90]
        }

        return {
            "total_saved": int(total),
            "goal": GOAL,
            "remaining": int(remaining),
            "percent_complete": round((total / GOAL) * 100, 1) if total else 0,
            "transaction_count": int(count),
            "average_deposit": round(avg),
            "last_7_days": daily_data,
            "avg_daily_last_week": round(avg_daily),
            "projected_days_to_goal": days_to_goal,
            "recommended_daily": recommendations
        }