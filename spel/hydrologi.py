"""
hydrologi.py – flödet i floderna månad för månad.

  Q(månad) = Q_medel * säsong(månad) * exp(sigma*z - sigma^2/2) * klimat
där z är en AR(1)-process per flodsystem (z_t = phi*z_(t-1) + sqrt(1-phi^2)*eps).
Med phi = 0,93 per månad hänger våta och torra år ihop, så fleråriga torkor uppstår.

Extremflöden: årets högsta flödestopp följer en Gumbelfördelning
  Q_topp = Q_medel * (mu + beta * y),   y ~ Gumbel(0, 1)
där medeltoppen r = mu + 0,577*beta är 3–9 gånger medelflödet (små floder är
"stötigare" än stora, se r(A) nedan) och variationskoefficienten är 0,25.
En T-årsflod har y_T = -ln(-ln(1 - 1/T)).

Klimatkrokar: klimatfaktorer(...) ger multiplikatorer. I fas 1 är alla 1,0.
"""

import math
from functools import lru_cache

from floder import hamta_plats, _punkt_for
from natverk import natverk
from spel.geografi import sasong, toppmanad

PHI = 0.93
CV_TOPP = 0.25
EULER = 0.5772


def klimatfaktorer(tillstand, plats) -> dict:
    """Multiplikatorer från klimatet för en plats. Fas 1: inget klimat än (alla 1,0).
    Fas 2 fyller i dessa från tillstand["klimat"] (temperatur, vädermönster)."""
    return {"medel": 1.0, "amplitud": 1.0, "extrem": 1.0, "avdunstning": 1.0}


@lru_cache(maxsize=4096)
def statistik(plats_id: str) -> dict:
    """Flodens grunddata: medelflöde, avrinningsområde, flodsystem, Gumbelparametrar."""
    p = hamta_plats(plats_id)
    nv = natverk()
    A, system = 1e5, plats_id
    if nv is not None:
        i = int(nv.punkt_strak[_punkt_for(p)])
        A = float(nv.upland[i])
        system = f"s{int(nv.main_riv[i])}"
    r = 3.0 + 6.0 * math.sqrt(1e4 / (A + 1e4))         # medeltopp / medelflöde
    beta = math.sqrt(6) / math.pi * CV_TOPP * r          # Gumbel: sd = pi*beta/sqrt(6)
    mu = r - EULER * beta
    sigma = 0.15 + 0.2 * 1e5 / (A + 1e5)                 # mellanårsvariation
    return {"Q": p.Q, "A": A, "system": system, "mu": mu, "beta": beta, "sigma": sigma,
            "sasong": sasong(p.lon, p.lat), "toppmanad": toppmanad(p.lon, p.lat)}


def y_T(T: float) -> float:
    return -math.log(-math.log(1 - 1 / T))


def dimensionerande_flode(plats_id: str, T: float, extrem: float = 1.0) -> float:
    """T-årsflödet (m3/s)."""
    s = statistik(plats_id)
    return s["Q"] * (s["mu"] + s["beta"] * y_T(T)) * extrem


def aterkomsttid(plats_id: str, Q_kap: float, extrem: float = 1.0) -> float:
    """Hur sällan (år) ett flöde Q_kap överskrids – baklänges från Gumbel."""
    s = statistik(plats_id)
    y = (Q_kap / (s["Q"] * extrem) - s["mu"]) / s["beta"]
    p = 1 - math.exp(-math.exp(-y))
    return 1 / p if p > 0 else float("inf")


def uppdatera_anomali(z_gammal: float, rng) -> float:
    return PHI * z_gammal + math.sqrt(1 - PHI ** 2) * rng.standard_normal()


def manadsflode(plats_id: str, manad: int, z: float, faktorer: dict) -> float:
    """Medelflöde (m3/s) för en månad (0 = januari) givet flodsystemets anomali z."""
    s = statistik(plats_id)
    sas = 1.0 + (s["sasong"][manad] - 1.0) * faktorer["amplitud"]
    sig = s["sigma"]
    return s["Q"] * faktorer["medel"] * max(sas, 0.05) * math.exp(sig * z - sig ** 2 / 2)


def flodtopp(plats_id: str, manad: int, Q_manad: float, faktorer: dict, rng) -> float:
    """Månadens högsta flödestopp (m3/s). Under toppmånaden dras årets högsta flod
    ur Gumbelfördelningen; andra månader är toppen bara lite över månadsmedel."""
    s = statistik(plats_id)
    if manad == s["toppmanad"]:
        y = -math.log(-math.log(rng.uniform(1e-12, 1 - 1e-12)))
        return s["Q"] * faktorer["extrem"] * (s["mu"] + s["beta"] * y)
    return 1.5 * Q_manad
