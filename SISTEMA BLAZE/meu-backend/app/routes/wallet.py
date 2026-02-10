from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.wallet import (
    DepositRequest,
    WalletResponse,
    TransactionResponse
)
from app.services.wallet_service import deposit
from app.routes.bets import get_current_user
from app.models.transaction import WalletTransaction

router = APIRouter(prefix="/wallet", tags=["Wallet"])

@router.get("/balance", response_model=WalletResponse)
def get_balance(user=Depends(get_current_user)):
    return {"balance": user.wallet.balance}

@router.post("/deposit", response_model=TransactionResponse)
def deposit_money(
    data: DepositRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return deposit(db, user, data.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/transactions", response_model=list[TransactionResponse])
def transactions(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return (
        db.query(WalletTransaction)
        .filter(WalletTransaction.user_id == user.id)
        .order_by(WalletTransaction.created_at.desc())
        .all()
    )
