"""
geografi.py – regioner, säsonger och seismiska zoner (inbyggda tabeller, ingen nedladdning).
"""

import math


# ---------------------------------------------------------------- regioner

def region(lon: float, lat: float) -> str:
    """Grov världsdelsindelning för acceptansen."""
    if lat > 35 and -25 <= lon <= 45:
        return "Europa"
    if 12 <= lat <= 42 and 25 <= lon <= 63:
        return "Mellanöstern"
    if -37 <= lat <= 37 and -20 <= lon <= 52:
        return "Afrika"
    if lon < -30:
        return "Nordamerika" if lat > 12 else "Sydamerika"
    if lat < -10 and lon > 110:
        return "Oceanien"
    return "Asien"


REGIONER = ["Europa", "Mellanöstern", "Afrika", "Nordamerika", "Sydamerika", "Asien", "Oceanien"]

# Regionernas namn för spelaren (nycklarna ovan används internt och i sparfilerna)
REGION_NAMN = {"Europa": "Europe", "Mellanöstern": "Middle East", "Afrika": "Africa",
               "Nordamerika": "North America", "Sydamerika": "South America", "Asien": "Asia",
               "Oceanien": "Oceania"}


def region_namn(r: str) -> str:
    return REGION_NAMN.get(r, r)


# ---------------------------------------------------------------- säsonger

def sasong(lon: float, lat: float, amplitud_faktor: float = 1.0) -> list:
    """12 månadsfaktorer (medel 1) för flodens flöde.
    Grova regler: monsun-Asien toppar i juli–augusti, snösmältning i maj–juni
    på höga breddgrader, tropikerna toppar i regnperioden osv."""
    if 60 <= lon <= 125 and 5 <= lat <= 35:
        topp, amp = 7.5, 0.85          # monsun (juli–augusti)
    elif lat > 45:
        topp, amp = 5.5, 0.7           # snösmältning
    elif lat > 25:
        topp, amp = 3.0, 0.4           # vinterregn/vårflod
    elif lat > 0:
        topp, amp = 8.5, 0.75          # norra tropikerna (t.ex. Nilen, Niger)
    elif lat > -25:
        topp, amp = 2.5, 0.6           # södra tropikerna
    else:
        topp, amp = 6.5, 0.4           # södra tempererade
    amp = min(amp * amplitud_faktor, 0.95)
    # månad 0 = januari
    return [1.0 + amp * math.cos(2 * math.pi * (m - topp) / 12) for m in range(12)]


def toppmanad(lon: float, lat: float) -> int:
    s = sasong(lon, lat)
    return max(range(12), key=lambda m: s[m])


# ---------------------------------------------------------------- jordbävningar
#
# Zoner: (namn, lon0, lon1, lat0, lat1, antal skalv M>=5,5 per år i zonen, största magnitud)
# Grova värden från global seismicitet; avsikten är rätt storleksordning, inte en riskkarta.

ZONER = [
    ("Himalaya", 70, 100, 25, 38, 3.0, 8.6),
    ("Inland China", 95, 122, 22, 42, 2.0, 8.0),
    ("Central Asia", 60, 90, 35, 46, 2.0, 8.0),
    ("Japan", 129, 146, 30, 46, 8.0, 9.1),
    ("Indonesia", 95, 128, -11, 6, 10.0, 9.2),
    ("Philippines and Taiwan", 117, 127, 5, 25, 4.0, 8.5),
    ("Andes", -80, -65, -45, 10, 6.0, 9.4),
    ("Mexico and Central America", -110, -77, 7, 22, 4.0, 8.2),
    ("California and the Cascades", -125, -114, 32, 50, 1.5, 9.0),
    ("Alaska", -180, -140, 50, 65, 4.0, 9.2),
    ("East African Rift", 28, 44, -15, 16, 1.0, 7.5),
    ("Mediterranean, Anatolia and Iran", -10, 62, 30, 45, 6.0, 8.0),
    ("New Zealand", 165, 180, -48, -34, 1.5, 8.2),
    ("Caucasus", 38, 50, 39, 45, 0.8, 7.2),
]
BAKGRUND_PER_AR = 0.002   # chans per damm och år för ett skalv M5,5 inom 30 km utanför zonerna
M_MIN = 5.5


def zon_for(lon: float, lat: float):
    for z in ZONER:
        if z[1] <= lon <= z[2] and z[3] <= lat <= z[4]:
            return z
    return None


def pga(M: float, R_km: float) -> float:
    """Markacceleration (andel av g) enligt Campbell (1981):
    ln PGA = -4,141 + 0,868 M - 1,09 ln(R + 0,0606 e^(0,7 M))"""
    return math.exp(-4.141 + 0.868 * M - 1.09 * math.log(R_km + 0.0606 * math.exp(0.7 * M)))


def avstand_km(lon1, lat1, lon2, lat2) -> float:
    dx = (lon1 - lon2) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 111.0
    return math.hypot(dx, dy)
