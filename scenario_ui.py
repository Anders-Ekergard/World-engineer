"""
scenario_ui.py – startval, introduktion, målruta och slutskärm i Världsingenjören.

  Startrutan:     välj scenariot "Nilen" (rekommenderat) eller fritt spel
  Introduktionen: 6 korta pratbubblor som visar hur spelet fungerar (kan hoppas över)
  Målrutan:       scenariots fyra mål med ✓ / ✗ / … medan man spelar
  Slutskärmen:    betyg och vad som gick bra och dåligt, och varför
"""

from dash import html, dcc, Input, Output, State, ctx, no_update

from spel import scenarier as SC
from spel.tillstand import nytt_spel, till_json, fran_json

# Källhänvisning som HydroSHEDS-licensen kräver (Exhibit B) samt ETOPO1
DATAKALLOR = (
    "This product World Engineer incorporates data from the HydroSHEDS version 1 database which is "
    "© World Wildlife Fund, Inc. (2006-2022) and has been used herein under license. WWF has not "
    "evaluated the data as altered and incorporated within World Engineer, and therefore gives no "
    "warranty regarding its accuracy, completeness, currency or suitability for any particular purpose. "
    "Portions of the HydroSHEDS v1 database incorporate data which are the intellectual property rights "
    "of © USGS (2006-2008), NASA (2000-2005), ESRI (1992-1998), CIAT (2004-2006), UNEP-WCMC (1993), "
    "WWF (2004), Commonwealth of Australia (2007), and Her Royal Majesty and the British Crown and are "
    "used under license. The HydroSHEDS v1 database and more information are available at "
    "https://www.hydrosheds.org. Sea floor and terrain: ETOPO1 (NOAA, Amante & Eakins 2009)."
)

INTRO = [
    ("Welcome, World Engineer!",
     "This is the Nile. You are responsible for two dams: Aswan in Egypt (built 1970) and the new "
     "GERD dam in Ethiopia, which is still filling. The scenario lasts 25 years."),
    ("Dams have parts, not just one health bar",
     "Click Aswan (▲ in Egypt). The damage panel shows the dam from the front: sections, core, "
     "foundation, spillway, gates and turbines, colored by condition."),
    ("Repair in time",
     "Click a yellow or orange part in the damage panel and press Repair. Gates and turbines "
     "are handled by the maintenance crew, but major repairs are your decision."),
    ("Time advances one month at a time",
     "Press Next month, +1 year or Autoplay. The Nile flood arrives in August–September. Read "
     "the event log below the map: it shows flows, faults and discoveries."),
    ("Build something new",
     "Click a river in the Nile basin to plan a dam. The Chemistry lab tab shows the water chemistry "
     "and the ASR risk of the aggregate, and the Concrete pour tab shows how concrete heats up as it "
     "cures. The mini-games are optional, but knowledge builds better dams."),
    ("Your objectives",
     "The objective panel shows four goals: power, no dam failures, acceptance in Africa, and "
     "water for Egypt during an approaching drought. They determine your bronze, silver or gold grade."),
]


def startruta(synlig: bool):
    return html.Div(id="startruta", style={
        "display": "flex" if synlig else "none", "position": "fixed", "inset": "0", "zIndex": "50",
        "background": "rgba(0,0,0,0.45)", "alignItems": "center", "justifyContent": "center"}, children=[
        html.Div([
            html.H2("World Engineer", style={"marginTop": 0}),
            html.P("Build, operate and save the world's dams. Every dam component can fail in "
                   "its own way, and the chemistry and physics are realistic."),
            html.Button(f"▶ {SC.INFO['nilen']['namn']}", id="starta-nilen", className="bygg",
                        style={"fontSize": "1.1em", "padding": "8px 16px"}),
            html.P(SC.INFO["nilen"]["beskrivning"], style={"fontSize": "0.85em", "color": "#555"}),
            html.Button("Free play (worldwide, no objectives)", id="starta-fritt"),
            html.P("Twelve real dams, a global budget and no rules. Best when you know the game.",
                   style={"fontSize": "0.85em", "color": "#555"}),
            html.Details([html.Summary("Data sources"), html.P(DATAKALLOR)],
                         style={"fontSize": "0.7em", "color": "#868e96", "marginTop": "10px"}),
        ], style={"background": "white", "padding": "24px", "borderRadius": "10px", "maxWidth": "460px"}),
    ])


