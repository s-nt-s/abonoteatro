from core.web import Driver
from os import environ
from selenium.webdriver.common.by import By
from typing import NamedTuple, Tuple, Set, Dict, List
import re
from bs4 import Tag, BeautifulSoup
from datetime import datetime, date
from .cache import Cache
import logging
from functools import cached_property
import base64
import json
from urllib.parse import quote
from .util import clean_js_obj, clean_txt, get_obj, trim, get_text, clean_html, simplify_html, re_or, re_and, plain_text, get_redirect
from .wpjson import WP
from dataclasses import dataclass, asdict, is_dataclass
from urllib.parse import quote_plus
from .img import MyImage


from .filemanager import FM

logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "dic")
NOW = datetime.now().strftime("%Y-%m-%d %H:%S")


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
        if is_dataclass(obj):
            obj = asdict(obj)
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
        return Sesion(**{**self._asdict(), **kwargs})

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
        txt = clean_txt(js['recinto'])
        txt = re.sub(r"\s*\(?eventos\)?\s*$", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\s*Madrid\s*$", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"^\s*\bCines\b\s+", "", txt, flags=re.IGNORECASE)
        words = txt.lower().split()
        if len({"mk2", "palacio", "hielo"}.difference(words))==0:
            txt = "Mk2 Palacio de Hielo"
        if len({"teatro", "príncipe", "pío"}.difference(words))==0:
            txt = "Teatro Príncipe Pío"
        return Lugar(
            txt=txt,
            direccion=trim((dire or "") + ' ' + (muni or ""))
        )

    @property
    def url(self):
        if self.direccion is None:
            return "#"
        return "https://www.google.com/maps/place/" + quote(self.direccion)


@dataclass(frozen=True, order=True)
class Evento:
    id: int
    img: str
    precio: float
    categoria: str
    lugar: Lugar
    sesiones: Tuple[Sesion] = tuple()
    txt: str = None
    subtitulo: str = None
    creado: str = None
    publicado: str = None

    def __post_init__(self):
        object.__setattr__(self, 'txt', clean_txt(self.txt))
        object.__setattr__(self, 'subtitulo', clean_txt(self.subtitulo))

    def merge(self, **kwargs):
        return Evento(**{**asdict(self), **kwargs})

    @staticmethod
    def build(*args, **kwargs):
        obj = get_obj(*args, **kwargs)
        obj['lugar'] = Lugar.build(obj['lugar'])
        obj['sesiones'] = tuple(map(Sesion.build, obj['sesiones']))
        return Evento(**obj)

    @cached_property
    def titulo(self):
        txt = re.sub(r"\s+en platea\b", "", self.txt, flags=re.IGNORECASE)
        txt = re.sub(r"[\s\-]+en Callao([\s\(]*Madrid Centro[\s\)]*)?$", "", txt, flags=re.IGNORECASE)
        if txt == txt.upper():
            txt = txt.title()
        if self.subtitulo is None:
            return txt
        return txt+", "+self.subtitulo

    @cached_property
    def more(self):
        if self.id == 1122:
            return "https://www.cinesur.com/es/cine-mk2-cinesur-luz-del-tajo"
        if self.id == 1178:
            return "https://www.cinepazmadrid.es/es/cartelera"
        if self.id == 3687:
            return "https://lavaguadacines.es/"
        if self.id == 722:
            return "https://yelmocines.es/cartelera/madrid"
        if self.id == 409:
            return "https://www.cinesa.es/peliculas/"
        if self.id == 2116:
            return "https://autocines.com/cartelera-cine-madrid/"
        if self.categoria is None:
            return None
        txt = quote_plus(self.txt)
        if self.categoria == "cine":
            url = get_redirect("https://www.filmaffinity.com/es/search.php?stype%5B%5D=title&stext="+txt)
            if url and re.match(r"https://www.filmaffinity.com/es/film\d+.html", url):
                return url
            return "https://www.google.es/search?&complete=0&gbv=1&q="+txt
        return "https://www.atrapalo.com/busqueda/?pg=buscar&producto=ESP&keyword="+txt

    @property
    def html(self) -> Tag:
        soup = FM.cached_load(f"rec/detail/{self.id}.html")
        if soup:
            return BeautifulSoup(clean_html(str(soup)), "html.parser")

    @cached_property
    def fichahtml(self):
        n = self.html.select_one("#informacioneventolargo")
        if n is None:
            return None
        for d in n.findAll("div"):
            if get_text(d) == "Ver menos":
                d.extract()
        for e in n.select(":scope > *"):
            txt = (get_text(e) or "")
            word = re.sub(r"\s+:", ":", txt).upper().split(":")[0].strip()
            if word in ("SINOPSIS", "SINOSPSIS"):
                break
            n.append(e)
        n = BeautifulSoup(simplify_html(str(n)), "html.parser")
        n.attrs.clear()
        return str(n)

    @cached_property
    def dias_hora(self):
        dias: Dict[str, List[Sesion]] = {}
        for e in self.sesiones:
            dia = 'Cualquier día'
            if re.search(r"V[áa]lid[oa]s?.*?de lunes a jueves", self.fichahtml, flags=re.IGNORECASE):
                dia = "L-J"
            if re.search(r"V[áa]lid[oa]s?.*?lunes, martes y jueves", self.fichahtml, flags=re.IGNORECASE):
                dia = "L,M,J"
            if e.fecha is not None:
                dh = e.fecha.split(" ")
                if len(dh[0]) == 10:
                    dt = date(*map(int, dh[0].split("-")))
                    dia = "LMXJVSD"[dt.weekday()] + \
                        f' {dt.day:>2}-'+MONTHS[dt.month-1]
            if dia not in dias:
                dias[dia] = []
            dias[dia].append(e)
        return tuple(dias.items())

    @cached_property
    def fechas(self):
        fechas: Set[str] = set()
        for e in self.sesiones:
            if e.fecha is not None:
                fechas.add(e.fecha)
        return tuple(sorted(fechas))

    @cached_property
    def isInfantil(self):
        t = plain_text(self.titulo)
        if re_or(t, "para niños", "familiar", "infantil"):
            return True
        i = plain_text(self.fichahtml, is_html=True)
        if re_or(
            i, 
            "los mas pequeños",
            "publico infantil",
            "espectaculo recomendado para niños",
            "a partir de 3 años",
            "la niñez que llevamos dentro",
            "pirata garrapata"
        ):
            return True
        if re_and(i, "niños", "familiar"):
            return True
        return False

    @staticmethod
    def create(js: Dict, detail: Tag, categoria: str, sesiones: Tuple[Sesion]):
        precio = max(0, (js.get('precio') or 0), (js.get('pvp') or 0))
        if int(precio) == precio:
            precio = int(precio)
        return Evento(
            id=js['id'],
            txt=clean_txt(js['name']),
            subtitulo=clean_txt(js['sub']),
            img=js['image'],
            precio=precio,
            lugar=Lugar.create(js),
            sesiones=sesiones,
            categoria=categoria
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
        self.click(
            '#dformrlogin input[type="button"].buyBtn', by=By.CSS_SELECTOR)
        self.wait(Api.IFRAME, by=By.CSS_SELECTOR)
        logger.info("login OK")

    def get(self, url):
        if self.current_url == url:
            return
        r = super().get(url)
        logger.info("GET "+url)
        self.wait_ready()
        return r

    def wait_ready(self):
        self.waitjs('window.document.readyState === "complete"')


class Api:
    IFRAME = 'div[role="main"] iframe'
    BTNDAY = "div.bsesion a.buyBtn"
    EVENT = '#modal_event_content > div.container'
    URLDAY = 'https://compras.abonoteatro.com/compra/?eventocurrence='
    DETAIL = 'https://www.abonoteatro.com/catalogo/detalle_evento.php'
    CATALOG = (
        "https://compras.abonoteatro.com/teatro/",
        "https://compras.abonoteatro.com/cine-y-eventos/",
        "https://www.abonoteatro.com/catalogo/cine_peliculas.php",
    )

    def __init__(self, publish=None):
        self.__w = None
        self.__base64: Dict[str, str] = {}
        self.__types = None
        self.publish: Dict[int, str] = publish or {}

    def get(self, url, *args, label_log=None, **kwargs):
        if self.w.url == url and len(args) == 0 and len(kwargs) == 0:
            return
        self.w.get(url, *args, **kwargs)
        log = (str(label_log)+":" if label_log is not None else "")
        if kwargs:
            logger.info(f"{log} POST {url}".strip())
        else:
            logger.info(f"{log} GET {url}".strip())
        self.__find_types()

    def __find_types(self):
        options = self.w.soup.select("#select_type_event option")
        if len(options) == 0:
            return
        typs = {}
        for o in options:
            val = o.attrs["value"].strip()
            txt = plain_text(o)
            if val.isdigit() and txt is not None:
                typs[int(val)] = txt.lower()
        if len(typs) == 0:
            return
        FM.dump("rec/types.json", typs)
        self.__types = typs

    @property
    def types(self):
        if self.__types is None:
            self.__find_types()
        return self.__types

    @property
    def w(self):
        if self.__w is None:
            with PortalDriver("firefox") as w:
                w.login()
                self.__w = w.to_web()
        return self.__w

    @cached_property
    def wp(self):
        w = WP(self.w.s, "https://compras.abonoteatro.com")
        return w

    @TupleCache("rec/eventos.json", builder=Evento.build)
    def get_events(self):
        evs: Dict[int, Evento] = {}
        for url in Api.CATALOG:
            for e in self.get_events_from(url):
                if e.id not in evs or e.precio > evs[e.id].precio:
                    evs[e.id] = e.merge(
                        publicado=self.publish.get(e.id, NOW),
                        creado=self.media_date.get(e.img)
                    )
        return tuple(sorted(evs.values()))

    @cached_property
    def media_date(self):
        data = {}
        for m in self.wp.media:
            f = m['modified'].replace("T", " ")[:16]
            u = m['source_url']
            data[u] = f
        return data

    def get_events_from(self, url):
        evs: Set[Evento] = set()
        for js in self.get_js_events(url):
            if js['name'] == "Compra o Regala ABONOTEATRO":
                continue
            id = js['id']
            detail = self.get_soup_detail(id)
            evs.add(Evento.create(
                js=js,
                detail=detail,
                categoria=self.find_category(url, js),
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
                w.wait_ready()
                iframe = src
            w.wait("h2", by=By.CSS_SELECTOR)
            w.waitjs("window.show_event_modal != null")
            soup = w.get_soup(iframe)
            npts = soup.select('input[type="hidden"]')
        if len(npts) == 0:
            raise ApiException(f"0 eventos en {url}")
        return npts

    @Cache("rec/detail/{}.html")
    def get_soup_detail(self, id: int):
        self.get(Api.DETAIL, action='show',
                 content=self.get_base64(id), label_log=id)
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
        if len(ses) == 0:
            logger.warning(f"{id} no se han encontrado sesiones")
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
        if m not in MONTHS:
            return self.__visit_day(id)
        month = MONTHS.index(m) + 1
        h, m = map(int, hm.split(":"))
        return Sesion(
            id=id,
            fecha=datetime(year, month, day, h, m, 0,
                           0).strftime("%Y-%m-%d %H:%M")
        )

    def __visit_day(self, id: int):
        soup = self.get_soup_day(id)
        txts = tuple(t for t in map(get_text, soup.select(
            "div.updated.published span")) if t is not None)
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

    def find_category(self, url: str, js: Dict):
        _id = js['id']
        cat = js['id_categoria']
        img = MyImage.get(js['image'])

        def _or(s: str, *args):
            b = re_or(s, *args)
            if b is not None:
                logger.debug(f"{_id} cumple {b}")
                return True
            return False

        def _and(s: str, *args):
            b = re_and(s, *args)
            if b is not None:
                logger.debug(f"{_id} cumple {b}")
                return True
            return False

        path = url.rstrip("/").split("/")[-1]
        if path == "cine_peliculas.php":
            return "cine"

        cabadrag = "cabaret / drag"
        humor = "humor / impro"
        musica = "musica / danza"
        expomus = "exposición / museo"
        name = plain_text(js['name'] + " "+(js['sub'] or ""))
        if img and img.isOK and img.txt:
            name = (name + " " + (plain_text(img.txt) or "")).strip()
        info = plain_text((js['info'] or "")+" "+(js['condicion'] or ""), is_html=True)
        name_info = (name+" "+(info or "")).strip()
        recinto = plain_text(js['recinto']) or ""
        if recinto == "wizink center baloncesto":
            return "otros"
        if _or(name+" "+recinto, "autocine", "cinesa", "cinesur", "yelmo"):
            return "cine"
        if _and(name+" "+recinto, "mk2", ("sesion", "director")):
            return "cine"
        if ("eventos" not in recinto) and _or(name+" "+recinto, "mk2"):
            return "cine"
        if _or(name, "cines"):
            return "cine"
        if _or(info, "jardin botanico"):
            return "otros"
        if _or(name, "exposicion", "exposiciones", "museum", "museo"):
            return expomus
        if path == "cine-y-eventos":
            return "otros"
        if _or(name, "magic", "magia", "magos?", "mentalistas?", "hipnosis"):
            return "magia"
        if _or(name, "impro", "el humor de", "clown"):
            return humor
        if _or(name, "flamenco", "saeta flamenca"):
            return "flamenco"
        if _or(name, "cabaret", "drag", "hole", "burlesque"):
            return cabadrag
        if _or(name, "bingo", "karaoke", "circo", "parque de atracciones"):
            return "otros"
        if _or(name, "b vocal", "opera", "musica en vivo", "jazz", "tributo", "sinfonico", "musical", "concierto", r"boleros?", "orquesta", "pianista"):
            return musica

        if _or(info, "monologo narrativo"):
            return "teatro"
        if _or(info, "mentalismo", "espectaculo de magia", "espiritismo"):
            return "magia"
        if _and(info, r"exposicion|expondran?", "obras"):
            return expomus
        if _or(
            name_info,
            "stand ?up",
            "stand-up",
            "open-mic",
            "open ?mic",
            "monologos",
            "monologuistas",
            r"impromonologos?",
            "comedia pura",
            "show de comedia",
            "humor blanco",
            "comedia totalmente improvisada",
            "improvisacion teatral",
            "comedy club",
            "show improvisado",
            "chic comedy",
            "humor inteligente",
            "comico ocasional",
            "humorista",
            "presenta su monologo",
            "un monologo para",
            "con un monologo que te"
        ):
            # imporate que 'monologos' sea en plural para no confundir con cosas que no son humor
            return humor

        if _or(
            info,
            r"comedias? musical(es)?",
            r"gran(des)? musical(es)?",
            "espectaculo musical",
            "musical integramente cantado",
            "viaje musical",
            "concierto",
            "percusion",
            "banda sonora"
        ):
            return musica
        if _and(name_info, "clown", "humor"):
            return humor
        if _or(info, "mentalista", "prestidigitador", "mentalismo"):
            return "magia"
        if _and(info, ("humor", "humores", "risas"), ("improvisar", "improvisacion", "comicos")):
            return humor
        if _and(info, "show", "comicos?"):
            return humor
        if _or(name, "el show de"):
            return humor
        if recinto == "sala de humor fuencarral":
            # importante que vaya al final
            # porque a veces hace magia u otras cosas
            return humor
        if recinto == "sala houdini":
            return "magia"
        if _or(info, "esta obra puede herir la sensibilidad del espectador"):
            return "teatro"
        if _or(
            info,
            "podcast",
            "globoflexia",
            "lanzamiento de su nuevo libro"
        ):
            return "otros"
        if _or(
            info,
            "cabaret",
            "drags?"
        ):
            return cabadrag
        if cat == 19 and _or(info, "tematica erotica"):
            return cabadrag
        categoria = {
            11: "teatro", # teatro / teatro musical
            15: "magia", # magia
            17: "otros", # circo / cabaret
            18: "otros", # conferencia
            19: musica, # musica
            20: "otros", # deporte
            21: "cine", # cine
            23: humor, # monologo
            24: expomus, # parque tematico / exposicion
            28: musica, # danza
            22: musica,
            25: "otros",
        }.get(cat)
        if categoria is not None:
            logger.debug(f"{_id} categoria={cat} -> "+categoria)
            return categoria
        logger.debug(f"{_id} no cumple ninguna condición")
        return "teatro"
