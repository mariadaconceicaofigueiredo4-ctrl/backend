from app.models.bet import Bet

def place_bet(db, user, event, amount: float):
    if not event.is_open:
        raise ValueError("Evento encerrado")

    if user.wallet.balance < amount:
        raise ValueError("Saldo insuficiente")

    user.wallet.balance -= amount
    possible_return = amount * event.odd

    bet = Bet(
        amount=amount,
        possible_return=possible_return,
        user_id=user.id,
        event_id=event.id
    )

    db.add(bet)
    db.commit()
    db.refresh(bet)

    return bet
