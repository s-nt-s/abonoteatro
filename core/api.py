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
import base64
import json
from urllib.parse import quote
from .util import clean_js_obj, clean_txt, get_obj, trim, get_text, get_or

from .filemanager import FM

logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")


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


class UrlCache(Cache):
    def parse_file_name(self, url: str, slf=None, **kargv):
        path = url.rstrip("/").split("/")[-1]
        return self.file.format(path)


class UrlTupleCache(TupleCache):
    def parse_file_name(self, url: str, slf=None, **kargv):
        path = url.rstrip("/").split("/")[-1]
        return self.file.format(path)


class Sesion(NamedTuple):
    id: int
    fecha: str = None

    @property
    def url(self):
        return Api.URLDAY + str(self.id)

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
    direccion: str

    @staticmethod
    def build(*args, **kwargs):
        obj = get_obj(*args, **kwargs)
        return Lugar(**obj)

    @staticmethod
    def create(js: Dict):
        dire = js['direccion']
        muni = js['municipio']

        return Lugar(
            txt=js['recinto'],
            direccion=trim((dire or "") + ' ' + (muni or ""))
        )

    @property
    def url(self):
        if self.direccion is None:
            return "#"
        return "https://www.google.com/maps/place/" + quote(self.direccion)


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
        d = (self.precio-Api.PRICE)
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
        return FM.cached_load(f"rec/detail/{self.id}.html")

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

    @staticmethod
    def create(js: Dict, detail: Tag, sesiones: Tuple[Sesion]):
        return Evento(
            id=js['id'],
            txt=clean_txt(js['name']),
            subtitulo=clean_txt(js['sub']),
            img=js['image'],
            precio=get_or(js, 'precio', 'pvp'),
            lugar=Lugar.create(js),
            sesiones=sesiones
        )


class ApiException(Exception):
    pass


USER = environ.get("ABONOTEATRO_USER")
PSW = environ.get("ABONOTEATRO_PSW")


class PortalDriver(Driver):
    def login(self, user: str = USER, psw: str = PSW):
        self.get("https://compras.abonoteatro.com/login/")
        self.val("nabonadologin", user)
        self.val("contrasenalogin", psw)
        self.click('button.cmplz-deny', by=By.CSS_SELECTOR)
        self.click('#dformrlogin input[type="button"].buyBtn', by=By.CSS_SELECTOR)
        self.wait(Api.IFRAME, by=By.CSS_SELECTOR)
        logger.info("login OK")

    def get(self, url):
        if self.current_url == url:
            return
        r = super().get(url)
        logger.info("GET "+url)
        self.waitjs('window.document.readyState === "complete"')
        return r


