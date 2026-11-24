"""
bassanger.py – megaprojekten: dammar över sund som stänger av ett innanhav.

Varje hav är en "låda" (box model) med vatten- och saltbalans, tidssteg 1 år.

Vattenbalans (d = hur många meter havsytan har sjunkit):
    netto = (P - E*a_w) * A(d) + floder + övrigt_inflöde        [m3/år]
    netto < 0  => havet förlorar vatten (avdunstningsunderskott)
    Utan damm fylls underskottet på genom sundet, så nivån ligger still.
    Med damm stängs sundet. Havet sjunker tills målnivån nås. Sedan släpper
    turbinerna in precis så mycket havsvatten att nivån hålls, och det ger el:
        P_el = rho * g * Q_in * d * eta

Hypsometri (hur ytan krymper när havet sjunker):
    Med ETOPO1-data (hamta_etopo.py): verklig tabell A(d), V(d) från havsbottnen.
    Utan data, en enkel formel:
    A(d) = A0 * (1 - d/dmax)^p        med p + 1 = dmax / medeldjup
    V(d) = V0 * (1 - d/dmax)^(p+1)

Saltbalans (kemi):
    Salt följer med inflödet men avdunstar inte. Med damm finns inget utflöde
    av tungt saltvatten längs botten (så fungerar Gibraltar i dag), så saltet
    ansamlas även när nivån hålls konstant.
    Mineraler faller ut i evaporitordning när havet koncentreras:
        CaCO3 (kalcit) -> CaSO4·2H2O (gips) -> NaCl (halit) -> Mg-/K-salter
    Vattnets aktivitet a_w sjunker i stark saltlösning, så avdunstningen
    minskar (ungefär 0,75 vid halitmättnad).
"""

from dataclasses import dataclass, field
import numpy as np

RHO = 1025.0          # havsvattnets densitet, kg/m3
G = 9.81
ETA = 0.90
VARLDSHAVET_YTA = 3.61e14   # m2, för global havsnivå

# Mineraler: (namn, massandel av havssaltet, total salthalt när utfällning börjar [g/L], densitet kg/m3)
MINERALER = [
    ("Calcite CaCO3", 0.003, 70.0, 2710.0),
    ("Gypsum CaSO4·2H2O", 0.036, 130.0, 2320.0),
    ("Halite NaCl", 0.778, 350.0, 2160.0),
    # resten: Mg- och K-salter (epsomit, karnallit ...) faller ut sist, när havet nästan är torrt
    ("Mg/K salts", 0.183, 450.0, 1700.0),
]


@dataclass
class Hav:
    id: str
    namn: str
    sund: str
    A0: float            # yta, m2
    V0: float            # volym, m3
    dmax: float          # största djup, m
    E: float             # avdunstning, m/år
    P: float             # nederbörd, m/år
    floder: float        # tillrinning från floder, m3/år
    ovrigt: float        # annat inflöde (t.ex. Svarta havet), m3/år
    S0: float            # salthalt i dag, g/L
    S_ocean: float       # salthalt i vattnet utanför sundet, g/L
    sund_bredd: float    # m
    sund_djup: float     # m (tröskeldjup där dammen byggs)
    markor: tuple        # (lon, lat) för klickbar symbol
    damm_linje: tuple    # ((lon1, lon2), (lat1, lat2))
    centrum: tuple       # (lon, lat) för etikett på kartan
    info: str = ""
    d_standard: float = 100.0
    d_max: float = 1000.0
    hyps: tuple | None = None   # (d, A, V) från ETOPO1, annars None


def hypsometri_p(hav: Hav) -> float:
    return hav.dmax / (hav.V0 / hav.A0) - 1.0


def yta(hav: Hav, d):
    if hav.hyps is not None:
        return np.interp(d, hav.hyps[0], hav.hyps[1])
    return hav.A0 * np.clip(1 - d / hav.dmax, 0, 1) ** hypsometri_p(hav)


def volym(hav: Hav, d):
    if hav.hyps is not None:
        return np.interp(d, hav.hyps[0], hav.hyps[2])
    return hav.V0 * np.clip(1 - d / hav.dmax, 0, 1) ** (hypsometri_p(hav) + 1)


