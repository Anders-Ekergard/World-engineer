"""
kaskad.py – hur dammar påverkar floden nedströms (och varandra).

För alla byggda floddammar räknas, från källorna mot havet:
  1) Vatten: magasinet avdunstar vatten. Dammar längre ned får mindre flöde
     och ger mindre el. Minskningen följer med ända ut i havet.
         Q_in(B)  = Q_naturligt(B) - summa(förluster från dammar uppströms)
         Q_ut(B)  = Q_in(B) - avdunstning(B)
  2) Sediment: magasinet fångar en andel TE av sedimentet (Brunes kurva).
     Sedimentet antas följa vattnet, så en damm på en biflod med flödet Q_A
     står för andelen Q_A / Q_B av sedimentet vid en damm B längre ned.
         sediment_in(B) = 1 - summa( Q_A/Q_B * (1 - sediment_ut(A)) )
         sediment_ut(B) = sediment_in(B) * (1 - TE_B)
     (andelar av det naturliga sedimentflödet)
  3) Kaskad: ligger dammfoten för dam A inne i magasinet bakom dam B
     (avstånd d längs floden < magasinets längd L_B), dämmer B upp vattnet
     vid A med  H_B * (1 - d/L_B).  A:s fallhöjd minskar lika mycket.
  4) Hav: floder som mynnar i Medelhavet eller Röda havet (eller i Svarta havet,
     som rinner vidare till Medelhavet) ger mindre tillrinning till havsmodellen.

Utan flodnätet (data/floder.npz) räknas varje damm för sig.
"""

from floder import hamta_plats, magasin, _punkt_for, SEK_PER_AR
from natverk import natverk, _nedstroms_cache
from terrang import hav_for_punkt

HAVSNAMN = {"gibraltar": "Mediterranean Sea", "rodahavet": "Red Sea",
            "svarta": "Black Sea (→ Mediterranean)"}


def relationer(dam_ider) -> dict | None:
    """Hur dammarna ligger i förhållande till varandra längs floderna.
    Returnerar punkt, till_hav (km), nedom[A][B] (km från A ned till B),
    narmast_ned[A], direkt_upp[B] och "ordning" (från källorna mot havet).
    None om flodnätet saknas. Används av kaskad() och av spelmotorn."""
    platser = {k: hamta_plats(k) for k in dam_ider if hamta_plats(k)}
    nv = natverk()
    if nv is None:
        return None
    punkt = {k: _punkt_for(p) for k, p in platser.items()}
    till_hav = {k: float(_nedstroms_cache(punkt[k])[2][-1]) for k in platser}
    nedom = {k: {} for k in platser}
    for a in platser:
        for b in platser:
            if a != b:
                d = nv.avstand_nedstroms(punkt[a], punkt[b])
                if d is not None:
                    nedom[a][b] = d
    narmast_ned = {a: min(nedom[a], key=nedom[a].get) if nedom[a] else None for a in platser}
    direkt_upp = {b: [a for a in platser if narmast_ned[a] == b] for b in platser}
    return {"punkt": punkt, "till_hav": till_hav, "nedom": nedom, "narmast_ned": narmast_ned,
            "direkt_upp": direkt_upp, "ordning": sorted(platser, key=lambda k: -till_hav[k])}


def kaskad(byggda: dict) -> dict:
    """byggda = {dam-id: dammhöjd}. Returnerar {"dammar": {id: info}, "hav": {hav_id: m3/år}}.
    Megaprojekten (nycklar som inte är floddammar) hoppas över."""
    platser = {k: hamta_plats(k) for k in byggda if hamta_plats(k)}
    nv = natverk()
    if nv is None:
        return {"dammar": {k: {"m": magasin(p, byggda[k]), "nedstroms": []}
                           for k, p in platser.items()}, "hav": {}}

    rel = relationer(platser)
    punkt, till_hav, nedom = rel["punkt"], rel["till_hav"], rel["nedom"]
    narmast_ned, direkt_upp = rel["narmast_ned"], rel["direkt_upp"]

    # grundgeometri (utan kaskad) behövs för magasinslängder
    L_km = {k: byggda[k] / p.lutning / 1e3 for k, p in platser.items()}

    info = {}
    # från källorna mot havet: längst till havet först
    for b in sorted(platser, key=lambda k: -till_hav[k]):
        p = platser[b]
        i = int(nv.punkt_strak[punkt[b]])
        Q_nat = float(nv.Q[i]) if p.uppskattad else p.Q
        upp = direkt_upp[b]
        forlust = sum(info[a]["Q_nat"] - info[a]["Q_ut"] for a in upp)
        sed_in = 1.0 - sum(min(1.0, info[a]["Q_nat"] / Q_nat) * (1 - info[a]["sed_ut"]) for a in upp)
        sed_in = max(0.0, sed_in)

        # uppdämning vid dammfoten från närmaste damm nedströms
        H = byggda[b]
        uppdamning = 0.0
        c = narmast_ned[b]
        if c is not None and nedom[b][c] < L_km[c]:
            uppdamning = byggda[c] * (1 - nedom[b][c] / L_km[c])
        Q_in = max(Q_nat - forlust, 1e-6)
        m = magasin(p, H, Q=Q_in, H_eff=max(H - uppdamning, 0.0))
        Q_ut = max(Q_in - m["avdunstning_m3s"], 0.0)

        info[b] = {
            "m": m, "Q_nat": Q_nat, "Q_in": Q_in, "Q_ut": Q_ut,
            "sed_in": sed_in, "sed_ut": sed_in * (1 - m["sediment_fangst"]),
            "uppdamning": uppdamning, "damm_ned": c,
            "dammar_upp": upp,
        }

    # vid mynningen: summera de dammar som inte har någon damm nedanför sig
    hav = {}
    for k in platser:
        lo, la, s, _ = _nedstroms_cache(punkt[k])
        info[k]["mynning"] = (float(lo[-1]), float(la[-1]))
        info[k]["till_hav_km"] = float(s[-1])
        info[k]["hav"] = hav_for_punkt(float(lo[-1]), float(la[-1]))
        steg = max(1, len(lo) // 400)
        info[k]["nedstroms"] = (lo[::steg].tolist() + [float(lo[-1])],
                                la[::steg].tolist() + [float(la[-1])])
    for k in platser:
        if narmast_ned[k] is None:
            forlust = info[k]["Q_nat"] - info[k]["Q_ut"]
            h = info[k]["hav"]
            if h:
                mal = "gibraltar" if h == "svarta" else h
                hav[mal] = hav.get(mal, 0.0) + forlust * SEK_PER_AR

    # sediment och flöde som når havet, per flodsystem (sista dammen före mynningen)
    for k in platser:
        sista = k
        while narmast_ned[sista] is not None:
            sista = narmast_ned[sista]
        pos = _nedstroms_cache(punkt[k])[3]
        mynning_strak = max(pos, key=pos.get)          # sista sträckan före havet
        Q_mynning = float(nv.Q[mynning_strak])
        toppar = [a for a in platser if narmast_ned[a] is None
                  and info[a]["mynning"] == info[sista]["mynning"]]
        info[k]["Q_mynning_nat"] = Q_mynning
        info[k]["Q_forlust_mynning"] = sum(info[a]["Q_nat"] - info[a]["Q_ut"] for a in toppar)
        info[k]["sed_mynning"] = max(0.0, 1.0 - sum(
            min(1.0, info[a]["Q_nat"] / Q_mynning) * (1 - info[a]["sed_ut"]) for a in toppar))
    return {"dammar": info, "hav": hav}
