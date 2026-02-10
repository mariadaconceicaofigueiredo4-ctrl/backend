from fastapi import APIRouter
from app.core.state import ultimo_resultado, ultimos_60
from app.core.database import SessionLocal
from app.models.result import Result

router = APIRouter(prefix="/results", tags=["Results"])

@router.get("/ultimo")
def ultimo():
    return ultimo_resultado

@router.get("/ultimos-60")
def ultimos():
    return list(ultimos_60)

@router.get("/historico")
def historico():
    db = SessionLocal()
    data = db.query(Result).order_by(Result.id.desc()).all()
    db.close()
    return data
