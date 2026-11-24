"""
spel_app.py – "Världsingenjören": turbaserat byggspel med dammar och megaprojekt.

Kör:   python spel_app.py        (även från Thonny)
Öppna: http://127.0.0.1:8060

Spelmotorn finns i paketet spel/ (fristående från Dash). Sandlådan är kvar i app.py.
"""

import webbrowser
from threading import Timer

import plotly.graph_objects as go
from dash import Dash, html, dcc, Input, Output, State, ctx, no_update, ALL, Patch

from floder import DAMMPLATSER, PLATS, hamta_plats
from bassanger import HAV_DICT, BERING
from sankor import SANKA_DICT
from karta import bas_figur, karta_patch, flod_patch, tal, S
from spel import komponenter as K
from spel import hydrologi as HY
from spel.anlaggning import STANDARD_DESIGN, forhandskalkyl
from spel.geografi import zon_for, region_namn
from spel.motor import nasta_manad, utfor, datum, mega_kalkyl, megaresultat
from spel.tillstand import nytt_spel, till_json, fran_json, spara, ladda, sparade_spel
import minispel_ui
import scenario_ui
from spel import scenarier as SC

MEGA_IDER = set(HAV_DICT) | {"bering"} | set(SANKA_DICT)
FARG_OK, FARG_GUL, FARG_ORANGE, FARG_ROD, FARG_SVART = "#2f9e44", "#f2c200", "#f08c00", "#e03131", "#212529"
FARG_REP, FARG_OKAND, FARG_BYGGE = "#4dabf7", "#adb5bd", "#868e96"
STATUS_NAMN = {"drift": "in operation", "bygge": "under construction", "havererad": "failed",
               "riven": "demolished"}
TYP_NAMN = {"betong": "concrete", "fyllning": "embankment"}


def farg(t: float) -> str:
    if t >= 0.8:
        return FARG_OK
    if t >= 0.5:
        return FARG_GUL
    if t >= 0.25:
        return FARG_ORANGE
    return FARG_ROD if t > 0 else FARG_SVART


def komp_farg(anl, namn) -> str:
    c = anl["komp"][namn]
    if c["rep"]:
        return FARG_REP
    if not K.synlig(anl, namn):
        return FARG_OKAND
    if namn == "karna" and c["sedd"]:
        return FARG_ROD
    return farg(c["t"])


def struktur_min(anl) -> float:
    return min(c["t"] for n, c in anl["komp"].items()
               if K.slag(n) in ("sektion", "fundament", "utskov", "karna") and K.synlig(anl, n))


# ---------------------------------------------------------------- skadepanelen

def _sektion_polygon(xa, xb, krona=5.0, mitt=5.0, lutning=1.2):
    mark = lambda x: abs(x - mitt) * lutning
    pts = [(xa, krona), (xb, krona), (xb, mark(xb))]
    if xa < mitt < xb:
        pts.append((mitt, 0.0))
    pts.append((xa, mark(xa)))
    pts.append((xa, krona))
    return [p[0] for p in pts], [p[1] for p in pts]


