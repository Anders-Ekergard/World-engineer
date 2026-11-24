"""
natverk.py – världens flodnät (HydroRIVERS, förbehandlat av hamta_floder.py).

Med nätet kan man bygga en damm var som helst på en större flod:
  * Flöde Q och avrinningsområde kommer från HydroRIVERS.
  * Magasinet följer den verkliga floden uppströms (huvudfåran = den gren
    som har störst avrinningsområde vid varje sammanflöde).
  * Flodens lutning finns inte i HydroRIVERS. Den uppskattas med Flints lag,
    en empirisk regel: stora floder är flackare än små.
        lutning = k * A^(-theta)       (A = avrinningsområde i km2)
    k och theta anpassas mot de kända dammarna i floder.py.
  * Dalsidornas lutning uppskattas på samma sätt från flodens lutning
    (flacka floder har breda dalar).
"""

import math
import os
from functools import lru_cache

import numpy as np

FIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "floder.npz")
KM_PER_GRAD = 111.0


class Natverk:
    def __init__(self, fil):
        d = np.load(fil)
        self.id = d["id"]
        self.next_down = d["next_down"]
        self.main_riv = d["main_riv"]
        self.Q = d["Q"].astype(np.float64)
        self.upland = d["upland"].astype(np.float64)
        self.start = d["start"]
        self.lon = d["lon"].astype(np.float64)
        self.lat = d["lat"].astype(np.float64)
        self.n = len(self.id)
        self.index = {int(h): i for i, h in enumerate(self.id)}
        # vilken sträcka varje punkt tillhör
        self.punkt_strak = np.repeat(np.arange(self.n), np.diff(self.start))
        # uppströms grenar: barn[i] = sträckor som rinner in i sträcka i
        self.barn = [[] for _ in range(self.n)]
        for i, ned in enumerate(self.next_down):
            j = self.index.get(int(ned))
            if j is not None:
                self.barn[j].append(i)

    def punkter(self, i):
        s, e = self.start[i], self.start[i + 1]
        return self.lon[s:e], self.lat[s:e]

    def narmaste(self, lon, lat, Q=None):
        """(sträcka, global punktindex) närmast en koordinat. Om Q anges väljs bara
        punkter på sträckor med ungefär det flödet (så att man inte hamnar på en biflod)."""
        dx = (self.lon - lon) * math.cos(math.radians(lat))
        dy = self.lat - lat
        avst = dx * dx + dy * dy
        if Q is not None:
            Qp = self.Q[self.punkt_strak]
            fel = (Qp < Q / 3) | (Qp > Q * 3)
            if not fel.all():
                avst = np.where(fel, np.inf, avst)
        p = int(np.argmin(avst))
        return int(self.punkt_strak[p]), p

    def uppstroms_bana(self, p, L_km):
        """Koordinater från punkt p (globalt index) uppströms längs huvudfåran,
        tills sträckan L_km är nådd eller floden tar slut. Returnerar (lon, lat, s_km)."""
        i = int(self.punkt_strak[p])
        lo = list(self.lon[self.start[i]:p + 1][::-1])
        la = list(self.lat[self.start[i]:p + 1][::-1])
        while True:
            s = _stracka(lo, la)
            if s[-1] >= L_km or not self.barn[i]:
                break
            i = max(self.barn[i], key=lambda b: self.upland[b])
            bl, ba = self.punkter(i)
            lo += list(bl[::-1][1:])
            la += list(ba[::-1][1:])
        s = _stracka(lo, la)
        k = int(np.searchsorted(s, L_km)) + 1
        return np.array(lo[:k]), np.array(la[:k]), s[:k]


    def nedstroms_bana(self, p):
        """Vägen från punkt p (globalt index) nedströms till mynningen.
        Returnerar (lon, lat, s_km, position) där position[sträcka] = index i
        listorna för sträckans första punkt (för sträckan där p ligger: punkt p)."""
        i = int(self.punkt_strak[p])
        lo = list(self.lon[p:self.start[i + 1]])
        la = list(self.lat[p:self.start[i + 1]])
        position = {i: 0}
        j = self.index.get(int(self.next_down[i]))
        while j is not None and j not in position:
            position[j] = len(lo)
            bl, ba = self.punkter(j)
            lo += list(bl)
            la += list(ba)
            j = self.index.get(int(self.next_down[j]))
        return np.array(lo), np.array(la), _stracka(lo, la), position

    def avstand_nedstroms(self, p_upp, p_ned):
        """Avstånd längs floden (km) från p_upp ned till p_ned, eller None om
        p_ned inte ligger nedströms p_upp."""
        _, _, s, pos = _nedstroms_cache(p_upp)
        j = int(self.punkt_strak[p_ned])
        if j not in pos:
            return None
        forsta = p_upp if j == int(self.punkt_strak[p_upp]) else int(self.start[j])
        if p_ned < forsta:
            return None           # samma sträcka men uppströms
        return float(s[pos[j] + (p_ned - forsta)])


@lru_cache(maxsize=256)
def _nedstroms_cache(p):
    return natverk().nedstroms_bana(p)


def _stracka(lo, la):
    lo, la = np.asarray(lo), np.asarray(la)
    dx = np.diff(lo) * np.cos(np.radians(la[:-1])) * KM_PER_GRAD
    dy = np.diff(la) * KM_PER_GRAD
    return np.concatenate([[0.0], np.cumsum(np.hypot(dx, dy))])


