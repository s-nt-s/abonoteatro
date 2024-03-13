#!/usr/bin/env python3

from core.api import Api, Evento
from core.j2 import Jnj2
from datetime import datetime
from core.log import config_log
from core.rss import EventosRss
from core.img import MyImage
import logging
from os import environ

import argparse

parser = argparse.ArgumentParser(
    description='Listar eventos de https://www.abonoteatro.com/')

args = parser.parse_args()
PAGE_URL = environ['PAGE_URL']
OUT = "out/"

config_log("log/build_site.log")
logger = logging.getLogger(__name__)
now = datetime.now()

eventos = sorted(
    Api().get_events(),
    key=lambda e: (e.publicado, e.precio, len(e.sesiones), e.txt, e.id),
    reverse=True
)
categorias = {}
for e in eventos:
    categorias[e.categoria] = categorias.get(e.categoria, 0) + 1

precio = dict(
    abonado=3.50,
    compa=3.50 + 5
)


def add_image(e: Evento):
    im = MyImage(e.img)
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
    local = f"img/{e.id}.jpg"
    lc = tb.save(OUT+local, quality=90)
    if lc is None or lc.isKO:
        return (im, e)
    lc.url = PAGE_URL+'/'+local
    return (lc, e)


img_eventos = tuple(map(add_image, eventos))

j = Jnj2("template/", OUT)
j.save(
    "index.html",
    eventos=img_eventos,
    precio=precio,
    now=now,
    categorias=categorias,
    count=len(eventos)
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

EventosRss(
    destino=OUT,
    root=PAGE_URL,
    eventos=eventos
).save("abonoteatro.rss")