def schema(anl: dict, vald_komp: str | None) -> go.Figure:
    """Dammen sedd framifrån, som skadeskärmen i ett krigsfartygsspel.
    Varje del färgas efter sitt tillstånd. Klicka för att välja en del."""
    fig = go.Figure()
    kant = 5.0 / 1.2
    # dalen
    fig.add_trace(go.Scatter(x=[-0.5, 5 - kant - 0.5, 5, 5 + kant + 0.5, 10.5, 10.5, -0.5, -0.5],
                             y=[5.6, 5.6, 0, 5.6, 5.6, -2.6, -2.6, 5.6], fill="toself",
                             fillcolor="#e9e2d0", line=dict(width=0), hoverinfo="skip"))
    k = anl["komp"]
    klick_x, klick_y, klick_namn, klick_text = [], [], [], []

    def del_(namn, x, y, text_extra=""):
        c = k[namn]
        tillstand = f"{100 * c['t']:.0f}%" if K.synlig(anl, namn) else "unknown (monitoring required)"
        hover = f"<b>{K.visningsnamn(namn)}</b><br>Condition: {tillstand}{text_extra}"
        if c["rep"]:
            hover += f"<br>Repair: {c['rep']} months remaining"
        fig.add_trace(go.Scatter(x=x, y=y, fill="toself", fillcolor=komp_farg(anl, namn),
                                 line=dict(width=3 if namn == vald_komp else 1,
                                           color="black" if namn == vald_komp else "#495057"),
                                 hoverinfo="skip", mode="lines"))
        # Plotly klickar på punkter, inte på ytor: en osynlig punkt mitt i delen
        klick_x.append(sum(x[:-1]) / (len(x) - 1))
        klick_y.append(sum(y[:-1]) / (len(y) - 1))
        klick_namn.append(namn)
        klick_text.append(hover)

    # fundament (strimma under dammen)
    xs = [5 - kant, 5, 5 + kant]
    del_("fundament", xs + xs[::-1] + [xs[0]], [5, -0.05, 5, 4.6, -0.45, 4.6, 5])
    # tre sektioner
    for namn, xa, xb in (("sektion_v", 5 - kant, 3.9), ("sektion_m", 3.9, 6.1), ("sektion_h", 6.1, 5 + kant)):
        x, y = _sektion_polygon(xa, xb)
        extra = "<br>ASR detected: the concrete is swelling" if anl["asr_kand"] else ""
        del_(namn, x, y, extra)
    # core
    if "karna" in k:
        c = k["karna"]
        extra = f"<br><b>INTERNAL EROSION {100 * c['dold']:.0f}%</b>" if c["sedd"] else ""
        del_("karna", [1.6, 8.4, 8.4, 1.6, 1.6], [3.2, 3.2, 3.6, 3.6, 3.2], extra)
    # spillway channel and gates
    del_("utskov", [4.45, 5.55, 5.55, 4.45, 4.45], [1.2, 1.2, 4.5, 4.5, 1.2],
         f"<br>Capacity {tal(anl['Q_utskov'])} m³/s")
    luckor = [n for n in k if K.slag(n) == "lucka"]
    bredd = 2.6 / max(len(luckor), 1)
    for i, n in enumerate(luckor):
        x0 = 3.7 + i * bredd
        del_(n, [x0 + 0.05, x0 + bredd - 0.05, x0 + bredd - 0.05, x0 + 0.05, x0 + 0.05],
             [4.55, 4.55, 5.25, 5.25, 4.55])
    fig.add_trace(go.Scatter(x=klick_x, y=klick_y, mode="markers", customdata=klick_namn,
                             text=klick_text, hovertemplate="%{text}<extra></extra>",
                             marker=dict(size=26, opacity=0)))
    # kraftstationen med turbiner
    turbiner = [n for n in k if K.slag(n) == "turbin"]
    fig.add_trace(go.Scatter(x=[1.2, 8.8, 8.8, 1.2, 1.2], y=[-2.3, -2.3, -0.9, -0.9, -2.3],
                             fill="toself", fillcolor="#dee2e6", line=dict(color="#868e96"),
                             hoverinfo="skip"))
    for i, n in enumerate(turbiner):
        x = 1.2 + 7.6 * (i + 0.5) / len(turbiner)
        av = n in anl["avstangda"]
        fig.add_trace(go.Scatter(
            x=[x], y=[-1.6], mode="markers+text", text=["off" if av else ""], textfont=dict(size=9),
            marker=dict(size=min(30, 200 / len(turbiner)), color=komp_farg(anl, n),
                        symbol="circle-x" if av else "circle",
                        line=dict(width=3 if n == vald_komp else 1, color="black")),
            customdata=[n], hovertemplate=f"<b>{K.visningsnamn(n)}</b><br>Condition: "
                                          f"{100 * k[n]['t']:.0f}%{' (shut down)' if av else ''}<extra></extra>"))
    # reservoir level
    f = anl["senast"].get("fyllnad", anl["V"] / max(anl["V_max"], 1))
    fig.add_annotation(x=-0.3, y=5.4, xanchor="left", showarrow=False, font=dict(size=11, color="#1c5aa6"),
                       text=f"Reservoir {100 * f:.0f}% full")
    fig.update_layout(showlegend=False, height=300, margin=dict(l=5, r=5, t=5, b=5),
                      xaxis=dict(visible=False, range=[-0.5, 10.5]),
                      yaxis=dict(visible=False, range=[-2.6, 5.8], scaleanchor="x"),
                      plot_bgcolor="white", clickmode="event")
    return fig


# ---------------------------------------------------------------- paneler

def rad(etikett, varde):
    return html.Tr([html.Td(etikett), html.Td(varde, style={"textAlign": "right", "fontWeight": "bold"})])


def knapp(text, namn, klass=""):
    return html.Button(text, id={"aktion": namn}, className=klass)


