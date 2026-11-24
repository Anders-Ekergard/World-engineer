"""
hamta_etopo.py – laddar ner höjd- och djupdata (ETOPO1, 1 bågminut ≈ 1,85 km)
från NOAA:s ERDDAP-server och sparar kompakta .npz-filer i data/.

Kör en gång:  python hamta_etopo.py      (ca 20–25 MB, tar någon minut)
Redan hämtade filer hoppas över.

Källa: NOAA NCEI, ETOPO1 Global Relief Model
https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.html
"""

import math
import os
import tempfile
import time
import urllib.request

import numpy as np
from scipy.io import netcdf_file

from floder import DAMMPLATSER

URL = ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.nc?"
       "altitude%5B({lat0}):{steg}:({lat1})%5D%5B({lon0}):{steg}:({lon1})%5D")
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Havsbassängerna: (lon0, lon1, lat0, lat1, steg i bågminuter)
HAV_RUTOR = {
    "gibraltar": (-6.5, 37.0, 30.0, 46.5, 2),
    "rodahavet": (32.0, 44.5, 12.0, 30.5, 1),
    # sänkor under havsytan (kanalprojekt, se sankor.py)
    "qattara": (25.0, 30.0, 28.3, 30.8, 1),
    "dodahavet": (34.8, 35.9, 29.4, 33.0, 1),
    "saharahavet": (5.3, 10.6, 33.0, 35.0, 1),
    "danakil": (39.4, 42.3, 12.8, 15.3, 1),
    "assal": (42.2, 42.9, 11.3, 11.9, 1),
}
FLOD_HALVBREDD = 6.0     # grader kring varje dammplats
FLOD_FORSKJUTNING = 3.0  # grader: rutans mitt flyttas uppströms, där magasinet hamnar


def ladda_ner(namn, lon0, lon1, lat0, lat1, steg):
    ut = os.path.join(DATA, f"etopo_{namn}.npz")
    if os.path.exists(ut):
        print(f"  {namn}: finns redan")
        return
    url = URL.format(lat0=lat0, lat1=lat1, lon0=lon0, lon1=lon1, steg=steg)
    tmp = os.path.join(tempfile.gettempdir(), f"etopo_{namn}.nc")
    for forsok in range(3):
        try:
            urllib.request.urlretrieve(url, tmp)
            break
        except Exception as fel:
            print(f"  {namn}: fel ({fel}), försöker igen ...")
            time.sleep(5)
    else:
        raise RuntimeError(f"kunde inte hämta {namn}")

    with netcdf_file(tmp, mmap=False) as f:
        z = np.array(f.variables["altitude"][:], dtype=np.int16)
        lat = np.array(f.variables["latitude"][:], dtype=np.float64)
        lon = np.array(f.variables["longitude"][:], dtype=np.float64)
    os.remove(tmp)
    np.savez_compressed(ut, z=z, lat=lat, lon=lon)
    print(f"  {namn}: {z.shape[1]}×{z.shape[0]} punkter, {os.path.getsize(ut) / 1e6:.1f} MB")


def main():
    os.makedirs(DATA, exist_ok=True)
    print("Havsbassänger:")
    for namn, (lon0, lon1, lat0, lat1, steg) in HAV_RUTOR.items():
        ladda_ner(namn, lon0, lon1, lat0, lat1, steg)

    print("Dammplatser:")
    for p in DAMMPLATSER:
        v = math.radians(p.riktning)
        mitt_lon = p.lon + FLOD_FORSKJUTNING * math.sin(v) / math.cos(math.radians(p.lat))
        mitt_lat = p.lat + FLOD_FORSKJUTNING * math.cos(v)
        ladda_ner(p.id,
                  round(max(mitt_lon - FLOD_HALVBREDD, -180), 2),
                  round(min(mitt_lon + FLOD_HALVBREDD, 180), 2),
                  round(max(mitt_lat - FLOD_HALVBREDD, -90), 2),
                  round(min(mitt_lat + FLOD_HALVBREDD, 90), 2), 1)
    print("Klart!")


if __name__ == "__main__":
    main()
