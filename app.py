"""
app.py – Dam Simulator: click on the map, build dams, see the consequences.

Run:   python app.py        (also from Thonny)
Open:  http://127.0.0.1:8050 in a web browser

Requires:  python -m pip install dash numpy scipy
Data:    python hamta_etopo.py   (once, ~14 MB)
         python hamta_floder.py  (once, 544 MB download -> ~9 MB saved)
"""

import webbrowser
from threading import Timer

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, html, dcc, Input, Output, State, ctx, no_update

from floder import hamta_plats
from bassanger import (HAV, HAV_DICT, BERING, MINERALER, simulera, dammvolym_km3,
                       bering_effekt_MW, bering_dammvolym_km3)
from kaskad import kaskad, HAVSNAMN
from sankor import (SANKA_DICT, megaprojekt, jamviktsniva, gravvolym_km3,
                    SUEZ_KM3)

from karta import bas_figur, karta_patch, flod_patch, tal

DE_TRE_RAVINERNA_KM3 = 0.0279   # dam body volume (concrete), for comparisons

# ---------------------------------------------------------------- panels

def rad(etikett, varde):
    return html.Tr([html.Td(etikett), html.Td(varde, style={"textAlign": "right",
                                                           "fontWeight": "bold"})])


def flod_detalj(id_, H, byggda):
    p = hamta_plats(id_)
    # Preview: calculate the cascade as if the dam were built at the slider height
    k = kaskad({**byggda, id_: H})["dammar"][id_]
    m = k["m"]
    status = ("selected point in river network" if p.uppskattad else
              "existing dam" if p.finns else "proposal/hypothetical")
    varning = None
    if p.uppskattad:
        varning = html.P(
            f"The flow comes from HydroRIVERS. The river slope ({tal(p.lutning * 1e5)} cm/km) and "
            f"valley width are ESTIMATED using Flint's law, calibrated against known dams. "
            f"The population is set to {tal(p.befolkning)} people/km².",
            style={"fontSize": "0.8em", "color": "#8a5a00", "background": "#fff4db",
                   "padding": "4px 6px"})
    return html.Div([
        html.H4(f"{p.namn} – {p.flod}"),
        html.P(f"({status}), dam height {H:.0f} m", style={"color": "#666"}),
        varning,
        html.Table([
            rad("Mean flow", f"{tal(p.Q)} m³/s"),
            rad("Reservoir length", f"{tal(m['langd_km'])} km"),
            rad("Flooded area", f"{tal(m['yta_km2'])} km²"),
            rad("Volume", f"{tal(m['volym_km3'], 1)} km³"),
            rad("Time to fill", f"{tal(m['fyllnad_ar'], 1)} years"),
            rad("Average power", f"{tal(m['effekt_MW'])} MW"),
            rad("Energy", f"{tal(m['energi_TWh'], 1)} TWh/year"),
            rad("Replaces coal power", f"{tal(m['co2_Mt'], 1)} Mt CO₂/year"),
            rad("People who must relocate", tal(m["fordrivna"])),
            rad("Reservoir evaporation",
                f"{tal(m['avdunstning_m3s'])} m³/s ({tal(m['flodforlust_procent'], 1)}% of the river)"),
            rad("Sediment trapped in the reservoir", f"{tal(100 * m['sediment_fangst'])}%"),
        ], className="tabell"),
        nedstroms_panel(k, byggda, id_),
    ])


def nedstroms_panel(k, byggda, id_):
    """Show how the dam is affected by upstream dams and what it does downstream."""
    m = k["m"]
    rader = []
    if k["dammar_upp"]:
        namn = ", ".join(hamta_plats(a).namn for a in k["dammar_upp"])
        rader.append(rad("Dams directly upstream", namn))
        rader.append(rad("Flow in (natural → current)", f"{tal(k['Q_nat'])} → {tal(k['Q_in'])} m³/s"))
        rader.append(rad("Sediment reaching the dam", f"{tal(100 * k['sed_in'])}%"))
    if k["uppdamning"] > 0:
        ned = hamta_plats(k["damm_ned"]).namn
        rader.append(rad(f"Backed up by {ned}",
                         f"+{tal(k['uppdamning'])} m at the dam toe → effective head {tal(m['H_eff'])} m"))
    if "till_hav_km" in k:
        hav = HAVSNAMN.get(k["hav"], "the sea") if k["hav"] else "the sea"
        rader.append(rad("Distance to mouth", f"{tal(k['till_hav_km'])} km ({hav})"))
        rader.append(rad("Flow at mouth (natural → current)",
                         f"{tal(k['Q_mynning_nat'])} → "
                         f"{tal(k['Q_mynning_nat'] - k['Q_forlust_mynning'])} m³/s"))
        rader.append(rad("Sediment reaching the delta", f"{tal(100 * k['sed_mynning'])}%"))
    text = ("Reservoir evaporation propagates downstream: dams farther downstream receive less "
            "water, and the sea receives less freshwater. Trapped sediment is missing from the delta, "
            "which may shrink as the sea erodes the coast (as happened to the Nile Delta after Aswan).")
    if not rader:
        return None
    return html.Div([
        html.H5("Upstream and downstream", style={"margin": "12px 0 4px"}),
        html.P(text, style={"fontSize": "0.8em", "color": "#555", "margin": "0 0 4px"}),
        html.Table(rader, className="tabell"),
    ])