def bygg_formular(vald, t):
    p = hamta_plats(vald)
    d = STANDARD_DESIGN
    design = html.Div([
        html.Label("Dam type"),
        dcc.RadioItems(id="b-typ", value=d["typ"], inline=True,
                       options=[{"label": " Concrete ", "value": "betong"},
                                {"label": " Embankment (earth/rock) ", "value": "fyllning"}]),
        html.Label("Head (m)"),
        dcc.Slider(id="b-H", min=5, max=p.H_max, step=1, value=min(p.H_standard, p.H_max),
                   tooltip={"placement": "bottom"}, marks=None),
        html.Label("Spillway is designed for"),
        dcc.RadioItems(id="b-T", value=1000, inline=True,
                       options=[{"label": f" {T}-year flood ", "value": T} for T in (100, 1000, 10000)]),
        html.Label("Seismic design (g)"),
        dcc.RadioItems(id="b-seis", value=0.15, inline=True,
                       options=[{"label": f" {g} ", "value": g} for g in (0.15, 0.3, 0.5)]),
        html.Label("Number of turbines"),
        dcc.Slider(id="b-nturb", min=1, max=12, step=1, value=4, marks=None,
                   tooltip={"placement": "bottom"}),
        html.Label("Utilization (turbine flow / mean flow)"),
        dcc.Slider(id="b-utb", min=0.5, max=2.0, step=0.1, value=1.3, marks=None,
                   tooltip={"placement": "bottom"}),
        html.Label("Monitoring"),
        dcc.RadioItems(id="b-overv", value=1, inline=True,
                       options=[{"label": " none ", "value": 0}, {"label": " normal ", "value": 1},
                                {"label": " extensive ", "value": 2}]),
        dcc.Checklist(id="b-reserv", value=["ja"], options=[{"label": " backup power for gates", "value": "ja"}]),
    ])
    return html.Div([
        html.H4(f"Build: {p.namn} – {p.flod}"),
        html.P("The mini-games are optional. If you skip them, the dam's chemistry stays unknown and "
               "the concrete is placed according to the standard plan.", style={"fontSize": "0.8em", "color": "#666"}),
        dcc.Tabs(value="design", children=[dcc.Tab(label="Design", value="design", children=design)]
                 + minispel_ui.minispel_flikar(t, vald, d["typ"])),
        html.Div(id="b-forhand", style={"margin": "8px 0"}),
        html.Button("Start construction", id="b-start", className="bygg"),
    ])


def mega_formular(vald):
    if vald in HAV_DICT:
        h = HAV_DICT[vald]
        namn, etikett, lo, hi, steg, v = h.sund, "Permitted lowering (m)", 0, h.d_max, 5, h.d_standard
    elif vald in SANKA_DICT:
        s = SANKA_DICT[vald]
        namn, etikett, lo, hi, steg, v = s.projekt, "Canal capacity (m³/s)", 5, s.Q_max, 5, s.Q_standard
    else:
        namn, etikett, lo, hi, steg, v = "Bering Dam", "Head (m)", 0.1, 1.0, 0.1, BERING["fallhojd_m"]
    return html.Div([
        html.H4(f"Megaproject: {namn}"),
        html.Label(etikett),
        dcc.Slider(id="m-varde", min=lo, max=hi, step=steg, value=v, marks=None,
                   tooltip={"placement": "bottom"}),
        html.Div(id="m-forhand", style={"margin": "8px 0"}),
        html.Button("Start megaproject", id="m-start", className="bygg"),
    ])


