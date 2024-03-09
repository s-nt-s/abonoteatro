#!/usr/bin/env python3

from core.api import Api
from core.j2 import Jnj2
from datetime import datetime
from core.log import config_log
import logging

import argparse

parser = argparse.ArgumentParser(
    description='Listar eventos de https://www.abonoteatro.com/')

args = parser.parse_args()

config_log("log/build_site.log")
logger = logging.getLogger(__name__)
now = datetime.now()

with Api("firefox") as api:
    api.login()
    eventos = sorted(api.eventos, key=lambda e: (-e.descuento, -len(e.sesiones)))

j = Jnj2("template/", "out/")
j.save(
    "index.html",
    eventos=eventos,
    precio=Api.PRECIO,
    now=now
)

for e in eventos:
    j.save(
        "evento.html",
        destino=f"e/{e.id}.html",
        e=e,
        precio=Api.PRECIO,
        now=now
    )