def introruta():
    return html.Div(id="introruta", style={"display": "none"}, children=[
        html.B(id="intro-rubrik"), html.P(id="intro-text", style={"margin": "4px 0"}),
        html.Span(id="intro-steg-text", style={"fontSize": "0.8em", "color": "#868e96", "marginRight": "8px"}),
        html.Button("Next", id="intro-nasta", className="bygg"),
        html.Button("Skip", id="intro-hoppa"),
    ])


INTRO_STIL = {"position": "absolute", "left": "12px", "bottom": "12px", "zIndex": "20", "maxWidth": "420px",
              "background": "#fff9db", "border": "2px solid #f08c00", "borderRadius": "8px",
              "padding": "10px 12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.2)"}


def malruta(t: dict):
    if not t.get("scenario"):
        return None
    ikon = {True: ("✓", "#2f9e44"), False: ("✗", "#e03131"), None: ("…", "#868e96")}
    return html.Div([html.Span(f"{ikon[ok][0]} {namn}: {varde}  ",
                               style={"color": ikon[ok][1], "marginRight": "10px"})
                     for namn, varde, ok in SC.mal_status(t)],
                    style={"fontSize": "0.8em", "padding": "2px 8px", "background": "#f8f9fa",
                           "borderBottom": "1px solid #ddd"})


def slutskarm(t: dict):
    sc = t.get("scenario")
    if not sc or not sc.get("resultat"):
        return None
    r = sc["resultat"]
    farg = {"guld": "#f08c00", "silver": "#868e96", "brons": "#a0522d", "underkänt": "#e03131"}[r["betyg"]]
    grade = {"guld": "GOLD", "silver": "SILVER", "brons": "BRONZE", "underkänt": "FAILED"}[r["betyg"]]
    return html.Div([
        html.H3(f"Scenario complete: {grade}", style={"color": farg, "margin": "0 0 6px"}),
        html.P(f"{r['antal']} of 4 objectives met."),
        html.Ul([html.Li(rad) for rad in r["rader"]]),
        html.P("Press New game to try again, or choose free play.", style={"color": "#555"}),
    ], style={"background": "white", "border": f"3px solid {farg}", "borderRadius": "8px",
              "padding": "12px", "margin": "6px 8px"})


def registrera(app):
    @app.callback(Output("spel", "data", allow_duplicate=True), Output("startruta", "style"),
                  Output("intro-steg", "data"), Output("vald", "data", allow_duplicate=True),
                  Input("starta-nilen", "n_clicks"), Input("starta-fritt", "n_clicks"),
                  State("startruta", "style"), prevent_initial_call=True)
    def valj_spel(_n, _f, stil):
        stil = {**stil, "display": "none"}
        if ctx.triggered_id == "starta-nilen":
            return till_json(SC.starta("nilen")), stil, 0, None
        return till_json(nytt_spel(1)), stil, None, None

    @app.callback(Output("startruta", "style", allow_duplicate=True), Input("nytt", "n_clicks"),
                  State("startruta", "style"), prevent_initial_call=True)
    def visa_startruta(_n, stil):
        return {**stil, "display": "flex"}

    @app.callback(Output("introruta", "style"), Output("intro-rubrik", "children"),
                  Output("intro-text", "children"), Output("intro-steg-text", "children"),
                  Output("intro-nasta", "children"), Input("intro-steg", "data"))
    def visa_intro(steg):
        if steg is None or steg >= len(INTRO):
            return {"display": "none"}, "", "", "", "Next"
        rubrik, text = INTRO[steg]
        return (INTRO_STIL, rubrik, text, f"{steg + 1} / {len(INTRO)}",
                "Start playing!" if steg == len(INTRO) - 1 else "Next")

    @app.callback(Output("intro-steg", "data", allow_duplicate=True),
                  Input("intro-nasta", "n_clicks"), Input("intro-hoppa", "n_clicks"),
                  State("intro-steg", "data"), prevent_initial_call=True)
    def bladdra_intro(_n, _h, steg):
        if steg is None:
            return no_update
        return None if ctx.triggered_id == "intro-hoppa" else steg + 1
