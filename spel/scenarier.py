"""
scenarier.py – avgränsade spel med mål, skriptade händelser och slutbetyg.

Första scenariot: "Nilen" (2030–2055). Spelaren tar över Assuan (Egypten, 1970) och den
nya GERD-dammen (Etiopien), som fortfarande fylls. Fyra mål:
  1. Energi:          minst MAL_TWH TWh/år (medel över det sista året)
  2. Säkerhet:        inget dammbrott
  3. Acceptans:       Afrika minst 40 när scenariot slutar
  4. Vattensäkerhet:  under den stora torkan (år 10–13) släpper Assuan i medel minst
                      70 % av Nilens normala flöde till Egypten
Betyg: 4 mål = guld, 3 = silver, 2 = brons, annars underkänt.

Skriptade händelser ger scenariot form (ingen slump):
  - GERD fylls i början -> Egypten oroas (acceptans)
  - år 5: inre erosion upptäcks i Assuans tätkärna
  - år 10–13: en flerårig torka i Nilens flodsystem
"""

import numpy as np

from spel import hydrologi as HY
from spel.anlaggning import befintlig, BEFINTLIGA
from spel.tillstand import nytt_spel

MAL_TWH = 30.0
TORKA = (120, 156)          # månader (år 10 till 13)
TORKA_Z = -2.0              # mycket torrt: flödet ca hälften av normalt
EROSION_MANAD = 60
SLUT_MANAD = 300
OMRADE = (24.0, 40.0, -4.0, 32.0)     # lon0, lon1, lat0, lat1: Nilbäckenet och västra öknen
MEGA_TILLATNA = {"qattara"}
BETYG_NAMN = {"guld": "GOLD", "silver": "SILVER", "brons": "BRONZE", "underkänt": "FAILED"}

INFO = {
    "nilen": {"namn": "Nile 2030–2055", "beskrivning":
              "Take charge of Aswan and GERD and guide the Nile Basin through 25 years: power, safety, "
              "acceptance and water for Egypt during the drought. Recommended for first-time players."},
}


def starta(namn: str = "nilen", fro: int = 1) -> dict:
    """Start a new game in the scenario."""
    t = nytt_spel(fro=fro, budget=15000.0, med_befintliga=False)
    rng = np.random.default_rng([fro, 999])
    for pid, byggar, typ, T, problem in BEFINTLIGA:
        if pid in ("nilen", "blanilen"):
            t["anlaggningar"][pid] = befintlig(pid, byggar, typ, T, problem, t["startar"], rng)
    gerd = t["anlaggningar"]["blanilen"]
    gerd["V"] = 0.25 * gerd["V_max"]                    # GERD fylls fortfarande
    t["anslag_per_ar"] = 600.0
    t["scenario"] = {"id": namn, "slut_manad": SLUT_MANAD, "torka_summa": 0.0, "torka_n": 0,
                     "dammbrott": 0, "resultat": None}
    t["logg"] = [{"m": 0, "niva": "info", "anl": None,
                  "text": "Nile scenario: you are responsible for Aswan and GERD for 25 years. The goals are "
                          "shown in the objective panel. Good luck, world engineer!"}]
    return t


def tillaten_plats(t: dict, lon: float, lat: float) -> bool:
    if not t.get("scenario"):
        return True
    lon0, lon1, lat0, lat1 = OMRADE
    return lon0 <= lon <= lon1 and lat0 <= lat <= lat1


def tillaten_mega(t: dict, mid: str) -> bool:
    return not t.get("scenario") or mid in MEGA_TILLATNA


def _logg(t, text, niva, anl=None):
    t["logg"].append({"m": t["manad"], "text": text, "niva": niva, "anl": anl})


def nil_system() -> str:
    return HY.statistik("nilen")["system"]


# ---------------------------------------------------------------- krokar i motorn

