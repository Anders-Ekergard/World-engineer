# World Engineer

A turn-based building game about the world's dams and water megaprojects, with real
hydrology, physics and chemistry.

Every dam is made of components that wear out and fail in their own way: dam sections,
the clay core (internal erosion), the foundation drains (clogged by calcite), the spillway,
gates and turbines. Floods, droughts and earthquakes test your designs. Two optional
mini-games put chemistry and physics to work: a water lab (Langelier Saturation Index and
alkali–silica reaction tests) and a mass-concrete pour (heat of hydration and cracking).

> **Status:** early playable prototype (a "vertical slice"). The first scenario,
> **Nile 2030–2055**, has objectives, scripted events and a final grade. Feedback welcome.

## Quick start

Requires Python 3.11 or later.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python hamta_floder.py          # once: builds the river network (downloads 544 MB from HydroSHEDS)
python spel_app.py              # the game: http://127.0.0.1:8060
```

`hamta_floder.py` is optional. Without it the game still runs, but you can only build at the
predefined dam sites, and the river network on the map and the downstream effects are
simplified.

There is also a free-form **sandbox** (`python app.py`, http://127.0.0.1:8050) for trying
out dams and megaprojects such as Atlantropa (damming the Strait of Gibraltar) or the
Qattara Depression canal without game rules.

## Project layout

| Path | Contents |
|---|---|
| `spel_app.py`, `scenario_ui.py`, `minispel_ui.py` | The game's user interface (Dash) |
| `spel/` | Game engine: monthly turns, components, events, economy, acceptance, scenarios, mini-games |
| `app.py` | The sandbox |
| `floder.py`, `natverk.py`, `kaskad.py` | Rivers, the river network and downstream (cascade) effects |
| `bassanger.py`, `sankor.py`, `terrang.py` | Seas, depressions below sea level and terrain (box models) |
| `kontroll.py`, `spel/kontroll_spel.py` | Checks of the models against real data and of the game engine |
| `IDEER.md` | Design notes, idea backlog and test protocol |

Much of the code (names and comments) is in Swedish; the game itself is in English.

## Data and attribution

**HydroSHEDS / HydroRIVERS** (river network, downloaded by `hamta_floder.py`).
The river network is not included in this repository, because the HydroSHEDS license does
not allow redistribution of the data on its own.

> This product World Engineer incorporates data from the HydroSHEDS version 1 database
> which is © World Wildlife Fund, Inc. (2006-2022) and has been used herein under license.
> WWF has not evaluated the data as altered and incorporated within World Engineer, and
> therefore gives no warranty regarding its accuracy, completeness, currency or suitability
> for any particular purpose. Portions of the HydroSHEDS v1 database incorporate data which
> are the intellectual property rights of © USGS (2006-2008), NASA (2000-2005), ESRI
> (1992-1998), CIAT (2004-2006), UNEP-WCMC (1993), WWF (2004), Commonwealth of Australia
> (2007), and Her Royal Majesty and the British Crown and are used under license. The
> HydroSHEDS v1 database and more information are available at https://www.hydrosheds.org.

Lehner, B., Verdin, K., Jarvis, A. (2008): New global hydrography derived from spaceborne
elevation data. *Eos, Transactions, AGU*, 89(10): 93–94.
Lehner, B., Grill, G. (2013): Global river hydrography and network routing: baseline data
and new approaches to study the world's large river systems. *Hydrological Processes*,
27(15): 2171–2186.

**ETOPO1** (sea floor and depressions, `data/etopo_*.npz`, downloaded by `hamta_etopo.py`
from NOAA ERDDAP). Amante, C. and B.W. Eakins (2009): ETOPO1 1 Arc-Minute Global Relief
Model: Procedures, Data Sources and Analysis. NOAA Technical Memorandum NESDIS NGDC-24.

## License

The source code is released under the MIT License (see `LICENSE`). The data listed above is
covered by its own terms.