def hav_figur(r, hav):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("Sea-level lowering (m)", "Salinity (g/L)",
                                        "Precipitated salt layers, mean thickness (m)"))
    fig.add_trace(go.Scatter(x=r["t"], y=-r["sankning"], name="level", line=dict(color="#1c5aa6")), 1, 1)
    fig.add_trace(go.Scatter(x=r["t"], y=r["salthalt"], name="salinity", line=dict(color="#a61e4d")), 2, 1)
    for namn, _a, S_start, _rho in MINERALER[:3]:
        fig.add_hline(y=S_start, line=dict(dash="dot", color="#999", width=1), row=2, col=1,
                      annotation_text=f"{namn.split()[0]} begins to precipitate",
                      annotation_font_size=10)
    for namn, _a, _s, _r in MINERALER:
        fig.add_trace(go.Scatter(x=r["t"], y=r["lager"][namn], name=namn, stackgroup="layers"), 3, 1)
    fig.update_xaxes(title_text="years after the dam closes", row=3, col=1)
    fig.update_layout(height=560, margin=dict(l=40, r=10, t=30, b=40),
                      legend=dict(orientation="h", y=-0.15), showlegend=True)
    return fig


def hav_detalj(id_, d_mal, ar, byggda):
    h = HAV_DICT[id_]
    mp = megaprojekt({**byggda, id_: d_mal}, ar)     # preview using the slider value
    fran_floder = mp["kaskad"]["hav"].get(id_, 0.0)
    till_kanaler = mp["uttag"].get(id_, 0.0)
    r = mp["hav"][id_]
    v = dammvolym_km3(h)
    return html.Div([
        html.H4(f"Dam across the {h.sund}"),
        html.P(h.info, style={"fontSize": "0.9em"}),
        html.P("Sea floor: ETOPO1 (NOAA), 1–2 arc minutes" if h.hyps is not None
               else "Sea floor: simplified formula (run hamta_etopo.py for real data)",
               style={"fontSize": "0.8em", "color": "#666"}),
        html.Table([
            rad("Permitted lowering", f"{tal(d_mal)} m"),
            rad(f"Lowering after {ar} years", f"{tal(r['sankning'][-1])} m"),
            rad("Exposed sea floor", f"{tal(r['torrlagt_km2'][-1])} km²"),
            rad("Salinity", f"{tal(h.S0)} → {tal(r['salthalt'][-1])} g/L"),
            rad("Inflow through turbines", f"{tal(r['inflode_m3s'][-1])} m³/s"),
            rad("Power station output", f"{tal(r['effekt_MW'][-1])} MW"),
            rad("Global sea-level rise", f"+{tal(r['global_havsniva_m'][-1], 2)} m"),
            rad("Dam body volume",
                f"{tal(v, 2)} km³ (≈ {tal(v / DE_TRE_RAVINERNA_KM3)} × Three Gorges dams)"),
            rad("River dams reduce inflow by", f"{tal(fran_floder / 1e9, 1)} km³/year"),
            rad("Canals to depressions take (final year)",
                f"{tal(np.atleast_1d(till_kanaler)[-1] / 1e9, 1)} km³/year"),
        ], className="tabell"),
        dcc.Graph(figure=hav_figur(r, h), config={"displayModeBar": False}),
    ])


