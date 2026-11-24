"""
anlaggning.py – en damm i spelet: designval, byggstatus, komponenter och magasin.

En anläggning är en vanlig dict (så att hela spelet kan sparas som JSON).
"""

import math

from floder import hamta_plats, magasin
from spel import komponenter as K
from spel.ekonomi import kalkyl
from spel.minispel import gjutning
from spel.geografi import region
from spel.hydrologi import dimensionerande_flode

STANDARD_DESIGN = {"typ": "betong", "H": 50.0, "utskov_T": 1000, "seismik_g": 0.15,
                   "n_turbiner": 4, "utbyggnad": 1.3, "overvakning": 1, "reservkraft": False}


def antal_luckor(Q_utskov: float) -> int:
    return int(min(8, max(2, math.ceil(Q_utskov / 8000))))


def forhandskalkyl(plats_id: str, design: dict) -> dict:
    """Kostnad, byggtid och nyckeltal innan man bestämmer sig."""
    p = hamta_plats(plats_id)
    Q_utskov = dimensionerande_flode(plats_id, design["utskov_T"])
    k = kalkyl(p, design, Q_utskov)
    m = magasin(p, design["H"])
    return {**k, "Q_utskov": Q_utskov, "yta_km2": m["yta_km2"], "volym_km3": m["volym_km3"],
            "effekt_MW_medel": m["effekt_MW"], "region": region(p.lon, p.lat)}


def ny_anlaggning(plats_id: str, design: dict, manad: int, rng, standardgjutning=False) -> dict:
    """standardgjutning=True: en betongdamm som byggs utan gjutningsminispelet får
    standardplanen (1,5 m lyft, 250 kg/m3, ingen kylning) vid platsens årsmedeltemperatur."""
    p = hamta_plats(plats_id)
    if standardgjutning and design["typ"] == "betong" and not design.get("gjutning"):
        T_ar = gjutning.lufttemperatur(p.lat, 0)[1]
        design = {**design, "gjutning": {**gjutning.STANDARD, "T_luft": T_ar, "T_ar": T_ar}}
    f = forhandskalkyl(plats_id, design)
    m = magasin(p, design["H"])
    a = {
        "id": plats_id, "namn": p.namn, "flod": p.flod, "lon": p.lon, "lat": p.lat,
        "region": f["region"], **{k: design[k] for k in STANDARD_DESIGN},
        "Q_utskov": f["Q_utskov"], "capex": f["total"], "MW": f["MW"],
        "status": "bygge", "byggstart": manad, "bygg_tot": f["byggtid_man"],
        "bygg_kvar": float(f["byggtid_man"]), "fordrivna": f["fordrivna"],
        "komp": K.skapa(design["typ"], antal_luckor(f["Q_utskov"]), design["n_turbiner"]),
        "avstangda": [], "underhall": 1, "drift": "normal",
        # dolda egenskaper som spelaren kan upptäcka
        "asr": design["typ"] == "betong" and bool(rng.uniform() < 0.15), "asr_kand": False,
        "kalk": float(rng.uniform(0.2, 1.0)),          # hur hårt vattnet är
        "V_max": m["volym_km3"] * 1e9, "V": 0.0, "sediment": 0.0,
        "senast": {}, "energi_MWh": 0.0, "haveri": None,
        "aggressiv": 0.0, "underhall_extra": 0.0, "minispel": {k: design[k] for k in ("labb", "gjutning")
                                                             if design.get(k)},
    }
    # minispelens utfall ersätter de slumpade dolda egenskaperna
    e = f["minispel"]
    for k in ("kalk", "aggressiv", "asr", "asr_kand", "underhall_extra"):
        if k in e:
            a[k] = e[k]
    if "sektion_t" in e:
        for namn in ("sektion_v", "sektion_m", "sektion_h"):
            a["komp"][namn]["t"] = e["sektion_t"]
    return a


# Verkliga dammar som spelaren tar över vid start: (id, byggår, typ, utskov_T, problem)
BEFINTLIGA = [
    ("yangtze", 2006, "betong", 1000, {}),
    ("colorado", 1936, "betong", 1000, {"utskov": 0.6}),               # Glen Canyon-lik kavitation
    ("nilen", 1970, "fyllning", 1000, {}),
    ("blanilen", 2022, "betong", 1000, {}),
    ("parana", 1984, "betong", 1000, {}),
    ("volga", 1961, "fyllning", 1000, {}),
    ("donau", 1972, "betong", 1000, {}),
    ("jenisej", 1972, "betong", 1000, {}),
    ("indus", 1976, "fyllning", 1000, {"sediment": 0.35}),               # Tarbela slammar igen
    ("zambezi", 1959, "betong", 1000, {"utskov": 0.35, "fundament": 0.5}),  # Karibas erosionsgrop
    ("columbia", 1942, "betong", 1000, {}),
    ("lulealv", 1951, "fyllning", 1000, {}),
]


def befintlig(plats_id: str, byggar: int, typ: str, T: int, problem: dict, startar: int, rng) -> dict:
    p = hamta_plats(plats_id)
    design = {**STANDARD_DESIGN, "typ": typ, "H": p.H_standard, "utskov_T": T,
              "n_turbiner": 6, "overvakning": 1, "reservkraft": byggar > 1980}
    a = ny_anlaggning(plats_id, design, 0, rng)
    alder = startar - byggar
    a.update(status="drift", bygg_kvar=0.0, byggstart=-(alder * 12), V=0.8 * a["V_max"])
    for namn, c in a["komp"].items():
        s = K.slag(namn)
        slit = {"sektion": 0.003, "karna": 0.002, "fundament": 0.006, "utskov": 0.004,
                "lucka": 0.008, "turbin": 0.006}[s]
        c["t"] = float(max(0.15, 1 - alder * slit * rng.uniform(0.5, 1.5)))
        if s in problem:
            c["t"] = min(c["t"], problem[s])
    if "sediment" in problem:
        a["sediment"] = problem["sediment"] * a["V_max"]
    return a
