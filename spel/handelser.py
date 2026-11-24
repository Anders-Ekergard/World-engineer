"""
handelser.py – jordbävningar.

Varje seismisk zon (geografi.ZONER) har en årlig takt av skalv med M >= 5,5.
Antalet skalv per månad är Poissonfördelat. Magnituden följer Gutenberg–Richter
med b = 1:  P(M > m) = 10^(-(m - 5,5)),  avkortad vid zonens största magnitud.
Epicentrum dras jämnt i zonen. Markaccelerationen vid dammen ges av Campbells formel.
Utanför zonerna finns en liten bakgrundsrisk per damm.
"""

import math

from spel.geografi import ZONER, BAKGRUND_PER_AR, M_MIN, zon_for, pga, avstand_km


def magnitud(rng, M_max: float) -> float:
    while True:
        M = M_MIN - math.log10(rng.uniform(1e-9, 1.0))
        if M <= M_max:
            return M


def skalv(anlaggningar: list, rng) -> list:
    """Månadens skalv som påverkar någon damm: lista med (lon, lat, M, zonnamn)."""
    ut = []
    zoner = {zon_for(a["lon"], a["lat"]) for a in anlaggningar} - {None}
    for z in sorted(zoner):                               # sorterat: deterministiskt
        namn, lon0, lon1, lat0, lat1, takt, M_max = z
        for _ in range(rng.poisson(takt / 12)):
            ut.append((rng.uniform(lon0, lon1), rng.uniform(lat0, lat1), magnitud(rng, M_max), namn))
    for a in anlaggningar:
        if zon_for(a["lon"], a["lat"]) is None and rng.uniform() < BAKGRUND_PER_AR / 12:
            R, vinkel = rng.uniform(5, 30), rng.uniform(0, 2 * math.pi)
            ut.append((a["lon"] + R * math.cos(vinkel) / (111 * math.cos(math.radians(a["lat"]))),
                       a["lat"] + R * math.sin(vinkel) / 111, magnitud(rng, 6.5), "bakgrund"))
    return ut


def paverkan(anl: dict, skalv_lista: list) -> list:
    """(PGA, M, R) för de skalv som skakar dammen märkbart (> 0,05 g)."""
    ut = []
    for lon, lat, M, _ in skalv_lista:
        R = avstand_km(lon, lat, anl["lon"], anl["lat"])
        a = pga(M, R)
        if a > 0.05:
            ut.append((a, M, R))
    return ut
