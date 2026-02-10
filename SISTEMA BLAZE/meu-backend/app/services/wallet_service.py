from sqlalchemy.orm import Session
from app.models.user import User


def deposit(db: Session, user_id: int, amount: float):
    if amount <= 0:
        raise ValueError("Valor inválido")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise ValueError("Usuário não encontrado")

    user.balance += amount
    db.commit()
    db.refresh(user)

    return user
