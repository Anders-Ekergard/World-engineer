# Idéparkeringen – Världsingenjören

**Regel:** en ny idé kommer in i spelet bara om den gör kärnloopen roligare:
**bygg → sköt om → klara en kris → förstå varför.**
Allt annat parkeras här tills det vertikala snittet (scenariot *Nilen*) har testats av
minst 3 personer. Då avgör testet vad som plockas fram.

## Parkerat

### Berättelse
- **Decennierapporter:** en historiker summerar spelarens arv vart tionde år.

### Progression
- **Fler scenarier:** introduktion med Harsprånget, Atlantropa, klimatkrisen.
- **Kunskapsbank:** fylls i när man stöter på ett fenomen (ASR, kalcit, Messinska
  salinitetskrisen, Clausius–Clapeyron).
- **Prestationer kopplade till förståelse,** till exempel "stoppade inre erosion under 50 %".
- **Teknikträd via milstolpar:** RCC-betong, fiskvägar, bättre turbiner.

### Minispel 3–7
- Injektering av tätkärnan
- Flodvågen (öppna luckor i rätt takt)
- Turbinvalet (Pelton, Francis eller Kaplan)
- Fångdammen
- Bymötet

### Fas 2 och senare
- **Klimat med återkoppling:** TCRE, havsnivå, Clausius–Clapeyron.
- **Kuststäder:** vallar, reträtt eller "Venedig-läge".
- **Dammbrottsvåg** genom kaskaden, skred (Vajont), jordbävningar utlösta av magasin.
- **Komponenter för megaprojekten:** slussar, pumpar, saltavlagringar.
- **Framtid och sci-fi:** innehållet bestäms senare.

### Polering
- **Påskägg:** en vit kanin som en hyllning till *Monty Python and the Holy Grail*, till
  exempel bakom en sten i fångdammsminispelet.
  - Egen ritad kanin, utan namn, repliker eller bilder från filmen (upphovsrätt).
  - Tas upp först när spelet ska poleras.
- **Porträtt och miljöbilder** via ett bild-API (beslut: inte nu, grafiken ritas i kod).

---

## Publicering (undersökt 2026-11-19, inget är köpt eller publicerat)

Spelet är en Python-server (Dash). Spelarens tillstånd ligger i webbläsaren (`dcc.Store`), så
flera spelare kan använda samma server samtidigt. Kontrollera aktuella priser innan beslut.

| Väg | Kostnad | För och emot |
|---|---|---|
| **Hugging Face Spaces** (Docker) | gratis | Gott om minne. Somnar efter en tids inaktivitet. Bra för testspelare. |
| **Render** (webbtjänst) | gratis nivå finns, annars några dollar/månad | Enkelt. Gratisnivån har lite minne och somnar. |
| **Fly.io** | några dollar/månad | Snabbt och stabilt, men ingen gratisnivå längre. |
| **Nedladdningsbar Windows-version** (PyInstaller) på itch.io | gratis | Ingen server. Ca 200 MB, kan ge varningar från antivirusprogram. |

**Rekommendation:** testa med **Hugging Face Spaces** (gratis) för testspelarna. Lägg en
**itch.io-sida** som länkar dit när spelet ska visas för fler.

**Före publicering:**
- Spara och ladda skriver i dag filer på servern (`sparade/`), vilket är delat mellan alla
  spelare. Det måste bli nedladdning och uppladdning av sparfilen, eller webbläsarens lagring.
- `data/raa/` (544 MB rådata) ska inte med, bara `floder.npz` och `etopo_*.npz` (ca 23 MB).
- Kontrollera licenserna: HydroSHEDS/HydroRIVERS och ETOPO1 (NOAA) kräver
  källhänvisning, som ska stå på en "Om spelet"-sida.

---

## Testprotokoll för det vertikala snittet

**Vem:** 3–5 personer som inte har sett spelet, gärna en som spelar strategispel och en som
inte gör det.

**Hur:**
1. Starta `python spel_app.py` och låt personen själv välja *Nilen 2030–2055*.
2. Säg bara: "Spela som du vill, tänk högt om du kan. Jag hjälper inte till."
3. Sitt tyst och anteckna. Hjälp bara om personen helt fastnar i mer än 2 minuter (anteckna
   det också).
4. Avbryt efter 45 minuter eller när scenariot är slut.

**Titta efter:**
- Var fastnar personen? Vad försöker hen klicka på som inte går att klicka på?
- När skrattar, stönar eller lutar hen sig fram? (Det är där spelet lever.)
- När tappar hen intresset (tittar bort, klickar autospel länge utan att läsa)?
- Läser hen introduktionen, eller hoppar hen över den?
- Förstår hen varför betyget blev som det blev?
- Provar hen minispelen? Frivilligt eller inte alls?

**Tre frågor efteråt:**
1. Vad var roligast, och vad var tråkigast?
2. Fanns det något du ville göra men inte kunde?
3. Skulle du vilja spela igen för att få ett bättre betyg? Varför eller varför inte?

**Efter testerna:** skriv ner de tre vanligaste problemen. Det är nästa steg, inte nya
funktioner ur listan ovan.
