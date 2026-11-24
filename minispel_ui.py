"""
minispel_ui.py – gränssnittet för minispelen i Världsingenjören (Dash).

  Kemilabbet:      vattenprov -> räkna Langeliers index steg för steg, välj dränering;
                   ASR-test -> jämför stenbrottens expansion, välj ballast och motåtgärd
  Betonggjutning:  reglage för lyft, cement, flygaska, förkylning och kylrör ->
                   temperaturkurvor, värmekarta, skiss med sprickor och ett utlåtande

All grafik ritas i kod med Plotly. Spelarens val samlas i dcc.Store "labb-val" och
"gjutning-val" och följer med i dammens design när bygget startar.
"""

import math

import numpy as np
import plotly.graph_objects as go
from dash import html, dcc, Input, Output, State, ctx, no_update

from floder import hamta_plats
from spel.minispel import labb as L, gjutning as G

TOL = {"A": 0.02, "B": 0.02, "C": 0.02, "D": 0.02, "pHs": 0.03}
FARG_BROTT = ["#1c7ed6", "#e8590c", "#2f9e44"]


def _tal(x, dec=2):
    return f"{x:.{dec}f}"


def _lasa(x):
    """Read a number entered by the player, with comma or period."""
    if x is None or x == "":
        return None
    try:
        return float(str(x).replace(",", ".").replace("−", "-"))
    except ValueError:
        return None


# ---------------------------------------------------------------- kemilabbet: grafik

def provror_figur(v: dict) -> go.Figure:
    """Five test tubes, filled according to their normal ranges."""
    rader = [("pH", v["pH"], 6.5, 9.0, ""), ("Temperature", v["T"], 0, 32, " °C"),
             ("Ca²⁺", v["Ca"], 0, 320, " mg/L"), ("Alkalinity", v["alk"], 0, 260, " mg/L"),
             ("TDS", v["TDS"], 0, 650, " mg/L")]
    fig = go.Figure()
    for i, (namn, varde, lo, hi, enhet) in enumerate(rader):
        x0 = i * 1.4
        niva = 0.2 + 2.6 * (varde - lo) / (hi - lo)
        fig.add_shape(type="rect", x0=x0, x1=x0 + 0.7, y0=0.2, y1=niva,
                      fillcolor="rgba(77, 171, 247, 0.6)", line_width=0)
        fig.add_shape(type="path", path=f"M {x0} 3 L {x0} 0.35 Q {x0 + 0.35} -0.05 {x0 + 0.7} 0.35 L {x0 + 0.7} 3",
                      line=dict(color="#495057", width=2))
        fig.add_annotation(x=x0 + 0.35, y=3.35, text=f"<b>{namn}</b>", showarrow=False, font=dict(size=11))
        fig.add_annotation(x=x0 + 0.35, y=-0.35, text=f"{_tal(varde, 2 if namn == 'pH' else 0)}{enhet}",
                           showarrow=False, font=dict(size=11))
    fig.update_layout(height=170, margin=dict(l=5, r=5, t=5, b=5), plot_bgcolor="white",
                      xaxis=dict(visible=False, range=[-0.3, 6.6]),
                      yaxis=dict(visible=False, range=[-0.6, 3.6]))
    return fig


def asr_figur(brott: list, vald: int | None) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=0.10, fillcolor="#d3f9d8", line_width=0, opacity=0.6)
    fig.add_hrect(y0=0.10, y1=0.20, fillcolor="#fff3bf", line_width=0, opacity=0.6)
    fig.add_hrect(y0=0.20, y1=0.5, fillcolor="#ffe3e3", line_width=0, opacity=0.6)
    for i, b in enumerate(brott):
        t, e = L.expansionskurva(b["E14"])
        fig.add_trace(go.Scatter(x=t, y=e, name=f"{i + 1}. {b['namn']}",
                                 line=dict(color=FARG_BROTT[i], width=4 if vald == i else 2)))
    fig.add_annotation(x=0.3, y=0.05, text="harmless", showarrow=False, xanchor="left", font=dict(size=10))
    fig.add_annotation(x=0.3, y=0.15, text="potentially reactive", showarrow=False, xanchor="left", font=dict(size=10))
    fig.add_annotation(x=0.3, y=0.30, text="reactive", showarrow=False, xanchor="left", font=dict(size=10))
    fig.update_layout(height=230, margin=dict(l=40, r=5, t=10, b=35),
                      xaxis_title="days in 1 M NaOH at 80 °C", yaxis_title="expansion (%)",
                      yaxis_range=[0, max(0.3, max(b["E14"] for b in brott) * 1.15)],
                      legend=dict(orientation="h", y=-0.35, font=dict(size=10)))
    return fig