class Api:
    IFRAME = 'div[role="main"] iframe'
    BTNDAY = "div.bsesion a.buyBtn"
    EVENT = '#modal_event_content > div.container'
    URLDAY = 'https://compras.abonoteatro.com/compra/?eventocurrence='
    DETAIL = 'https://www.abonoteatro.com/catalogo/detalle_evento.php'
    PRICE = 3.50
    CATALOG = (
        "https://compras.abonoteatro.com/teatro/",
        "https://compras.abonoteatro.com/cine-y-eventos/",
        "https://www.abonoteatro.com/catalogo/cine_peliculas.php",
    )

    def __init__(self):
        self.__w = None
        self.__base64: Dict[str, str] = {}

    def get(self, url, *args, **kwargs):
        if self.w.url == url and len(args) == 0 and len(kwargs) == 0:
            return
        self.w.get(url, *args, **kwargs)
        if kwargs:
            logger.info("POST "+url)
        else:
            logger.info("GET "+url)

    @property
    def w(self):
        if self.__w is None:
            with PortalDriver("firefox") as w:
                w.login()
                self.__w = w.to_web()
        return self.__w

    @cached_property
    def events(self):
        evs: Set[Evento] = set()
        for url in Api.CATALOG:
            evs = evs.union(self.get_events(url))
        return tuple(sorted(evs))

    def get_events(self, url):
        evs: Set[Evento] = set()
        for js in self.get_js_events(url):
            if js['name'] == "Compra o Regala ABONOTEATRO":
                continue
            id = js['id']
            detail = self.get_soup_detail(id)
            evs.add(Evento.create(
                js=js,
                detail=detail,
                sesiones=self.find_days(js['id'])
            ))
        return tuple(sorted(evs))

    @UrlCache("rec/event/{}.json")
    def get_js_events(self, url: str):
        evs: Dict[int, Dict] = {}
        for id, value, data in self.get_base64_event(url):
            logger.info(f"{id:>6} {data['name']}")
            data["__parent__"] = self.w.url
            evs[data['id']] = data
        return tuple(sorted(evs.values(), key=lambda e: e['id']))

    def get_base64_event(self, url: str):
        inpt = self.__get_list_event(url)
        for i in inpt:
            id = i.attrs.get("id")
            if id is None or not re.match(r"^event_content_json_id_\d+$", id):
                continue
            value = i.attrs.get("value")
            if value is None or len(value.strip()) == 0:
                continue
            js = base64.b64decode(value).decode()
            data: Dict = clean_js_obj(json.loads(js))
            self.__base64[data['id']] = value
            yield (data['id'], value, data)

    def __get_list_event(self, url: str):
        self.get(url)
        iframe = self.w.soup.select_one(Api.IFRAME)
        if iframe is not None:
            self.get(iframe.attrs["src"])
        npts = self.w.soup.select('input[type="hidden"]')
        if len(npts) > 0:
            return npts
        with PortalDriver("firefox") as w:
            w.login()
            w.get(url)
            iframe = w.safe_wait(Api.IFRAME, by=By.CSS_SELECTOR, seconds=5)
            if iframe is not None:
                src = iframe.get_attribute("src")
                w.driver.switch_to.frame(iframe)
                iframe = src
            w.wait("h2", by=By.CSS_SELECTOR)
            w.waitjs("window.show_event_modal != null")
            soup = w.get_soup(iframe)
            return soup.select('input[type="hidden"]')

    @Cache("rec/detail/{}.html")
    def get_soup_detail(self, id: int):
        self.get(Api.DETAIL, action='show', content=self.get_base64(id))
        return self.w.soup

    def get_base64(self, id: int):
        if id not in self.__base64:
            for url in Api.CATALOG:
                list(self.get_base64_event(url))
                if id in self.__base64:
                    return self.__base64[id]
        return self.__base64[id]

    def find_days(self, id: int):
        arr = []
        soup = self.get_soup_detail(id)
        for a in soup.select(Api.BTNDAY):
            href = a.attrs["href"]
            if not href.startswith(Api.URLDAY):
                raise ApiException("URL de sesion extraña: "+href)
            _, did = href.split("=", 1)
            if not did.isdigit():
                raise ApiException("URL de sesion extraña: "+href)
            arr.append((int(did), a))
        ses: Set[Sesion] = set()
        for did, a in arr:
            ses.add(self.__get_day(did, a))
        return tuple(sorted(ses, key=lambda s: (s.fecha, s.id)))

    def __get_day(self, id: int, a: Tag):
        div = a.find_parent("div", class_=re.compile(r".*\bbsesion\b.*"))
        hm = get_text(a)
        if hm is None or not re.match(r"^\d+:\d+$", hm):
            hm = get_text(div.select_one("h3.horasesion"))
        if hm is None or not re.match(r"^\d+:\d+$", hm):
            return self.__visit_day(id)
        fch = tuple(map(get_text, div.select("div.bfechasesion > p")))
        if len(fch) != 3 or not fch[1].isdigit():
            return self.__visit_day(id)
        day = int(fch[1])
        my = fch[0].split()
        if len(my) != 2 or not my[1].isdigit():
            return self.__visit_day(id)
        year = int(my[1])
        m = my[0].lower()[:3]
        months = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "dic")
        if m not in months:
            return self.__visit_day(id)
        month = months.index(m) + 1
        h, m = map(int, hm.split(":"))
        return Sesion(
            id=id,
            fecha=datetime(year, month, day, h, m, 0, 0).strftime("%Y-%m-%d %H:%M")
        )

    def __visit_day(self, id: int):
        soup = self.get_soup_day(id)
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

    @Cache("rec/day/{}.html")
    def get_soup_day(self, id: int):
        url = Api.URLDAY + str(id)
        self.get(url)
        logger.info("GET "+url)
        return self.w.soup