def djup_fran_volym(hav: Hav, V):
    if hav.hyps is not None:
        # V minskar med d, så tabellen vänds för np.interp
        return np.interp(V, hav.hyps[2][::-1], hav.hyps[0][::-1])
    return hav.dmax * (1 - (V / hav.V0) ** (1 / (hypsometri_p(hav) + 1)))


def vattenaktivitet(S):
    """Förenklad: a_w = 1 i sötvatten, ca 0,75 vid halitmättnad (350 g/L)."""
    return max(0.5, 1.0 - 0.25 * S / 350.0)


def fall_ut(lost: dict, utfallt: dict, V: float):
    """Utfällning: inget mineral kan ha högre halt än vid sin mättnad.
    Överskottet flyttas från `lost` till `utfallt` (kg). Ändrar i dicten."""
    for namn, andel, S_start, _rho in MINERALER:
        max_lost = andel * S_start * V
        if lost[namn] > max_lost:
            utfallt[namn] += lost[namn] - max_lost
            lost[namn] = max_lost


def dammvolym_km3(hav: Hav, kronbredd=50.0, slant=2.0) -> float:
    """Fyllnadsdamm med släntlutning 1:2 över ett V-format sund.
    Medeltvärsnitt = kronbredd*D/2 + slant*D^2/3."""
    D = hav.sund_djup
    return hav.sund_bredd * (kronbredd * D / 2 + slant * D ** 2 / 3) / 1e9


def simulera(hav: Hav, d_mal: float, ar: int, byggd: bool = True,
             floder_minskning=0.0) -> dict:
    """Simulerar havet i `ar` år. d_mal = hur många meter havet får sjunka
    innan turbinerna börjar släppa in vatten. floder_minskning = hur mycket
    mindre sötvatten (m3/år) som når havet p.g.a. floddammar (kaskad.py) och
    kanaler till sänkor (sankor.py). Ett tal, eller en array med ett värde per år."""
    minskning = np.broadcast_to(np.asarray(floder_minskning, dtype=float), (ar + 1,))
    n = ar + 1
    t = np.arange(n)
    d = np.zeros(n)
    S = np.zeros(n)
    Q_in = np.zeros(n)            # m3/s genom dammen/sundet
    effekt = np.zeros(n)          # MW
    lager = {m[0]: np.zeros(n) for m in MINERALER}   # utfällt lager, m

    V = hav.V0
    # löst salt per komponent, kg (g/L == kg/m3)
    lost = {m[0]: m[1] * hav.S0 * V for m in MINERALER}
    utfallt = {m[0]: 0.0 for m in MINERALER}
    S[0] = hav.S0

    for i in range(1, n):
        di = djup_fran_volym(hav, V)
        A = yta(hav, di)
        netto = ((hav.P - hav.E * vattenaktivitet(S[i - 1])) * A
                 + hav.floder + hav.ovrigt - minskning[i])

        if not byggd:
            # naturligt: sundet fyller på underskottet, saltet exporteras
            inflode = max(-netto, 0.0)
            V_ny = V
            salt_in = 0.0          # in- och utflöde av salt i jämvikt
            fallhojd = 0.0
        elif di < d_mal:
            inflode = 0.0          # sundet stängt, havet sjunker
            V_ny = V + netto
            salt_in = 0.0
            fallhojd = di
        else:
            inflode = max(-netto, 0.0)   # turbinerna håller nivån
            V_ny = V + netto + inflode
            salt_in = inflode * hav.S_ocean
            fallhojd = di

        V = max(V_ny, 1.0)
        for m in MINERALER:
            lost[m[0]] += m[1] * salt_in

        fall_ut(lost, utfallt, V)

        d[i] = djup_fran_volym(hav, V)
        S[i] = sum(lost.values()) / V
        Q_in[i] = inflode / 3.156e7
        effekt[i] = RHO * G * Q_in[i] * fallhojd * ETA / 1e6
        for namn, _a, _s, rho_min in MINERALER:
            lager[namn][i] = utfallt[namn] / rho_min / hav.A0   # medeltjocklek

    tapp = hav.V0 - volym(hav, d)
    return {
        "t": t,
        "sankning": d,
        "salthalt": S,
        "inflode_m3s": Q_in,
        "effekt_MW": effekt,
        "lager": lager,
        "torrlagt_km2": (hav.A0 - yta(hav, d)) / 1e6,
        "global_havsniva_m": tapp / VARLDSHAVET_YTA,
    }


