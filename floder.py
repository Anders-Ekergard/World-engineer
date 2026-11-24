"""
floder.py – dammplatser i världens stora floder och en enkel magasinsmodell.

Modellen (utan höjddata):
  Dalen antas vara V-formad och floden har konstant lutning.
  En damm med höjd H dämmer då upp vatten så här långt uppströms:
      L = H / lutning                      (magasinets längd)
  och dalen är så här bred vid dammen:
      W = 2 * H / dalsida                  (dalsidornas lutning)
  Magasinet blir en "pyramid" (triangel i plan, triangel i tvärsnitt):
      A = L * W / 2                        (yta)
      V = A * H / 3                        (volym)
  Parametrarna är kalibrerade så att kända dammar (De tre ravinerna,
  Hoover, Assuan, Itaipu ...) får ungefär rätt yta och volym.

Vattenkraft:  P = rho * g * Q * H * eta
"""

import math
from dataclasses import dataclass
from functools import lru_cache

RHO = 1000.0        # vattnets densitet, kg/m3
G = 9.81            # tyngdacceleration, m/s2
ETA = 0.90          # turbinernas verkningsgrad
SEK_PER_AR = 3.156e7
CO2_KOL = 0.9       # Mt CO2 per TWh kolkraft som ersätts


@dataclass
class Dammplats:
    id: str
    flod: str
    namn: str            # namn på dammen (befintlig eller påhittad plats)
    lon: float
    lat: float
    Q: float             # medelflöde, m3/s
    lutning: float       # flodbottens lutning, m/m
    dalsida: float       # dalsidornas lutning, m/m (litet värde = flack, bred dal)
    befolkning: float    # invånare per km2 i dalen som dränks
    riktning: float      # kompassriktning uppströms, grader (0 = norr, 90 = öster)
    avdunstning: float   # avdunstning från fri vattenyta, m/år
    H_standard: float    # förvald dammhöjd, m
    H_max: float         # största tillåtna dammhöjd i simulatorn, m
    finns: bool          # True = dammen finns i verkligheten
    uppskattad: bool = False   # True = parametrarna är uppskattade (vald punkt i flodnätet)
    punkt: int | None = None   # punktindex i flodnätet (natverk.py), om det finns


DAMMPLATSER = [
    Dammplats("yangtze", "Yangtze", "Three Gorges", 111.00, 30.82,
              14300, 1.8e-4, 0.060, 1200, 270, 0.8, 110, 200, True),
    Dammplats("colorado", "Colorado", "Hoover", -114.74, 36.02,
              640, 1.0e-3, 0.050, 5, 80, 2.0, 180, 250, True),
    Dammplats("nilen", "Nile", "Aswan", 32.88, 23.97,
              2830, 1.5e-4, 0.007, 20, 180, 2.0, 75, 120, True),
    Dammplats("blanilen", "Blue Nile", "GERD (Ethiopia)", 35.09, 11.21,
              1550, 5.4e-4, 0.0175, 10, 120, 1.8, 133, 180, True),
    Dammplats("parana", "Paraná", "Itaipu", -54.59, -25.41,
              12000, 7.0e-4, 0.015, 30, 0, 1.2, 118, 160, True),
    Dammplats("volga", "Volga", "Volgograd", 44.68, 48.80,
              8000, 5.0e-5, 0.0047, 30, 30, 0.8, 27, 60, True),
    Dammplats("donau", "Danube", "Iron Gate", 22.53, 44.67,
              5500, 2.1e-4, 0.050, 50, 270, 0.8, 27, 80, True),
    Dammplats("jenisej", "Yenisei", "Krasnoyarsk", 92.35, 55.93,
              2800, 2.6e-4, 0.020, 5, 180, 0.5, 100, 150, True),
    Dammplats("indus", "Indus", "Tarbela", 72.69, 34.09,
              2400, 1.7e-3, 0.044, 380, 0, 1.5, 136, 200, True),
    Dammplats("zambezi", "Zambezi", "Kariba", 28.76, -16.52,
              1400, 4.5e-4, 0.004, 10, 240, 1.7, 100, 140, True),
    Dammplats("columbia", "Columbia", "Grand Coulee", -118.98, 47.96,
              3100, 4.1e-4, 0.074, 5, 20, 1.0, 100, 160, True),
    Dammplats("lulealv", "Lule River", "Harsprånget", 19.87, 66.93,
              500, 1.5e-3, 0.050, 1, 300, 0.3, 107, 150, True),
    Dammplats("kongo", "Congo", "Grand Inga (planned)", 13.60, -5.50,
              41000, 1.0e-3, 0.100, 50, 60, 1.2, 150, 200, False),
    Dammplats("tsangpo", "Yarlung Tsangpo", "Medog (planned)", 95.00, 29.50,
              4400, 5.0e-3, 0.500, 5, 270, 0.5, 200, 300, False),
    Dammplats("mekong", "Mekong", "Pa Mong (planned)", 102.20, 18.00,
              4500, 2.0e-4, 0.030, 100, 330, 1.2, 80, 120, False),
    Dammplats("amazonas", "Amazon", "Óbidos (hypothetical)", -55.50, -1.90,
              180000, 2.0e-5, 0.001, 5, 270, 1.0, 30, 60, False),
    Dammplats("mississippi", "Mississippi", "Vicksburg (hypothetical)", -90.90, 32.30,
              17000, 6.0e-5, 0.003, 40, 0, 1.2, 25, 50, False),
]

PLATS = {p.id: p for p in DAMMPLATSER}


