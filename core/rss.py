import rfeed
from datetime import datetime
from textwrap import dedent
from xml.dom.minidom import parseString as parseXml
import re
import os
from typing import List

from .api import Evento

re_last_modified = re.compile(
    r'^\s*<lastBuildDate>[^>]+</lastBuildDate>\s*$',
    flags=re.MULTILINE
)


class EventosRss:
    def __init__(self, destino, root: str, eventos: List[Evento]):
        self.root = root
        self.eventos = eventos
        self.destino = destino

    def save(self, out: str):
        feed = rfeed.Feed(
            title="Abono Teatro",
            link=self.root+'/'+out,
            description="Eventos de Abono Teatro",
            language="es-ES",
            lastBuildDate=datetime.now(),
            items=list(self.iter_items())
        )

        destino = self.destino + out
        directorio = os.path.dirname(destino)

        if not os.path.exists(directorio):
            os.makedirs(directorio)

        rss = self.__get_rss(feed)
        if self.__is_changed(destino, rss):
            with open(destino, "w") as f:
                f.write(rss)

    def __is_changed(self, destino, new_rss):
        if not os.path.isfile(destino):
            return True
        with open(destino, "r") as f:
            old_rss = f.read()
        new_rss = re_last_modified.sub("", new_rss)
        old_rss = re_last_modified.sub("", old_rss)
        if old_rss == new_rss:
            return False
        return True

    def __get_rss(self, feed: rfeed.Feed):
        def bkline(s: str, i: int):
            return s.split("\n", 1)[i]
        rss = feed.rss()
        dom = parseXml(rss)
        prt = dom.toprettyxml()
        rss = bkline(rss, 0)+'\n'+bkline(prt, 1)
        return rss

    def iter_items(self):
        for e in self.eventos:
            link = f'{self.root}/e/{e.id}'
            yield rfeed.Item(
                title=f'{e.titulo}',
                link=link,
                guid=rfeed.Guid(link),
                categories=rfeed.Category(e.categoria),
                description=dedent(f'''
                    {int(round(e.precio))}€ {e.categoria},
                    <a href="{e.lugar.url}">{e.lugar.txt} ({e.lugar.direccion})</a>
                ''').strip().replace("Nonem², ", "").replace("\n", "<br/>"),
                #pubDate=datetime(*map(int, p.fecha.split("-")))
            )
