"""
motor.py – spelets hjärta: utfor(tillstand, beslut) och nasta_manad(tillstand).

En månad, i den här ordningen:
  1. bygget går framåt (betalas efter hand)
  2. hydrologi: flöde och flödestopp för varje damm (AR(1)-anomali per flodsystem)
  3. reglering från källorna mot havet:
       Q_in(B) = Q_nat(B) - summa(Q_nat(A) - Q_ut(A))  för dammar A direkt uppströms
     magasinets vattenbalans: dV = (Q_in - avdunstning - Q_ut) * dt
  4. flödestoppen: magasinet dämpar, turbiner + utskov ska klara resten,
     annars överströmning (luckor kan krångla, särskilt vid strömavbrott)
  5. slitage, slumpfel, inre erosion, jordbävningar
  6. haverier
  7. ekonomi (el, underhåll, anslag, ränta) och megaprojekt
  8. acceptans, CO2, historik

Allt slump kommer från np.random.default_rng([frö, månad]), så samma frö och samma
beslut ger exakt samma spel.
"""

import math
from functools import lru_cache

import numpy as np

from floder import hamta_plats, magasin, sedimentfangst, RHO, G
from kaskad import relationer
from bassanger import HAV_DICT, BERING, dammvolym_km3, bering_dammvolym_km3, bering_effekt_MW
from sankor import SANKA_DICT, gravvolym_km3, megaprojekt
from spel import komponenter as K
from spel import acceptans as ACC
from spel import hydrologi as HY
from spel.anlaggning import ny_anlaggning, forhandskalkyl
from spel.ekonomi import UNDERHALL_PER_AR, intakt_MS
from spel.geografi import region, region_namn
from spel import scenarier as SC
from spel.handelser import skalv, paverkan as skakning

SEK_MANAD = 3.156e7 / 12
ANSLAG_PER_AR = 4000.0           # M$ från världens länder varje år
KONKURS_VID = -30000.0           # M$
RANTA_MANAD = 0.005              # på negativ budget
CO2_PER_MWH = 0.9e-9             # Gt CO2 per MWh kolkraft som ersätts
DODLIGHET = {0: 0.005, 1: 0.002, 2: 0.0005}   # andel av de drabbade, beroende på förvarning
SKADA_PER_DRABBAD = 0.02         # M$
MAL_FYLLNAD = {"normal": 0.85, "torka": 0.95, "sank": 0.3}
GARANTI_TORKA = 0.8             # "spara vatten": andel av normalflödet som garanteras nedströms


# ---------------------------------------------------------------- hjälp

def logg(t: dict, text: str, niva: str = "info", anl: str | None = None):
    t["logg"].append({"m": t["manad"], "text": text, "niva": niva, "anl": anl})


