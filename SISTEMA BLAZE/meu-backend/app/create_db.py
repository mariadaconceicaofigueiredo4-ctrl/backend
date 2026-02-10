from app.core.database import Base, engine
from app.models import User, Event, Bet

Base.metadata.create_all(bind=engine)
print("Banco criado com sucesso")