def sanka_figur(r):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("Lake level (m above sea level)", "Salinity (g/L)",
                                        "Net power (MW)"))
    fig.add_trace(go.Scatter(x=r["t"], y=r["niva"], name="level", line=dict(color="#1b7c8c")), 1, 1)
    fig.add_trace(go.Scatter(x=r["t"], y=r["salthalt"], name="salinity",
                             line=dict(color="#a61e4d")), 2, 1)
    for namn, _a, S_start, _rho in MINERALER[:3]:
        fig.add_hline(y=S_start, line=dict(dash="dot", color="#999", width=1), row=2, col=1,
                      annotation_text=f"{namn.split()[0]} begins to precipitate", annotation_font_size=10)
    fig.add_trace(go.Scatter(x=r["t"], y=r["effekt_MW"], name="power",
                             line=dict(color="#d9480f")), 3, 1)
    fig.update_xaxes(title_text="years after the canal opens", row=3, col=1)
    fig.update_layout(height=560, margin=dict(l=40, r=10, t=30, b=40), showlegend=False)
    return fig


def sanka_detalj(id_, Q, ar, byggda):
    s = SANKA_DICT[id_]
    mp = megaprojekt({**byggda, id_: Q}, ar)
    r = mp["sankor"][id_]
    utan = megaprojekt({**byggda, id_: 0}, ar)["sankor"][id_]
    nivaer = r["niva"]
    topp = int(np.argmax(nivaer))
    kalla = HAVSNAMN.get(s.kalla, s.kalla)
    rader = [
        rad("Source", f"{kalla}, canal {tal(s.kanal_km)} km"),
        rad("Lake level from start → year " + str(ar), f"{tal(nivaer[0])} → {tal(nivaer[-1])} m"),
        rad("Without the canal, year " + str(ar), f"{tal(utan['niva'][-1])} m"),
        rad("Freshwater equilibrium (approx.)", f"{tal(jamviktsniva(s, Q))} m"),
        rad("Highest level", f"{tal(nivaer[topp])} m (year {topp})"),
        rad("Lake area", f"{tal(r['yta_km2'][-1])} km²"),
        rad("Water in lake", f"{tal(r['volym_km3'][-1])} km³"),
        rad("Inflow (final year)", f"{tal(r['inflode_m3s'][-1])} m³/s"),
        rad("Net power year 1 → final year", f"{tal(r['effekt_MW'][1])} → {tal(r['effekt_MW'][-1])} MW"),
    ]
    if s.lyft:
        rader.append(rad(f"of which pumping over the {tal(s.lyft)} m ridge", f"−{tal(r['pump_MW'][1])} MW"))
    rader += [
        rad("Salinity", f"{tal(r['salthalt'][1])} → {tal(r['salthalt'][-1])} g/L"),
        rad("Salt layer on bottom (gypsum + halite)",
            f"{tal(r['lager']['Gypsum CaSO4·2H2O'][-1] + r['lager']['Halite NaCl'][-1], 2)} m"),
        rad("Canal excavation volume",
            f"{tal(gravvolym_km3(s, Q), 2)} km³ (≈ {tal(gravvolym_km3(s, Q) / SUEZ_KM3, 1)} × Suez Canal)"),
        rad("Global sea level", f"{tal(1000 * r['global_havsniva_m'][-1], 1)} mm"),
    ]
    return html.Div([
        html.H4(f"{s.projekt} – {s.namn}"),
        html.P(s.info, style={"fontSize": "0.9em"}),
        html.P("Basin shape: ETOPO1 (NOAA). Evaporation, canal length and ridges are estimated. "
               "The canal takes water from the " + kalla + "; this shows in that sea's panel when it is dammed.",
               style={"fontSize": "0.8em", "color": "#8a5a00", "background": "#fff4db", "padding": "4px 6px"}),
        html.Table(rader, className="tabell"),
        dcc.Graph(figure=sanka_figur(r), config={"displayModeBar": False}),
    ])


def bering_detalj(fallhojd):
    v = bering_dammvolym_km3()
    return html.Div([
        html.H4("Dam across the Bering Strait"),
        html.P(BERING["info"], style={"fontSize": "0.9em"}),
        html.Table([
            rad("Strait width / depth", f"{tal(BERING['bredd'] / 1e3)} km / {tal(BERING['djup'])} m"),
            rad("Flow blocked", f"{tal(BERING['flode_Sv'] * 1e6)} m³/s"),
            rad("Head", f"{tal(fallhojd, 1)} m"),
            rad("Potential power", f"{tal(bering_effekt_MW(fallhojd))} MW"),
            rad("Dam body volume", f"{tal(v, 2)} km³ (≈ {tal(v / DE_TRE_RAVINERNA_KM3)} × Three Gorges dams)"),
        ], className="tabell"),
    ])


