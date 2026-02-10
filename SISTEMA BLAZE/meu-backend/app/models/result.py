from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.core.database import Base

class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, index=True)
    cor = Column(String)
    numero = Column(Integer)
    horario = Column(String)
    criado_em = Column(DateTime, default=datetime.utcnow)
