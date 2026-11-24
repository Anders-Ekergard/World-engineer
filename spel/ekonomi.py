"""
ekonomi.py – vad dammar kostar, hur lång tid de tar att bygga och vad de tjänar.
Alla belopp i miljoner US-dollar (M$, 2025 års penningvärde).

Dammkroppen:
  Konstruktionshöjd  Hs = 1,4*H + 10   (fallhöjden H är lägre än dammens höjd
                                         över grunden: fribord + nedströms vattennivå)
  Krönlängd          Lk = verklig krönlängd (kända dammar) eller 35 % av dalbredden
  Dalen är V-formad, så dammens höjd varierar från 0 vid kanterna till Hs i mitten.
  Medeltvärsnitt (höjd h likformig på [0, Hs]):
    fyllning (slänter 1:2,5, krön 10 m):  5*Hs + 0,833*Hs^2
    betong (gravitation, bas 0,8*Hs, krön 8 m): 4*Hs + 0,133*Hs^2
Kalibrering: De tre ravinerna ≈ 30–37 miljarder $, Itaipu ≈ 20–45 miljarder $ (dagens pengar).
"""

import math

from floder import magasin, RHO, G, ETA
from spel.minispel import effekter

PRIS = {"betong": 250e-6, "fyllning": 25e-6}     # M$ per m3
KRAFTVERK_PER_MW = 1.0                            # M$ per installerad MW
UTSKOV_PER_M3S = 0.025                            # M$ per m3/s kapacitet
OMFLYTTNING_PER_PERSON = 0.010                    # M$ per person
SEISMIK_TILLAGG = {0.15: 1.0, 0.3: 1.10, 0.5: 1.25}   # dyrare damm för högre dimensionerande PGA
OVERVAKNING_KOSTNAD = {0: 0.0, 1: 0.005, 2: 0.015}    # andel av dammkroppens kostnad
RESERVKRAFT = 20.0                                 # M$
ELPRIS = 50.0                                      # $ per MWh
INTAKTSANDEL = 0.3     # världsingenjören får 30 % av elintäkterna, resten stannar hos länderna
UNDERHALL_PER_AR = {0: 0.0, 1: 0.005, 2: 0.012}    # andel av anläggningskostnaden per år
BYGGTAKT = {"betong": 2.5e6, "fyllning": 40e6}     # m3 per år

# Dammar byggs där dalen är smalast. Verkliga krönlängder (m) för de kända platserna;
# för nya platser antas krönet vara 35 % av dalens bredd i magasinsmodellen.
KRONA_M = {"yangtze": 2335, "colorado": 379, "nilen": 3830, "blanilen": 1780, "parana": 7919,
           "volga": 3250, "donau": 1278, "jenisej": 1065, "indus": 2743, "zambezi": 579,
           "columbia": 1592, "lulealv": 1000, "kongo": 2000, "tsangpo": 600, "mekong": 1500,
           "amazonas": 12000, "mississippi": 4000}
KRONA_ANDEL = 0.35


def kronlangd_m(plats, H: float) -> float:
    if plats.id in KRONA_M:
        return KRONA_M[plats.id]
    return KRONA_ANDEL * magasin(plats, H)["bredd_km"] * 1e3


def dammvolym_m3(typ: str, H: float, krona_m: float) -> float:
    Hs = 1.4 * H + 10
    tvarsnitt = 5 * Hs + 0.833 * Hs ** 2 if typ == "fyllning" else 4 * Hs + 0.133 * Hs ** 2
    return krona_m * tvarsnitt


def installerad_MW(plats, H: float, utbyggnad: float) -> float:
    """Turbinernas sammanlagda effekt: dimensionerande turbinflöde = utbyggnad * Q_medel."""
    return RHO * G * utbyggnad * plats.Q * H * ETA / 1e6


def kalkyl(plats, design: dict, Q_utskov: float) -> dict:
    """Kostnad (M$) och byggtid (månader) för en damm. design har typ, H, utbyggnad,
    seismik_g, overvakning, reservkraft."""
    m = magasin(plats, design["H"])
    krona = kronlangd_m(plats, design["H"])
    V = dammvolym_m3(design["typ"], design["H"], krona)
    e = effekter(design)                                   # kemilabbet och gjutningen
    damm = V * PRIS[design["typ"]] * SEISMIK_TILLAGG[design["seismik_g"]] * e["damm_faktor"]
    MW = installerad_MW(plats, design["H"], design["utbyggnad"])
    kraftverk = MW * KRAFTVERK_PER_MW
    utskov = Q_utskov * UTSKOV_PER_M3S
    omflyttning = m["fordrivna"] * OMFLYTTNING_PER_PERSON
    ovrigt = damm * OVERVAKNING_KOSTNAD[design["overvakning"]] + \
        (RESERVKRAFT if design["reservkraft"] else 0.0)
    total = damm + kraftverk + utskov + omflyttning + ovrigt
    # större bygge = fler arbetslag: takten växer med roten ur volymen
    takt = BYGGTAKT[design["typ"]] * max(1.0, math.sqrt(V / (4 * BYGGTAKT[design["typ"]])))
    ar = 3 + V / takt * e["tid_faktor"] + MW / 4000         # 4 GW turbiner per år
    return {
        "damm": damm, "kraftverk": kraftverk, "utskov": utskov, "omflyttning": omflyttning,
        "ovrigt": ovrigt, "total": total, "volym_m3": V, "krona_m": krona, "MW": MW,
        "byggtid_man": int(round(min(ar, 25) * 12)), "fordrivna": m["fordrivna"],
        "minispel": e,
    }


def intakt_MS(MWh: float) -> float:
    return MWh * ELPRIS * INTAKTSANDEL / 1e6
