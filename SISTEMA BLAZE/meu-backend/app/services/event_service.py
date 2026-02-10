from sqlalchemy.orm import Session
from app.models.bet import Bet
from app.models.transaction import WalletTransaction

def resolve_event(db: Session, event, result: bool):
    if not event.is_open:
        raise ValueError("Evento já resolvido")

    event.is_open = False
    event.result = result

    bets = db.query(Bet).filter(Bet.event_id == event.id).all()

    for bet in bets:
        if result:
            bet.won = True
            tx = WalletTransaction(
                amount=bet.possible_return,
                type="win",
                user_id=bet.user_id
            )
            bet_user = bet.user
            bet_user.wallet.balance += bet.possible_return
            db.add(tx)
        else:
            bet.won = False

    db.commit()