def anl_panel(t, a, vald_komp):
    if a["status"] == "bygge":
        klart = 1 - a["bygg_kvar"] / a["bygg_tot"]
        return html.Div([
            html.H4(f"{a['namn']} – {a['flod']}"),
            html.P(f"Under construction: {100 * klart:.0f}% complete, about {tal(a['bygg_kvar'] / 12, 1)} years left."
                   + (" Construction halted by protests!" if a.get("protest") else "")),
            html.Div(html.Div(style={"width": f"{100 * klart:.0f}%", "height": "10px",
                                     "background": FARG_BYGGE}),
                     style={"background": "#eee", "width": "100%"}),
        ])
    if a["status"] == "havererad":
        return html.Div([html.H4(f"{a['namn']} – FAILED"),
                         html.P(f"The dam failed {datum(t, a['haveri']['manad'])}: {a['haveri']['orsak']}."),
                         knapp("Demolish remains", "riv")])
    if a["status"] == "riven":
        return html.Div([html.H4(f"{a['namn']} – demolished"), html.P("The river flows freely.")])

    s = a["senast"]
    T_nu = HY.aterkomsttid(a["id"], K.utskov_kapacitet(a, K.antal(a, "lucka")) + a["utbyggnad"] * hamta_plats(a["id"]).Q)
    zon = zon_for(a["lon"], a["lat"])
    info = html.Table([
        rad("Type / head", f"{TYP_NAMN[a['typ']]}, {tal(a['H'])} m"),
        rad("Inflow (natural)", f"{tal(s.get('Q_in', 0))} ({tal(s.get('Q_nat', 0))}) m³/s"),
        rad("Power now", f"{tal(s.get('P_MW', 0))} MW, {s.get('turbiner', 0)} of {K.antal(a, 'turbin')} turbines"),
        rad("Reservoir", f"{100 * s.get('fyllnad', 0):.0f}% full, {100 * a['sediment'] / a['V_max']:.0f}% silted up"),
        rad("Spillway can handle today", f"about a {tal(min(T_nu, 1e6))}-year flood"),
        rad("Seismic zone", f"{zon[0]} (designed for {a['seismik_g']} g)" if zon else "low risk"),
        rad("Maintenance", f"${tal(a['capex'] * [0, 0.005, 0.012][a['underhall']])} M/year"),
    ], className="tabell")

    komp_ruta = html.P("Click a dam component to inspect and repair it.", style={"color": "#666", "fontSize": "0.85em"})
    if vald_komp and vald_komp in a["komp"]:
        c = a["komp"][vald_komp]
        kost = K.reparationskostnad(a, vald_komp)
        knappar = [knapp(f"Repair (${tal(kost)} M, {K.REPARATION[K.slag(vald_komp)][1]} months)",
                         "reparera", "bygg") if not c["rep"] else html.Span("Repairing… ")]
        if K.slag(vald_komp) == "turbin":
            av = vald_komp in a["avstangda"]
            knappar.append(knapp("Start turbine" if av else "Shut down turbine", "turbin"))
        komp_ruta = html.Div([
            html.B(K.visningsnamn(vald_komp)),
            html.Span(f" – {100 * c['t']:.0f}%" if K.synlig(a, vald_komp) else " – condition unknown"),
            html.Div(knappar, style={"marginTop": "4px"}),
        ], style={"background": "#f1f3f5", "padding": "6px", "borderRadius": "4px"})

    return html.Div([
        html.H4(f"{a['namn']} – {a['flod']}"),
        dcc.Graph(id="schema", figure=schema(a, vald_komp), config={"displayModeBar": False}),
        html.Div([html.Span("■ ", style={"color": c_}) for c_ in (FARG_OK, FARG_GUL, FARG_ORANGE, FARG_ROD)] +
                 [html.Span(" condition  "), html.Span("■ ", style={"color": FARG_REP}), html.Span("repairing  "),
                  html.Span("■ ", style={"color": FARG_OKAND}), html.Span("unknown")], style={"fontSize": "0.8em"}),
        komp_ruta,
        html.Hr(), info,
        html.Label("Maintenance level"),
        dcc.RadioItems(id={"inst": "underhall"}, value=a["underhall"], inline=True,
                       options=[{"label": " none ", "value": 0}, {"label": " normal ", "value": 1},
                                {"label": " high ", "value": 2}]),
        html.Label("Operating mode"),
        dcc.RadioItems(id={"inst": "drift"}, value=a["drift"], inline=True,
                       options=[{"label": " normal ", "value": "normal"},
                                {"label": " flood control ", "value": "flodskydd"},
                                {"label": " conserve water ", "value": "torka"},
                                {"label": " lower reservoir ", "value": "sank"}]),
        html.Div([
            knapp("Inspect", "inspektera"),
            knapp("Upgrade monitoring", "overvakning") if a["overvakning"] < 2 else None,
            knapp("Backup power ($20 M)", "reservkraft") if not a["reservkraft"] else None,
            knapp("Demolish dam", "riv"),
        ], style={"marginTop": "8px"}),
    ])


def mega_panel(t, mid):
    m = t["mega"][mid]
    if m["status"] == "bygge":
        klart = 1 - m["bygg_kvar"] / m["bygg_tot"]
        return html.Div([html.H4("Megaproject under construction"),
                         html.P(f"{100 * klart:.0f}% complete, about {tal(m['bygg_kvar'] / 12, 1)} years left.")])
    mr, ar = megaresultat(t)
    rader = [rad("In operation since", datum(t, m["klar"]))]
    if mr is not None and mid in mr["hav"]:
        r = mr["hav"][mid]
        i = min(ar, len(r["sankning"]) - 1)
        rader += [rad("Sea level drop", f"{tal(r['sankning'][i])} m"),
                  rad("Power", f"{tal(r['effekt_MW'][i])} MW"),
                  rad("Salinity", f"{tal(r['salthalt'][i])} g/L")]
    elif mr is not None and mid in mr["sankor"]:
        r = mr["sankor"][mid]
        i = min(ar, len(r["niva"]) - 1)
        rader += [rad("Lake level", f"{tal(r['niva'][i])} m"),
                  rad("Power", f"{tal(r['effekt_MW'][i])} MW"),
                  rad("Salinity", f"{tal(r['salthalt'][i])} g/L")]
    return html.Div([html.H4("Megaproject in operation"), html.Table(rader, className="tabell")])


def oversikt(t):
    acc = t["acceptans"]
    staplar = [html.Div([
        html.Span(region_namn(r), style={"display": "inline-block", "width": "110px"}),
        html.Div(style={"display": "inline-block", "width": f"{v * 2:.0f}px", "height": "10px",
                        "background": farg(v / 100)}),
        html.Span(f" {v:.0f}")]) for r, v in sorted(acc.items())]
    i_drift = [a for a in t["anlaggningar"].values() if a["status"] == "drift"]
    varsta = sorted(i_drift, key=struktur_min)[:5]
    return html.Div([
        html.H4("Overview"),
        html.P("Click a river or ▲ to build, an existing dam to manage it, "
               "or ◆ for a megaproject.", style={"fontSize": "0.85em", "color": "#555"}),
        html.B("Acceptance by region"), html.Div(staplar, style={"fontSize": "0.85em"}),
        html.Br(),
        html.B("Dams in poorest condition"),
        html.Ul([html.Li(f"{a['namn']}: {100 * struktur_min(a):.0f}%",
                         style={"color": farg(struktur_min(a))}) for a in varsta]),
    ])