def datum(t: dict, manad: int | None = None) -> str:
    m = t["manad"] if manad is None else manad
    namn = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{namn[m % 12]} {t['startar'] + m // 12}"


@lru_cache(maxsize=64)
def _relationer(ider: tuple):
    return relationer(list(ider))


def sediment_koncentration(lon: float, lat: float) -> float:
    """kg/m3 sediment i flodvattnet: monsun-Asien är mycket slammigare."""
    return 1.5 if (60 <= lon <= 125 and 5 <= lat <= 40) else 0.5


def i_drift(t: dict) -> list:
    return [a for a in t["anlaggningar"].values() if a["status"] == "drift"]


# ---------------------------------------------------------------- spelarens beslut

def utfor(t: dict, beslut: dict, rng=None) -> str:
    """Execute a decision immediately. Return a status message."""
    rng = rng or np.random.default_rng([t["fro"], t["manad"], 7])
    typ = beslut["typ"]
    if typ == "bygg":
        pid = beslut["plats"]
        if pid in t["anlaggningar"] and t["anlaggningar"][pid]["status"] != "riven":
            return "A dam already exists here."
        p_ = hamta_plats(pid)
        if not SC.tillaten_plats(t, p_.lon, p_.lat):
            return "This location is outside the scenario area (the Nile Basin)."
        f = forhandskalkyl(pid, beslut["design"])
        if t["acceptans"][f["region"]] < 20:
            return f"Acceptance in {region_namn(f['region'])} is too low to start a new construction project."
        a = ny_anlaggning(pid, beslut["design"], t["manad"], rng, standardgjutning=True)
        t["anlaggningar"][pid] = a
        andel = min(25.0, a["fordrivna"] / 40000)
        t["paverkan"][a["region"]] = t["paverkan"].get(a["region"], 0.0) - andel
        logg(t, f"Construction of {a['namn']} ({a['flod']}) has started: ${f['total'] / 1e3:.1f} "
                f"billion, {f['byggtid_man'] / 12:.0f} years; {a['fordrivna']:,.0f} people "
                f"must relocate.", "info", pid)
        return "Construction started."
    if typ == "bygg_mega":
        mid = beslut["id"]
        if not SC.tillaten_mega(t, mid):
            return "The megaproject is not included in this scenario."
        k = mega_kalkyl(mid, beslut["varde"])
        t["mega"][mid] = {"varde": beslut["varde"], "status": "bygge", "capex": k["total"],
                          "bygg_tot": k["byggtid_man"], "bygg_kvar": float(k["byggtid_man"]),
                          "klar": None, "MW": k["MW"], "region": k["region"]}
        for r, d in k["acceptans"].items():
            t["paverkan"][r] = t["paverkan"].get(r, 0.0) + d
        logg(t, f"Megaproject {k['namn']} has started: ${k['total'] / 1e3:.0f} billion, "
                f"{k['byggtid_man'] / 12:.0f} years", "info", mid)
        return "Megaproject started."

    a = t["anlaggningar"].get(beslut.get("id"))
    if a is None:
        return "No such facility."
    if typ == "reparera":
        kost = K.starta_reparation(a, beslut["komp"])
        t["budget"] -= kost
        if kost:
            logg(t, f"{a['namn']}: repair of {K.visningsnamn(beslut['komp']).lower()} "
                    f"started (${kost:,.0f} M)", "info", a["id"])
        return f"Repair started (${kost:,.0f} M)."
    if typ == "inspektera":
        kost = 0.0005 * a["capex"] + 5
        t["budget"] -= kost
        for text, niva in K.inspektera(a, rng):
            logg(t, f"{a['namn']}: {text}", niva, a["id"])
        return f"Inspection complete (${kost:,.0f} M)."
    if typ == "underhall":
        a["underhall"] = int(beslut["niva"])
        return "Maintenance level changed."
    if typ == "drift":
        a["drift"] = beslut["lage"]
        return "Operating mode changed."
    if typ == "turbin":
        if beslut["av"] and beslut["komp"] not in a["avstangda"]:
            a["avstangda"].append(beslut["komp"])
        elif not beslut["av"] and beslut["komp"] in a["avstangda"]:
            a["avstangda"].remove(beslut["komp"])
        return "Turbine toggled."
    if typ == "overvakning":
        niva = int(beslut["niva"])
        if niva > a["overvakning"]:
            kost = 0.01 * a["capex"] * (niva - a["overvakning"])
            t["budget"] -= kost
            a["overvakning"] = niva
            return f"Monitoring upgraded (${kost:,.0f} M)."
        return "Monitoring can only be upgraded."
    if typ == "reservkraft":
        if not a["reservkraft"]:
            t["budget"] -= 20.0
            a["reservkraft"] = True
        return "Backup power installed ($20 M)."
    if typ == "riv":
        kost = 0.1 * a["capex"]
        t["budget"] -= kost
        a["status"] = "riven"
        logg(t, f"{a['namn']} demolished (${kost:,.0f} M). The river flows freely again.", "info", a["id"])
        return "Dam is being demolished."
    return "Unknown decision."


# ---------------------------------------------------------------- megaprojekt

def mega_kalkyl(mid: str, varde: float) -> dict:
    """Kostnad (M$) och byggtid för megaprojekten (fyllningsdammar 25 $/m3, kanaler 15 $/m3)."""
    if mid == "bering":
        MW = bering_effekt_MW(varde)
        return {"namn": "Bering Strait dam", "total": bering_dammvolym_km3() * 1e9 * 25e-6 + MW,
                "byggtid_man": 180, "MW": MW, "region": "Nordamerika",
                "acceptans": {"Nordamerika": -5, "Asien": -3}}
    if mid in HAV_DICT:
        h = HAV_DICT[mid]
        r = megaprojekt({mid: varde}, 300)["hav"][mid]
        MW = float(r["effekt_MW"].max())
        reg = region(*h.markor)
        drabbade = {"gibraltar": ["Europa", "Afrika", "Mellanöstern"],
                    "rodahavet": ["Mellanöstern", "Afrika"]}[mid]
        return {"namn": f"Dam across the {h.sund}", "total": dammvolym_km3(h) * 1e9 * 25e-6 + MW,
                "byggtid_man": 300, "MW": MW, "region": reg,
                "acceptans": {r_: -15 for r_ in drabbade}}
    s = SANKA_DICT[mid]
    r = megaprojekt({mid: varde}, 200)["sankor"][mid]
    MW = float(max(r["effekt_MW"].max(), 0.0))
    grav = gravvolym_km3(s, varde)
    return {"namn": s.projekt, "total": grav * 1e9 * 15e-6 + MW + float(r["pump_MW"].max()),
            "byggtid_man": int(12 * min(20, 5 + grav / 0.05)), "MW": MW,
            "region": region(*s.markor), "acceptans": {region(*s.markor): -3}}


def mega_i_drift(t: dict) -> dict:
    return {k: m for k, m in t["mega"].items() if m["status"] == "drift"}


def megaresultat(t: dict):
    """Megaprojektens tillstånd just nu (sankor.megaprojekt med tiden sedan det första blev klart)."""
    drift = mega_i_drift(t)
    if not drift:
        return None, 0
    ar = max(1, (t["manad"] - min(m["klar"] for m in drift.values())) // 12)
    byggda = {k: m["varde"] for k, m in drift.items()}
    byggda.update({a["id"]: a["H"] for a in i_drift(t)})
    return megaprojekt(byggda, ar), ar


# ---------------------------------------------------------------- en månad

def nasta_manad(t: dict) -> dict:
    if t["slut"]:
        return t
    rng = np.random.default_rng([t["fro"], t["manad"]])
    man = t["manad"] % 12
    SC.fore_manad(t)
    paverkan = t["paverkan"]
    rapport = {"MWh": 0.0, "intakt": 0.0, "kostnad": 0.0}

    # 1. bygget
    for a in list(t["anlaggningar"].values()) + list(t["mega"].values()):
        if a["status"] != "bygge":
            continue
        reg = a["region"]
        if a.get("protest", 0) > 0:
            a["protest"] -= 1
            continue
        if t["acceptans"][reg] < 15 and rng.uniform() < 0.1:
            a["protest"] = 6
            logg(t, f"Protests in {region_namn(reg)} halt construction of {a.get('namn', 'the megaproject')} "
                    "for 6 months",
                 "varning", a.get("id"))
            continue
        takt = ACC.byggtakt(t["acceptans"][reg])
        kost = a["capex"] / a["bygg_tot"] * (1 if takt == 1 else 1.2)   # långsamt bygge blir dyrare
        t["budget"] -= kost * takt
        rapport["kostnad"] += kost * takt
        a["bygg_kvar"] -= takt
        if a["bygg_kvar"] <= 0:
            a["status"] = "drift"
            if "komp" in a:
                logg(t, f"{a['namn']} is complete! The reservoir is beginning to fill.", "info", a["id"])
            else:
                a["klar"] = t["manad"]
                logg(t, "The megaproject is complete and entering operation.", "info")

    # 2–4. hydrologi och reglering (floddammar i drift)
    drift = {a["id"]: a for a in i_drift(t)}
    rel = _relationer(tuple(sorted(drift))) if drift else None
    ordning = rel["ordning"] if rel else list(drift)
    z = t["hydrologi"]
    system_denna = {HY.statistik(i)["system"] for i in drift}
    for s in sorted(system_denna):
        z[s] = HY.uppdatera_anomali(z.get(s, 0.0), rng)
        tvang = SC.tvingad_anomali(t, s)                 # scenariots skriptade torka
        if tvang is not None:
            z[s] = tvang

    skalv_lista = skalv(list(drift.values()), rng)
    ut = {}            # per damm: Q_nat, Q_ut, topp_nat, topp_ut, sed_ut
    for b in ordning:
        a = drift[b]
        p = hamta_plats(b)
        st = HY.statistik(b)
        fak = HY.klimatfaktorer(t, p)
        Q_nat = HY.manadsflode(b, man, z[st["system"]], fak)
        topp_nat = HY.flodtopp(b, man, Q_nat, fak, rng)
        upp = rel["direkt_upp"][b] if rel else []
        Q_in = max(Q_nat - sum(ut[x]["Q_nat"] - ut[x]["Q_ut"] for x in upp), 0.0)
        topp_in = max(topp_nat - sum(ut[x]["topp_nat"] - ut[x]["topp_ut"] for x in upp), Q_in)
        sed_in = max(0.0, 1.0 - sum(min(1.0, ut[x]["Q_nat"] / Q_nat) * (1 - ut[x]["sed_ut"])
                                    for x in upp)) if Q_nat > 0 else 0.0

        # magasinet
        V_max = max(a["V_max"] - a["sediment"], 0.05 * a["V_max"])
        mag = magasin(p, a["H"])
        f0 = min(a["V"] / V_max, 1.0)
        yta = mag["yta_km2"] * 1e6 * f0 ** (2 / 3)
        avdunst = yta * p.avdunstning * fak["avdunstning"] / 3.156e7       # m3/s
        mal = MAL_FYLLNAD.get(a["drift"], 0.85)
        if a["drift"] == "flodskydd":
            fore = (st["toppmanad"] - man) % 12
            mal = 0.6 if fore <= 3 else 0.85
        Q_min = min(0.1 * p.Q, Q_in)                       # miljöflöde
        if a["drift"] == "torka":
            # spara vatten: håll magasinet fullt, men garantera 80 % av normalflödet
            # nedströms så länge det finns vatten över 10 % i magasinet
            Q_min = min(GARANTI_TORKA * p.Q, Q_in + max(a["V"] - 0.1 * V_max, 0.0) / SEK_MANAD)
        Q_rel = max(Q_in - avdunst + (a["V"] - mal * V_max) / SEK_MANAD, Q_min)
        V_ny = a["V"] + (Q_in - avdunst - Q_rel) * SEK_MANAD
        if V_ny > V_max:
            Q_rel += (V_ny - V_max) / SEK_MANAD
            V_ny = V_max
        if V_ny < 0:
            Q_rel = max(Q_rel + V_ny / SEK_MANAD, 0.0)
            V_ny = 0.0
        a["V"] = V_ny

        # el
        turb = K.turbiner_i_drift(a)
        n_turb = max(K.antal(a, "turbin"), 1)
        Q_turb_max = a["utbyggnad"] * p.Q * len(turb) / n_turb
        Q_turb = min(Q_rel, Q_turb_max)
        f = min(V_ny / V_max, 1.0)
        fall = a["H"] * ((f0 + f) / 2) ** (1 / 3)
        P_MW = RHO * G * Q_turb * fall * 0.9 * K.turbin_verkningsgrad(a) / 1e6
        MWh = P_MW * 730
        a["energi_MWh"] += MWh
        rapport["MWh"] += MWh

        # flödestoppen
        ledigt = max(V_max - V_ny, 0.0) + 0.02 * V_max
        dampning = min(max(topp_in - Q_in, 0.0), ledigt / (5 * 86400))
        behov_utskov = topp_in - dampning - Q_turb_max
        stromavbrott = any(pga_ > 0.2 for pga_, _, _ in skakning(a, skalv_lista))
        topp_kvot, topp_ut = 0.0, topp_in - dampning
        handelser = []
        if behov_utskov > 0.3 * a["Q_utskov"]:
            luckor = K.oppna_luckor(a, stromavbrott, rng)
            kap = K.utskov_kapacitet(a, luckor)
            topp_kvot = behov_utskov / a["Q_utskov"]
            if luckor < K.antal(a, "lucka"):
                handelser.append((f"{K.antal(a, 'lucka') - luckor} of {K.antal(a, 'lucka')} gates "
                                  "could not be opened when the flood wave arrived", "varning"))
            if behov_utskov > kap:
                s = (behov_utskov - kap) / max(kap, 0.05 * a["Q_utskov"])
                handelser += K.overstromning(a, s, rng)
        if topp_in > 2 * p.Q and dampning > 0.2 * topp_in and man == st["toppmanad"]:
            paverkan[a["region"]] = paverkan.get(a["region"], 0.0) + 1.0
            handelser.append((f"The reservoir attenuated this year's flood peak from {topp_in:,.0f} to "
                              f"{topp_ut:,.0f} m³/s", "info"))
        if z[st["system"]] < -1.5 and Q_rel > Q_in:
            paverkan[a["region"]] = paverkan.get(a["region"], 0.0) + 0.5

        # sediment
        uppehall = V_max / max(Q_in * 3.156e7, 1.0)
        TE = sedimentfangst(uppehall)
        sed_vol = Q_in * SEK_MANAD * sediment_koncentration(p.lon, p.lat) / 1300 * sed_in
        a["sediment"] = min(a["sediment"] + TE * sed_vol, 0.95 * a["V_max"])
        sed_ut = sed_in * (1 - TE)

        # 5. slitage, slumpfel, jordbävningar
        handelser += K.fortsatt_reparationer(a)
        handelser += K.manad(a, f, sed_in * sediment_koncentration(p.lon, p.lat), topp_kvot, rng)
        for pga_, M, R in skakning(a, skalv_lista):
            handelser += K.jordbavning(a, pga_, M, R, rng)

        a["senast"] = {"Q_nat": Q_nat, "Q_in": Q_in, "Q_ut": Q_rel, "topp": topp_in,
                       "fyllnad": f, "P_MW": P_MW, "turbiner": len(turb), "sed_in": sed_in,
                       "avdunst": avdunst}

        # 6. haverier
        haveri = next((orsak for text, orsak in handelser if text == K.HAVERI), None)
        for text, niva in handelser:
            if text == K.KOSTNAD:
                t["budget"] -= niva
                rapport["kostnad"] += niva
            elif text != K.HAVERI:
                logg(t, f"{a['namn']}: {text}", niva, b)
        if haveri:
            dammbrott(t, a, haveri)
            Q_rel, topp_ut, sed_ut = Q_in, topp_in, sed_in
        ut[b] = {"Q_nat": Q_nat, "Q_ut": Q_rel, "topp_nat": topp_nat, "topp_ut": topp_ut,
                 "sed_ut": sed_ut}
        if sed_in < 0.3 and (not rel or rel["narmast_ned"][b] is None):
            paverkan[a["region"]] = paverkan.get(a["region"], 0.0) - 0.1

    # 7. ekonomi
    for a in i_drift(t):
        kost = a["capex"] * (UNDERHALL_PER_AR[a["underhall"]] + a.get("underhall_extra", 0.0)) / 12
        t["budget"] -= kost
        rapport["kostnad"] += kost
    mr, mar = megaresultat(t)
    if mr is not None:
        for mid, m in mega_i_drift(t).items():
            if mid in mr["hav"]:
                P = float(mr["hav"][mid]["effekt_MW"][min(mar, len(mr["hav"][mid]["effekt_MW"]) - 1)])
            elif mid in mr["sankor"]:
                P = float(mr["sankor"][mid]["effekt_MW"][min(mar, len(mr["sankor"][mid]["effekt_MW"]) - 1)])
            else:
                P = bering_effekt_MW(m["varde"])
            rapport["MWh"] += max(P, 0.0) * 730
    rapport["intakt"] = intakt_MS(rapport["MWh"])
    t["budget"] += rapport["intakt"] + t.get("anslag_per_ar", ANSLAG_PER_AR) / 12
    if t["budget"] < 0:
        t["budget"] *= 1 + RANTA_MANAD

    # el ger acceptans
    for a in i_drift(t):
        GWh = a["senast"].get("P_MW", 0.0) * 0.73
        paverkan[a["region"]] = paverkan.get(a["region"], 0.0) + min(0.05, GWh / 50000)

    # 8. acceptans, CO2, historik
    ACC.uppdatera(t["acceptans"], paverkan)
    t["paverkan"] = {}
    t["klimat"]["co2_sparad_Gt"] += rapport["MWh"] * CO2_PER_MWH
    t["stat"]["energi_TWh"] += rapport["MWh"] / 1e6
    hist = t["historik"]
    hist["budget"].append(round(t["budget"], 1))
    hist["TWh_ar"].append(round(rapport["MWh"] * 12 / 1e6, 2))
    hist["acceptans"].append(round(sum(t["acceptans"].values()) / len(t["acceptans"]), 1))
    t["senaste_rapport"] = rapport
    if t["budget"] < KONKURS_VID:
        t["slut"] = "Bankruptcy: the world's countries stop funding the World Engineer."
        logg(t, t["slut"], "fara")
    SC.efter_manad(t)
    t["manad"] += 1
    return t


def dammbrott(t: dict, a: dict, orsak: str):
    """Dammen brister: magasinet töms, människor nedströms drabbas."""
    a["status"] = "havererad"
    a["haveri"] = {"orsak": orsak, "manad": t["manad"]}
    p = hamta_plats(a["id"])
    drabbade = p.befolkning * a["V"] / 3.0 / 1e6           # magasinet sprids 3 m djupt
    doda = int(drabbade * DODLIGHET[a["overvakning"]])
    kost = drabbade * SKADA_PER_DRABBAD
    t["budget"] -= kost
    t["stat"]["dodsoffer"] += doda
    a["V"] = 0.0
    for r in t["acceptans"]:
        t["paverkan"][r] = t["paverkan"].get(r, 0.0) - (40 if r == a["region"] else 10)
    t["paverkan"][a["region"]] -= min(30.0, doda / 1000)
    logg(t, f"DAM FAILURE at {a['namn']} ({orsak})! {drabbade:,.0f} people downstream were "
            f"affected and {doda:,.0f} died. The damage costs ${kost / 1e3:.1f} billion.",
         "fara", a["id"])
