"""
tillstand.py – nytt spel, spara och ladda.

Hela spelet är en dict som går att spara som JSON:
  fro, startar, manad, budget, anlaggningar, mega, acceptans, paverkan, hydrologi (AR(1)-
  anomalier per flodsystem), klimat, stat, logg, historik, slut
"""

import json
import os

import numpy as np

from spel import acceptans as ACC
from spel.anlaggning import BEFINTLIGA, befintlig

MAPP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sparade")
VERSION = 1


def nytt_spel(fro: int = 1, startar: int = 2030, budget: float = 60000.0,
              med_befintliga: bool = True) -> dict:
    t = {
        "version": VERSION, "fro": int(fro), "startar": startar, "manad": 0,
        "budget": budget, "anlaggningar": {}, "mega": {}, "acceptans": ACC.ny(), "paverkan": {},
        "hydrologi": {}, "klimat": {"dT": 0.0, "havsniva_m": 0.0, "co2_sparad_Gt": 0.0},
        "stat": {"energi_TWh": 0.0, "dodsoffer": 0},
        "logg": [], "historik": {"budget": [], "TWh_ar": [], "acceptans": []},
        "senaste_rapport": {}, "slut": None,
    }
    if med_befintliga:
        rng = np.random.default_rng([fro, 999])
        for pid, byggar, typ, T, problem in BEFINTLIGA:
            t["anlaggningar"][pid] = befintlig(pid, byggar, typ, T, problem, startar, rng)
    t["logg"].append({"m": 0, "niva": "info", "anl": None,
                      "text": f"Welcome, world engineer! You have inherited {len(t['anlaggningar'])} "
                              "dams, some of them old. Keep them in good condition and build new ones."})
    return t


def _json(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


def till_json(t: dict) -> str:
    return json.dumps(t, default=_json, ensure_ascii=False)


def fran_json(s: str) -> dict:
    return json.loads(s)


def spara(t: dict, namn: str) -> str:
    os.makedirs(MAPP, exist_ok=True)
    fil = os.path.join(MAPP, f"{namn}.json")
    with open(fil, "w", encoding="utf-8") as f:
        f.write(till_json(t))
    return fil


def ladda(namn: str) -> dict:
    with open(os.path.join(MAPP, f"{namn}.json"), encoding="utf-8") as f:
        return fran_json(f.read())


def sparade_spel() -> list:
    if not os.path.isdir(MAPP):
        return []
    return sorted(f[:-5] for f in os.listdir(MAPP) if f.endswith(".json"))