def logg_vy(t):
    farger = {"info": "#495057", "varning": "#e8590c", "fara": "#c92a2a"}
    return [html.Div([html.Span(datum(t, l["m"]) + " ", style={"color": "#999"}),
                      html.Span(l["text"], style={"color": farger[l["niva"]],
                                                  "fontWeight": "bold" if l["niva"] == "fara" else "normal"})],
                     style={"fontSize": "0.8em", "marginBottom": "3px"})
            for l in reversed(t["logg"][-40:])]


def topprad(t):
    r = t.get("senaste_rapport") or {}
    hist = t["historik"]
    def ruta(v, etikett, farg_=None):
        return html.Div([html.Div(v, className="siffra", style={"color": farg_} if farg_ else None),
                         html.Div(etikett)], className="ruta")
    acc = sum(t["acceptans"].values()) / len(t["acceptans"])
    return [
        ruta(datum(t), "date"),
        ruta(f"{t['budget'] / 1e3:,.1f}", "budget, $ billion", FARG_ROD if t["budget"] < 0 else None),
        ruta(f"{(r.get('intakt', 0) + t.get('anslag_per_ar', 4000) / 12 - r.get('kostnad', 0)):+,.0f}",
             "$ M last month"),
        ruta(tal(hist["TWh_ar"][-1] if hist["TWh_ar"] else 0), "TWh/year"),
        ruta(f"{acc:.0f}", "acceptance", farg(acc / 100)),
        ruta(f"{t['klimat']['co2_sparad_Gt']:.2f}", "Gt CO₂ avoided"),
        ruta(tal(t["stat"]["dodsoffer"]), "fatalities", FARG_ROD if t["stat"]["dodsoffer"] else None),
    ]


# ---------------------------------------------------------------- layout

app = Dash(__name__, title="World Engineer", suppress_callback_exceptions=True)
app.index_string = app.index_string.replace("</head>", """<style>
body { font-family: system-ui, sans-serif; margin: 0; background: #fafafa; color: #222; }
.huvud { display: flex; height: 100vh; }
.karta { flex: 1 1 60%; min-width: 0; display: flex; flex-direction: column; position: relative; }
.panel { flex: 0 0 460px; overflow-y: auto; padding: 10px 14px; background: white; border-left: 1px solid #ddd; }
.rutor { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 8px; align-items: center; }
.ruta { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 3px 9px; font-size: 0.75em; color: #555; }
.siffra { font-size: 1.3em; font-weight: bold; color: #222; }
.tabell { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.tabell td { padding: 2px 4px; border-bottom: 1px solid #eee; }
button { padding: 5px 12px; margin: 2px 4px 2px 0; border-radius: 4px; border: 1px solid #888; cursor: pointer; background: white; }
button.bygg { background: #d9480f; color: white; border-color: #d9480f; }
.logg { max-height: 220px; overflow-y: auto; border-top: 1px solid #ddd; padding: 6px 8px; background: white; }
@media (max-width: 800px) { .huvud { flex-direction: column; height: auto; } .karta { height: 70vh; }
  .panel { flex: none; border-left: none; } }
</style></head>""")

app.layout = html.Div([
    dcc.Store(id="spel", data=till_json(nytt_spel(1))),
    dcc.Store(id="vald", data=None),
    dcc.Store(id="vald-komp", data=None),
    dcc.Store(id="labb-val", data=None),
    dcc.Store(id="intro-steg", data=None),
    scenario_ui.startruta(True),
    dcc.Store(id="gjutning-val", data=None),
    dcc.Interval(id="auto", interval=700, disabled=True),
    html.Div([
        html.Div([
            html.Div(id="topprad", className="rutor", style={"display": "inline-flex"}),
            html.Button("Next month ▶", id="nasta", className="bygg"),
            html.Button("+1 year ⏩", id="ett-ar"),
            html.Button("Autoplay", id="autospel"),
        ], className="rutor"),
        html.Div(id="malruta"),
        html.Div(id="slut-banner"),
        scenario_ui.introruta(),
        dcc.Graph(id="karta", figure=bas_figur(1000), style={"flex": "1", "minHeight": "350px"},
                  responsive=True, config={"scrollZoom": True}),
        html.Div(id="logg", className="logg"),
    ], className="karta"),
    html.Div([
        html.H3("World Engineer", style={"margin": "0 0 4px"}),
        html.Div([
            dcc.RadioItems(id="projektion", value="natural earth", inline=True,
                           options=[{"label": " Map ", "value": "natural earth"},
                                    {"label": " Globe ", "value": "orthographic"}]),
            dcc.RadioItems(id="q_min", value=1000, inline=True,
                           options=[{"label": f" rivers ≥{q} m³/s ", "value": q} for q in (5000, 1000, 300)]),
        ], style={"fontSize": "0.85em"}),
        html.Div([
            dcc.Input(id="sparnamn", value="game1", style={"width": "90px"}),
            html.Button("Save", id="spara"),
            dcc.Dropdown(id="laddlista", options=sparade_spel(), placeholder="Load…",
                         style={"width": "140px", "display": "inline-block", "verticalAlign": "middle"}),
            html.Button("New game", id="nytt"),
            html.Span(id="sparmedd", style={"fontSize": "0.8em", "color": "#2f9e44"}),
        ], style={"margin": "6px 0"}),
        html.Div(id="meddelande", style={"fontSize": "0.85em", "color": "#1c5aa6", "minHeight": "1em"}),
        html.Hr(style={"margin": "6px 0"}),
        html.Div(id="panel-form"),
        html.Div(id="panel-anl"),
    ], className="panel"),
], className="huvud")


