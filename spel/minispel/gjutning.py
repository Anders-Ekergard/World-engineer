"""
gjutning.py – Betonggjutningen: härdningsvärme och sprickrisk i en gjutetapp (lyft).

När cement reagerar med vatten (hydratisering) frigörs värme. I en tunn platta försvinner
värmen genast, men i en massiv damm stängs den inne. Kärnan blir varm, sedan svalnar den
under veckor till år. Betongen har då redan hårdnat och vill krympa när den svalnar, men
hålls fast av berget och äldre betong -> dragspänning -> sprickor. Tumregel för massiv
betong: håll temperaturfallet och skillnaden mellan kärna och yta under ca 20 °C.

Modell (1D, lyftens höjd z från botten till ovansidan, tid t i dygn):
    dT/dt = alfa * d2T/dz2 + q(t)/(rho*cp) - kylror
    q(t)  = c_pc*Q_pc*k_pc*exp(-k_pc*t) + c_fa*Q_fa*k_fa*exp(-k_fa*t)   (första ordningens)
    Adiabatisk höjning (utan värmeförlust):  dT_ad = (c_pc*Q_pc + c_fa*Q_fa) / (rho*cp)
Randvillkor: ovansidan avger värme till luften (h = 10 W/m2K), undersidan ligger mot
tidigare lyft som håller ungefär luftens temperatur + 5 °C. Kylrören (som i Hooverdammen)
tar bort värme i lyftens inre i proportion till (T - kylvattnets temperatur).
Explicita finita differenser.
"""

import math
from functools import lru_cache

import numpy as np

RHO_CP = 2400.0          # kJ/(m3·K)   (rho 2400 kg/m3 * cp 1,0 kJ/(kg·K))
ALFA = 1.0e-6 * 86400    # m2/dygn     (temperaturledningstal 1e-6 m2/s)
Q_PC, K_PC = 400.0, 0.30     # portlandcement: kJ/kg, per dygn
Q_FA, K_FA = 200.0, 0.08     # flygaska: hälften så mycket värme, och mycket långsammare
H_LUFT = 10.0 * 86400 / (RHO_CP * 1000)    # värmeövergång ovansida, m/dygn
KYLROR = 0.30            # per dygn, kylrörens effekt
T_KYLVATTEN = 5.0        # °C
DAGAR = 28
SPRICKGRANS = 20.0       # °C
KRAV_BINDEMEDEL = 200.0  # kg/m3 effektivt bindemedel (flygaska räknas med faktor 0,5)
STANDARD = {"lyft": 1.5, "cement": 250, "flygaska": 0.0, "forkylning": 0.0, "kylror": False,
            "T_luft": 20.0, "T_ar": 15.0}


def lufttemperatur(lat: float, manad: int) -> tuple:
    """(lufttemperatur denna månad, årsmedel) från latitud. manad 0 = januari."""
    medel = 27 - 0.4 * abs(lat)
    amp = 2 + 0.25 * abs(lat)
    fas = 6.5 if lat >= 0 else 0.5                 # varmast i juli i norr, januari i söder
    return medel + amp * math.cos(2 * math.pi * (manad - fas) / 12), medel


def adiabatisk_hojning(cement: float, flygaska: float) -> float:
    return (cement * (1 - flygaska) * Q_PC + cement * flygaska * Q_FA) / RHO_CP


def bindemedel(cement: float, flygaska: float) -> float:
    return cement * (1 - flygaska) + 0.5 * cement * flygaska


@lru_cache(maxsize=256)
def _simulera(lyft, cement, flygaska, forkylning, kylror, T_luft, alfa=ALFA, noder=21):
    dz = lyft / (noder - 1)
    dt = min(0.4 * dz * dz / alfa if alfa > 0 else 0.05, 0.05)
    steg = int(math.ceil(DAGAR / dt))
    dt = DAGAR / steg
    T_gjut = max(T_luft + 3.0 - forkylning, 4.0)
    T = np.full(noder, T_gjut)
    c_pc, c_fa = cement * (1 - flygaska), cement * flygaska
    inre = slice(1, noder - 1)
    spara_var = max(1, steg // 112)
    tider, karna, yta, profiler = [0.0], [T_gjut], [T_gjut], [T.copy()]
    for n in range(1, steg + 1):
        t = (n - 0.5) * dt
        q = (c_pc * Q_PC * K_PC * math.exp(-K_PC * t) + c_fa * Q_FA * K_FA * math.exp(-K_FA * t)) / RHO_CP
        dT = np.full(noder, q)
        dT[inre] += alfa * (T[:-2] - 2 * T[inre] + T[2:]) / dz ** 2
        # ovansidan: halv cell med värmeförlust till luften
        dT[-1] += alfa * 2 * (T[-2] - T[-1]) / dz ** 2 - 2 * H_LUFT * (T[-1] - T_luft) / dz
        if kylror:
            dT[inre] -= KYLROR * (T[inre] - T_KYLVATTEN)
        T = T + dt * dT
        T[0] = T_luft + 5.0                              # mot äldre lyft
        if n % spara_var == 0 or n == steg:
            tider.append(n * dt)
            karna.append(float(T.max()))
            yta.append(float(T[-1]))
            profiler.append(T.copy())
    return (np.array(tider), np.array(karna), np.array(yta), np.array(profiler),
            np.linspace(0, lyft, noder))


def simulera(p: dict, alfa=ALFA) -> dict:
    t, karna, yta, prof, z = _simulera(float(p["lyft"]), float(p["cement"]), float(p["flygaska"]),
                                       float(p["forkylning"]), bool(p["kylror"]), float(p["T_luft"]),
                                       alfa)
    return {"t": t, "karna": karna, "yta": yta, "profil": prof, "z": z}


def utvardera(p: dict) -> dict:
    s = simulera(p)
    T_max = float(s["karna"].max())
    fall = max(0.0, T_max - float(p.get("T_ar", p["T_luft"])))   # kärnan svalnar till årsmedel
    gradient = float((s["karna"] - s["yta"]).max())
    index = max(fall, gradient) / SPRICKGRANS
    if index <= 1.0:
        utlatande = "No cracks"
    elif index <= 1.3:
        utlatande = "Fine cracks"
    elif index <= 1.7:
        utlatande = "Cracks"
    else:
        utlatande = "Severe cracks"
    sektion_t = 1.0 if index <= 1.0 else 1.0 - 0.3 * min(1.0, (index - 1.0) / 0.8)
    bind = bindemedel(p["cement"], p["flygaska"])
    kostnad = 1 + 0.3 * (bind / 250 - 1) - 0.05 * p["flygaska"]    # cement ≈ 30 % av betongen
    kostnad += 0.05 if p["kylror"] else 0.0
    kostnad += 0.002 * p["forkylning"]
    return {"T_max": T_max, "fall": fall, "gradient": gradient, "index": index,
            "utlatande": utlatande, "sektion_t": sektion_t,
            "hallfast": bind >= KRAV_BINDEMEDEL, "bindemedel": bind,
            "kostnad_faktor": kostnad, "tid_faktor": (1.5 / p["lyft"]) ** 0.4,
            "dT_ad": adiabatisk_hojning(p["cement"], p["flygaska"])}
