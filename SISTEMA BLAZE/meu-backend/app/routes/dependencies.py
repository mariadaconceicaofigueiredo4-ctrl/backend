from fastapi import Depends, HTTPException
from app.routes.bets import get_current_user

def admin_only(user=Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return user