# ---------------------------------------------------------------- callbacks: tid

@app.callback(Output("spel", "data"), Output("meddelande", "children"),
              Input("nasta", "n_clicks"), Input("ett-ar", "n_clicks"), Input("auto", "n_intervals"),
              State("spel", "data"), prevent_initial_call=True)
def tiden_gar(_n, _a, _i, data):
    t = fran_json(data)
    if t["slut"]:
        return no_update, t["slut"]
    for _ in range(12 if ctx.triggered_id == "ett-ar" else 1):
        nasta_manad(t)
        if t["slut"]:
            break
    return till_json(t), ""


@app.callback(Output("auto", "disabled"), Output("autospel", "children"),
              Input("autospel", "n_clicks"), State("auto", "disabled"), prevent_initial_call=True)
def vaxla_autospel(_n, av):
    return (not av), ("Autoplay" if not av else "Pause ⏸")


# ---------------------------------------------------------------- callbacks: val

@app.callback(Output("vald", "data"), Output("vald-komp", "data", allow_duplicate=True),
              Input("karta", "clickData"), prevent_initial_call=True)
def valj(click):
    try:
        cd = click["points"][0]["customdata"]
    except (TypeError, KeyError, IndexError):
        return no_update, no_update
    if cd is None:
        return no_update, no_update
    return (f"p{int(cd)}" if isinstance(cd, (int, float)) else cd), None


@app.callback(Output("vald-komp", "data"), Input("schema", "clickData"), prevent_initial_call=True)
def valj_komp(click):
    try:
        return click["points"][0]["customdata"]
    except (TypeError, KeyError, IndexError):
        return no_update


@app.callback(Output("panel-form", "children"), Output("labb-val", "data", allow_duplicate=True),
              Output("gjutning-val", "data", allow_duplicate=True),
              Input("vald", "data"), State("spel", "data"), prevent_initial_call=True)
def visa_formular(vald, data):
    if vald is None:
        return None, None, None
    t = fran_json(data)
    utanfor = html.P("This location is not part of the scenario. Here you build in the Nile Basin "
                     "(and the Qattara Depression).", style={"color": "#868e96"})
    if vald in MEGA_IDER:
        if vald in t["mega"]:
            return None, None, None
        return (mega_formular(vald) if SC.tillaten_mega(t, vald) else utanfor), None, None
    if hamta_plats(vald) and (vald not in t["anlaggningar"] or t["anlaggningar"][vald]["status"] == "riven"):
        p = hamta_plats(vald)
        if not SC.tillaten_plats(t, p.lon, p.lat):
            return utanfor, None, None
        return bygg_formular(vald, t), None, None
    return None, None, None


@app.callback(Output("panel-anl", "children"), Input("vald", "data"), Input("vald-komp", "data"),
              Input("spel", "data"))
def visa_anlaggning(vald, vald_komp, data):
    t = fran_json(data)
    if vald in t["anlaggningar"] and t["anlaggningar"][vald]["status"] != "riven":
        return anl_panel(t, t["anlaggningar"][vald], vald_komp)
    if vald in t["mega"]:
        return mega_panel(t, vald)
    if vald is None:
        return oversikt(t)
    return None


def design_fran(typ, H, T, seis, nturb, utb, overv, reserv, labb_val=None, gjutning_val=None):
    d = {"typ": typ, "H": float(H), "utskov_T": int(T), "seismik_g": float(seis),
         "n_turbiner": int(nturb), "utbyggnad": float(utb), "overvakning": int(overv),
         "reservkraft": bool(reserv)}
    if labb_val:
        d["labb"] = labb_val
    if gjutning_val and typ == "betong":
        d["gjutning"] = gjutning_val
    return d


def minispel_rader(f):
    """Vad minispelen betyder för dammen, för förhandskalkylen."""
    e = f.get("minispel", {})
    rader = []
    if "kalk" in e:
        rader.append(rad("Calcite in the drains (0–1)", tal(e["kalk"], 2)))
        rader.append(rad("Aggressive water (0–1)", tal(e["aggressiv"], 2)))
    if "asr" in e:
        rader.append(rad("ASR in the concrete", "YES – the concrete will swell" if e["asr"] else "no"))
    if "sektion_t" in e:
        rader.append(rad("Dam body after the pour", f"{round(100 * e['sektion_t'])}%"))
    if not rader:
        rader.append(rad("Mini-games", "not played (hidden chemistry, standard pour)"))
    return rader