# ---------------------------------------------------------------- kemilabbet: flik

def labb_flik(prov: dict) -> html.Div:
    v = prov["vatten"]
    falt = lambda namn: dcc.Input(id=f"l-{namn}", type="text", placeholder=namn, debounce=True,
                                  style={"width": "70px", "marginRight": "6px"})
    return html.Div([
        dcc.Store(id="labb-prov", data=prov),
        dcc.Store(id="l-lsi", data=None),
        html.H5("A. River water sample", style={"margin": "8px 0 2px"}),
        dcc.Graph(figure=provror_figur(v), config={"displayModeBar": False, "staticPlot": True}),
        html.P(["Calculate the ", html.B("Langelier Saturation Index"), ": will the water precipitate calcite "
                "(clogging the drains) or dissolve lime from the concrete?"], style={"fontSize": "0.85em"}),
        html.Pre("A = (log₁₀ TDS − 1) / 10\nB = −13.12·log₁₀(T + 273) + 34.55\nC = log₁₀(Ca) − 0.4\n"
                 "D = log₁₀(alkalinity)\npHs = (9.3 + A + B) − (C + D)      LSI = pH − pHs",
                 style={"fontSize": "0.8em", "background": "#f8f9fa", "padding": "6px"}),
        html.Div([falt("A"), falt("B"), falt("C"), falt("D"), falt("pHs")]),
        html.Button("Check", id="l-kontroll", className="bygg"),
        html.Button("Show solution", id="l-visa"),
        html.Div(id="l-aterkoppling", style={"fontSize": "0.85em", "margin": "4px 0"}),
        html.Div(id="l-val-box", style={"display": "none"}, children=[
            html.Label("Foundation drainage"),
            dcc.RadioItems(id="l-dranering", value="standard",
                           options=[{"label": f" {txt}", "value": k} for k, (txt, *_r) in L.DRANERING.items()]),
            dcc.Checklist(id="l-ytskydd", value=[],
                          options=[{"label": " Dense concrete and surface protection against aggressive water (+1%)",
                                    "value": "ja"}]),
        ]),
        html.Hr(),
        html.H5("B. Aggregate: ASR test of three quarries", style={"margin": "8px 0 2px"}),
        dcc.Graph(id="l-asr-graf", figure=asr_figur(prov["brott"], None), config={"displayModeBar": False}),
        dcc.RadioItems(id="l-brott", value=None, options=[
            {"label": f" {i + 1}. {b['namn']} – {b['beskrivning']}; price {int(round(100 * b['pris']))}%, "
                      f"{b['km']} km", "value": i} for i, b in enumerate(prov["brott"])],
            style={"fontSize": "0.85em"}),
        html.Label("ASR mitigation"),
        dcc.RadioItems(id="l-motatgard", value="ingen", inline=True, options=[
            {"label": " none ", "value": "ingen"}, {"label": " low-alkali cement (+3%) ", "value": "lagalkali"},
            {"label": " fly ash ≥25% (set on the Concrete pour tab) ", "value": "flygaska"}],
            style={"fontSize": "0.85em"}),
        html.Div(id="l-asr-text", style={"fontSize": "0.85em", "marginTop": "4px"}),
    ])


# ---------------------------------------------------------------- gjutningen: grafik

