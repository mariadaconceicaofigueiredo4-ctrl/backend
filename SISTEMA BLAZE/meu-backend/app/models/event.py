from sqlalchemy import Column, Integer, String
from app.core.database import Base

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    status = Column(String, default="open")
    result = Column(String, nullable=True)
