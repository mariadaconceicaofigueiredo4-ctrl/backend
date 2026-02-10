from sqlalchemy import Column, Integer, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.core.database import Base

class Bet(Base):
    __tablename__ = "bets"

    id = Column(Integer, primary_key=True)
    amount = Column(Float, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("events.id"))

    user = relationship("User", back_populates="bets")
    event = relationship("Event")
