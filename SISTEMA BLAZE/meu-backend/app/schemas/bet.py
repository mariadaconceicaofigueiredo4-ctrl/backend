from pydantic import BaseModel

class BetCreate(BaseModel):
    event_id: int
    amount: float

class BetResponse(BaseModel):
    id: int
    amount: float
    possible_return: float

    class Config:
        from_attributes = True