HAV = [
    Hav("gibraltar", "Mediterranean Sea", "Strait of Gibraltar (Atlantropa)",
        A0=2.5e12, V0=3.75e15, dmax=5000, E=1.25, P=0.45,
        floder=4.0e11, ovrigt=3.0e11, S0=38.0, S_ocean=36.0,
        sund_bredd=20e3, sund_djup=300,
        markor=(-5.6, 35.95), damm_linje=((-5.61, -5.47), (36.00, 35.91)),
        centrum=(18.0, 35.0), d_standard=100, d_max=1500,
        info="Herman Sörgel's Atlantropa (1928): lower the Mediterranean by 100–200 m, "
             "reclaim land and build a giant power station. Between 5.9 and 5.3 million years "
             "ago the strait closed naturally and the Mediterranean almost dried up "
             "(the Messinian salinity crisis), leaving salt layers up to 1–2 km thick."),
    Hav("rodahavet", "Red Sea", "Bab-el-Mandeb",
        A0=4.38e11, V0=2.33e14, dmax=3040, E=2.0, P=0.06,
        floder=0.0, ovrigt=0.0, S0=40.0, S_ocean=36.5,
        sund_bredd=26e3, sund_djup=200,
        markor=(43.4, 12.58), damm_linje=((43.47, 43.33), (12.67, 12.48)),
        centrum=(38.5, 20.5), d_standard=50, d_max=1000,
        info="The Red Sea has almost no rivers and one of the highest evaporation rates "
             "in the world (about 2 m/year). If Bab-el-Mandeb is closed, the sea drops fast "
             "and turns into a brine lake. The idea has been discussed for hydropower."),
]

HAV_DICT = {h.id: h for h in HAV}

# Verklig hypsometri från ETOPO1 om datafilerna finns (annars gäller formeln ovan)
from terrang import hypsometri
for _h in HAV:
    _t = hypsometri(_h.id)
    if _t is not None:
        _h.hyps = _t
        _h.A0, _h.V0, _h.dmax = float(_t[1][0]), float(_t[2][0]), float(_t[0][-1])


# Beringssundet: ingen nivåeffekt att tala om, bara strömmar och klimat.
BERING = {
    "id": "bering",
    "namn": "Bering Strait",
    "markor": (-168.9, 65.85),
    "damm_linje": ((-169.65, -168.09), (66.08, 65.64)),
    "bredd": 82e3,
    "djup": 50.0,
    "flode_Sv": 0.8,      # Stilla havet -> Norra ishavet, 1 Sv = 1e6 m3/s
    "fallhojd_m": 0.5,    # Stilla havet ligger ca 0,5 m högre
    "info": ("About 0.8 Sv (800,000 m³/s) flows through the strait from the Pacific to the "
             "Arctic Ocean. The difference in level is only about 0.5 m, so the power station "
             "would be small. The big effects are on the climate: the Arctic would get less heat "
             "and less fresh water from the Pacific. That could affect the sea ice and the "
             "Atlantic Meridional Overturning Circulation (AMOC), but model studies disagree "
             "on how. SPECULATIVE – shown only qualitatively."),
}


def bering_effekt_MW(fallhojd_m: float) -> float:
    return RHO * G * BERING["flode_Sv"] * 1e6 * fallhojd_m * ETA / 1e6


def bering_dammvolym_km3(kronbredd=50.0, slant=2.0) -> float:
    D = BERING["djup"]
    return BERING["bredd"] * (kronbredd * D / 2 + slant * D ** 2 / 3) / 1e9
