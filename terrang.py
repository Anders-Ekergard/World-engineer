"""
terrang.py – använder ETOPO1-höjddata (hämtas med hamta_etopo.py).

1) Floddammar: "flood-fill" i terrängen (EXPERIMENTELL, används inte i appen än).
   Vattenytan hamnar på nivån  flodbotten + dammhöjd.  Alla celler som ligger
   lägre och hänger ihop med dammen på uppströmssidan dränks. Dammen är en
   rät linje tvärs över floden (vinkelrät mot uppströmsriktningen).
   OBS: ETOPO1 (1,85 km) är för grov för smala floddalar, och befintliga
   dammsjöar finns med som platt vattenyta, så botten under dem saknas.
   Kräver bättre data, t.ex. HydroSHEDS 15" (hydrologiskt korrigerad).

2) Hav: verklig hypsometri, alltså havsytans area A(d) och volym V(d) när
   havet har sjunkit d meter, samt den nya kustlinjen.

Finns ingen datafil används de förenklade modellerna i floder.py/bassanger.py.
"""

import math
import os
from functools import lru_cache

import numpy as np
from scipy import ndimage
import contourpy

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
R_JORD = 6.371e6    # m

# Havsbassänger: frö (en punkt mitt i havet) och vad som ska spärras bort.
#   Medelhavet: väster om Gibraltardammen, samt Dardanellerna -> Marmara/Svarta havet.
#   Röda havet: söder om Bab-el-Mandeb och Adenviken.
BASSANG = {
    "gibraltar": {"fro": (18.0, 35.0),
                  "sparr": lambda LON, LAT: (LON < -5.55) | ((LON > 26.0) & (LAT > 40.25))},
    "rodahavet": {"fro": (38.5, 20.5),
                  "sparr": lambda LON, LAT: (LAT < 12.6) | (LON > 43.6)},
}


@lru_cache(maxsize=None)
def ruta(namn):
    """Läser data/etopo_<namn>.npz. Returnerar (z, lon, lat, cellyta_m2) eller None."""
    fil = os.path.join(DATA, f"etopo_{namn}.npz")
    if not os.path.exists(fil):
        return None
    d = np.load(fil)
    z, lon, lat = d["z"].astype(np.float64), d["lon"], d["lat"]
    dlat = math.radians(abs(lat[1] - lat[0]))
    dlon = math.radians(abs(lon[1] - lon[0]))
    cell = (R_JORD ** 2) * dlat * dlon * np.cos(np.radians(lat))[:, None] * np.ones((1, len(lon)))
    return z, lon, lat, cell


def har_data(namn):
    return ruta(namn) is not None


# ---------------------------------------------------------------- konturer

