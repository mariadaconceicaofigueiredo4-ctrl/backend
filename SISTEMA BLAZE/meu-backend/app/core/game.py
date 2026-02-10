import random

def sortear_resultado():
    r = random.random()

    if r < 0.47:
        return "red"
    elif r < 0.94:
        return "black"
    else:
        return "white"