@app.callback(Output("b-forhand", "children"),
              Input("b-typ", "value"), Input("b-H", "value"), Input("b-T", "value"), Input("b-seis", "value"),
              Input("b-nturb", "value"), Input("b-utb", "value"), Input("b-overv", "value"),
              Input("b-reserv", "value"), Input("labb-val", "data"), Input("gjutning-val", "data"),
              State("vald", "data"))
def forhandsvisa(typ, H, T, seis, nturb, utb, overv, reserv, labb_val, gjutning_val, vald):
    if not hamta_plats(vald or ""):
        return None
    f = forhandskalkyl(vald, design_fran(typ, H, T, seis, nturb, utb, overv, reserv, labb_val, gjutning_val))
    zon = zon_for(*(lambda p: (p.lon, p.lat))(hamta_plats(vald)))
    return html.Table([
        rad("Cost", f"${tal(f['total'] / 1e3, 1)} billion"),
        rad("  of which dam / power station", f"{tal(f['damm'] / 1e3, 1)} / {tal(f['kraftverk'] / 1e3, 1)}"),
        rad("  of which spillway / resettlement", f"{tal(f['utskov'] / 1e3, 1)} / {tal(f['omflyttning'] / 1e3, 1)}"),
        rad("Construction time", f"{tal(f['byggtid_man'] / 12, 1)} years"),
        rad("Installed capacity", f"{tal(f['MW'])} MW"),
        rad("Reservoir", f"{tal(f['yta_km2'])} km², {tal(f['volym_km3'], 1)} km³"),
        rad("People who must relocate", tal(f["fordrivna"])),
        rad("Spillway capacity", f"{tal(f['Q_utskov'])} m³/s ({T}-year flood)"),
        rad("Seismic zone", zon[0] if zon else "low risk"),
        rad("Region", region_namn(f["region"])),
        *minispel_rader(f),
    ], className="tabell")


@app.callback(Output("m-forhand", "children"), Input("m-varde", "value"), State("vald", "data"))
def forhandsvisa_mega(varde, vald):
    if vald not in MEGA_IDER:
        return None
    k = mega_kalkyl(vald, varde)
    return html.Table([rad("Cost", f"${k['total'] / 1e3:,.0f} billion"),
                       rad("Construction time", f"{k['byggtid_man'] / 12:.0f} years"),
                       rad("Peak power", f"{tal(k['MW'])} MW")], className="tabell")


# ---------------------------------------------------------------- callbacks: beslut

@app.callback(Output("spel", "data", allow_duplicate=True), Output("meddelande", "children", allow_duplicate=True),
              Output("panel-form", "children", allow_duplicate=True),
              Input("b-start", "n_clicks"),
              State("b-typ", "value"), State("b-H", "value"), State("b-T", "value"), State("b-seis", "value"),
              State("b-nturb", "value"), State("b-utb", "value"), State("b-overv", "value"),
              State("b-reserv", "value"), State("labb-val", "data"), State("gjutning-val", "data"),
              State("vald", "data"), State("spel", "data"), prevent_initial_call=True)
def starta_bygge(n, typ, H, T, seis, nturb, utb, overv, reserv, labb_val, gjutning_val, vald, data):
    if not n:
        return no_update, no_update, no_update
    t = fran_json(data)
    medd = utfor(t, {"typ": "bygg", "plats": vald,
                     "design": design_fran(typ, H, T, seis, nturb, utb, overv, reserv,
                                           labb_val, gjutning_val)})
    return till_json(t), medd, None


@app.callback(Output("spel", "data", allow_duplicate=True), Output("meddelande", "children", allow_duplicate=True),
              Output("panel-form", "children", allow_duplicate=True),
              Input("m-start", "n_clicks"), State("m-varde", "value"), State("vald", "data"),
              State("spel", "data"), prevent_initial_call=True)
def starta_mega(n, varde, vald, data):
    if not n:
        return no_update, no_update, no_update
    t = fran_json(data)
    medd = utfor(t, {"typ": "bygg_mega", "id": vald, "varde": varde})
    return till_json(t), medd, None


@app.callback(Output("spel", "data", allow_duplicate=True), Output("meddelande", "children", allow_duplicate=True),
              Input({"aktion": ALL}, "n_clicks"), State("vald", "data"), State("vald-komp", "data"),
              State("spel", "data"), prevent_initial_call=True)
