#!/usr/bin/env python3

from core.api import Api, Evento
from core.j2 import Jnj2
from datetime import datetime, timedelta
from core.log import config_log
from core.rss import EventosRss
from core.img import MyImage
from core.util import dict_add, safe_get_list_dict, safe_get_dict
import logging
from os import environ
from os.path import isfile
from typing import Dict, Set, Tuple
from statistics import multimode
from core.filemanager import FM
import math


import argparse

parser = argparse.ArgumentParser(
    description='Listar eventos de https://www.abonoteatro.com/')

args = parser.parse_args()
PAGE_URL = environ['PAGE_URL']
OUT = "out/"

config_log("log/build_site.log")
logger = logging.getLogger(__name__)
now = datetime.now()
too_old = (now - timedelta(days=3)).strftime("%Y-%m-%d 00:00")
white = (255, 255, 255)


def distance_to_white(*color) -> Tuple[int]:
    arr = []
    for c in color:
        d = math.sqrt(sum([(c1 - c2) ** 2 for c1, c2 in zip(c, white)]))
        arr.append(d)
    return tuple(arr)


def get_trim_image(im: MyImage):
    tr = im.trim()
    if tr is None or tr.isKO:
        return None
    if (im.isLandscape and tr.isPortrait):
        return tr
    if len(set(im.im.size).intersection(tr.im.size)) == 1:
        return tr
    diff_height = abs(im.im.height-tr.im.height)
    diff_width = abs(im.im.width-tr.im.width)
    if diff_height < (im.im.height*0.10) and diff_width > (im.im.width*0.20):
        return tr
    if diff_width < (im.im.width*0.10) and diff_height > (im.im.height*0.20):
        return tr
    dist = distance_to_white(im.get_corner_colors().get_most_common())
    if max(dist) < 260:
        return tr
    return None


def add_image(e: Evento):
    local = f"img/{e.id}.jpg"
    file = OUT+local
    im = MyImage.get(e.img)
    if isfile(file):
        lc = MyImage(file, parent=im, background=im.background)
    else:
        if im.isKO:
            return (im, e)
        width = 500
        height = [im.im.height, 300, width*(9/16)]
        im = get_trim_image(im) or im
        tb = im.thumbnail(width=width, height=min(height))
        if tb is None or tb.isKO:
            return (im, e)
        lc = tb.save(file, quality=80)
        if lc is None or lc.isKO:
            return (im, e)
    lc.url = PAGE_URL+'/'+local
    return (lc, e)


logger.info("Recuperar fechas de publicación")
fechas = {}
for k, f in safe_get_dict(environ['PAGE_URL']+'/fechas.json').items():
    if f >= too_old:
        fechas[int(k)] = f
for e in safe_get_list_dict(environ['PAGE_URL']+'/eventos.json'):
    f = e.get('publicado')
    if not isinstance(f, str) or len(f) == 0:
        continue
    if e['id'] not in fechas or f < fechas[e['id']]:
        fechas[e['id']] = f
logger.info("Fechas recuperadas: "+str(fechas))

logger.info("Recuperar eventos")
eventos = list(Api(publish=fechas).get_events())
logger.info(f"{len(eventos)} recuperados")
categorias = {}
sesiones: Dict[str, Set[int]] = {}
sin_sesiones: Set[int] = set()
cine_precio = []

for e in eventos:
    fechas[e.id] = e.publicado
    categorias[e.categoria] = categorias.get(e.categoria, 0) + 1
    if e.categoria == "cine":
        if e.precio > 0:
            cine_precio.append(e.precio)
    if len(e.fechas) == 0:
        sin_sesiones.add(e.id)
        continue
    for f in e.fechas:
        f = f.split()[0]
        dict_add(sesiones, f, e.id)

if len(cine_precio) > 0:
    p = min(multimode(cine_precio))
    for i, e in enumerate(eventos):
        if e.categoria == "cine" and e.precio == 0:
            logger.info(f"{e.id} ({e.categoria}) precio 0 -> {p}")
            eventos[i] = e.merge(precio=p)


precio = dict(
    abonado=3.50,
    compa=3.50 + 5
)

eventos = sorted(
    eventos,
    key=lambda e: (e.publicado, e.creado or e.publicado, e.precio, len(e.sesiones), e.txt, e.id),
    reverse=True
)

logger.info("Añadiendo imágenes")
img_eventos = tuple(map(add_image, eventos))
logger.info("Creando web")

FM.dump("out/fechas.json", fechas)

j = Jnj2("template/", OUT, favicon="🎭")
j.create_script(
    "rec/info.js",
    EVENTOS=set((e.id for e in eventos)),
    SESIONES=sesiones,
    SIN_SESIONES=sin_sesiones,
    replace=True,
)
j.save(
    "index.html",
    eventos=img_eventos,
    precio=precio,
    now=now,
    categorias=categorias,
    count=len(eventos),
    fecha=dict(
        ini=min(sesiones.keys()),
        fin=max(sesiones.keys())
    )
)

for img, e in img_eventos:
    j.save(
        "evento.html",
        destino=f"e/{e.id}.html",
        e=e,
        img=img,
        precio=precio,
        now=now,
        count=len(eventos)
    )

logger.info(f"Creando rss")
EventosRss(
    destino=OUT,
    root=PAGE_URL,
    eventos=eventos
).save("abonoteatro.rss")

logger.info("Fin")
