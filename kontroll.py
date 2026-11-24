"""
kontroll.py – rimlighetskontroll av modellerna (hav, floddammar, flodnät och kaskad).
Kör:  python kontroll.py
"""

from floder import PLATS, magasin
from bassanger import HAV_DICT, simulera, volym, dammvolym_km3, MINERALER, bering_effekt_MW

# Verkliga värden: (yta km2, volym km3, medeleffekt MW)
VERKLIGT = {
    "yangtze": (1084, 39.3, 11400),
    "colorado": (640, 35.2, 450),
    "nilen": (5250, 132, 1200),
    "parana": (1350, 29, 10000),
    "jenisej": (2000, 73, 2300),
    "zambezi": (5580, 185, 800),
}

print("=== Floddammar: modell mot verklighet ===")
print(f"{'damm':22s} {'yta km2':>16s} {'volym km3':>16s} {'effekt MW':>16s}")
for id_, (A, V, P) in VERKLIGT.items():
    p = PLATS[id_]
    m = magasin(p, p.H_standard)
    print(f"{p.namn:22s} {m['yta_km2']:7.0f} ({A:6.0f}) {m['volym_km3']:7.1f} ({V:6.1f})"
          f" {m['effekt_MW']:7.0f} ({P:6.0f})")

print("\n=== Megaprojekt ===")
for hav in HAV_DICT.values():
    r0 = simulera(hav, d_mal=1e9, ar=10)
    print(f"{hav.namn}: sjunker {r0['sankning'][1]:.2f} m första året, "
          f"dammvolym {dammvolym_km3(hav):.2f} km3")

    # vattenbalans: sjunkningen stämmer med volymen
    assert abs(volym(hav, 0) - hav.V0) < 1

    r = simulera(hav, d_mal=hav.d_standard, ar=500)
    print(f"  mål {hav.d_standard:.0f} m: nivå efter 500 år {r['sankning'][-1]:.1f} m, "
          f"effekt {r['effekt_MW'][-1]:.0f} MW, salthalt {r['salthalt'][-1]:.0f} g/L, "
          f"global havsnivå +{r['global_havsniva_m'][-1]:.2f} m")

    # saltbevarande: sundet stängt för alltid -> totalt salt konstant
    r = simulera(hav, d_mal=1e9, ar=3000)
    V = volym(hav, r["sankning"])
    lost = r["salthalt"] * V
    utfallt = sum(r["lager"][m[0]][-1] * m[3] * hav.A0 for m in MINERALER)
    salt0 = hav.S0 * hav.V0
    fel = abs(lost[-1] + utfallt - salt0) / salt0
    print(f"  stängt 3000 år: sjunkit {r['sankning'][-1]:.0f} m, salthalt "
          f"{r['salthalt'][-1]:.0f} g/L, halitlager {r['lager']['Halite NaCl'][-1]:.1f} m, "
          f"saltbalansfel {fel:.1e}")
    assert fel < 1e-3, "saltet bevaras inte!"

print(f"\nBeringssundet: {bering_effekt_MW(0.5):.0f} MW vid 0,5 m fallhöjd")
from natverk import natverk, flodnamn, kalibrering
from floder import DAMMPLATSER, PLATS, hamta_plats, _punkt_for
nv = natverk()
if nv is None:
    print("\n(flodnätet saknas – kör hamta_floder.py)")
