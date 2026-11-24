"""
hamta_floder.py – laddar ner HydroRIVERS (världens flodnät, 544 MB) och sparar
bara de större floderna (medelflöde >= Q_MIN) i en kompakt fil: data/floder.npz

Kör en gång:  python hamta_floder.py     (nedladdning + ca 5–10 min bearbetning)
Kräver:       python -m pip install pyshp

Källa: Lehner & Grill (2013), HydroSHEDS / HydroRIVERS v1.0, www.hydrosheds.org
Varje flodsträcka ("reach") har bl.a.:
  HYRIV_ID    eget id
  NEXT_DOWN   id för sträckan nedströms (0 = mynning)
  MAIN_RIV    id för huvudflodens mynningssträcka (samma för hela flodsystemet)
  DIS_AV_CMS  medelflöde, m3/s
  UPLAND_SKM  avrinningsområde uppströms, km2
  LENGTH_KM   sträckans längd
Linjerna är ritade i flödesriktningen (uppströms -> nedströms).
"""

import os
import time
import urllib.request
import zipfile

import numpy as np
import shapefile   # pyshp

Q_MIN = 50.0        # m3/s – mindre floder sparas inte
GLESNING = 3        # behåll var 3:e punkt i linjerna (plus första och sista)

HAR = os.path.dirname(os.path.abspath(__file__))
RAA = os.path.join(HAR, "data", "raa")
UT = os.path.join(HAR, "data", "floder.npz")
URL = "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_shp.zip"
ZIP = os.path.join(RAA, "HydroRIVERS_v10_shp.zip")


def ladda_ner():
    os.makedirs(RAA, exist_ok=True)
    if not os.path.exists(ZIP):
        print("Laddar ner HydroRIVERS (544 MB) ...")
        urllib.request.urlretrieve(URL, ZIP)
    shp = [os.path.join(rot, f) for rot, _, filer in os.walk(RAA) for f in filer if f.endswith(".shp")]
    if not shp:
        print("Packar upp ...")
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(RAA)
        shp = [os.path.join(rot, f) for rot, _, filer in os.walk(RAA) for f in filer if f.endswith(".shp")]
    return shp[0]


def main():
    sokvag = ladda_ner()
    print("Läser", sokvag)
    t0 = time.time()
    r = shapefile.Reader(sokvag)
    falt = [f[0] for f in r.fields[1:]]
    kol = {n: falt.index(n) for n in
           ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "DIS_AV_CMS", "UPLAND_SKM", "LENGTH_KM"]}

    # 1) gå igenom alla ~8,5 miljoner poster, spara index för de stora floderna
    behall, rader = [], []
    for i, rec in enumerate(r.iterRecords()):
        if rec[kol["DIS_AV_CMS"]] >= Q_MIN:
            behall.append(i)
            rader.append([rec[kol[n]] for n in kol])
        if i % 1_000_000 == 0:
            print(f"  {i:,} poster, {len(behall):,} sparade ({time.time() - t0:.0f} s)")
    rader = np.array(rader, dtype=np.float64)

    # 2) läs geometrin bara för dem vi behåller
    lon, lat, start = [], [], [0]
    for n, i in enumerate(behall):
        pts = r.shape(i).points
        pts = pts[::GLESNING] + ([pts[-1]] if (len(pts) - 1) % GLESNING else [])
        lon += [p[0] for p in pts]
        lat += [p[1] for p in pts]
        start.append(len(lon))
        if n % 20000 == 0:
            print(f"  geometri {n:,}/{len(behall):,}")

    np.savez_compressed(
        UT,
        id=rader[:, 0].astype(np.int64),
        next_down=rader[:, 1].astype(np.int64),
        main_riv=rader[:, 2].astype(np.int64),
        Q=rader[:, 3].astype(np.float32),
        upland=rader[:, 4].astype(np.float32),
        langd=rader[:, 5].astype(np.float32),
        start=np.array(start, dtype=np.int64),
        lon=np.array(lon, dtype=np.float32),
        lat=np.array(lat, dtype=np.float32),
    )
    print(f"Klart: {len(behall):,} flodsträckor, {len(lon):,} punkter -> {UT} "
          f"({os.path.getsize(UT) / 1e6:.1f} MB, {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
