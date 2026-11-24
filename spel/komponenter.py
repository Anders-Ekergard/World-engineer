"""
komponenter.py – dammens delar, hur de slits, går sönder och lagas.

Som i ett krigsfartygsspel har dammen ingen enda hälsostapel. Varje komponent har:
  t     tillstånd 0–1 (1 = som ny)
  dold  dold skada (används för inre erosion i tätkärnan, 0–1, där 1 = genombrott)
  sedd  om den dolda skadan har upptäckts
  rep   månader kvar på en pågående reparation (0 = ingen)

Komponenter och vad de gör:
  sektion_v/m/h  dammkroppen (vänster/mitt/höger). Svaga sektioner kan brista.
                 Betong kan drabbas av ASR (alkali–kiselsyrareaktion): kiselsyra i
                 ballasten reagerar med alkali i cementen och bildar en gel som sväller.
  karna          tätkärna med filter (bara fyllningsdammar). Inre erosion ("piping"):
                 läckande vatten för med sig finmaterial, kanalen växer i det tysta.
  fundament      grund och dränering. Hårt vatten fäller ut kalcit i dränerna:
                     Ca2+ + 2 HCO3-  ->  CaCO3(s) + CO2 + H2O
                 Igensatta dräner ger högre upptryck under dammen -> risk för glidning.
  utskov         utskovsrännan. Höga flöden ger kavitation och erosion (Glen Canyon 1983).
  lucka_N        utskovsluckor. En lucka som inte öppnas minskar kapaciteten.
  turbin_N       turbiner. Slits av sand (sediment) och kavitation.

Haveriorsakerna kalibreras mot ICOLD: ungefär en tredjedel vardera överströmning,
inre erosion och fundament/övrigt, totalt ca 1e-4 per damm och år för välskötta dammar.
"""

import math

DT = 1 / 12   # en månad i år

# Interna markeringar i händelselistan (visas aldrig för spelaren). motor.py läser dem
# härifrån, så att de inte kan glida isär om texterna översätts.
HAVERI = "FAILURE"      # ("FAILURE", orsak): dammen brister
KOSTNAD = "COST"        # ("COST", M$): en kostnad som ska dras från budgeten

# slitage per år vid normalt underhåll
SLITAGE = {"sektion_fyllning": 0.003, "sektion_betong": 0.002, "asr": 0.012, "aggressiv": 0.008,
           "karna": 0.002,
           "fundament": 0.04, "utskov": 0.004, "lucka": 0.015, "turbin": 0.02}
UNDERHALL_FAKTOR = {0: 2.0, 1: 1.0, 2: 0.4}     # hur fort saker slits vid underhållsnivå 0/1/2
LOPANDE = {1: 0.05, 2: 0.15}                    # luckor/turbiner återställs per år av löpande underhåll
AUTOREPARATION = {1: 0.25, 2: 1.0}              # chans per månad att en trasig lucka/turbin lagas
UPPTACKT_VID = {0: 0.8, 1: 0.4, 2: 0.15}        # hur långt inre erosion hunnit innan den syns
SYNS_UTAN_OVERVAKNING = ("sektion", "utskov", "lucka", "turbin")

# reparation: (andel av anläggningskostnaden, månader)
REPARATION = {"sektion": (0.02, 12), "karna": (0.015, 6), "fundament": (0.003, 3),
              "utskov": (0.01, 6), "lucka": (0.002, 2), "turbin": (0.01, 3)}

NAMN = {"sektion_v": "Dam body, left", "sektion_m": "Dam body, middle",
        "sektion_h": "Dam body, right", "karna": "Core and filter",
        "fundament": "Foundation and drains", "utskov": "Spillway channel"}


def slag(namn: str) -> str:
    return namn.split("_")[0]


def visningsnamn(namn: str) -> str:
    if namn in NAMN:
        return NAMN[namn]
    s, n = namn.split("_")
    return {"lucka": "Gate", "turbin": "Turbine"}[s] + " " + n


def ny(t=1.0) -> dict:
    return {"t": t, "dold": 0.0, "sedd": False, "rep": 0}


def skapa(typ: str, n_luckor: int, n_turbiner: int) -> dict:
    k = {"sektion_v": ny(), "sektion_m": ny(), "sektion_h": ny(), "fundament": ny(), "utskov": ny()}
    if typ == "fyllning":
        k["karna"] = ny()
    for i in range(1, n_luckor + 1):
        k[f"lucka_{i}"] = ny()
    for i in range(1, n_turbiner + 1):
        k[f"turbin_{i}"] = ny()
    return k


def synlig(anl: dict, namn: str) -> bool:
    """Ser spelaren komponentens tillstånd? Dränering och tätkärna kräver övervakning."""
    return namn.startswith(SYNS_UTAN_OVERVAKNING) or anl["overvakning"] >= 1


def antal(anl: dict, s: str) -> int:
    return sum(1 for n in anl["komp"] if slag(n) == s)


# ---------------------------------------------------------------- funktion

