"""
labb.py – Kemilabbet: vattenprov och ASR-test innan dammen byggs.

A. Langeliers mättnadsindex (LSI) säger om vattnet vill fälla ut eller lösa kalcit:
     LSI = pH - pHs
     pHs = (9,3 + A + B) - (C + D)
     A = (log10 TDS - 1) / 10                    TDS i mg/L
     B = -13,12 * log10(T + 273) + 34,55         T i °C
     C = log10(Ca2+ som CaCO3) - 0,4             mg/L
     D = log10(alkalinitet som CaCO3)            mg/L
   LSI > 0: övermättat -> kalcit fälls ut och sätter igen dammens dräner:
            Ca2+ + 2 HCO3-  ->  CaCO3(s) + CO2 + H2O
   LSI < 0: undermättat ("aggressivt") vatten löser kalciumhydroxid och kalk ur betongen.

B. Alkali–kiselsyrareaktion (ASR): amorf eller mikrokristallin kiselsyra i ballasten
   reagerar med alkali (Na+, K+, OH-) i cementens porvätska och bildar en gel som sväller.
   Accelererat bruksprismatest (som ASTM C1260): prismor i 1 M NaOH vid 80 °C i 14 dygn.
     expansion < 0,10 %   ofarlig
     0,10–0,20 %          potentiellt reaktiv
     > 0,20 %             reaktiv
   Motåtgärder: lågalkaliskt cement, eller flygaska som binder alkali (puzzolanreaktion).

Provdata dras deterministiskt ur (frö, plats), så samma plats ger alltid samma prov.
"""

import math
import zlib

import numpy as np

# (namn, beskrivning, expansion efter 14 dygn [min, max] i %, prisfaktor)
BERGARTER = [
    ("Granite", "coarse-grained quartz, feldspar and mica", (0.03, 0.08), 1.00),
    ("Basalt", "fine-grained, with a little volcanic glass", (0.06, 0.13), 1.05),
    ("Dolomitic limestone", "carbonate rock with a little clay", (0.04, 0.09), 0.95),
    ("Quartzite", "microcrystalline and deformed quartz", (0.12, 0.22), 0.90),
    ("Flint gravel", "rounded gravel with flint, chalcedony and opal", (0.25, 0.45), 0.70),
]
DRANERING = {
    "standard": ("Standard drains", 1.0, 0.0, 0.0),
    "spolbar": ("Flushable drains with a larger diameter", 0.5, 0.005, 0.0),
    "syra": ("Acid-treatment program (dissolves calcite)", 0.1, 0.0, 0.002),
}   # (text, faktor på igensättning, engångskostnad som andel av dammen, extra underhåll per år)
YTSKYDD_KOSTNAD = 0.01
LAGALKALI_KOSTNAD = 0.03
ASR_GRANS = 0.15          # så här mycket expansion räcker för skadlig ASR utan motåtgärd


def _rng(fro: int, plats_id: str):
    return np.random.default_rng([int(fro), zlib.crc32(plats_id.encode("utf-8"))])


def prov(fro: int, plats_id: str, lat: float) -> dict:
    """Vattenprov och tre stenbrott för en plats."""
    rng = _rng(fro, plats_id)
    h = rng.uniform()                                   # hur hårt vattnet är (0–1)
    vatten = {
        "pH": round(float(np.clip(6.8 + 1.8 * (0.25 + 0.75 * h) * rng.uniform(0.85, 1.1), 6.8, 8.6)), 2),
        "T": round(float(np.clip(25 - 0.3 * abs(lat) + rng.uniform(-3, 3), 4, 30)), 1),
        "Ca": round(float(np.clip(10 + 290 * h ** 1.5 * rng.uniform(0.7, 1.1), 10, 300))),
        "alk": round(float(np.clip(20 + 230 * h * rng.uniform(0.8, 1.1), 20, 250))),
        "TDS": round(float(np.clip(50 + 550 * h * rng.uniform(0.8, 1.2), 50, 600))),
    }
    # tre olika stenbrott, alltid minst ett billigt och reaktivt och minst ett säkert
    reaktiva = [b for b in BERGARTER if b[2][0] >= 0.12]
    sakra = [b for b in BERGARTER if b[2][1] < 0.12]
    val = [reaktiva[int(rng.integers(len(reaktiva)))], sakra[int(rng.integers(len(sakra)))]]
    ovriga = [b for b in BERGARTER if b not in val]
    val.append(ovriga[int(rng.integers(len(ovriga)))])
    rng.shuffle(val)
    brott = []
    for namn, beskr, (lo, hi), pris in val:
        km = round(float(rng.uniform(5, 40) if pris < 0.95 else rng.uniform(20, 150)))
        brott.append({"namn": namn, "beskrivning": beskr, "E14": round(float(rng.uniform(lo, hi)), 3),
                      "pris": pris, "km": km})
    return {"vatten": vatten, "brott": brott}


