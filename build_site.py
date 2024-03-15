#!/usr/bin/env python3

from core.api import Api, Evento
from core.j2 import Jnj2
from datetime import datetime
from core.log import config_log
from core.rss import EventosRss
from core.img import MyImage
from core.util import dict_add
import logging
from os import environ
from os.path import isfile
from typing import Dict, Set
from statistics import multimode


import argparse

parser = argparse.ArgumentParser(
    description='Listar eventos de https://www.abonoteatro.com/')

args = parser.parse_args()
PAGE_URL = environ['PAGE_URL']
OUT = "out/"

config_log("log/build_site.log")
logger = logging.getLogger(__name__)
now = datetime.now()


def add_image(e: Evento):
    local = f"img/{e.id}.jpg"
    file = OUT+local
    im = MyImage(e.img)
    if isfile(file):
        lc = MyImage(file, parent=im)
    else:
        if im.isKO:
            return (im, e)
        width = 500
        height = im.height
        if im.isPortrait:
            height = width*(9/16)
        tb = im.thumbnail(width=width, height=height)
        if tb is None or tb.isKO:
            return (im, e)
        tr = tb.trim()
        if tr is not None and tr.isOK and im.isLandscape and tr.isPortrait:
            tb = tr
        lc = tb.save(file, quality=90)
        if lc is None or lc.isKO:
            return (im, e)
    lc.url = PAGE_URL+'/'+local
    return (lc, e)


logger.info("Recuperar eventos")
eventos = list(Api().get_events())
logger.info(f"{len(eventos)} recuperados")
categorias = {}
sesiones: Dict[str, Set[int]] = {}
sin_sesiones: Set[int] = set()
cine_precio = []

for e in eventos:
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
    key=lambda e: (e.publicado, e.precio, len(e.sesiones), e.txt, e.id),
    reverse=True
)

logger.info("Añadiendo imágenes")
img_eventos = tuple(map(add_image, eventos))
logger.info("Creando web")

j = Jnj2("template/", OUT)
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