def konturer(mask, lon, lat, max_punkter=4000):
    """Ytterkonturer av en sann/falsk-mask som (lon-lista, lat-lista) med None mellan ringar."""
    gen = contourpy.contour_generator(x=lon, y=lat, z=mask.astype(np.float64),
                                      line_type=contourpy.LineType.Separate)
    linjer = gen.lines(0.5)
    totalt = sum(len(l) for l in linjer) or 1
    steg = max(1, totalt // max_punkter)
    lo, la = [], []
    for l in linjer:
        if len(l) < 4:
            continue
        l = l[::steg] if len(l) > 3 * steg else l
        lo += list(l[:, 0]) + [l[0, 0], None]
        la += list(l[:, 1]) + [l[0, 1], None]
    return lo, la


# ---------------------------------------------------------------- floddammar

def _dammcell(z, lon, lat, plats, radie=3):
    """Närmaste cell till dammplatsen, flyttad till lägsta punkten inom `radie` celler
    (koordinaterna ligger inte alltid exakt i flodfåran)."""
    i = int(np.argmin(abs(lat - plats.lat)))
    j = int(np.argmin(abs(lon - plats.lon)))
    i0, j0 = max(i - radie, 0), max(j - radie, 0)
    bit = z[i0:i + radie + 1, j0:j + radie + 1]
    di, dj = np.unravel_index(np.argmin(bit), bit.shape)
    return i0 + di, j0 + dj


@lru_cache(maxsize=512)
def magasin_dem(plats_id, H):
    """Flood-fill bakom en damm med höjd H (m). None om data saknas."""
    from floder import PLATS
    r = ruta(plats_id)
    if r is None:
        return None
    z, lon, lat, cell = r
    p = PLATS[plats_id]
    i, j = _dammcell(z, lon, lat, p)
    botten = z[i, j]
    niva = botten + H

    # avstånd (km) från dammen, projicerat på uppströmsriktningen
    v = math.radians(p.riktning)
    ost = (lon[None, :] - lon[j]) * 111.0 * math.cos(math.radians(lat[i]))
    nord = (lat[:, None] - lat[i]) * 111.0
    uppstrom = ost * math.sin(v) + nord * math.cos(v)
    halvcell = 0.5 * 111.0 * abs(lat[1] - lat[0])

    kandidat = (z < niva) & (uppstrom > -halvcell)
    etiketter, _ = ndimage.label(kandidat)          # 4-grannskap: inga läckor snett
    if etiketter[i, j] == 0:
        return None
    region = etiketter == etiketter[i, j]

    djup = np.where(region, niva - z, 0.0)
    A = float(cell[region].sum())
    V = float((djup * cell).sum())
    kant = bool(region[0, :].any() or region[-1, :].any() or region[:, 0].any() or region[:, -1].any())
    ii, jj = np.nonzero(region)
    langd = float(uppstrom[ii, jj].max()) if len(ii) else 0.0
    lo, la = konturer(region, lon, lat)
    return {
        "yta_km2": A / 1e6,
        "volym_km3": V / 1e9,
        "langd_km": langd,
        "botten_m": float(botten),
        "niva_m": float(niva),
        "nar_kanten": kant,
        "kontur": (lo, la),
        "dammpunkt": (float(lon[j]), float(lat[i])),
    }


# ---------------------------------------------------------------- hav

@lru_cache(maxsize=None)
def bassang_mask(hav_id):
    r = ruta(hav_id)
    if r is None:
        return None
    z, lon, lat, _ = r
    LON, LAT = np.meshgrid(lon, lat)
    b = BASSANG[hav_id]
    hav = (z < 0) & ~b["sparr"](LON, LAT)
    etiketter, _ = ndimage.label(hav)
    i = int(np.argmin(abs(lat - b["fro"][1])))
    j = int(np.argmin(abs(lon - b["fro"][0])))
    return etiketter == etiketter[i, j]


def hav_for_punkt(lon, lat, radie=6):
    """Vilket innanhav en flodmynning ligger vid: "gibraltar" (Medelhavet),
    "rodahavet", "svarta" (Svarta havet, rinner vidare till Medelhavet) eller None."""
    if 27.0 <= lon <= 42.0 and 40.9 <= lat <= 47.5:
        return "svarta"
    for hav_id in BASSANG:
        r = ruta(hav_id)
        mask = bassang_mask(hav_id)
        if r is None:
            continue
        _, lo, la, _ = r
        if not (lo[0] <= lon <= lo[-1] and la[0] <= lat <= la[-1]):
            continue
        i = int(np.argmin(abs(la - lat)))
        j = int(np.argmin(abs(lo - lon)))
        if mask[max(i - radie, 0):i + radie + 1, max(j - radie, 0):j + radie + 1].any():
            return hav_id
    return None


@lru_cache(maxsize=None)
def hypsometri(hav_id, steg=2.0):
    """Tabell: sänkning d (m) -> yta A (m2) och kvarvarande volym V (m3)."""
    r = ruta(hav_id)
    mask = bassang_mask(hav_id)
    if mask is None:
        return None
    z, _, _, cell = r
    djup = -z[mask]
    area = cell[mask]
    ordning = np.argsort(djup)
    djup, area = djup[ordning], area[ordning]
    # summor från djupaste änden: A(d) = sum(area där djup > d), V(d) = sum(area*(djup-d))
    A_kum = np.cumsum(area[::-1])[::-1]
    AD_kum = np.cumsum((area * djup)[::-1])[::-1]
    d = np.arange(0.0, djup.max() + steg, steg)
    k = np.searchsorted(djup, d, side="right")
    A = np.where(k < len(djup), A_kum[np.minimum(k, len(djup) - 1)], 0.0)
    AD = np.where(k < len(djup), AD_kum[np.minimum(k, len(djup) - 1)], 0.0)
    V = AD - d * A
    return d, A, V


# ---------------------------------------------------------------- sänkor under havsytan
#
# En sjö i en sänka fylls från den lägsta punkten. Vid nivån h är sjön det
# sammanhängande området med z < h som innehåller den lägsta punkten (andra gropar
# i rutan räknas först när vattnet når dem). Havet i rutan (punkterna i hav_fro, och
# allt under 0 m som når rutans kant) spärras bort.

SANKOR = {
    "qattara": {"hav_fro": []},
    # Jordansänkan når under havsytan ända till Gennesaretsjön, därför inte kantregeln här
    "dodahavet": {"hav_fro": [(34.95, 29.45), (34.82, 32.9)], "kant_ar_hav": False},  # Aqaba, Medelhavet
    "saharahavet": {"hav_fro": [(10.5, 34.0)]},    # Gabèsbukten
    "danakil": {"hav_fro": [(40.9, 15.25)]},       # Röda havet
    "assal": {"hav_fro": [(42.62, 11.52)]},        # Ghoubbet
}


@lru_cache(maxsize=None)
def _sanka_grund(sanka_id):
    """(z, lon, lat, cell, havsmask, lägsta cell) eller None om data saknas."""
    r = ruta(sanka_id)
    if r is None:
        return None
    z, lon, lat, cell = r
    # hav = områden under 0 m som hänger ihop med hav_fro eller når rutans kant
    etiketter, _ = ndimage.label(z < 0)
    kant = set()
    if SANKOR[sanka_id].get("kant_ar_hav", True):
        kant = set(np.concatenate([etiketter[0], etiketter[-1], etiketter[:, 0], etiketter[:, -1]]))
    for fro in SANKOR[sanka_id]["hav_fro"]:
        kant.add(etiketter[int(np.argmin(abs(lat - fro[1]))), int(np.argmin(abs(lon - fro[0])))])
    kant.discard(0)
    hav = np.isin(etiketter, list(kant))
    lagst = np.unravel_index(np.argmin(np.where(hav, np.inf, z)), z.shape)
    return z, lon, lat, cell, hav, lagst


def sjo_mask(sanka_id, niva):
    g = _sanka_grund(sanka_id)
    if g is None:
        return None
    z, _, _, _, hav, lagst = g
    etiketter, _ = ndimage.label((z < niva) & ~hav)
    if etiketter[lagst] == 0:
        return np.zeros(z.shape, dtype=bool)
    return etiketter == etiketter[lagst]


@lru_cache(maxsize=None)
def sanka_hypsometri(sanka_id, steg=1.0):
    """Tabell: sjönivå h (m, stigande från lägsta punkten till 0) -> yta A (m2), volym V (m3)."""
    g = _sanka_grund(sanka_id)
    if g is None:
        return None
    z, _, _, cell, _, lagst = g
    h = np.arange(np.floor(z[lagst]) + steg, 0.0 + steg / 2, steg)
    A, V = np.zeros(len(h)), np.zeros(len(h))
    for k, niva in enumerate(h):
        m = sjo_mask(sanka_id, niva)
        A[k] = cell[m].sum()
        V[k] = ((niva - z[m]) * cell[m]).sum()
    return np.concatenate([[z[lagst]], h]), np.concatenate([[0.0], A]), np.concatenate([[0.0], V])


def sanka_lagsta(sanka_id):
    """(lon, lat, z) för sänkans lägsta punkt."""
    g = _sanka_grund(sanka_id)
    if g is None:
        return None
    z, lon, lat, _, _, (i, j) = g
    return float(lon[j]), float(lat[i]), float(z[i, j])


@lru_cache(maxsize=512)
def ny_sjo(sanka_id, niva):
    """Sjöns strandlinje vid nivån `niva` (heltal, m) som (lon-lista, lat-lista)."""
    g = _sanka_grund(sanka_id)
    if g is None:
        return None
    m = sjo_mask(sanka_id, niva)
    if not m.any():
        return None
    return konturer(m, g[1], g[2], max_punkter=3000)


@lru_cache(maxsize=256)
def ny_kust(hav_id, sankning):
    """Ny kustlinje och torrlagd havsbotten när havet sjunkit `sankning` meter."""
    r = ruta(hav_id)
    mask = bassang_mask(hav_id)
    if mask is None or sankning <= 0:
        return None
    z, lon, lat, _ = r
    glesning = max(1, round((8 / 60) / abs(lon[1] - lon[0])))   # ca 8 bågminuter mellan punkter
    kvar = mask & (-z > sankning)
    torr = mask & ~kvar
    lo, la = konturer(kvar, lon, lat, max_punkter=6000)
    # torrlagd botten som glesa punkter (för att färga den som land på kartan)
    ii, jj = np.nonzero(torr[::glesning, ::glesning])
    return {
        "kust": (lo, la),
        "torr_lon": lon[::glesning][jj].tolist(),
        "torr_lat": lat[::glesning][ii].tolist(),
    }
