"""
karta.py – världskartan: flodnät, magasin, megaprojekt, nya kuster och sjöar.

Används av både sandlådan (app.py) och spelet (spel_app.py).
Kartan byggs EN gång (bas_figur) med ett fast antal lager, och sedan skickas bara
ändringar (karta_patch, flod_patch) som dash.Patch.
"""

from functools import lru_cache

import numpy as np
import plotly.graph_objects as go
from dash import Patch

from floder import DAMMPLATSER, PLATS, hamta_plats, magasin_polygon
from natverk import natverk
from bassanger import HAV, BERING
from terrang import ny_kust, ny_sjo
from sankor import SANKOR_LISTA, SANKA_DICT, megaprojekt


def tal(x, dec=0):
    """Tal med engelsk formatering: 12,345.6"""
    return f"{x:,.{dec}f}"


FARG_FLOD = "#2f6fb3"
FARG_BYGGD = "#d9480f"
FARG_MAGASIN = "rgba(30, 110, 200, 0.55)"
FARG_MEGA = "#a61e4d"
FARG_TORR = "#d8c28a"


# ---------------------------------------------------------------- kartan
#
# Kartan byggs EN gång med ett fast antal lager ("spår"). Sedan skickas bara
# ändringar (dash.Patch), så att flodnätet inte behöver skickas om vid varje klick.

SPAR = ["flod_liten", "flod_mellan", "flod_stor", "nedstroms", "magasin", "sjo", "damm_byggd",
        "damm_forslag",
        "torr", "kust", "etikett", "vald", "floddammar", "megaprojekt"]
S = {namn: i for i, namn in enumerate(SPAR)}
FLOD_KLASSER = [("flod_liten", 0, 1000, 1.0), ("flod_mellan", 1000, 10000, 1.8),
                ("flod_stor", 10000, 1e9, 2.8)]
MEGA = [(h.id, h.sund, h.markor, h.damm_linje) for h in HAV] + \
       [(BERING["id"], BERING["namn"], BERING["markor"], BERING["damm_linje"])] + \
       [(s.id, s.projekt, s.markor, s.kanal) for s in SANKOR_LISTA]


@lru_cache(maxsize=16)
def flodlager(klass, q_min):
    """Linjer för floder i en flödesklass, med punktindex som customdata (för klick)."""
    nv = natverk()
    if nv is None:
        return [], [], []
    _, q_lag, q_hog, _ = next(k for k in FLOD_KLASSER if k[0] == klass)
    lon, lat, cd = [], [], []
    for i in np.nonzero((nv.Q >= max(q_min, q_lag)) & (nv.Q < q_hog))[0]:
        s, e = nv.start[i], nv.start[i + 1]
        idx = list(range(s, e, 2))            # varannan punkt räcker för att rita
        if idx[-1] != e - 1:
            idx.append(e - 1)
        lon += nv.lon[idx].round(3).tolist() + [None]
        lat += nv.lat[idx].round(3).tolist() + [None]
        cd += idx + [None]
    return lon, lat, cd


def tom_spar(namn, **kw):
    return go.Scattergeo(lon=[], lat=[], name=namn, showlegend=False, **kw)