def sammanfattning(byggda, ar):
    MW = TWh = fordrivna = yta = 0.0
    mp = megaprojekt(byggda, ar)
    k = mp["kaskad"]
    for info in k["dammar"].values():
        m = info["m"]
        MW += m["effekt_MW"]; TWh += m["energi_TWh"]
        fordrivna += m["fordrivna"]; yta += m["yta_km2"]
    global_niva = 0.0
    for h in HAV:
        if h.id in byggda:
            r = mp["hav"][h.id]
            MW += r["effekt_MW"][-1]
            TWh += r["effekt_MW"][-1] * 8760 / 1e6
            global_niva += r["global_havsniva_m"][-1]
    for r in mp["sankor"].values():
        MW += r["effekt_MW"][-1]
        TWh += r["effekt_MW"][-1] * 8760 / 1e6
        global_niva += r["global_havsniva_m"][-1]
    if "bering" in byggda:
        MW += bering_effekt_MW(byggda["bering"])
        TWh += bering_effekt_MW(byggda["bering"]) * 8760 / 1e6

    n_flod = sum(1 for k in byggda if hamta_plats(k))
    n_mega = len(byggda) - n_flod
    return html.Div([
        html.Div([html.Div(tal(MW), className="siffra"), html.Div("Total MW")], className="ruta"),
        html.Div([html.Div(tal(TWh), className="siffra"), html.Div("TWh/year")], className="ruta"),
        html.Div([html.Div(tal(fordrivna), className="siffra"), html.Div("displaced")], className="ruta"),
        html.Div([html.Div(tal(yta), className="siffra"), html.Div("km² inundated")], className="ruta"),
        html.Div([html.Div(f"{global_niva:+.2f}", className="siffra"),
                  html.Div(f"m global sea level (year {ar})")], className="ruta"),
        html.Div(f"{n_flod} river dam{'s' * (n_flod != 1)} and {n_mega} megaproject{'s' * (n_mega != 1)} built",
                 style={"width": "100%", "color": "#666", "fontSize": "0.85em"}),
    ], className="rutor")


# ---------------------------------------------------------------- layout

app = Dash(__name__, title="Dam Simulator")

app.index_string = app.index_string.replace("</head>", """<style>
body { font-family: system-ui, sans-serif; margin: 0; background: #fafafa; color: #222; }
.huvud { display: flex; height: 100vh; }
.karta { flex: 1 1 60%; min-width: 0; display: flex; flex-direction: column; }
.panel { flex: 0 0 440px; overflow-y: auto; padding: 12px 16px; background: white;
         border-left: 1px solid #ddd; }
.rutor { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px; }
.ruta { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 4px 10px;
        font-size: 0.8em; color: #555; }
.siffra { font-size: 1.4em; font-weight: bold; color: #222; }
.tabell { width: 100%; border-collapse: collapse; font-size: 0.9em; }
.tabell td { padding: 3px 4px; border-bottom: 1px solid #eee; }
button { padding: 6px 14px; margin-right: 6px; border-radius: 4px; border: 1px solid #888;
         cursor: pointer; background: white; }
button.bygg { background: #d9480f; color: white; border-color: #d9480f; }
@media (max-width: 800px) { .huvud { flex-direction: column; height: auto; }
  .karta { height: 70vh; } .panel { flex: none; border-left: none; } }
</style></head>""")

app.layout = html.Div([
    dcc.Store(id="byggda", data={}),
    dcc.Store(id="vald", data=None),
    html.Div([
        html.Div(id="sammanfattning"),
        dcc.Graph(id="karta", figure=bas_figur(1000), style={"flex": "1", "minHeight": "400px"},
                  responsive=True, config={"scrollZoom": True}),
    ], className="karta"),
    html.Div([
        html.H3("Dam Simulator", style={"marginTop": 0}),
        html.Label("Map view"),
        dcc.RadioItems(id="projektion", value="natural earth", inline=True,
                       options=[{"label": " World map ", "value": "natural earth"},
                                {"label": " Flat ", "value": "equirectangular"},
                                {"label": " Globe ", "value": "orthographic"}]),
        html.Label("Show rivers with mean flow at least"),
        dcc.RadioItems(id="q_min", value=1000, inline=True,
                       options=[{"label": f" {q} m³/s ", "value": q} for q in (5000, 1000, 300)]),
        html.Label("Simulated time for megaprojects (years)"),
        dcc.Slider(id="ar", min=10, max=3000, step=10, value=500,
                   marks={10: "10", 500: "500", 1000: "1000", 2000: "2000", 3000: "3000"},
                   tooltip={"placement": "bottom"}),
        html.Hr(),
        html.Div(id="val-rubrik", children="Click a river, a ▲ (existing dam) or a ◆ (megaproject) on the map."),
        html.Div(id="reglage-box", children=[
            html.Label(id="reglage-etikett"),
            dcc.Slider(id="reglage", min=0, max=100, value=50, tooltip={"placement": "bottom"}),
            html.Button("Build / change", id="bygg", className="bygg"),
            html.Button("Demolish", id="riv"),
        ], style={"display": "none"}),
        html.Hr(),
        html.Div(id="detalj"),
    ], className="panel"),
], className="huvud")


