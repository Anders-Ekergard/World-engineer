"""
minispel – frivilliga minispel kopplade till dammbygget.

  labb.py      Kemilabbet: vattenprov (Langeliers mättnadsindex) och ASR-test av ballasten
  gjutning.py  Betonggjutningen: härdningsvärme och sprickrisk i en gjutetapp

effekter(design) räknar ut vad spelarens val betyder för anläggningen. Funktionen är ren
(samma design -> samma resultat), så valen kan sparas i design-dicten och följa med i sparfilen.
"""

from spel.minispel import labb, gjutning


def effekter(design: dict) -> dict:
    """Samlade effekter av minispelen. Nycklar som saknas betyder "ingen ändring":
    damm_faktor, tid_faktor (betongens byggtid), underhall_extra (andel av capex per år),
    kalk, aggressiv, asr, asr_kand, sektion_t."""
    e = {"damm_faktor": 1.0, "tid_faktor": 1.0, "underhall_extra": 0.0}
    betong = design.get("typ") == "betong"
    g = design.get("gjutning") if betong else None
    flygaska = 0.0
    if g:
        r = gjutning.utvardera(g)
        e["damm_faktor"] *= r["kostnad_faktor"]
        e["tid_faktor"] *= r["tid_faktor"]
        e["sektion_t"] = r["sektion_t"]
        flygaska = g["flygaska"]
    lv = design.get("labb")
    if lv:
        r = labb.utvardera(lv, betong, flygaska)
        e["damm_faktor"] *= r["kostnad_faktor"]
        e["underhall_extra"] += r["underhall_extra"]
        if r["kalk"] is not None:                # vattenprovet är gjort
            e.update(kalk=r["kalk"], aggressiv=r["aggressiv"])
        if r["asr"] is not None:                 # ballasten är testad: ingenjören vet
            e.update(asr=r["asr"], asr_kand=True)
    return e