def turbiner_i_drift(anl: dict) -> list:
    return [n for n, c in anl["komp"].items()
            if slag(n) == "turbin" and c["t"] >= 0.2 and c["rep"] == 0 and n not in anl["avstangda"]]


def turbin_verkningsgrad(anl: dict) -> float:
    i_drift = turbiner_i_drift(anl)
    if not i_drift:
        return 0.0
    return sum(0.7 + 0.3 * anl["komp"][n]["t"] for n in i_drift) / len(i_drift)


def utskov_kapacitet(anl: dict, lyckade_luckor: int) -> float:
    n = max(antal(anl, "lucka"), 1)
    t_utskov = anl["komp"]["utskov"]["t"]
    return anl["Q_utskov"] * (0.5 + 0.5 * t_utskov) * lyckade_luckor / n


def oppna_luckor(anl: dict, stromavbrott: bool, rng) -> int:
    """Hur många luckor som faktiskt går att öppna när de behövs."""
    if stromavbrott and not anl["reservkraft"] and rng.uniform() < 0.7:
        return 0
    ok = 0
    for n, c in anl["komp"].items():
        if slag(n) != "lucka" or c["t"] < 0.2 or c["rep"]:
            continue
        if rng.uniform() > 0.01 + 0.25 * (1 - c["t"]):
            ok += 1
    return ok


# ---------------------------------------------------------------- slitage och slumpfel

def manad(anl: dict, f: float, sediment: float, topp_kvot: float, rng) -> list:
    """Slitage under en månad. f = magasinets fyllnadsgrad (0–1), sediment = andel av
    flodens naturliga sediment som når dammen, topp_kvot = flödestopp / utskovskapacitet.
    Returnerar en lista med händelser (text, nivå) och eventuellt (HAVERI, orsak)."""
    h = []
    U = UNDERHALL_FAKTOR[anl["underhall"]]
    k = anl["komp"]
    for namn, c in k.items():
        if c["rep"]:
            continue                          # under reparation slits inget
        s = slag(namn)
        if s == "sektion":
            c["t"] -= DT * SLITAGE["sektion_" + anl["typ"]] * U
            if anl["asr"]:
                c["t"] -= DT * SLITAGE["asr"]
            if anl["typ"] == "betong" and anl.get("aggressiv", 0.0) > 0:
                c["t"] -= DT * SLITAGE["aggressiv"] * anl["aggressiv"]   # urlakning av kalk
        elif s == "karna":
            c["t"] -= DT * SLITAGE["karna"] * U
        elif s == "fundament":
            c["t"] -= DT * SLITAGE["fundament"] * anl["kalk"] * U
        elif s == "utskov":
            c["t"] -= DT * SLITAGE["utskov"] * U
            if topp_kvot > 0.6:
                c["t"] -= 0.08 * (topp_kvot - 0.6)
                if topp_kvot > 0.9:
                    h.append(("Cavitation damage in the spillway channel after high flow", "varning"))
        elif s == "lucka":
            c["t"] -= DT * SLITAGE["lucka"] * U
            if rng.uniform() < 0.001 * (1 + 5 * (1 - c["t"])) * U:
                c["t"] -= 0.4
                h.append((f"{visningsnamn(namn)} jammed during a test run", "varning"))
        elif s == "turbin" and namn not in anl["avstangda"]:
            c["t"] -= DT * (SLITAGE["turbin"] + 0.10 * sediment) * U
            if rng.uniform() < 0.002 * (1 + 3 * (1 - c["t"])) * U:
                c["t"] -= 0.3
                h.append((f"{visningsnamn(namn)}: generator fault", "varning"))
        c["t"] = max(c["t"], 0.0)

        if s in ("lucka", "turbin") and anl["underhall"] >= 1:
            c["t"] = min(1.0, c["t"] + DT * LOPANDE[anl["underhall"]])
            if c["t"] < 0.3 and rng.uniform() < AUTOREPARATION[anl["underhall"]]:
                h.append((KOSTNAD, starta_reparation(anl, namn)))
                h.append((f"Maintenance crew repairs {visningsnamn(namn).lower()}", "info"))

    if "karna" in k:
        c = k["karna"]
        t_f = k["fundament"]["t"]
        if c["dold"] == 0:
            takt = 4e-3 * (1 + 4 * (1 - c["t"])) * (0.5 + f) * (1 + 2 * (1 - t_f))
            if rng.uniform() < DT * takt:
                c["dold"] = 0.01
        else:
            fart = rng.lognormal(math.log(0.2), 0.8) * (0.3 + f) * (0.5 if c["rep"] else 1.0)
            c["dold"] += DT * fart
            if c["dold"] < 0.3 and not c["rep"] and rng.uniform() < 0.04 * c["t"]:
                c["dold"], c["sedd"] = 0.0, False
            elif not c["sedd"] and c["dold"] >= UPPTACKT_VID[anl["overvakning"]]:
                c["sedd"] = True
                h.append(("Turbid seepage and sinkholes on the crest: INTERNAL EROSION "
                          f"({100 * c['dold']:.0f}% of the way through the core). Lower the reservoir and "
                          "repair the core!", "fara"))
            if c["dold"] >= 1.0:
                h.append((HAVERI, "internal erosion"))

    t_f = k["fundament"]["t"]
    if rng.uniform() < DT * 2e-5 * math.exp(6 * (1 - t_f)) * (0.3 + f):
        h.append((HAVERI, "foundation sliding"))

    for namn in ("sektion_v", "sektion_m", "sektion_h"):
        t = k[namn]["t"]
        if t < 0.2 and rng.uniform() < DT * 0.3 * (1 - t / 0.2) * (0.3 + f):
            h.append((HAVERI, f"{visningsnamn(namn).lower()} failed"))
    return h