# Fler flodnamn (HydroRIVERS har inga namn): (namn, lon, lat, ungefärligt flöde m3/s)
FLER_FLODER = [
    ("Rhine", 6.6, 51.8, 2300), ("Rhône", 4.6, 43.9, 1700), ("Elbe", 10.0, 53.5, 870),
    ("Ganges", 88.1, 24.4, 12000), ("Brahmaputra", 89.7, 25.0, 19000),
    ("Irrawaddy", 95.2, 17.5, 13000), ("Yellow River", 117.0, 36.9, 1500),
    ("Amur", 137.0, 50.5, 10000), ("Lena", 127.0, 71.0, 17000), ("Ob", 66.5, 66.0, 12000),
    ("Mackenzie", -134.0, 67.5, 9900), ("Yukon", -162.0, 62.0, 6400),
    ("St. Lawrence", -71.5, 46.8, 10000), ("Orinoco", -63.0, 8.2, 33000),
    ("Niger", 6.5, 5.5, 5600), ("Tigris–Euphrates", 47.5, 30.8, 1500),
    ("Dnieper", 33.5, 46.9, 1700), ("Göta River", 12.0, 58.3, 550), ("Ångerman River", 17.8, 63.0, 500),
    ("Salween", 97.7, 16.6, 6000), ("Murray", 139.6, -35.2, 500), ("Tocantins", -49.3, -3.8, 11000),
    ("São Francisco", -37.0, -10.3, 2900), ("Orange", -17.0, -28.6, 360), ("Nelson", -93.0, 56.5, 2400),
]


@lru_cache(maxsize=1)
def natverk():
    return Natverk(FIL) if os.path.exists(FIL) else None


# ---------------------------------------------------------------- kalibrering

@lru_cache(maxsize=1)
def kalibrering():
    """Anpassar Flints lag och dalsidor mot de kända dammplatserna (log-log-regression)."""
    from floder import DAMMPLATSER
    nv = natverk()
    A, S, D = [], [], []
    for p in DAMMPLATSER:
        i, _ = nv.narmaste(p.lon, p.lat, p.Q)
        A.append(nv.upland[i]); S.append(p.lutning); D.append(p.dalsida)
    A, S, D = np.log(A), np.log(S), np.log(D)
    b1, a1 = np.polyfit(A, S, 1)          # log S = a1 + b1 log A
    b2, a2 = np.polyfit(S, D, 1)          # log dalsida = a2 + b2 log S
    return {"k": math.exp(a1), "theta": -b1, "c": math.exp(a2), "beta": b2}


@lru_cache(maxsize=1)
def namnkarta():
    """Flodnamn per sträcka. Från varje namngiven punkt får huvudfåran uppströms
    namnet (hög prioritet), och vägen nedströms till mynningen får namnet från
    den största floden (låg prioritet)."""
    from floder import DAMMPLATSER
    nv = natverk()
    punkter = [(p.flod, p.lon, p.lat, p.Q) for p in DAMMPLATSER] + FLER_FLODER
    start = [(nv.narmaste(lon, lat, Q)[0], namn, Q) for namn, lon, lat, Q in punkter]
    namn = {}
    prio = {}
    # nedströms: största floden vinner
    for i, n, Q in sorted(start, key=lambda x: -x[2]):
        j = i
        while j is not None:
            if j not in namn:
                namn[j], prio[j] = n, 1
            j = nv.index.get(int(nv.next_down[j]))
    # uppströms längs huvudfåran
    for i, n, _Q in start:
        j = i
        while True:
            if prio.get(j, 0) < 2:
                namn[j], prio[j] = n, 2
            if not nv.barn[j]:
                break
            j = max(nv.barn[j], key=lambda b: nv.upland[b])
    return namn


def uppskattad_lutning(upland_km2):
    k = kalibrering()
    return float(np.clip(k["k"] * upland_km2 ** -k["theta"], 1e-5, 0.02))


def uppskattad_dalsida(lutning):
    k = kalibrering()
    return float(np.clip(k["c"] * lutning ** k["beta"], 0.001, 0.5))


def uppskattad_avdunstning(lat):
    """Grov: ca 1,8 m/år vid ekvatorn, ca 0,5 m/år vid polcirkeln."""
    return 0.3 + 1.5 * math.cos(math.radians(lat)) ** 2


def flodnamn(i):
    """Namn på sträcka i, eller "biflod till X" om den rinner till en namngiven flod."""
    nv = natverk()
    namn = namnkarta()
    if i in namn:
        return namn[i]
    j = nv.index.get(int(nv.next_down[i]))
    while j is not None:
        if j in namn:
            return f"tributary of the {namn[j]}"
        j = nv.index.get(int(nv.next_down[j]))
    return "unnamed river"


# ---------------------------------------------------------------- magasinets form

def magasin_langs_floden(p_index, L_km, W_km):
    """Polygon som följer floden uppströms: bredd W vid dammen, smalnar av till 0.
    Returnerar (lon-lista, lat-lista) eller None om nätet saknas."""
    nv = natverk()
    if nv is None:
        return None
    lo, la, s = nv.uppstroms_bana(p_index, L_km)
    if len(lo) < 2:
        return None
    L_verklig = max(s[-1], 1e-6)
    halv = W_km / 2 * np.clip(1 - s / L_verklig, 0, 1)
    # normalriktning i varje punkt (km-koordinater)
    kx = np.cos(np.radians(la)) * KM_PER_GRAD
    dx = np.gradient(lo) * kx
    dy = np.gradient(la) * KM_PER_GRAD
    norm = np.hypot(dx, dy) + 1e-12
    nx, ny = -dy / norm, dx / norm
    vl = lo + nx * halv / kx, la + ny * halv / KM_PER_GRAD
    hl = lo - nx * halv / kx, la - ny * halv / KM_PER_GRAD
    plon = list(vl[0]) + list(hl[0][::-1]) + [vl[0][0]]
    plat = list(vl[1]) + list(hl[1][::-1]) + [vl[1][0]]
    return plon, plat
