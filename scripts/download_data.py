"""Download + unpack the Recipe Box JSON files into ./data  (dataset page: https://eightportions.com/datasets/Recipes/).
If the automatic download fails, download the zip manually from that page and unzip the three
recipes_raw_nosource_{ar,epi,fn}.json files into ./data."""
import io, sys, urllib.request, zipfile
from pathlib import Path

URL = "https://storage.googleapis.com/recipe-box/recipes_raw.zip"   # link listed on the dataset page; verify there if this fails
out = Path(__file__).resolve().parents[1] / "data"
out.mkdir(exist_ok=True)
try:
    print("Downloading", URL)
    data = urllib.request.urlopen(URL, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.endswith(".json") and "nosource" in n:
                (out / Path(n).name).write_bytes(z.read(n)); print("extracted", Path(n).name)
except Exception as e:
    sys.exit(f"Download failed ({e}). Get the zip from https://eightportions.com/datasets/Recipes/ and unzip the 3 JSON files into {out}")
