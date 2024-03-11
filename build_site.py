#!/usr/bin/env python3

from core.api import Api
from core.j2 import Jnj2
from datetime import datetime
from core.log import config_log
from core.rss import EventosRss
import logging

import argparse

parser = argparse.ArgumentParser(
    description='Listar eventos de https://www.abonoteatro.com/')

args = parser.parse_args()

config_log("log/build_site.log")
logger = logging.getLogger(__name__)
now = datetime.now()

api = Api()
eventos = sorted(api.events, key=lambda e: (-e.descuento, -len(e.sesiones)))
categorias = {}
for e in eventos:
    categorias[e.categoria] = categorias.get(e.categoria, 0) + 1

precio = dict(
    abonado=Api.PRICE,
    compa=Api.COMPANION
)

j = Jnj2("template/", "out/")
j.save(
    "index.html",
    eventos=eventos,
    precio=precio,
    now=now,
    categorias=categorias,
    count=len(eventos)
)

for e in eventos:
    j.save(
        "evento.html",
        destino=f"e/{e.id}.html",
        e=e,
        precio=precio,
        now=now,
        count=len(eventos)
    )

EventosRss(
    destino="out/",
    root="https://s-nt-s.github.io/abonoteatro",
    eventos=eventos
).save("abonoteatro.rss")
