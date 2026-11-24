"""
acceptans.py – hur regionerna tar emot världsingenjörens projekt (0–100).

Varje månad dras acceptansen sakta mot 50 (människor glömmer), plus det som hänt:
  - bygge startar:        -fördrivna/40 000 (högst -25)
  - el i drift:           +GWh/50 000 per damm och månad (högst +0,05)
  - dammen dämpade en flod  +1,  vatten under torka  +0,5
  - deltat svälts på sediment  -0,1 per månad
  - dammbrott:            -40 i regionen, -10 i övriga, plus -dödsoffer/1 000 (högst -30)
Låg acceptans (< 30) halverar byggtakten, och under 15 kan protester stoppa bygget.
"""

from spel.geografi import REGIONER

GLOMSKA = 0.01


def ny() -> dict:
    return {r: 50.0 for r in REGIONER}


def uppdatera(acc: dict, paverkan: dict):
    for r in acc:
        acc[r] += GLOMSKA * (50.0 - acc[r]) + paverkan.get(r, 0.0)
        acc[r] = min(100.0, max(0.0, acc[r]))


def byggtakt(acc_region: float) -> float:
    return 0.5 if acc_region < 30 else 1.0
