# Idea backlog – World Engineer

**Rule:** a new idea goes into the game only if it makes the core loop more fun:
**build → maintain → survive a crisis → understand why.**
Everything else is parked here until the vertical slice (the *Nile* scenario) has been
tested by at least 3 people. The test results then decide what is taken off the shelf.

## Parked

### Story (worldbuilding)
- **The Habsburg–Qing family:** around 1900 an archduke marries a Qing princess. After both
  empires have fallen, the family seeks legitimacy through great works instead of thrones.
- **The family council:** the Builder, the Chemist, the Diplomat, the Financier and the Heir
  of Yu ("dam or divert" – Gun versus Da Yu), who often disagree.
- **Generations:** the game runs until 2300, and the legacy passes from one generation to
  the next.
- **Decade reports:** a historian sums up the family's legacy every ten years.

### Progression
- **More scenarios:** a tutorial with Harsprånget, Atlantropa, the climate crisis.
- **Knowledge base:** fills up as the player encounters phenomena (ASR, calcite, the
  Messinian salinity crisis, Clausius–Clapeyron).
- **Achievements tied to understanding,** for example "stopped internal erosion below 50%".
- **Technology tree unlocked by milestones:** roller-compacted concrete (RCC), fish passes,
  better turbines.

### Mini-games 3–7
- Grouting the dam core
- The flood wave (opening the gates at the right pace)
- Choosing the turbine (Pelton, Francis or Kaplan)
- The cofferdam
- The village meeting

### Phase 2 and later
- **Climate with feedback:** TCRE, sea level, Clausius–Clapeyron.
- **Coastal cities:** dikes, retreat or "Venice mode".
- **Dam-break wave** through the cascade, landslides (Vajont), reservoir-induced earthquakes.
- **Components for the megaprojects:** locks, pumps, salt deposits.
- **The future and science fiction:** content to be decided later.

### Polish
- **Easter egg:** a white rabbit as a tribute to *Monty Python and the Holy Grail*, for
  example hiding behind a rock in the cofferdam mini-game.
  - An original drawing, with no names, lines or images from the film (copyright).
  - Only considered once the game is being polished.
- **Portraits and scenery** from an image-generation API (decision: not now; graphics are
  drawn in code).

---

## Publishing (investigated 2026-11-19; nothing has been bought or published)

The game is a Python server (Dash). Each player's state lives in the browser (`dcc.Store`),
so several players can share one server. Check current prices before deciding.

| Option | Cost | Pros and cons |
|---|---|---|
| **Hugging Face Spaces** (Docker) | free | Plenty of memory. Goes to sleep after a period of inactivity. Good for test players. |
| **Render** (web service) | free tier, otherwise a few dollars/month | Simple. The free tier has little memory and goes to sleep. |
| **Fly.io** | a few dollars/month | Fast and stable, but no free tier any more. |
| **Downloadable Windows version** (PyInstaller) on itch.io | free | No server. About 200 MB, may trigger antivirus warnings. |

**Recommendation:** use **Hugging Face Spaces** (free) for the test players. Add an
**itch.io page** that links there when the game is ready for a wider audience.

**Before publishing:**
- Save and load currently write files on the server (`sparade/`), which would be shared by
  all players. This must become a download/upload of the save file, or browser storage.
- The river network (`data/floder.npz`) must not be published as data on its own (HydroSHEDS
  license), so a hosted version has to build it with `hamta_floder.py`. The raw data
  (`data/raa/`, 544 MB) never goes into the repository.
- The attribution required by HydroSHEDS and ETOPO1 is in `README.md` and in the game's
  start screen ("Data sources").

---

## Test protocol for the vertical slice

**Who:** 3–5 people who have not seen the game, ideally one who plays strategy games and one
who does not.

**How:**
1. Start `python spel_app.py` and let the person choose *Nile 2030–2055* themselves.
2. Say only: "Play however you like, and think aloud if you can. I won't help."
3. Sit quietly and take notes. Only help if the person is completely stuck for more than
   2 minutes (and note that too).
4. Stop after 45 minutes or when the scenario ends.

**Watch for:**
- Where does the person get stuck? What do they try to click that cannot be clicked?
- When do they laugh, groan or lean forward? (That is where the game comes alive.)
- When do they lose interest (look away, run Autoplay for a long time without reading)?
- Do they read the introduction, or skip it?
- Do they understand why they got the grade they got?
- Do they try the mini-games? On their own initiative, or not at all?

**Three questions afterwards:**
1. What was the most fun, and what was the most boring?
2. Was there anything you wanted to do but couldn't?
3. Would you play again to get a better grade? Why, or why not?

**After the tests:** write down the three most common problems. Those are the next step, not
new features from the list above.