# ---------------------------------------------------------------- callbacks

@app.callback(Output("vald", "data"), Input("karta", "clickData"), prevent_initial_call=True)
def valj(click):
    try:
        cd = click["points"][0]["customdata"]
    except (TypeError, KeyError, IndexError):
        return no_update
    if cd is None:
        return no_update
    return f"p{int(cd)}" if isinstance(cd, (int, float)) else cd   # tal = punkt i flodnätet


@app.callback(
    Output("reglage-box", "style"), Output("reglage-etikett", "children"),
    Output("reglage", "min"), Output("reglage", "max"), Output("reglage", "step"),
    Output("reglage", "value"), Output("reglage", "marks"), Output("val-rubrik", "children"),
    Input("vald", "data"), State("byggda", "data"))
def visa_reglage(vald, byggda):
    if vald is None:
        return {"display": "none"}, "", 0, 1, 1, 0, None, no_update
    if hamta_plats(vald):
        p = hamta_plats(vald)
        v = byggda.get(vald, p.H_standard)
        return ({}, "Dam height (m)", 5, p.H_max, 1, v, {5: "5", p.H_max: str(p.H_max)},
                f"Selected: {p.namn} in {p.flod}")
    if vald in HAV_DICT:
        h = HAV_DICT[vald]
        v = byggda.get(vald, h.d_standard)
        return ({}, "How far may the sea drop before the turbines let water in? (m)",
                0, h.d_max, 5, v, {0: "0", h.d_max: str(h.d_max)}, f"Selected: {h.sund}")
    if vald in SANKA_DICT:
        s_ = SANKA_DICT[vald]
        v = byggda.get(vald, s_.Q_standard)
        return ({}, "Canal capacity (m³/s)", 0, s_.Q_max, 5, v,
                {0: "0", s_.Q_max: str(s_.Q_max)}, f"Selected: {s_.projekt} to {s_.namn}")
    v = byggda.get("bering", BERING["fallhojd_m"])
    return ({}, "Dam head (m)", 0.1, 1.0, 0.1, v, {0.1: "0.1", 1: "1"},
            "Selected: Bering Strait")


@app.callback(Output("byggda", "data"),
              Input("bygg", "n_clicks"), Input("riv", "n_clicks"),
              State("vald", "data"), State("reglage", "value"), State("byggda", "data"),
              prevent_initial_call=True)
def bygg_eller_riv(_b, _r, vald, varde, byggda):
    if vald is None:
        return no_update
    byggda = dict(byggda)
    if ctx.triggered_id == "bygg":
        byggda[vald] = varde
    else:
        byggda.pop(vald, None)
    return byggda


@app.callback(Output("karta", "figure"), Output("sammanfattning", "children"),
              Input("byggda", "data"), Input("vald", "data"), Input("projektion", "value"),
              Input("ar", "value"))
def uppdatera_karta(byggda, vald, projektion, ar):
    return karta_patch(byggda, vald, projektion, ar), sammanfattning(byggda, ar)


@app.callback(Output("karta", "figure", allow_duplicate=True), Input("q_min", "value"),
              prevent_initial_call=True)
def byt_floder(q_min):
    return flod_patch(q_min)


@app.callback(Output("detalj", "children"),
              Input("vald", "data"), Input("reglage", "value"), Input("ar", "value"),
              Input("byggda", "data"))
def uppdatera_detalj(vald, varde, ar, byggda):
    # Preview: the panel shows consequences for the slider value directly
    if vald is None or varde is None:
        return html.P("Tip: drag the slider to preview, then click Build.",
                      style={"color": "#666"})
    if hamta_plats(vald):
        return flod_detalj(vald, varde, byggda)
    if vald in HAV_DICT:
        return hav_detalj(vald, varde, ar, byggda)
    if vald in SANKA_DICT:
        return sanka_detalj(vald, varde, ar, byggda)
    return bering_detalj(varde)


if __name__ == "__main__":
    Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8050")).start()
    app.run(debug=False)