def fore_manad(t: dict):
    """Skriptade händelser i början av månaden."""
    sc = t.get("scenario")
    if not sc:
        return
    m = t["manad"]
    a = t["anlaggningar"]
    if m == 1:
        _logg(t, "GERD is still filling its reservoir. Less water reaches Egypt, and "
                 "Cairo protests.", "varning", "blanilen")
        t["paverkan"]["Mellanöstern"] = t["paverkan"].get("Mellanöstern", 0.0) - 8.0
    if m == EROSION_MANAD and a.get("nilen", {}).get("status") == "drift":
        k = a["nilen"]["komp"]["karna"]
        k["dold"], k["sedd"] = max(k["dold"], 0.35), True
        _logg(t, "Aswan: turbid seepage at the toe of the dam! INTERNAL EROSION in the core (35%). "
                 "Lower the reservoir and repair the core before it is too late.", "fara", "nilen")
    if m == TORKA[0]:
        _logg(t, "The rains over the Ethiopian Highlands have failed. A multi-year drought has begun.", "fara")
    if m == TORKA[1]:
        _logg(t, "The rains have returned. The drought is over.", "info")


def tvingad_anomali(t: dict, system: str):
    """Scenariots torka styr Nilens flöde (None = vanlig slump)."""
    sc = t.get("scenario")
    if sc and TORKA[0] <= t["manad"] < TORKA[1] and system == nil_system():
        return TORKA_Z
    return None


def efter_manad(t: dict):
    """Följ målen och avsluta scenariot när tiden är ute (anropas innan månaden räknas upp)."""
    sc = t.get("scenario")
    if not sc or sc["resultat"]:
        return
    assuan = t["anlaggningar"].get("nilen")
    if TORKA[0] <= t["manad"] < TORKA[1] and assuan:
        q = assuan["senast"].get("Q_ut", 0.0) if assuan["status"] == "drift" else 0.0
        sc["torka_summa"] += q / HY.statistik("nilen")["Q"]
        sc["torka_n"] += 1
    sc["dammbrott"] = sum(1 for a in t["anlaggningar"].values() if a["status"] == "havererad")
    if t["manad"] + 1 >= sc["slut_manad"]:
        sc["resultat"] = utvardera(t)
        r = sc["resultat"]
        t["slut"] = f"Scenario complete: {BETYG_NAMN[r['betyg']]} ({r['antal']} of 4 objectives met)."
        _logg(t, t["slut"], "info")


# ---------------------------------------------------------------- objectives and grades

def mal_status(t: dict, slut: bool = False) -> list:
    """[(name, value as text, met: True/False/None)] – None = not decided yet.
    slut=True: evaluate everything now (when the scenario ends)."""
    sc = t["scenario"]
    hist = t["historik"]["TWh_ar"][-12:]
    twh = sum(hist) / len(hist) if hist else 0.0
    torka = sc["torka_summa"] / sc["torka_n"] if sc["torka_n"] else None
    afrika = t["acceptans"]["Afrika"]
    klar = slut or sc["resultat"] is not None
    drought_complete = slut or t["manad"] >= TORKA[1]
    return [
        ("Energy", f"{twh:.1f} of {MAL_TWH:.0f} TWh/year", (twh >= MAL_TWH) if klar else None),
        ("No dam failures", "none" if sc["dammbrott"] == 0
         else f"{sc['dammbrott']} failure{'s' if sc['dammbrott'] > 1 else ''}", sc["dammbrott"] == 0),
        ("Acceptance in Africa", f"{afrika:.0f} (at least 40)", (afrika >= 40) if klar else None),
        ("Water for Egypt during drought",
         "the drought has not come yet" if torka is None else f"{100 * torka:.0f}% of normal (at least 70%)",
         (torka is not None and torka >= 0.7) if drought_complete else None),
    ]


def utvardera(t: dict) -> dict:
    sc = t["scenario"]
    status = mal_status(t, slut=True)
    antal = sum(1 for _, _, ok in status if ok)
    betyg = {4: "guld", 3: "silver", 2: "brons"}.get(antal, "underkänt")
    rader = []
    for namn, varde, ok in status:
        rader.append(f"{'✓' if ok else '✗'} {namn}: {varde}")
    if sc["dammbrott"]:
        rader.append("A dam failure costs lives and trust. Good monitoring reveals internal erosion "
                     "in time, and lowering the reservoir stops it.")
    if not status[3][2]:
        rader.append("A drought calls for water in reserve: switch to 'conserve water' before it "
                     "starts, and keep GERD full so it can release water downstream.")
    if not status[0][2]:
        rader.append("More power needs more turbines or new dams, but every new dam upstream "
                     "takes water and sediment from Egypt.")
    return {"betyg": betyg, "antal": antal, "rader": rader}
