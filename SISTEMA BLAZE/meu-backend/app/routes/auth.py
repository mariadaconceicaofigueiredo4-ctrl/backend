from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.user import UserCreate
from app.schemas.auth import Token
from app.core.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=Token)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")

    user = User(
        username=user_data.username,
        password=hash_password(user_data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    wallet = Wallet(user_id=user.id, balance=0.0)
    db.add(wallet)
    db.commit()

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token}

@router.post("/login", response_model=Token)
def login(user_data: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()

    if not user or not verify_password(user_data.password, user.password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token}