def kurv_figur(s: dict, p: dict, u: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s["t"], y=s["karna"], name="core", line=dict(color="#e03131", width=3)))
    fig.add_trace(go.Scatter(x=s["t"], y=s["yta"], name="top surface", line=dict(color="#1c7ed6")))
    fig.add_hline(y=p["T_luft"], line=dict(dash="dot", color="#868e96"),
                  annotation_text=f"air {_tal(p['T_luft'], 0)} °C", annotation_font_size=10)
    fig.add_hline(y=p["T_ar"] + G.SPRICKGRANS, line=dict(dash="dash", color="#f08c00"),
                  annotation_text="cracking limit (annual mean + 20 °C)", annotation_font_size=10,
                  annotation_position="bottom right")
    fig.update_layout(height=220, margin=dict(l=40, r=5, t=10, b=35), xaxis_title="days",
                      yaxis_title="°C", legend=dict(orientation="h", y=1.15, font=dict(size=10)))
    return fig


def varmekarta(s: dict) -> go.Figure:
    fig = go.Figure(go.Heatmap(x=s["t"], y=s["z"], z=s["profil"].T, colorscale="Inferno",
                               colorbar=dict(title="°C", thickness=10)))
    fig.update_layout(height=180, margin=dict(l=40, r=5, t=10, b=35), xaxis_title="days",
                      yaxis_title="lift height (m)")
    return fig


def skiss(p: dict, u: dict) -> go.Figure:
    """Lyften i genomskärning: äldre lyftar under, den nya överst, kylrör och sprickor."""
    fig = go.Figure()
    H = p["lyft"]
    for i in range(3):                                   # äldre lyftar
        fig.add_shape(type="rect", x0=0, x1=10, y0=-(i + 1) * 1.5, y1=-i * 1.5,
                      fillcolor="#ced4da", line=dict(color="#868e96"))
    varm = min(1.0, max(0.0, (u["T_max"] - p["T_luft"]) / 45))
    farg = f"rgb({int(200 + 55 * varm)}, {int(200 - 120 * varm)}, {int(200 - 160 * varm)})"
    fig.add_shape(type="rect", x0=0, x1=10, y0=0, y1=H, fillcolor=farg, line=dict(color="#495057"))
    if p["kylror"]:
        n = max(2, int(H / 0.75))
        for j in range(1, n + 1):
            y = H * j / (n + 1)
            fig.add_trace(go.Scatter(x=np.arange(0.5, 10, 1.0), y=[y] * 10, mode="markers",
                                     marker=dict(size=7, color="#1c7ed6"), hoverinfo="skip"))
    n_spricka = {"No cracks": 0, "Fine cracks": 2, "Cracks": 4, "Severe cracks": 7}[u["utlatande"]]
    rng = np.random.default_rng(int(10 * u["index"] * 100))
    for _ in range(n_spricka):
        x = rng.uniform(1, 9)
        ys = np.linspace(H, H * rng.uniform(0.1, 0.6), 5)
        xs = x + np.cumsum(rng.normal(0, 0.12, 5))
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#212529", width=2),
                                 hoverinfo="skip"))
    fig.add_annotation(x=5, y=H / 2, text=f"new lift {_tal(H, 2)} m<br>max {_tal(u['T_max'], 0)} °C",
                       showarrow=False, font=dict(size=11))
    fig.update_layout(height=170, margin=dict(l=5, r=5, t=5, b=5), showlegend=False, plot_bgcolor="white",
                      xaxis=dict(visible=False, range=[-0.2, 10.2]), yaxis=dict(visible=False, range=[-3.2, 3.2]))
    return fig


# ---------------------------------------------------------------- gjutningen: flik