# ---------------------------------------------------------------- yttre påfrestningar

def overstromning(anl: dict, s: float, rng) -> list:
    """Vattnet går över krönet. s = (flödestopp - kapacitet) / kapacitet."""
    k = anl["komp"]
    sek = rng.choice(["sektion_v", "sektion_m", "sektion_h"])
    if anl["typ"] == "fyllning":
        k[sek]["t"] = max(0.0, k[sek]["t"] - min(0.6, 0.2 + 2 * s))
        p_brott = min(0.95, 0.4 + 3 * s)
    else:
        k[sek]["t"] = max(0.0, k[sek]["t"] - (0.1 + 0.5 * s))
        k["fundament"]["t"] = max(0.0, k["fundament"]["t"] - 0.1)
        p_brott = min(0.5, 0.02 + 0.5 * s)
    k["utskov"]["t"] = max(0.0, k["utskov"]["t"] - 0.1)
    h = [(f"OVERTOPPING: the flood exceeded the spillway capacity by {100 * s:.0f}% and "
          f"water flowed over the crest", "fara")]
    if rng.uniform() < p_brott:
        h.append((HAVERI, "overtopping"))
    return h


def jordbavning(anl: dict, a: float, M: float, R: float, rng) -> list:
    """Skalv med markacceleration a (g). Skadan beror på a jämfört med dimensionerande PGA."""
    r = a / anl["seismik_g"]
    if r < 0.5:
        return [(f"Earthquake M{M:.1f} felt {R:.0f} km away ({a:.2f} g), no damage", "info")]
    k = anl["komp"]
    x = r - 0.5
    for namn, c in k.items():
        s = slag(namn)
        skada = {"sektion": 0.15, "karna": 0.2, "fundament": 0.1, "utskov": 0.05,
                 "lucka": 0.2, "turbin": 0.1}[s] * x * rng.uniform(0.3, 1.5)
        c["t"] = max(0.0, c["t"] - skada)
    h = [(f"EARTHQUAKE M{M:.1f} {R:.0f} km away: {a:.2f} g against a design value of "
          f"{anl['seismik_g']:.2f} g. The dam is damaged.", "fara" if r > 1 else "varning")]
    if "karna" in k and k["karna"]["dold"] == 0 and rng.uniform() < 0.3 * x:
        k["karna"]["dold"] = 0.05
    if anl["typ"] == "fyllning" and r > 2 and rng.uniform() < 0.2 * (r - 1.5):
        h.append((HAVERI, "earthquake"))
    if anl["typ"] == "betong" and r > 2.5 and rng.uniform() < 0.1 * (r - 2):
        h.append((HAVERI, "earthquake"))
    return h


# ---------------------------------------------------------------- reparationer

def reparationskostnad(anl: dict, namn: str) -> float:
    andel, _ = REPARATION[slag(namn)]
    if slag(namn) in ("lucka", "turbin"):
        andel /= max(antal(anl, slag(namn)), 1) / 2
    return anl["capex"] * andel


def starta_reparation(anl: dict, namn: str) -> float:
    """Startar en reparation. Returnerar kostnaden (M$)."""
    c = anl["komp"][namn]
    if c["rep"]:
        return 0.0
    c["rep"] = REPARATION[slag(namn)][1]
    return reparationskostnad(anl, namn)


def fortsatt_reparationer(anl: dict) -> list:
    h = []
    for namn, c in anl["komp"].items():
        if c["rep"]:
            c["rep"] -= 1
            if c["rep"] == 0:
                c["t"], c["dold"], c["sedd"] = 1.0, 0.0, False
                h.append((f"{visningsnamn(namn)} repaired", "info"))
    return h


def inspektera(anl: dict, rng) -> list:
    h = []
    k = anl["komp"]
    if "karna" in k and k["karna"]["dold"] > 0:
        k["karna"]["sedd"] = True
        h.append((f"The inspection found internal erosion in the core "
                  f"({100 * k['karna']['dold']:.0f}%)", "fara"))
    if anl["asr"] and not anl["asr_kand"]:
        anl["asr_kand"] = True
        h.append(("The inspection found ASR: the concrete is swelling and cracking. Sections "
                  "will deteriorate faster than normal.", "varning"))
    if not h:
        h.append(("The inspection found no hidden damage", "info"))
    return h
