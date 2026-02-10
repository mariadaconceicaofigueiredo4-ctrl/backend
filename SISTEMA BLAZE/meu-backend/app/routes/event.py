from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.event import Event
from app.schemas.event import EventCreate, EventResponse
from app.core.game import sortear_resultado
from app.core.state import ultimo_resultado

router = APIRouter(prefix="/events", tags=["Events"])

@router.get("/status")
def status_atual():
    return ultimo_resultado

@router.post("/", response_model=EventResponse)
def create_event(_: EventCreate, db: Session = Depends(get_db)):
    open_event = db.query(Event).filter(Event.status == "open").first()

    if open_event:
        raise HTTPException(status_code=400, detail="Já existe um evento aberto")

    event = Event(status="open", result=None)
    db.add(event)
    db.commit()
    db.refresh(event)

    return event

@router.post("/{event_id}/finish", response_model=EventResponse)
def finish_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    if event.status != "open":
        raise HTTPException(status_code=400, detail="Evento não está aberto")

    event.result = sortear_resultado()
    event.status = "finished"

    db.commit()
    db.refresh(event)

    return event

@router.get("/", response_model=list[EventResponse])
def list_events(db: Session = Depends(get_db)):
    return db.query(Event).order_by(Event.id.asc()).all()