def lsi(pH: float, T: float, Ca: float, alk: float, TDS: float) -> dict:
    A = (math.log10(TDS) - 1) / 10
    B = -13.12 * math.log10(T + 273) + 34.55
    C = math.log10(Ca) - 0.4
    D = math.log10(alk)
    pHs = (9.3 + A + B) - (C + D)
    return {"A": A, "B": B, "C": C, "D": D, "pHs": pHs, "LSI": pH - pHs}


def tolka_lsi(L: float) -> str:
    if L > 0.5:
        return "Highly supersaturated: calcite precipitates rapidly in the drains."
    if L > 0:
        return "Slightly supersaturated: calcite precipitates slowly."
    if L > -0.5:
        return "Near equilibrium: neither precipitation nor attack is significant."
    return "Aggressive: the water dissolves lime and calcium hydroxide from the concrete."


def expansionskurva(E14: float, dagar=None):
    """Expansion (%) mot tid: snabb början som planar ut, lika med E14 efter 14 dygn."""
    t = np.linspace(0, 14, 57) if dagar is None else np.asarray(dagar)
    tau = 6.0
    return t, E14 * (1 - np.exp(-t / tau)) / (1 - math.exp(-14 / tau))


def klass(E14: float) -> str:
    if E14 < 0.10:
        return "harmless"
    return "potentially reactive" if E14 <= 0.20 else "reactive"


def utvardera(val: dict, betong: bool, flygaska: float) -> dict:
    """val: LSI, dranering, ytskydd (bool), brott (dict med E14, pris, km), motatgard.
    flygaska = andel flygaska från gjutningen (skyddar mot ASR)."""
    L = val.get("LSI")
    kalk = aggressiv = None                 # None = vattenprovet inte gjort, slumpen gäller
    kostnad, underhall = 1.0, 0.0
    if L is not None:
        _, faktor, kost, underhall = DRANERING[val.get("dranering", "standard")]
        kalk = float(np.clip((L + 0.5) / 1.5, 0.05, 1.0)) * faktor
        aggressiv = float(np.clip(-L, 0.0, 1.0))
        kostnad += kost
        if val.get("ytskydd"):
            aggressiv = 0.0
            kostnad += YTSKYDD_KOSTNAD
    asr = None                     # None = inget stenbrott valt, ASR förblir okänt och slumpat
    b = val.get("brott")
    if b and betong:
        kostnad += 0.15 * (b["pris"] - 1.0) + 0.0005 * b["km"]      # ballasten ≈ 15 % av betongen
        mot = val.get("motatgard", "ingen")
        if mot == "lagalkali":
            kostnad += LAGALKALI_KOSTNAD
        skyddad = (mot == "lagalkali" and b["E14"] <= 0.30) or (flygaska >= 0.25 and b["E14"] <= 0.45)
        asr = betong and b["E14"] >= ASR_GRANS and not skyddad
    if aggressiv is not None and not betong:
        aggressiv = 0.0
    return {"kalk": kalk, "aggressiv": aggressiv, "asr": asr,
            "kostnad_faktor": kostnad, "underhall_extra": underhall}