else:
    print(f"\n=== Flodnätet: {nv.n:,} sträckor ===".replace(",", " "))
    k = kalibrering()
    print(f"Flints lag: lutning = {k['k']:.3f} * A^-{k['theta']:.2f}")
    for p in DAMMPLATSER:
        i = int(nv.punkt_strak[_punkt_for(p)])
        kvot = nv.Q[i] / p.Q
        assert 0.33 < kvot < 3, f"{p.namn} hamnar på fel flod"
        assert flodnamn(i) == p.flod, f"{p.namn}: namnet blev {flodnamn(i)}"
    print("Alla kända dammar hamnar på rätt flod med rätt namn")
    _, pp = nv.narmaste(7.6, 47.56)
    pl = hamta_plats(f"p{pp}")
    print(f"Stickprov: {pl.namn} i {pl.flod}, Q = {pl.Q:.0f} m³/s")
    assert pl.flod == "Rhine" and 800 < pl.Q < 1300

    from kaskad import kaskad
    print("\n=== Kaskad: dammar påverkar varandra och havet ===")
    k = kaskad({"nilen": 75, "blanilen": 133})
    assuan, gerd = k["dammar"]["nilen"], k["dammar"]["blanilen"]
    print(f"Assuan: flöde in {assuan['Q_nat']:.0f} -> {assuan['Q_in']:.0f} m³/s med GERD uppströms, "
          f"sediment till deltat {100 * assuan['sed_mynning']:.0f} %")
    print(f"Medelhavet får {k['hav']['gibraltar'] / 1e9:.1f} km³/år mindre flodvatten "
          f"(verkligheten: Nassersjön avdunstar ca 10–16 km³/år)")
    assert gerd["damm_ned"] == "nilen" and assuan["Q_in"] < assuan["Q_nat"]
    assert 5e9 < k["hav"]["gibraltar"] < 25e9
    # en låg damm inne i De tre ravinernas magasin dränks helt
    p3 = _punkt_for(PLATS["yangtze"])
    lo, la, _ = nv.uppstroms_bana(p3, 150)
    _, pp = nv.narmaste(lo[-1], la[-1], 14000)
    k = kaskad({"yangtze": 110, f"p{pp}": 60})
    print(f"Damm 150 km uppströms De tre ravinerna: uppdämd {k['dammar'][f'p{pp}']['uppdamning']:.0f} m, "
          f"fallhöjd {k['dammar'][f'p{pp}']['m']['H_eff']:.0f} m")
    assert k["dammar"][f"p{pp}"]["m"]["H_eff"] == 0

from sankor import SANKOR_LISTA, SANKA_DICT, simulera_sanka, megaprojekt
from terrang import sanka_hypsometri, sanka_lagsta
print("\n=== Sänkor under havsytan (kanalprojekt) ===")
for s in SANKOR_LISTA:
    h, A, V = sanka_hypsometri(s.id)
    r = simulera_sanka(s, s.Q_standard, 500)
    print(f"{s.namn:22s} lägsta {sanka_lagsta(s.id)[2]:5.0f} m, yta under 0 m {A[-1] / 1e6:6.0f} km², "
          f"{s.Q_standard:4.0f} m³/s -> nivå {r['niva'][-1]:6.1f} m efter 500 år, "
          f"{r['effekt_MW'][1]:5.0f} MW år 1")
    # saltbalans: löst + utfällt = det som fanns + det som kom in
    from bassanger import MINERALER as MIN
    vatten = max(r["volym_km3"][-1] * 1e9 + s.V_extra, 1.0) if r["niva"][-1] >= h[0] else None
    salt_in = s.S0 * s.V_extra + sum(r["inflode_m3s"]) * 3.156e7 * 38.0 if s.kalla == "gibraltar" \
        else s.S0 * s.V_extra + sum(r["inflode_m3s"]) * 3.156e7 * 40.0
    utfallt = sum(r["lager"][m[0]][-1] * m[3] * max(A[-1], 1.0) for m in MIN)
    if vatten:
        fel = abs(r["salthalt"][-1] * vatten + utfallt - salt_in) / salt_in
        assert fel < 1e-3, f"{s.namn}: saltbalansfel {fel:.1e}"

q = sanka_hypsometri("qattara")
import numpy as np
A60 = np.interp(-60, q[0], q[1]) / 1e6
print(f"Qattara: {q[1][-1] / 1e6:.0f} km² under havet (litteraturen ca 19 600), "
      f"{A60:.0f} km² vid −60 m (Bassler: ca 12 000)")
assert 17000 < q[1][-1] / 1e6 < 21000 and 10000 < A60 < 14000

d = SANKA_DICT["dodahavet"]
utan = simulera_sanka(d, 0, 10)["niva"]
med = simulera_sanka(d, 60, 10)["niva"]
print(f"Döda havet: utan kanal {utan[10] - utan[0]:+.1f} m på 10 år, med 60 m³/s {med[10] - med[0]:+.1f} m")
assert -13 < utan[10] - utan[0] < -7 and med[10] > med[0]

mp = megaprojekt({"qattara": 600, "gibraltar": 100}, 500)
r = mp["sankor"]["qattara"]
print(f"Qattara + Atlantropa: inflödet stannar när Medelhavet sjunkit under sjön "
      f"(år 1: {r['inflode_m3s'][1]:.0f} m³/s, år 500: {r['inflode_m3s'][-1]:.0f} m³/s)")
assert r["inflode_m3s"][1] > 0 and r["inflode_m3s"][-1] == 0

print("\nAlla kontroller OK")
