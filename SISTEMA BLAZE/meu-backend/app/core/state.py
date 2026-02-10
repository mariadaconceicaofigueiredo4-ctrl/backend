from collections import deque

ultimo_resultado = {
    "cor": None,
    "numero": None,
    "horario": None
}

ultimos_60 = deque(maxlen=60)