def gjutning_flik(T_luft: float, T_ar: float, manad_text: str) -> html.Div:
    st = G.STANDARD
    regl = lambda id_, lo, hi, steg, v: dcc.Slider(id=id_, min=lo, max=hi, step=steg, value=v, marks=None,
                                                    tooltip={"placement": "bottom"})
    return html.Div([
        dcc.Store(id="g-klimat", data={"T_luft": T_luft, "T_ar": T_ar}),
        html.P(f"Concrete placement begins {manad_text}: the air temperature is about {_tal(T_luft, 0)} °C "
               f"(annual mean {_tal(T_ar, 0)} °C). Cement hydration warms the concrete. If the core "
               "cools by more than about 20 °C after it has set, it may crack.", style={"fontSize": "0.85em"}),
        html.Label("Lift height (m) – thinner lifts cool more easily but take longer"),
        regl("g-lyft", 0.5, 3.0, 0.25, st["lyft"]),
        html.Label("Cement content (kg/m³)"),
        regl("g-cement", 150, 350, 10, st["cement"]),
        html.Label("Fly ash fraction (replaces cement; releases less heat, and more slowly)"),
        regl("g-fa", 0, 0.5, 0.05, st["flygaska"]),
        html.Label("Pre-cooling with ice in the mix (°C)"),
        regl("g-forkyl", 0, 15, 1, st["forkylning"]),
        dcc.Checklist(id="g-ror", value=[], options=[{"label": " Cooling pipes with cold water (as at Hoover Dam, +5%)",
                                                      "value": "ja"}]),
        html.Div(id="g-utlatande", style={"margin": "6px 0", "fontSize": "0.9em"}),
        dcc.Graph(id="g-skiss", config={"displayModeBar": False, "staticPlot": True}),
        dcc.Graph(id="g-kurva", config={"displayModeBar": False}),
        dcc.Graph(id="g-karta", config={"displayModeBar": False}),
    ])


# ---------------------------------------------------------------- callbacks

