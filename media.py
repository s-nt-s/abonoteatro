from typing import Dict
from core.wpjson import WP
from requests import Session
import json
from io import BytesIO
from zipfile import ZipFile
from requests import RequestException
from os.path import exists
from os import remove

out_file = "media.zip"
if exists(out_file):
    remove(out_file)


s = Session()
wp = WP(s, "https://compras.abonoteatro.com")


def getBytesIO(url: str):
    try:
        r = s.get(url)
        r.raise_for_status()
        b = BytesIO(r.content)
        return b
    except RequestException:
        return None


url_date: Dict[str, str] = {}
id_url: Dict[int, str] = {}
for m in wp.media:
    f = m['modified'].replace("T", " ")[:16]
    u = m['source_url']
    id_url[m['id']] = u
    old = url_date.get(u)
    if old is None or old > f:
        url_date[u] = f

with ZipFile(out_file, "w") as zip_file:
    json_data = json.dumps(url_date, indent=2)
    zip_file.writestr("url_date.json", json_data)

    for id, url in sorted(id_url.items()):
        ext = url.rsplit(".", 1)[-1]
        img = str(id)+'.'+ext.lower()
        idata = getBytesIO(url)
        if idata is None:
            continue
        zip_file.writestr(img, idata.getvalue())