def hamta_plats(id_: str) -> Dammplats | None:
    """Kända dammplatser finns i PLATS. Id "p<nummer>" = valfri punkt i flodnätet
    (HydroRIVERS), där parametrarna uppskattas."""
    if id_ in PLATS:
        return PLATS[id_]
    if id_ and id_.startswith("p") and id_[1:].isdigit():
        return _plats_i_natet(int(id_[1:]))
    return None


@lru_cache(maxsize=1024)
def _plats_i_natet(p: int) -> Dammplats | None:
    import natverk as nv_mod
    nv = nv_mod.natverk()
    if nv is None or not 0 <= p < len(nv.lon):
        return None
    i = int(nv.punkt_strak[p])
    lon, lat = float(nv.lon[p]), float(nv.lat[p])
    lutning = nv_mod.uppskattad_lutning(nv.upland[i])
    ns = "N" if lat >= 0 else "S"
    ow = "E" if lon >= 0 else "W"
    return Dammplats(
        id=f"p{p}", flod=nv_mod.flodnamn(i),
        namn=f"New dam {abs(lat):.2f}°{ns} {abs(lon):.2f}°{ow}",
        lon=lon, lat=lat, Q=float(nv.Q[i]), lutning=lutning,
        dalsida=nv_mod.uppskattad_dalsida(lutning),
        befolkning=30.0,                      # grovt världsgenomsnitt, landsbygd
        riktning=0.0,                         # används inte: magasinet följer floden
        avdunstning=nv_mod.uppskattad_avdunstning(lat),
        H_standard=50, H_max=250, finns=False, uppskattad=True, punkt=p,
    )


def _punkt_for(plats: Dammplats):
    """Punktindex i flodnätet för en dammplats (kända platser: närmaste punkt)."""
    if plats.punkt is not None:
        return plats.punkt
    import natverk as nv_mod
    nv = nv_mod.natverk()
    if nv is None:
        return None
    plats.punkt = nv.narmaste(plats.lon, plats.lat, plats.Q)[1]   # spara, sökningen är långsam
    return plats.punkt


def sedimentfangst(uppehallstid_ar: float) -> float:
    """Andel av flodens sediment som fastnar i magasinet (Brunes kurva, i formen
    från Vörösmarty m.fl. 1997):  TE = 1 - 0,05 / sqrt(uppehållstid i år)."""
    if uppehallstid_ar <= 0:
        return 0.0
    return max(0.0, 1.0 - 0.05 / math.sqrt(uppehallstid_ar))


def magasin(plats: Dammplats, H: float, Q: float | None = None,
            H_eff: float | None = None) -> dict:
    """Beräknar magasin och konsekvenser för en damm med höjd H (m).
    Q     = flöde in till dammen (mindre än plats.Q om dammar uppströms avdunstar vatten)
    H_eff = fallhöjd (mindre än H om en damm nedströms dämmer upp vattnet vid dammfoten)"""
    Q = plats.Q if Q is None else Q
    H_eff = H if H_eff is None else H_eff
    L = H / plats.lutning                   # m
    W = 2 * H / plats.dalsida               # m
    A = L * W / 2                           # m2
    V = A * H / 3                           # m3

    P = RHO * G * Q * H_eff * ETA           # W (medeleffekt)
    energi_TWh = P * 8760 / 1e12            # TWh per år
    fyllnad_ar = V / (Q * SEK_PER_AR)
    avdunst_m3s = A * plats.avdunstning / SEK_PER_AR

    return {
        "langd_km": L / 1e3,
        "bredd_km": W / 1e3,
        "yta_km2": A / 1e6,
        "volym_km3": V / 1e9,
        "effekt_MW": P / 1e6,
        "energi_TWh": energi_TWh,
        "co2_Mt": energi_TWh * CO2_KOL,
        "fyllnad_ar": fyllnad_ar,
        "avdunstning_m3s": avdunst_m3s,
        "flodforlust_procent": 100 * avdunst_m3s / Q,
        "fordrivna": A / 1e6 * plats.befolkning,
        "sediment_fangst": sedimentfangst(fyllnad_ar),   # fyllnadstid = uppehållstid V/Q
        "Q": Q,
        "H_eff": H_eff,
    }


def magasin_polygon(plats: Dammplats, H: float):
    """Magasinets form på kartan: bred vid dammen, spetsig längst uppströms.
    Med flodnätet följer den verkliga floden, annars en rak triangel.
    Returnerar (lon-lista, lat-lista)."""
    L = H / plats.lutning / 1e3             # km
    W = 2 * H / plats.dalsida / 1e3         # km
    p = _punkt_for(plats)
    if p is not None:
        from natverk import magasin_langs_floden
        poly = magasin_langs_floden(p, L, W)
        if poly is not None:
            return poly
    km_per_grad_lat = 111.0
    km_per_grad_lon = 111.0 * math.cos(math.radians(plats.lat))

    v = math.radians(plats.riktning)
    # enhetsvektor uppströms (öster, norr) och vinkelrät mot den
    ux, uy = math.sin(v), math.cos(v)
    px, py = -uy, ux

    def punkt(x_km, y_km):
        return (plats.lon + x_km / km_per_grad_lon,
                plats.lat + y_km / km_per_grad_lat)

    hörn = [punkt(px * W / 2, py * W / 2),
            punkt(ux * L, uy * L),
            punkt(-px * W / 2, -py * W / 2)]
    hörn.append(hörn[0])                    # stäng polygonen
    return [h[0] for h in hörn], [h[1] for h in hörn]