def bas_figur(q_min):
    fig = go.Figure()
    for namn, _lo, _hi, bredd in FLOD_KLASSER:
        lon, lat, cd = flodlager(namn, q_min)
        fig.add_trace(go.Scattergeo(lon=lon, lat=lat, customdata=cd, mode="lines",
                                    line=dict(width=bredd, color="#3d85c6"), name=namn,
                                    showlegend=False,
                                    hovertemplate="Click to build a dam here<extra></extra>"))
    fig.add_trace(go.Scattergeo(lon=[], lat=[], mode="lines", name="Affected downstream",
                                line=dict(width=4, color="rgba(230, 120, 20, 0.75)"),
                                hoverinfo="skip"))
    fig.add_trace(tom_spar("magasin", mode="lines", fill="toself", fillcolor=FARG_MAGASIN,
                           line=dict(width=1, color="#1c5aa6"), hoverinfo="skip"))
    fig.add_trace(tom_spar("sjo", mode="lines", fill="toself", fillcolor="rgba(40, 150, 170, 0.6)",
                           line=dict(width=1, color="#1b7c8c"), hoverinfo="skip"))
    fig.add_trace(tom_spar("damm_byggd", mode="lines", line=dict(width=6, color=FARG_MEGA),
                           hoverinfo="skip"))
    fig.add_trace(tom_spar("damm_forslag", mode="lines",
                           line=dict(width=3, color="#999", dash="dot"), hoverinfo="skip"))
    fig.add_trace(tom_spar("torr", mode="markers", hoverinfo="skip",
                           marker=dict(size=4, color=FARG_TORR, symbol="square")))
    fig.add_trace(tom_spar("kust", mode="lines", line=dict(width=1.5, color="#1c5aa6"),
                           hoverinfo="skip"))
    fig.add_trace(tom_spar("etikett", mode="text", textfont=dict(size=13, color=FARG_MEGA),
                           hoverinfo="skip"))
    fig.add_trace(tom_spar("vald", mode="markers", hoverinfo="skip",
                           marker=dict(size=18, color="rgba(0,0,0,0)",
                                       line=dict(width=2.5, color="black"))))
    fig.add_trace(go.Scattergeo(lon=[], lat=[], mode="markers", name="River dams", hoverinfo="text",
                                marker=dict(symbol="triangle-up", size=11,
                                            line=dict(width=0.5, color="black"))))
    fig.add_trace(go.Scattergeo(lon=[m[2][0] for m in MEGA], lat=[m[2][1] for m in MEGA],
                                customdata=[m[0] for m in MEGA],
                                text=[f"<b>Megaproject</b><br>{m[1]}" for m in MEGA],
                                hoverinfo="text", mode="markers", name="Megaprojects",
                                marker=dict(symbol="diamond", size=15,
                                            line=dict(width=0.5, color="black"))))
    fig.update_geos(
        projection_type="natural earth", projection_rotation=dict(lon=0, lat=0),
        center=dict(lon=0, lat=0),
        resolution=50,
        showland=True, landcolor="#efe9dc", showocean=True, oceancolor="#cfe3f3",
        showlakes=True, lakecolor="#cfe3f3", showrivers=natverk() is None, rivercolor="#6fa8dc",
        showcountries=True, countrycolor="#bbb", coastlinecolor="#777",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), uirevision="karta",
                      legend=dict(x=0.01, y=0.02, bgcolor="rgba(255,255,255,0.7)"),
                      clickmode="event", hoverdistance=8)
    return fig


def med_none(listor):
    """Slår ihop flera (lon, lat)-listor med None emellan."""
    lo, la = [], []
    for l1, l2 in listor:
        lo += list(l1) + [None]
        la += list(l2) + [None]
    return lo, la


def medurs(lo, la):
    """Vänder varje ring (delar mellan None) så att den går medurs.
    På en glob avgör varvriktningen vilken sida som fylls: går ringen åt fel håll
    fyller Plotly hela jorden UTOM polygonen."""
    ut_lo, ut_la, ring_lo, ring_la = [], [], [], []
    for x, y in zip(list(lo) + [None], list(la) + [None]):
        if x is None:
            if len(ring_lo) > 2:
                area2 = sum(ring_lo[i] * ring_la[i + 1] - ring_lo[i + 1] * ring_la[i]
                            for i in range(len(ring_lo) - 1))
                if area2 > 0:                    # moturs -> vänd
                    ring_lo, ring_la = ring_lo[::-1], ring_la[::-1]
                ut_lo += ring_lo + [None]
                ut_la += ring_la + [None]
            ring_lo, ring_la = [], []
        else:
            ring_lo.append(x)
            ring_la.append(y)
    return ut_lo, ut_la


