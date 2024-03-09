from core.web import Driver
from os import environ
from selenium.webdriver.common.by import By
from typing import NamedTuple, Tuple, Set, Dict, List
import re
from bs4 import Tag
from datetime import datetime, date
from .cache import Cache
import logging
from functools import cached_property
from .filemanager import FM

logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")


def clean_txt(s: str):
    if s is None:
        return None
    if s == s.upper():
        s = s.title()
    s = re.sub(r"\\", "", s)
    s = re.sub(r"´", "'", s)
    return s


def get_obj(*args, **kwargs) -> dict:
    if len(args) != 0 and len(kwargs) != 0:
        raise ValueError()
    if len(args) > 1:
        raise ValueError()
    if len(args) == 0:
        return kwargs
    obj = args[0]
    if not isinstance(obj, (dict, list)):
        raise ValueError()
    return obj


class TupleCache(Cache):
    def __init__(self, *args, builder=None, **kwargs):
        if not callable(builder):
            raise ValueError('builder is None')
        self.builder = builder
        super().__init__(*args, **kwargs)

    def read(self, file, *args, **kwargs):
        data = super().read(file, *args, **kwargs)
        if isinstance(data, dict):
            return self.builder(data)
        return tuple((self.builder(d) for d in data))

    def __parse(self, obj):
        if getattr(obj, "_asdict", None) is not None:
            obj = obj._asdict()
        if isinstance(obj, (list, tuple, set)):
            return tuple(map(self.__parse, obj))
        if isinstance(obj, dict):
            obj = {k: self.__parse(v) for k, v in obj.items()}
        return obj

    def save(self, file, data, *args, **kwargs):
        data = self.__parse(data)
        return super().save(file, data, *args, **kwargs)


class UrlTupleCache(TupleCache):
    def parse_file_name(self, url: str, slf=None, **kargv):
        path = url.rstrip("/").split("/")[-1]
        return self.file.format(path)


class Sesion(NamedTuple):
    id: int
    fecha: str = None

    @property
    def url(self):
        return Api.URLSES + str(self.id)

    def merge(self, **kwargs):
        return Evento(**{**self._asdict(), **kwargs})

    @staticmethod
    def build(*args, **kwargs):
        obj = get_obj(*args, **kwargs)
        return Sesion(**obj)

    @property
    def hora(self):
        if self.fecha is not None:
            fch = self.fecha.split(" ")
            if len(fch[-1]) == 5:
                return fch[-1]
        return None


class Lugar(NamedTuple):
    txt: str
    url: str

    @staticmethod
    def build(*args, **kwargs):
        obj = get_obj(*args, **kwargs)
        return Lugar(**obj)


class Evento(NamedTuple):
    id: int
    txt: str
    img: str
    subtitulo: str
    precio: float
    lugar: Lugar
    sesiones: Tuple[Sesion] = tuple()

    def merge(self, **kwargs):
        return Evento(**{**self._asdict(), **kwargs})

    @staticmethod
    def build(*args, **kwargs):
        obj = get_obj(*args, **kwargs)
        obj['lugar'] = Lugar.build(obj['lugar'])
        obj['sesiones'] = tuple(map(Sesion.build, obj['sesiones']))
        return Evento(**obj)

    @property
    def descuento(self):
        if self.precio in (None, 0):
            return 0
        d = (self.precio-Api.PRECIO)
        return round((d/self.precio)*100)

    @property
    def titulo(self):
        tit = clean_txt(self.txt)
        sub = clean_txt(self.subtitulo)
        if sub is None:
            return tit
        return tit+", "+sub

    @property
    def html(self) -> Tag:
        return FM.cached_load(f"rec/evento/html/{self.id}.html")

    @property
    def condiciones(self):
        n = self.html.select_one("#informacioneventolargo")
        if n is None:
            return None
        for d in n.findAll("div"):
            if get_text(d) == "Ver menos":
                d.extract()
        n.attrs.clear()
        n.attrs["class"] = "condiciones"
        return str(n)

    @property
    def dias_hora(self):
        dias: Dict[str, List[Sesion]] = {}
        for e in self.sesiones:
            dia = 'Cualquier día'
            if e.fecha is not None:
                dh = e.fecha.split(" ")
                if len(dh[0]) == 10:
                    dt = date(*map(int, dh[0].split("-")))
                    dia = "LMXJVSD"[dt.weekday()]+' '+dh[0]
            if dia not in dias:
                dias[dia] = []
            dias[dia].append(e)
        return dias.items()


def get_text(n: Tag):
    if n is None:
        return None
    txt = n.get_text()
    txt = re_sp.sub(r" ", txt)
    txt = txt.strip()
    if len(txt) == 0:
        return None
    return txt


def get_float(n: Tag):
    txt = get_text(n)
    if txt is None:
        return None
    txt = txt.strip(" €")
    txt = txt.replace(",", ".")
    num = float(txt)
    if num == int(num):
        num = int(num)
    return num


class ApiException(Exception):
    pass


