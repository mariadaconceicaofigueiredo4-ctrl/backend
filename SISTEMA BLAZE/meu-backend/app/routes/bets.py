from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.event import Event
from app.services.bet_service import place_bet
from app.schemas.bet import BetCreate, BetResponse

router = APIRouter(prefix="/bets", tags=["Bets"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user

@router.post("/", response_model=BetResponse)
def create_bet(
    data: BetCreate,
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event = db.query(Event).get(data.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    return place_bet(db, user, event, data.amount)
