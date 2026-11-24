"""
sankor.py – kanaler från havet till sänkor under havsytan (Qattara, Döda havet ...).

Idén (t.ex. Qattara-projektet, 1950-talet och framåt):
  Havsvatten rinner genom en kanal ned i en sänka. Fallhöjden driver turbiner.
  Sjön växer tills avdunstningen från sjöytan är lika stor som inflödet:
      E * A(h) = Q_kanal          -> jämviktsnivån h uppstår av sig själv
  Salt kommer in men avdunstar inte. Sjön blir saltare och saltare, och till sist
  faller gips och salt ut på botten (samma evaporitkemi som i bassanger.py).

Tidssteg 1 år:
    dV/dt = Q_in + tillrinning + (P - E * a_w(S)) * A(h)
    el    = rho*g*Q_in*(lyft + h_källa - h)*eta_turbin - rho*g*Q_in*lyft/eta_pump
(lyft > 0 bara om vattnet måste pumpas över en ås, som i Röda–Döda-kanalen)

Sänkornas form (A och V som funktion av nivån) kommer från ETOPO1 (terrang.py).

megaprojekt(byggda, ar) räknar ihop ALLA megaprojekt i rätt ordning, eftersom de
påverkar varandra:
  1) sänkorna med källhavet i normal nivå -> hur mycket vatten kanalerna tar
  2) haven (Medelhavet, Röda havet) med minskad tillrinning från floddammar + kanaler
  3) sänkorna igen, med källhavets nya nivå och salthalt (t.ex. Qattara + Atlantropa)
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from bassanger import (HAV_DICT, MINERALER, VARLDSHAVET_YTA, fall_ut, simulera,
                       vattenaktivitet)
from terrang import sanka_hypsometri

RHO = 1025.0
G = 9.81
ETA_TURBIN = 0.90
ETA_PUMP = 0.85
SEK_PER_AR = 3.156e7
KANAL_FART = 1.5          # m/s, vattnets hastighet i kanalen
KANAL_DJUP = 10.0         # m
SUEZ_KM3 = 0.075          # grävvolym för Suezkanalen när den byggdes (1869)


@dataclass
class Sanka:
    id: str
    namn: str
    projekt: str
    kalla: str               # "gibraltar" (Medelhavet) eller "rodahavet"
    kanal: tuple             # ((lon...), (lat...)) från havet till sänkan
    markor: tuple            # (lon, lat) klickbar symbol
    E: float                 # avdunstning från sötvattenyta, m/år
    P: float                 # nederbörd, m/år
    tillrinning: float       # annat inflöde (floder, grundvatten), m3/år
    S0: float                # salthalt i sjön från början, g/L
    V_extra: float           # vatten som redan finns under ETOPO:s yta (Döda havet), m3
    lyft: float              # pumphöjd över en ås, m
    kanal_km: float          # kanalens/tunnelns längd
    as_hojd: float           # hur högt över havet åsen som ska grävas igenom är, m
    as_km: float             # hur lång den biten är, km
    Q_standard: float        # förvald kapacitet, m3/s
    Q_max: float             # största kapacitet i reglaget, m3/s
    info: str = ""


SANKOR_LISTA = [
    Sanka("qattara", "Qattara Depression", "Qattara Canal", "gibraltar",
          kanal=((28.95, 28.3, 27.7), (30.83, 30.2, 29.8)), markor=(27.2, 29.6),
          E=1.9, P=0.02, tillrinning=0.0, S0=0.0, V_extra=0.0, lyft=0.0,
          kanal_km=75, as_hojd=150, as_km=60, Q_standard=600, Q_max=3000,
          info="The Qattara Depression in Egypt's Western Desert reaches about 133 m below sea "
               "level. Friedrich Bassler's plan (1950s–70s) was a 60–80 km canal from the "
               "Mediterranean near El Alamein. The lake would settle around −60 m, where "
               "evaporation balances the inflow. Blasting the canal with nuclear charges was "
               "even considered."),
    Sanka("dodahavet", "Dead Sea", "Red Sea–Dead Sea Canal", "rodahavet",
          kanal=((35.0, 35.1, 35.2, 35.35, 35.45), (29.53, 29.9, 30.3, 31.0, 31.25)),
          markor=(35.5, 31.5),
          E=1.9, P=0.05, tillrinning=0.2e9, S0=340.0, V_extra=1.1e11, lyft=220,
          kanal_km=180, as_hojd=0, as_km=0, Q_standard=60, Q_max=400,
          info="The Dead Sea is dropping about 1 m/year because irrigation has almost dried up "
               "the Jordan River. The Red Sea–Dead Sea Canal would pump water from Aqaba over "
               "the Arava ridge (about 220 m) and let it fall to about −430 m. Chemical risk: "
               "the Dead Sea brine is rich in calcium, and the sulfate in seawater can "
               "precipitate gypsum that turns the water milky white. (ETOPO1 shows the surface "
               "at about −415 m; today it is about −440 m.)"),
    Sanka("saharahavet", "Saharan Sea (chotts)", "Roudaire's Canal", "gibraltar",
          kanal=((10.1, 9.2, 8.4, 7.5, 6.4), (33.9, 33.85, 33.8, 34.0, 34.2)), markor=(7.8, 34.0),
          E=2.0, P=0.1, tillrinning=0.0, S0=0.0, V_extra=0.0, lyft=0.0,
          kanal_km=360, as_hojd=45, as_km=20, Q_standard=300, Q_max=1500,
          info="In the 1870s François Roudaire proposed flooding the salt lakes (chotts) of "
               "Tunisia and Algeria with water from the Gulf of Gabès, creating an 'inland sea' "
               "that would bring rain to the Sahara. Chott Melrhir lies about 40 m below sea "
               "level. Jules Verne wrote a novel about the project."),
    Sanka("danakil", "Danakil Depression", "Danakil Canal", "rodahavet",
          kanal=((40.33, 40.35, 40.4), (14.88, 14.6, 14.25)), markor=(40.45, 14.0),
          E=3.0, P=0.05, tillrinning=0.0, S0=0.0, V_extra=0.0, lyft=0.0,
          kanal_km=60, as_hojd=100, as_km=30, Q_standard=400, Q_max=2000,
          info="The Danakil Depression in Ethiopia and Eritrea (about −125 m) is one of the "
               "hottest places on Earth and part of the East African Rift. It has been sea floor "
               "several times before and holds thick salt beds that are still mined by hand today."),
    Sanka("assal", "Lake Assal", "Ghoubbet–Assal", "rodahavet",
          kanal=((42.6, 42.5, 42.42), (11.53, 11.58, 11.62)), markor=(42.42, 11.66),
          E=3.0, P=0.05, tillrinning=0.0, S0=0.0, V_extra=0.0, lyft=0.0,
          kanal_km=12, as_hojd=60, as_km=8, Q_standard=15, Q_max=100,
          info="Lake Assal in Djibouti is the lowest point in Africa (about −155 m) and one of "
               "the saltiest lakes in the world. It is already fed by seawater seeping through "
               "the lava field from the Ghoubbet Gulf, only about 10 km away."),
]
SANKA_DICT = {s.id: s for s in SANKOR_LISTA}


# ---------------------------------------------------------------- geometri

def _tabell(s):
    t = sanka_hypsometri(s.id)
    if t is None:
        raise RuntimeError(f"ETOPO data missing for {s.id} – run hamta_etopo.py")
    return t


# Under ETOPO:s lägsta yta (Döda havets botten saknas i datan) antas sjön vara en
# skål (paraboloid): V = A*D/2 och A proportionell mot djupet D. Då krymper ytan
# när sjön sjunker, och avdunstningen minskar.

def _skal_djup(s):
    h, A, _ = _tabell(s)
    return 2 * s.V_extra / A[1]          # djupet vid ETOPO:s yta, m


def niva_fran_volym(s, V):
    h, A, Vt = _tabell(s)
    if V < 0:
        D0 = _skal_djup(s)
        D = D0 * np.sqrt(max(s.V_extra + V, 0.0) / s.V_extra)
        return float(h[0] - (D0 - D))
    return float(np.interp(V, Vt, h))


def yta_vid(s, h_niva):
    h, A, _ = _tabell(s)
    if h_niva <= h[0]:
        if not s.V_extra:
            return 0.0
        D0 = _skal_djup(s)
        return float(A[1] * max(D0 - (h[0] - h_niva), 0.0) / D0)
    return float(np.interp(h_niva, h, A))


def gravvolym_km3(s, Q):
    """Kanalens tvärsnitt Q/v, plus en genomgrävd ås (bottenbredd = tvärsnitt/djup)."""
    tvarsnitt = Q / KANAL_FART
    return (s.kanal_km * 1e3 * tvarsnitt + s.as_km * 1e3 * s.as_hojd * tvarsnitt / KANAL_DJUP) / 1e9


# ---------------------------------------------------------------- simulering

def simulera_sanka(s: Sanka, Q_max: float, ar: int, kallniva=None, kall_salthalt=None) -> dict:
    """kallniva = källhavets nivå (m, 0 = dagens) per år, kall_salthalt = g/L per år."""
    n = ar + 1
    kallniva = np.broadcast_to(np.asarray(0.0 if kallniva is None else kallniva, float), (n,))
    S_kalla = HAV_DICT[s.kalla].S0 if kall_salthalt is None else kall_salthalt
    S_kalla = np.broadcast_to(np.asarray(S_kalla, float), (n,))
    h_tab, A_tab, V_tab = _tabell(s)
    V_topp = float(V_tab[-1])

    niva, S, Q_in, effekt, pump, yta = (np.zeros(n) for _ in range(6))
    lager = {m[0]: np.zeros(n) for m in MINERALER}
    V = 0.0                                          # vatten ovanför ETOPO:s lägsta yta
    lost = {m[0]: m[1] * s.S0 * s.V_extra for m in MINERALER}
    utfallt = {m[0]: 0.0 for m in MINERALER}
    niva[0], S[0], yta[0] = h_tab[0], s.S0, yta_vid(s, h_tab[0]) if s.V_extra else 0.0

    for i in range(1, n):
        h = niva_fran_volym(s, V)
        A = yta_vid(s, h) if (V > 0 or s.V_extra) else 0.0
        naturligt = s.tillrinning + (s.P - s.E * vattenaktivitet(S[i - 1])) * A   # m3/år
        kn = kallniva[i]
        if Q_max <= 0 or kn <= h:
            q = 0.0                                  # ingen kanal, eller havet ligger lägre än sjön
        elif h >= -0.5:
            q = min(Q_max, max(0.0, -naturligt) / SEK_PER_AR)   # full: håll nivån
        else:
            q = Q_max
        V = min(V + q * SEK_PER_AR + naturligt, V_topp)
        V = max(V, -s.V_extra)                       # kan inte bli tommare än tom
        vatten = V + s.V_extra
        for namn, andel, *_ in MINERALER:
            lost[namn] += andel * q * SEK_PER_AR * S_kalla[i]
        if vatten > 1e6:
            fall_ut(lost, utfallt, vatten)

        niva[i] = niva_fran_volym(s, V)
        yta[i] = yta_vid(s, niva[i]) if vatten > 1e6 else 0.0
        S[i] = sum(lost.values()) / vatten if vatten > 1e6 else 0.0
        Q_in[i] = q
        fall = max(s.lyft + kn - h, 0.0)
        pump[i] = RHO * G * q * s.lyft / ETA_PUMP / 1e6
        effekt[i] = RHO * G * q * fall * ETA_TURBIN / 1e6 - pump[i]
        A_ref = max(float(A_tab[-1]), 1.0)
        for namn, _a, _s, rho_min in MINERALER:
            lager[namn][i] = utfallt[namn] / rho_min / A_ref

    V_arr = np.array([np.interp(x, h_tab, V_tab) if x >= h_tab[0] else 0.0 for x in niva])
    return {
        "t": np.arange(n), "niva": niva, "yta_km2": yta / 1e6, "volym_km3": V_arr / 1e9,
        "salthalt": S, "inflode_m3s": Q_in, "effekt_MW": effekt, "pump_MW": pump,
        "lager": lager, "global_havsniva_m": -V_arr / VARLDSHAVET_YTA,
    }


def jamviktsniva(s: Sanka, Q: float):
    """Nivån där avdunstningen tar ut inflödet, räknat med sötvattenavdunstning.
    En salt sjö avdunstar mindre (lägre vattenaktivitet) och hamnar därför högre."""
    h, A, _ = _tabell(s)
    behov = Q * SEK_PER_AR + s.tillrinning
    netto_E = (s.E - s.P) * A
    k = int(np.searchsorted(netto_E, behov))
    return 0.0 if k >= len(h) else float(h[k])


# ---------------------------------------------------------------- allt tillsammans

def megaprojekt(byggda: dict, ar: int) -> dict:
    nyckel = tuple(sorted((k, float(v)) for k, v in byggda.items()))
    return _megaprojekt(nyckel, ar)


@lru_cache(maxsize=64)
def _megaprojekt(nyckel, ar):
    from kaskad import kaskad
    byggda = dict(nyckel)
    kas = kaskad(byggda)

    # 1) sänkorna med havet i dagens nivå
    sankor = {sid: simulera_sanka(SANKA_DICT[sid], Q, ar)
              for sid, Q in byggda.items() if sid in SANKA_DICT}
    uttag = {}
    for sid, r in sankor.items():
        k = SANKA_DICT[sid].kalla
        uttag[k] = uttag.get(k, 0.0) + r["inflode_m3s"] * SEK_PER_AR

    # 2) haven med minskad tillrinning
    minskning = {h: kas["hav"].get(h, 0.0) + uttag.get(h, 0.0) for h in HAV_DICT}
    hav = {h: simulera(HAV_DICT[h], byggda[h], ar, floder_minskning=minskning[h])
           for h in HAV_DICT if h in byggda}

    # 3) sänkor vars källhav har dämts: räkna om med havets nya nivå och salthalt
    for sid in list(sankor):
        k = SANKA_DICT[sid].kalla
        if k in hav:
            sankor[sid] = simulera_sanka(SANKA_DICT[sid], byggda[sid], ar,
                                         kallniva=-hav[k]["sankning"],
                                         kall_salthalt=hav[k]["salthalt"])

    # 4) haven en sista gång med kanalernas verkliga uttag (inflödet kan ha stannat)
    uttag = {}
    for sid, r in sankor.items():
        k = SANKA_DICT[sid].kalla
        uttag[k] = uttag.get(k, 0.0) + r["inflode_m3s"] * SEK_PER_AR
    minskning = {h: kas["hav"].get(h, 0.0) + uttag.get(h, 0.0) for h in HAV_DICT}
    hav = {h: simulera(HAV_DICT[h], byggda[h], ar, floder_minskning=minskning[h])
           for h in HAV_DICT if h in byggda}
    return {"kaskad": kas, "hav": hav, "sankor": sankor, "uttag": uttag, "minskning": minskning}
