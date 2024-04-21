#!/usr/bin/env python3

from core.api import Api, Evento, Sesion
from core.j2 import Jnj2, toTag
from datetime import datetime, timedelta
from core.log import config_log
from core.rss import EventosRss
from core.img import MyImage
from core.util import dict_add, safe_get_list_dict, safe_get_dict, get_domain, to_datetime
import logging
from os import environ
from os.path import isfile
from typing import Dict, Set, Tuple, List
from statistics import multimode
from core.filemanager import FM
from core.ics import IcsEvent
import math
import bs4
import re


import argparse

parser = argparse.ArgumentParser(
    description='Listar eventos de https://www.abonoteatro.com/')

args = parser.parse_args()
PAGE_URL = environ['PAGE_URL']
OUT = "out/"

config_log("log/build_site.log")
logger = logging.getLogger(__name__)
now = datetime.now()
too_old = (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00")
white = (255, 255, 255)
fechas_url = environ['PAGE_URL']+'/fechas.json'
evento_url = environ['PAGE_URL']+'/eventos.json'


def safe_get_fechas():
    fechas: Dict[int, Dict[str, str]] = {}
    for k, v in safe_get_dict(fechas_url).items():
        k = int(k)
        if v['visto'] >= too_old:
            fechas[int(k)] = v
    for e in safe_get_list_dict(evento_url):
        f = e.get('publicado')
        if not isinstance(f, str) or len(f) == 0:
            continue
        if e['id'] not in fechas:
            fechas[e['id']] = dict(publicado=f, visto=now.strftime("%Y-%m-%d %H:%M"))
            continue
        if f < fechas[e['id']]['publicado']:
            fechas[e['id']]['publicado'] = f
    return fechas


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
fechas = safe_get_fechas()
logger.info(f"{len(fechas)} fechas recuperadas")
publish = {k: v['publicado'] for k, v in fechas.items()}

logger.info("Recuperar eventos")
eventos = list(Api(publish=publish).get_events())
logger.info(f"{len(eventos)} recuperados")
categorias = {}
lugares = {}
sesiones: Dict[str, Set[int]] = {}
sin_sesiones: Set[int] = set()
cine_precio = []

for e in eventos:
    fechas[e.id] = dict(publicado=e.publicado, visto=now.strftime("%Y-%m-%d %H:%M"))
    categorias[e.categoria] = categorias.get(e.categoria, 0) + 1
    lugares[e.lugar.txt] = lugares.get(e.lugar.txt, 0) + 1
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


def event_to_ics(e: Evento, s: Sesion):
    if s.fecha is None:
        return None
    url = f"{PAGE_URL}/e/{e.id}"
    description = "\n".join(filter(lambda x: x is not None, [
        f'{e.precio}€', url, s.url, e.more
    ])).strip()
    dtstart = to_datetime(s.fecha)
    dtend = dtstart + timedelta(minutes=60)
    return IcsEvent(
        uid=f"{e.id}_{s.id}",
        dtstamp=now,
        url=(s.url or url),
        categories=e.categoria,
        summary=e.titulo,
        description=description,
        location=e.lugar.direccion,
        organizer=e.lugar.txt,
        dtstart=dtstart,
        dtend=dtend
    )


precio = dict(
    abonado=3.50,
    compa=3.50 + 5
)


def mysorted(eventos: List[Evento]):
    def get_key(e: Evento):
        return (e.titulo.lower(), e.lugar.direccion.strip().split()[-1])
    arr1 = sorted(
        eventos,
        key=lambda e: (e.publicado, e.creado or e.publicado, e.precio, len(e.sesiones), e.txt, e.id)
    )
    arr2 = []
    for i1, e1 in enumerate(arr1):
        if e1 in arr2:
            continue
        arr2.append(e1)
        for e2 in arr1[i1+1:]:
            if get_key(e1) == get_key(e2):
                arr2.append(e2)
    return tuple(reversed(arr2))


eventos: Tuple[Evento] = mysorted(eventos)

logger.info("Añadiendo ics")
icsevents = []
for e in eventos:
    for s in e.sesiones:
        ics = event_to_ics(e, s)
        if ics is not None:
            ics.dumpme(f"out/cal/{e.id}_{s.id}.ics")
            icsevents.append(ics)
IcsEvent.dump("out/eventos.ics", *icsevents)

logger.info("Añadiendo imágenes")
img_eventos = tuple(map(add_image, eventos))
logger.info("Creando web")

FM.dump("out/fechas.json", fechas)


def set_icons(html: str, **kwargs):
    a: bs4.Tag
    soup = bs4.BeautifulSoup(html, 'html.parser')
    for a in soup.findAll("a", string=re.compile(r"\s*🔗\s*")):
        txt = a.get_text().strip()
        href = a.attrs["href"]
        dom = get_domain(href)
        dom = dom.rsplit(".", 1)[0]
        ico = {
            "autocines": "https://autocines.com/wp-content/uploads/2021/01/cropped-favicon-32x32-1-32x32.png",
            "filmaffinity": "https://www.filmaffinity.com/favicon.png",
            "atrapalo": "https://www.atrapalo.com/favicon.ico",
            "google": "https://www.google.es/favicon.ico",
            "cinesa": "https://www.cinesa.es/scripts/dist/favicon/es/favicon.ico",
            "yelmocines": "https://eu-static.yelmocines.es/img/favicon.ico",
            "lavaguadacines": "https://lavaguadacines.es/assets/images/favicon.jpg"
        }.get(dom)
        if ico is None:
            continue
        a.string = ""
        a.append(toTag(f'<img src="{ico}" class="ico" alt="{txt}"/>'))
        tit = {
            "filmaffinity": "Ver en Filmaffinity",
            "atrapalo": "Buscar en Atrapalo",
            "google": "Buscar en Google",
        }.get(dom)
        if tit and not a.attrs.get("title"):
            a.attrs["title"] = tit
    return str(soup)


j = Jnj2("template/", OUT, favicon="🎭", post=set_icons)
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
    lugares=lugares,
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