class Api(Driver):
    IFRAME = 'div[role="main"] iframe'
    SESION = "div.bsesion a.buyBtn"
    EVENTO = '#modal_event_content > div.container'
    URLSES = 'https://compras.abonoteatro.com/compra/?eventocurrence='
    PRECIO = 3.50
    LISTAS = (
        "https://compras.abonoteatro.com/teatro/",
        "https://compras.abonoteatro.com/cine-y-eventos/",
        "https://www.abonoteatro.com/catalogo/cine_peliculas.php",
    )

    def login(self, user: str = environ.get("ABONOTEATRO_USER"), psw: str = environ.get("ABONOTEATRO_PSW")):
        self.get("https://compras.abonoteatro.com/login/")
        self.val("nabonadologin", user)
        self.val("contrasenalogin", psw)
        self.click('button.cmplz-deny', by=By.CSS_SELECTOR)
        self.click('#dformrlogin input[type="button"].buyBtn', by=By.CSS_SELECTOR)
        self.wait(Api.IFRAME, by=By.CSS_SELECTOR)
        logger.info("login OK")

    def get(self, url, *args, **kwargs):
        if self.current_url == url:
            return
        super().get(url, *args, **kwargs)
        logger.info("GET "+url)

    @UrlTupleCache("rec/evento/{}.json", builder=Evento.build)
    def get_eventos(self, url):
        self.get(url)
        iframe = self.safe_wait(Api.IFRAME, by=By.CSS_SELECTOR, seconds=5)
        if iframe is not None:
            src = iframe.get_attribute("src")
            self.driver.switch_to.frame(iframe)
            iframe = src
        self.wait("h2", by=By.CSS_SELECTOR)
        self.waitjs("window.show_event_modal != null")
        soup = self.get_soup(iframe)
        event = self.find_events(soup)
        logger.info(f"{len(event)} eventos encontrados")
        event = list(event)
        for i, e in enumerate(event):
            node = self.get_evento_soup(e.id)
            ids = self.find_ids_sesion(node)
            if len(ids) == 0:
                logger.warning(f"Evento {e.id} ({e.txt}) no tiene sesiones")
                continue
            event[i] = e.merge(
                sesiones=tuple(map(self.get_sesion, ids))
            )
        if iframe is not None:
            self.driver.switch_to.default_content()
        return tuple(event)

    def find_events(self, soup: Tag):
        event: Set[Evento] = set()
        for row in soup.select("div.row > div"):
            author = row.select_one("div.author")
            auttxt = get_text(author)
            if auttxt == "ABONOTEATRO":
                continue
            _id = int(row.attrs["id"].split("-")[-1])
            h2 = row.find("h2")
            txt = get_text(h2)
            href = h2.find("a").attrs["href"]
            if href != "#":
                if href in Api.LISTAS:
                    continue
                raise ApiException(f"KO {_id} {txt} URL en H2 {href}")
            logger.info(f"{_id:>5}: {txt}")
            event.add(Evento(
                id=_id,
                txt=txt,
                subtitulo=get_text(row.select_one("p.subtitulo")),
                img=row.select_one("a img").attrs["src"],
                precio=get_float(row.select_one("span.precioboxsesion")),
                lugar=Lugar(
                    txt=auttxt,
                    url=author.find("a").attrs["href"]
                )
            ))
        return tuple(sorted(event))

    def find_ids_sesion(self, soup: Tag):
        ids: Set[int] = set()
        for a in soup.select(Api.SESION):
            href = a.attrs["href"]
            if not href.startswith(Api.URLSES):
                raise ApiException("URL de sesion extraña: "+href)
            _, _id = href.split("=", 1)
            if not _id.isdigit():
                raise ApiException("URL de sesion extraña: "+href)
            ids.add(int(_id))
        return tuple(sorted(ids))

    @Cache("rec/evento/html/{}.html")
    def get_evento_soup(self, id: int):
        self.execute_script(f"show_event_modal({id})")
        self.wait(Api.EVENTO, by=By.CSS_SELECTOR)
        node = self.get_soup().select_one(Api.EVENTO)
        self.click("btnModeClose")
        return node

    @Cache("rec/sesion/html/{}.html")
    def get_sesion_soup(self, id: int):
        url = Api.URLSES + str(id)
        w = self.to_web()
        w.get(url)
        logger.info("GET "+url)
        return w.soup

    def get_sesion(self, id: int):
        soup = self.get_sesion_soup(id)
        txts = tuple(t for t in map(get_text, soup.select("div.updated.published span")) if t is not None)
        fecha = None
        dia, hora = None, None
        for txt in txts:
            if re.match(r"^\d+/\d+/\d+$", txt):
                dia = tuple(reversed(tuple(map(int, txt.split("/")))))
            elif re.match(r"^.*\s+\d+:\d+$", txt):
                hora = tuple(map(int, txt.split()[-1].split(":")))
        if None not in (dia, hora):
            fecha = datetime(*dia, *hora, 0, 0).strftime("%Y-%m-%d %H:%M")
        elif dia is not None:
            fecha = datetime(*dia, 0, 0, 0, 0).strftime("%Y-%m-%d")
        elif hora is not None:
            fecha = datetime(2000, 1, 1, *hora, 0, 0).strftime("%H:%M")
        return Sesion(id=id, fecha=fecha)

    @cached_property
    def eventos(self):
        evs: Set[Evento] = set()
        for url in Api.LISTAS:
            evs = evs.union(self.get_eventos(url))
        return tuple(sorted(evs))


if __name__ == "__main__":
    with Api("firefox") as api:
        api.login()
        list(api.eventos)