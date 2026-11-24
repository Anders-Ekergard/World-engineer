"""
kontroll_spel.py – kontroller av spelmotorn (seedade, utan Dash).
Kör från dammsim-mappen:  python spel/kontroll_spel.py
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from floder import PLATS
from spel import hydrologi as HY
from spel import komponenter as K
from spel.ekonomi import kalkyl
from spel.motor import nasta_manad, utfor, SEK_MANAD
from spel.tillstand import nytt_spel, till_json, fran_json

OK = True


def kontroll(villkor, text):
    global OK
    print(("  OK   " if villkor else "  FEL  ") + text)
    OK &= bool(villkor)


# ---------------------------------------------------------------- 1. kostnader
print("=== Kostnader och byggtid (verkligheten inom en faktor 2) ===")
for pid, typ, kost_verklig, ar_verklig in [("yangtze", "betong", 35e3, 12), ("parana", "betong", 30e3, 9)]:
    p = PLATS[pid]
    d = {"typ": typ, "H": p.H_standard, "utbyggnad": 1.3, "seismik_g": 0.15,
         "overvakning": 1, "reservkraft": True}
    k = kalkyl(p, d, HY.dimensionerande_flode(pid, 1000))
    ar = k["byggtid_man"] / 12
    print(f"  {p.namn}: {k['total'] / 1e3:.1f} miljarder $ ({kost_verklig / 1e3:.0f}), {ar:.1f} år ({ar_verklig})")
    kontroll(0.5 < k["total"] / kost_verklig < 2 and 0.5 < ar / ar_verklig < 2, f"{p.namn} kostnad och byggtid")

# ---------------------------------------------------------------- 2. utskov och klimatkrok
print("\n=== Extremflöden: 1000-årsflödet överskrids 1 gång på 1000 år ===")
rng = np.random.default_rng(1)
pid = "zambezi"
Q1000 = HY.dimensionerande_flode(pid, 1000)
toppman = HY.statistik(pid)["toppmanad"]
for extrem in (1.0, 1.3):
    fak = {"medel": 1.0, "amplitud": 1.0, "extrem": extrem, "avdunstning": 1.0}
    N = 200_000
    over = sum(HY.flodtopp(pid, toppman, 0.0, fak, rng) > Q1000 for _ in range(N))
    T = N / max(over, 1)
    print(f"  extremfaktor {extrem}: överskrids en gång per {T:.0f} år")
    if extrem == 1.0:
        kontroll(700 < T < 1400, "Gumbelfördelningen ger rätt återkomsttid")
    else:
        kontroll(T < 200, "varmare klimat (+30 % extremflöden) gör en 1000-årsdamm till en <200-årsdamm")

# ---------------------------------------------------------------- 3. vattenbalans
print("\n=== Vattenbalans i magasinen ===")
t = nytt_spel(3)
fel_max = 0.0
for _ in range(36):
    fore = {k: a["V"] for k, a in t["anlaggningar"].items() if a["status"] == "drift"}
    nasta_manad(t)
    for k, V0 in fore.items():
        a = t["anlaggningar"][k]
        if a["status"] != "drift":
            continue
        s = a["senast"]
        forvantat = V0 + (s["Q_in"] - s["avdunst"] - s["Q_ut"]) * SEK_MANAD
        fel_max = max(fel_max, abs(a["V"] - forvantat) / a["V_max"])
kontroll(fel_max < 1e-9, f"dV = (Q_in - avdunstning - Q_ut)*dt varje månad (största fel {fel_max:.1e})")

# ---------------------------------------------------------------- 4. kaskad
print("\n=== Kaskad: ett magasin som fylls uppströms tar vatten från dammen nedanför ===")
t = nytt_spel(4)
t["anlaggningar"]["blanilen"]["V"] = 0.0           # GERD tomt -> fyller på
nasta_manad(t)
s = t["anlaggningar"]["nilen"]["senast"]
print(f"  Assuan: naturligt {s['Q_nat']:.0f} m³/s, in {s['Q_in']:.0f} m³/s (GERD fyller sitt magasin)")
kontroll(s["Q_in"] < s["Q_nat"] - 100, "Assuan får mindre vatten när GERD fyller sitt magasin")

# ---------------------------------------------------------------- 5. spara/ladda
print("\n=== Spara och ladda: samma frö + samma beslut = samma spel ===")
a1 = nytt_spel(7)
for _ in range(24):
    nasta_manad(a1)
utfor(a1, {"typ": "bygg", "plats": "mekong", "design": {
    "typ": "fyllning", "H": 60, "utskov_T": 1000, "seismik_g": 0.15, "n_turbiner": 4,
    "utbyggnad": 1.3, "overvakning": 1, "reservkraft": True}})
b1 = fran_json(till_json(a1))
for _ in range(24):
    nasta_manad(a1)
    nasta_manad(b1)
kontroll(till_json(a1) == till_json(b1), "identiskt efter spara/ladda och 24 månader till")


# ---------------------------------------------------------------- 6. haverifrekvens
def valskott(t):
    """En ansvarsfull spelare: lagar strukturella skador i tid och sänker magasinet vid inre erosion."""
    for a in t["anlaggningar"].values():
        if a["status"] != "drift":
            continue
        for namn, c in a["komp"].items():
            grans = 0.6 if K.slag(namn) == "lucka" else 0.5
            if K.slag(namn) in ("sektion", "fundament", "utskov", "karna", "lucka") and \
                    not c["rep"] and K.synlig(a, namn) and (c["t"] < grans or c["sedd"]):
                t["budget"] -= K.starta_reparation(a, namn)
        karna = a["komp"].get("karna")
        a["drift"] = "sank" if karna and (karna["sedd"] or karna["rep"]) else "normal"


def simulera(policy, fron, ar):
    orsaker, dammar = Counter(), 0
    for fro in fron:
        t = nytt_spel(fro)
        for a in t["anlaggningar"].values():
            a["underhall"] = 0 if policy is None else 1
        for _ in range(ar * 12):
            if policy:
                policy(t)
            nasta_manad(t)
        dammar += ar * len(t["anlaggningar"])
        for a in t["anlaggningar"].values():
            if a["haveri"]:
                orsaker[a["haveri"]["orsak"]] += 1
    return sum(orsaker.values()) / dammar, orsaker, dammar


print("\n=== Haverier (ICOLD: ca 1e-4 per damm och år för välskötta dammar) ===")
f_bra, o_bra, n_bra = simulera(valskott, range(1, 31), 30)
print(f"  välskötta:  {f_bra:.1e} per damm och år ({sum(o_bra.values())} haverier på {n_bra} dammår) {dict(o_bra)}")
f_dalig, o_dalig, n_dalig = simulera(None, range(1, 11), 30)
print(f"  försummade: {f_dalig:.1e} per damm och år ({sum(o_dalig.values())} haverier på {n_dalig} dammår) {dict(o_dalig)}")
kontroll(f_bra < 1e-3, "välskötta dammar haverar sällan (< 1e-3 per år)")
kontroll(f_dalig > 5 * max(f_bra, 1e-4), "försummade dammar haverar mycket oftare")
kontroll(len(o_dalig) >= 2, "flera olika haveriorsaker förekommer")

# ---------------------------------------------------------------- 7. minispelen
from spel.minispel import labb as LB, gjutning as GJ, effekter
from spel.anlaggning import ny_anlaggning

print("\n=== Kemilabbet ===")
r = LB.lsi(pH=7.5, T=25, Ca=150, alk=34, TDS=320)        # handräknat: LSI = -0,731
print(f"  läroboksexempel: pHs = {r['pHs']:.3f}, LSI = {r['LSI']:.3f} (handräknat -0,731)")
kontroll(abs(r["LSI"] - (-0.731)) < 0.01, "Langeliers index stämmer med handräkningen")
hart = LB.utvardera({"LSI": 0.8, "dranering": "standard"}, True, 0.0)
mjukt = LB.utvardera({"LSI": -1.0, "dranering": "standard"}, True, 0.0)
kontroll(hart["kalk"] > mjukt["kalk"] and mjukt["aggressiv"] > 0 == hart["aggressiv"],
         "hårt vatten sätter igen dräner, mjukt vatten angriper betongen")
kontroll(LB.prov(1, "mekong", 18) == LB.prov(1, "mekong", 18), "samma frö och plats ger samma prov")
reaktiv = {"namn": "Flintgrus", "E14": 0.35, "pris": 0.7, "km": 10}
kontroll(LB.utvardera({"LSI": None, "brott": reaktiv, "motatgard": "ingen"}, True, 0.0)["asr"] is True
         and LB.utvardera({"LSI": None, "brott": reaktiv, "motatgard": "flygaska"}, True, 0.30)["asr"] is False,
         "reaktiv ballast ger ASR, men inte med 30 % flygaska")

print("\n=== Betonggjutningen ===")
dT_ad = GJ.adiabatisk_hojning(250, 0.0)
s = GJ.simulera({**GJ.STANDARD, "lyft": 20.0}, alfa=1e-9)
hojning = s["karna"].max() - (GJ.STANDARD["T_luft"] + 3)
full = dT_ad * (1 - np.exp(-GJ.K_PC * GJ.DAGAR))
print(f"  adiabatisk höjning: modell {hojning:.2f} °C, formel {full:.2f} °C")
kontroll(abs(hojning - full) / full < 0.02, "utan värmeförlust blir höjningen c·Q/(ρ·cp)")
topp = lambda **k: GJ.utvardera({**GJ.STANDARD, **k})["T_max"]
kontroll(topp(lyft=3.0) > topp(lyft=1.5) > topp(lyft=0.5), "tjockare lyft blir varmare")
kontroll(topp(kylror=True) < topp() and topp(flygaska=0.3) < topp() and topp(forkylning=10) < topp(),
         "kylrör, flygaska och förkylning sänker topptemperaturen")
kontroll(topp(T_luft=28) > topp(T_luft=5), "sommargjutning är varmare än vintergjutning")
hoover = GJ.utvardera({**GJ.STANDARD, "kylror": True, "forkylning": 10, "T_luft": 30, "T_ar": 20})
kontroll(hoover["utlatande"] == "No cracks", "Hoover-planen (kylrör + förkylning) spricker inte")

print("\n=== Minispelen styr dammens dolda egenskaper ===")
design = {"typ": "betong", "H": 60.0, "utskov_T": 1000, "seismik_g": 0.15, "n_turbiner": 4,
          "utbyggnad": 1.3, "overvakning": 1, "reservkraft": True,
          "labb": {"LSI": 0.9, "dranering": "syra", "brott": reaktiv, "motatgard": "ingen"},
          "gjutning": {**GJ.STANDARD, "lyft": 3.0}}
a = ny_anlaggning("mekong", design, 0, np.random.default_rng(1))
kontroll(a["asr"] and a["asr_kand"] and abs(a["kalk"] - (0.9 + 0.5) / 1.5 * 0.1) < 1e-9
         and a["underhall_extra"] > 0,
         "labbet bestämmer ASR, kalcit och extra underhåll")
kontroll(a["komp"]["sektion_m"]["t"] < 0.8, "svåra sprickor ger en sämre dammkropp från början")
utan = ny_anlaggning("mekong", {k: v for k, v in design.items() if k not in ("labb", "gjutning")},
                     0, np.random.default_rng(1))
kontroll(not utan["asr_kand"] and utan["komp"]["sektion_m"]["t"] == 1.0 and effekter(design)["damm_faktor"] != 1,
         "utan minispel gäller slumpen som förut")

# ---------------------------------------------------------------- 8. scenariot Nilen
from spel import scenarier as SC

print("\n=== Scenariot Nilen ===")
t = SC.starta("nilen", fro=1)
kontroll(sorted(t["anlaggningar"]) == ["blanilen", "nilen"] and t["scenario"]["slut_manad"] == 300,
         "startar med Assuan och GERD och pågår i 25 år")
kontroll(not SC.tillaten_plats(t, 102.2, 18.0) and SC.tillaten_plats(t, 31.8, 18.7),
         "bara Nilbäckenet går att bygga i")
handelser = {}
while not t["slut"]:
    m = t["manad"]
    nasta_manad(t)
    if m == SC.EROSION_MANAD:
        handelser["erosion"] = t["anlaggningar"]["nilen"]["komp"]["karna"]["sedd"]
    if SC.TORKA[0] <= m < SC.TORKA[1]:
        handelser["torka"] = handelser.get("torka", True) and \
            t["hydrologi"][SC.nil_system()] == SC.TORKA_Z
kontroll(handelser.get("erosion") and handelser.get("torka"),
         "den skriptade erosionen och torkan inträffar i rätt månader")
r = t["scenario"]["resultat"]
kontroll(t["manad"] == 300 and r is not None and r["betyg"] in ("guld", "silver", "brons", "underkänt"),
         f"slutbetyg efter 300 månader (passiv spelare: {r['betyg']})")
kontroll(r["betyg"] == "underkänt", "en spelare som inte gör något blir underkänd")
t2 = SC.starta("nilen", fro=1)
while not t2["slut"]:
    nasta_manad(t2)
kontroll(till_json(t) == till_json(t2), "samma frö ger samma scenario")

print("\nAlla kontroller OK" if OK else "\nNÅGON KONTROLL MISSLYCKADES")
sys.exit(0 if OK else 1)