def karta_patch(byggda, vald, projektion, ar):
    p = Patch()

    def satt(spar, **egenskaper):
        for nyckel, varde in egenskaper.items():
            p["data"][S[spar]][nyckel] = varde

    # magasin för byggda floddammar
    lo, la = med_none(magasin_polygon(hamta_plats(k), H) for k, H in byggda.items()
                      if hamta_plats(k))
    satt("magasin", **dict(zip(("lon", "lat"), medurs(lo, la))))

    # påverkad sträcka nedströms (till mynningen)
    mp = megaprojekt(byggda, ar)
    kas = mp["kaskad"]
    lo, la = med_none(i["nedstroms"] for i in kas["dammar"].values() if i["nedstroms"])
    satt("nedstroms", lon=lo, lat=la)

    # megaprojektens dammlinjer
    lo, la = med_none(m[3] for m in MEGA if m[0] in byggda)
    satt("damm_byggd", lon=lo, lat=la)
    lo, la = med_none(m[3] for m in MEGA if m[0] not in byggda)
    satt("damm_forslag", lon=lo, lat=la)

    # sänkta hav: torrlagd botten, ny kustlinje, etikett
    torr_lo, torr_la, kust, et_lo, et_la, et_txt = [], [], [], [], [], []
    for h in HAV:
        if h.id in byggda:
            sankt = mp["hav"][h.id]["sankning"][-1]
            k = ny_kust(h.id, int(round(sankt)))
            if k is not None:
                torr_lo += k["torr_lon"]
                torr_la += k["torr_lat"]
                kust.append(k["kust"])
            et_lo.append(h.centrum[0])
            et_la.append(h.centrum[1])
            et_txt.append(f"{h.namn}<br>−{sankt:.0f} m (year {ar})")
    # nya sjöar i sänkorna
    sjoar = []
    for sid, r in mp["sankor"].items():
        niva = r["niva"][-1]
        kontur = ny_sjo(sid, int(round(niva)))
        if kontur is not None:
            sjoar.append(kontur)
        s_ = SANKA_DICT[sid]
        et_lo.append(s_.markor[0])
        et_la.append(s_.markor[1] - 0.6)
        et_txt.append(f"{s_.namn}<br>{niva:.0f} m")
    lo, la = med_none(sjoar)
    satt("sjo", **dict(zip(("lon", "lat"), medurs(lo, la))))
    satt("torr", lon=torr_lo, lat=torr_la)
    lo, la = med_none(kust)
    satt("kust", lon=lo, lat=la)
    satt("etikett", lon=et_lo, lat=et_la, text=et_txt)

    # ring runt vald plats
    punkt = None
    if vald in {m[0] for m in MEGA}:
        punkt = next(m[2] for m in MEGA if m[0] == vald)
    elif vald and hamta_plats(vald):
        punkt = (hamta_plats(vald).lon, hamta_plats(vald).lat)
    satt("vald", lon=[punkt[0]] if punkt else [], lat=[punkt[1]] if punkt else [])

    # floddammar: kända platser + byggda punkter i flodnätet
    platser = DAMMPLATSER + [hamta_plats(k) for k in byggda
                             if k not in PLATS and hamta_plats(k)]
    satt("floddammar", lon=[q.lon for q in platser], lat=[q.lat for q in platser],
         customdata=[q.id for q in platser],
         text=[f"<b>{q.namn}</b><br>{q.flod}, Q = {tal(q.Q)} m³/s" for q in platser])
    p["data"][S["floddammar"]]["marker"]["color"] = [FARG_BYGGD if q.id in byggda else FARG_FLOD
                                                     for q in platser]
    p["data"][S["megaprojekt"]]["marker"]["color"] = [FARG_MEGA if m[0] in byggda else "#e599b3"
                                                      for m in MEGA]
    p["layout"]["geo"]["projection"]["type"] = projektion
    return p


def flod_patch(q_min):
    p = Patch()
    for namn, *_ in FLOD_KLASSER:
        lon, lat, cd = flodlager(namn, q_min)
        p["data"][S[namn]]["lon"] = lon
        p["data"][S[namn]]["lat"] = lat
        p["data"][S[namn]]["customdata"] = cd
    return p
