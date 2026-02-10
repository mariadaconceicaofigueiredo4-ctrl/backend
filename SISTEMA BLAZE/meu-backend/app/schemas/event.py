from pydantic import BaseModel

class EventCreate(BaseModel):
    status: str = "open"

class EventResponse(BaseModel):
    id: int
    status: str
    result: str | None

    class Config:
        from_attributes = True
