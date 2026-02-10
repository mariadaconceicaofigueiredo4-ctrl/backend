from pydantic import BaseModel
from datetime import datetime

class DepositRequest(BaseModel):
    amount: float

class WalletResponse(BaseModel):
    balance: float

class TransactionResponse(BaseModel):
    id: int
    amount: float
    type: str
    created_at: datetime

    class Config:
        from_attributes = True