def aktion(klick, vald, vald_komp, data):
    if not ctx.triggered_id or not any(klick):
        return no_update, no_update
    namn = ctx.triggered_id["aktion"]
    t = fran_json(data)
    a = t["anlaggningar"].get(vald)
    if namn == "reparera":
        beslut = {"typ": "reparera", "id": vald, "komp": vald_komp}
    elif namn == "turbin":
        beslut = {"typ": "turbin", "id": vald, "komp": vald_komp, "av": vald_komp not in a["avstangda"]}
    elif namn == "overvakning":
        beslut = {"typ": "overvakning", "id": vald, "niva": a["overvakning"] + 1}
    else:
        beslut = {"typ": namn, "id": vald}
    medd = utfor(t, beslut)
    return till_json(t), medd


@app.callback(Output("spel", "data", allow_duplicate=True),
              Input({"inst": ALL}, "value"), State("vald", "data"), State("spel", "data"),
              prevent_initial_call=True)
def installning(_varden, vald, data):
    if not ctx.triggered_id:
        return no_update
    t = fran_json(data)
    a = t["anlaggningar"].get(vald)
    if a is None:
        return no_update
    nytt = ctx.triggered[0]["value"]
    if ctx.triggered_id["inst"] == "underhall" and nytt != a["underhall"]:
        utfor(t, {"typ": "underhall", "id": vald, "niva": nytt})
    elif ctx.triggered_id["inst"] == "drift" and nytt != a["drift"]:
        utfor(t, {"typ": "drift", "id": vald, "lage": nytt})
    else:
        return no_update
    return till_json(t)


@app.callback(Output("spel", "data", allow_duplicate=True), Output("sparmedd", "children"),
              Output("laddlista", "options"), Output("vald", "data", allow_duplicate=True),
              Input("spara", "n_clicks"), Input("laddlista", "value"),
              State("sparnamn", "value"), State("spel", "data"), prevent_initial_call=True)
def spara_ladda(_s, ladda_namn, namn, data):
    if ctx.triggered_id == "spara":
        spara(fran_json(data), (namn or "game").strip().replace(" ", "_"))
        return no_update, f"Saved as {namn}", sparade_spel(), no_update
    if ladda_namn:
        return till_json(ladda(ladda_namn)), f"Loaded {ladda_namn}", no_update, None
    return no_update, no_update, no_update, no_update


minispel_ui.registrera(app)
scenario_ui.registrera(app)


# ---------------------------------------------------------------- callbacks: kartan och toppraden

@app.callback(Output("karta", "figure"), Output("topprad", "children"), Output("logg", "children"),
              Output("slut-banner", "children"), Output("malruta", "children"),
              Input("spel", "data"), Input("vald", "data"), Input("projektion", "value"))
def rita(data, vald, projektion):
    t = fran_json(data)
    byggda = {a["id"]: a["H"] for a in t["anlaggningar"].values() if a["status"] == "drift"}
    mega = {k: m["varde"] for k, m in t["mega"].items() if m["status"] == "drift"}
    _, ar = megaresultat(t)
    p = karta_patch({**byggda, **mega}, vald, projektion, max(ar, 1))
    # floddammarna: kända platser + spelarens anläggningar, färgade efter skick
    egna = list(t["anlaggningar"].values())
    platser = [q for q in DAMMPLATSER if q.id not in t["anlaggningar"]]
    lon = [q.lon for q in platser] + [a["lon"] for a in egna]
    lat = [q.lat for q in platser] + [a["lat"] for a in egna]
    ids = [q.id for q in platser] + [a["id"] for a in egna]
    text = [f"<b>{q.namn}</b> (available site)<br>{q.flod}" for q in platser] + \
           [f"<b>{a['namn']}</b> – {STATUS_NAMN[a['status']]}<br>{a['flod']}" for a in egna]

    def egen_farg(a):
        if a["status"] == "bygge":
            return FARG_BYGGE
        if a["status"] in ("havererad", "riven"):
            return FARG_SVART
        return farg(struktur_min(a))
    farger = ["#a5d8ff"] * len(platser) + [egen_farg(a) for a in egna]
    p["data"][S["floddammar"]]["lon"] = lon
    p["data"][S["floddammar"]]["lat"] = lat
    p["data"][S["floddammar"]]["customdata"] = ids
    p["data"][S["floddammar"]]["text"] = text
    p["data"][S["floddammar"]]["marker"]["color"] = farger
    p["data"][S["floddammar"]]["marker"]["size"] = [9] * len(platser) + [13] * len(egna)
    if t.get("scenario") and t["manad"] == 0:          # zooma in på scenariots område
        p["layout"]["geo"]["center"] = {"lon": 32, "lat": 17}
        p["layout"]["geo"]["projection"]["scale"] = 3.2
    banner = scenario_ui.slutskarm(t) or (
        html.Div(t["slut"], style={"background": FARG_ROD, "color": "white", "padding": "8px"})
        if t["slut"] else None)
    return p, topprad(t), logg_vy(t), banner, scenario_ui.malruta(t)


@app.callback(Output("karta", "figure", allow_duplicate=True), Input("q_min", "value"), prevent_initial_call=True)
def byt_floder(q_min):
    return flod_patch(q_min)


if __name__ == "__main__":
    Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8060")).start()
    app.run(debug=False, port=8060)