def registrera(app):
    @app.callback(Output("l-aterkoppling", "children"), Output("l-lsi", "data"), Output("l-val-box", "style"),
                  Output("l-A", "value"), Output("l-B", "value"), Output("l-C", "value"),
                  Output("l-D", "value"), Output("l-pHs", "value"),
                  Input("l-kontroll", "n_clicks"), Input("l-visa", "n_clicks"),
                  State("l-A", "value"), State("l-B", "value"), State("l-C", "value"),
                  State("l-D", "value"), State("l-pHs", "value"), State("labb-prov", "data"),
                  prevent_initial_call=True)
    def kontrollera_lsi(_k, _v, A, B, C, D, pHs, prov):
        v = prov["vatten"]
        facit = L.lsi(v["pH"], v["T"], v["Ca"], v["alk"], v["TDS"])
        visa = {"display": "block"}
        if ctx.triggered_id == "l-visa":
            text = html.Span([f"Solution: A = {_tal(facit['A'], 3)}, B = {_tal(facit['B'], 3)}, "
                              f"C = {_tal(facit['C'], 3)}, D = {_tal(facit['D'], 3)}, pHs = {_tal(facit['pHs'])}. ",
                              html.B(f"LSI = {_tal(facit['LSI'])}: {L.tolka_lsi(facit['LSI'])}")])
            return (text, facit["LSI"], visa, _tal(facit["A"], 3), _tal(facit["B"], 3),
                    _tal(facit["C"], 3), _tal(facit["D"], 3), _tal(facit["pHs"]))
        svar = {"A": A, "B": B, "C": C, "D": D, "pHs": pHs}
        bitar, ratt_phs = [], False
        for k, x in svar.items():
            x = _lasa(x)
            if x is None:
                continue
            ok = abs(x - facit[k]) <= TOL[k]
            ratt_phs |= (k == "pHs" and ok)
            bitar.append(html.Span(f"{k} {'✓' if ok else '✗'}  ",
                                   style={"color": "#2f9e44" if ok else "#e03131", "fontWeight": "bold"}))
        if not bitar:
            return "Enter at least one value first.", no_update, no_update, *[no_update] * 5
        if ratt_phs:
            bitar.append(html.Div(html.B(f"Correct! LSI = pH − pHs = {_tal(v['pH'])} − {_tal(facit['pHs'])} = "
                                         f"{_tal(facit['LSI'])}. {L.tolka_lsi(facit['LSI'])}")))
            return html.Div(bitar), facit["LSI"], visa, *[no_update] * 5
        bitar.append(html.Div("Tip: log₁₀ in Python is math.log10. Check the units: T in °C, "
                              "Ca and alkalinity as mg/L CaCO₃.", style={"color": "#666"}))
        return html.Div(bitar), no_update, no_update, *[no_update] * 5

    @app.callback(Output("labb-val", "data"), Output("l-asr-graf", "figure"), Output("l-asr-text", "children"),
                  Input("l-lsi", "data"), Input("l-dranering", "value"), Input("l-ytskydd", "value"),
                  Input("l-brott", "value"), Input("l-motatgard", "value"), State("labb-prov", "data"),
                  prevent_initial_call=True)
    def samla_labb(lsi, dranering, ytskydd, brott, motatgard, prov):
        fig = asr_figur(prov["brott"], brott)
        text = None
        if brott is not None:
            b = prov["brott"][brott]
            text = html.Span([html.B(f"{b['namn']}: {_tal(b['E14'], 3)}% expansion after 14 days = {L.klass(b['E14'])}. "),
                              "Silica in the aggregate reacts with alkali in the pore solution: "
                              "SiO₂ + 2 NaOH → Na₂SiO₃·nH₂O (a swelling gel). "
                              "Fly ash binds alkali; low-alkali cement produces less NaOH from the start."])
        if lsi is None and brott is None:
            return None, fig, text
        val = {"LSI": lsi if lsi is not None else 0.0, "dranering": dranering if lsi is not None else "standard",
               "ytskydd": bool(ytskydd) and lsi is not None,
               "brott": prov["brott"][brott] if brott is not None else None,
               "motatgard": motatgard, "vatten_gjort": lsi is not None}
        if lsi is None:
            val["LSI"] = None
        return val, fig, text

    @app.callback(Output("g-skiss", "figure"), Output("g-kurva", "figure"), Output("g-karta", "figure"),
                  Output("g-utlatande", "children"), Output("gjutning-val", "data"),
                  Input("g-lyft", "value"), Input("g-cement", "value"), Input("g-fa", "value"),
                  Input("g-forkyl", "value"), Input("g-ror", "value"), State("g-klimat", "data"))
    def rita_gjutning(lyft, cement, fa, forkyl, ror, klimat):
        p = {"lyft": float(lyft), "cement": float(cement), "flygaska": float(fa),
             "forkylning": float(forkyl), "kylror": bool(ror), **klimat}
        s = G.simulera(p)
        u = G.utvardera(p)
        farger = {"No cracks": "#2f9e44", "Fine cracks": "#f2c200", "Cracks": "#f08c00",
                  "Severe cracks": "#e03131"}
        delar = [html.B(u["utlatande"], style={"color": farger[u["utlatande"]], "fontSize": "1.1em"}),
                 html.Span(f"  The core reaches {_tal(u['T_max'], 0)} °C and then cools by {_tal(u['fall'], 0)} °C; "
                           f"the core–surface difference is {_tal(u['gradient'], 0)} °C. Without heat loss the concrete "
                           f"would warm by {_tal(u['dT_ad'], 0)} °C (adiabatic rise). "
                           f"The dam body starts in {round(100 * u['sektion_t'])}% condition, "
                           f"concrete cost ×{_tal(u['kostnad_faktor'])}, construction time ×{_tal(u['tid_faktor'])}." )]
        if not u["hallfast"]:
            delar.append(html.Div(f"Concrete too weak: {_tal(u['bindemedel'], 0)} kg/m³ effective binder, "
                                  f"requirement {_tal(G.KRAV_BINDEMEDEL, 0)} (fly ash counts as half). "
                                  "The plan is rejected – the standard plan is used.",
                                  style={"color": "#e03131", "fontWeight": "bold"}))
        val = p if u["hallfast"] else None
        return skiss(p, u), kurv_figur(s, p, u), varmekarta(s), html.Div(delar), val


def manad_text(manad_index: int, startar: int) -> str:
    namn = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December"]
    return f"in {namn[manad_index % 12]} {startar + manad_index // 12}"


def minispel_flikar(t: dict, vald: str, typ_standard: str):
    """Flikarna Kemilabb och Gjutning för en plats."""
    p = hamta_plats(vald)
    prov = L.prov(t["fro"], vald, p.lat)
    T_luft, T_ar = G.lufttemperatur(p.lat, t["manad"] % 12)
    return [
        dcc.Tab(label="Chemistry lab", value="labb", children=labb_flik(prov)),
        dcc.Tab(label="Concrete pour", value="gjutning", children=[
            html.P("Applies only to concrete dams. Choosing an embankment dam has no effect.",
                   style={"fontSize": "0.8em", "color": "#868e96"}),
            gjutning_flik(T_luft, T_ar, manad_text(t["manad"], t["startar"]))]),
    ]
