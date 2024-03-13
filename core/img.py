from PIL import Image, UnidentifiedImageError, ImageChops
import requests
from io import BytesIO
import logging
from os.path import dirname
from os import makedirs
from typing import List, Tuple, Any, NamedTuple, Union
from functools import cached_property
from os.path import isfile

logger = logging.getLogger(__name__)


class CornerColor(NamedTuple):
    top_left: Tuple[int, int, int]
    top_right: Tuple[int, int, int]
    bottom_left: Tuple[int, int, int]
    bottom_right: Tuple[int, int, int]


class DwnImage:
    def __init__(self, quality: int, max_width: int, max_height: int):
        self.max_width = max_width
        self.max_height = max_height
        self.quality = quality

    @property
    def aspect_ratio(self):
        return self.max_width / self.max_height

    def dwn(self, url: str, output_filename: str):
        try:
            response = requests.get(url)
            im = Image.open(BytesIO(response.content))

            width, height = im.size
            if width <= self.max_width and height <= self.max_height:
                return False

            im = im.convert('RGB')
            im = self.trim(im)

            im.thumbnail((self.max_width, self.max_height))

            dr = dirname(output_filename)
            if dr:
                makedirs(dr, exist_ok=True)
            im.save(output_filename, quality=self.quality)
            return True
        except requests.exceptions.RequestException:
            logger.critical("No se pudo descargar la imagen "+str(url), exc_info=True)
        except UnidentifiedImageError:
            logger.critical("La URL no apunta a una imagen válida "+str(url), exc_info=True)
        except IOError:
            logger.critical("Error de entrada/salida al guardar la imagen "+str(url), exc_info=True)
        return False

    def trim(self, im: Image.Image):
        colors = self.get_corner_colors(im)
        count = {}
        for c in colors:
            count[c] = count.get(c, 0) + 1
        order: List[Tuple[Any, int]] = sorted(count.items(), key=lambda kv:(kv[1], kv[0]))
        color = order.pop()[0]
        im = self.__trim(im, color)
        if count[color] < 2 or len(order) == 0:
            return im
        color = order.pop()[0]
        if count[color] < 2:
            return im
        im = self.__trim(im, color)
        return im

    def get_corner_colors(self, im: Image.Image) -> CornerColor:
        top_left_color = im.getpixel((0, 0))
        top_right_color = im.getpixel((im.width - 1, 0))
        bottom_left_color = im.getpixel((0, im.height - 1))
        bottom_right_color = im.getpixel((im.width - 1, im.height - 1))
        return CornerColor(
            top_left=top_left_color,
            top_right=top_right_color,
            bottom_left=bottom_left_color,
            bottom_right=bottom_right_color
        )

    def __trim(self, im: Image.Image, color):
        bg = Image.new(im.mode, im.size, color)
        diff = ImageChops.difference(im, bg)
        diff = ImageChops.add(diff, diff, 1, -50)
        bbox = diff.getbbox()
        if not bbox:
            logger.warning("diff.getbbox() is None")
            return im
        if bbox == im.getbbox():
            logger.warning("no se ha detectado ningún marco")
            return im

        bbox = list(bbox)
        left, upper, right, lower = bbox
        new_width = right-left
        new_height = lower-upper
        old_width, old_height = im.size
        add_width, add_height = 0, 0
        if (new_width < self.max_width):
            add_width = max(0, round((self.max_width-new_width)/2))
            wanted_height = self.max_width * 1/self.aspect_ratio
            add_height = max(0, round((wanted_height-new_height)/2))
        elif True: #(old_width-new_width) > (old_height-new_height):
            wanted_width = new_height * self.aspect_ratio
            if (wanted_width < self.max_width):
                wanted_width = self.max_width
                wanted_height = self.max_width * 1/self.aspect_ratio
                add_height = max(0, round((wanted_height-new_height)/2))
            add_width = max(0, round((wanted_width-new_width)/2))
            print(wanted_width)
        else:
            wanted_height = new_width * 1/self.aspect_ratio
            add_height = max(0, round((wanted_height-new_height)/2))

        add_right = max(0, -(left  - add_width))
        add_left  = max(0,  (right + add_width-old_width))
        add_upper = max(0, -(upper - add_height))
        add_lower = max(0,  (lower + add_height-old_height))

        bbox[0] = max(0, left - add_width + add_left)
        bbox[1] = max(0, upper - add_height + add_upper)
        bbox[2] = min(old_width, right + add_width + add_right)
        bbox[3] = min(old_height, lower + add_height + add_lower)
        bbox = tuple(bbox)
        return im.crop(bbox)


class MyImage:
    def __init__(self, image: Union[str, Image.Image], origin: Image.Image = None):
        self.__path_or_image = image
        self.__url = None
        self.origin = None

    @property
    def url(self):
        if isinstance(self.__url, str):
            return self.__url
        if isinstance(self.__path_or_image, str) and not isfile(self.__path_or_image):
            return self.__path_or_image
        raise ValueError("No hay url asociada a esta imagen")

    @url.setter
    def url(self, url: str):
        self.__url = url

    @property
    def path(self):
        if isinstance(self.__path_or_image, str):
            return self.__path_or_image

    @property
    def proto(self):
        return self.path.split("://")[0].lower()

    @cached_property
    def im(self):
        if isinstance(self.__path_or_image, Image.Image):
            return self.__path_or_image
        try:
            path = str(self.path)
            if not isfile(path):
                response = requests.get(self.path)
                path = BytesIO(response.content)
            im = Image.open(path)
            im = im.convert('RGB')
            return im
        except requests.exceptions.RequestException:
            logger.critical("No se pudo descargar la imagen "+str(self.path), exc_info=True)
        except UnidentifiedImageError:
            logger.critical("La ruta no apunta a una imagen válida "+str(self.path), exc_info=True)
        return None

    def trim(self):
        colors = self.get_corner_colors()
        count = {}
        for c in colors:
            count[c] = count.get(c, 0) + 1
        order: List[Tuple[Any, int]] = sorted(count.items(), key=lambda kv:(kv[1], kv[0]))
        color = order.pop()[0]
        im = self.__trim(color)
        if im is None or im.isKO:
            return None
        if count[color] < 2 or len(order) == 0:
            return im
        color = order.pop()[0]
        if count[color] < 2:
            return im
        im2 = im.__trim(color)
        if im2 is None or im2.isKO:
            return im
        return im2

    def __trim(self, color):
        bg = Image.new(self.im.mode, self.im.size, color)
        diff = ImageChops.difference(self.im, bg)
        diff = ImageChops.add(diff, diff, 2, -100)
        bbox = diff.getbbox()
        if not bbox:
            #logger.warning("diff.getbbox() is None")
            return None
        if bbox == self.im.getbbox():
            #logger.warning("no se ha detectado ningún marco")
            return None
        im = self.im.crop(bbox)
        return MyImage(im)

    def get_corner_colors(self) -> CornerColor:
        top_left_color = self.im.getpixel((0, 0))
        top_right_color = self.im.getpixel((self.im.width - 1, 0))
        bottom_left_color = self.im.getpixel((0, self.im.height - 1))
        bottom_right_color = self.im.getpixel((self.im.width - 1, self.im.height - 1))
        return CornerColor(
            top_left=top_left_color,
            top_right=top_right_color,
            bottom_left=bottom_left_color,
            bottom_right=bottom_right_color
        )

    @property
    def isOK(self):
        return isinstance(self.im, Image.Image)

    @property
    def isKO(self):
        return not isinstance(self.im, Image.Image)

    @property
    def width(self):
        return self.im.size[0]

    @property
    def height(self):
        return self.im.size[1]

    @property
    def isLandscape(self):
        return self.width >= self.height

    @property
    def isPortrait(self):
        return self.width < self.height

    @property
    def orientation(self):
        if not self.isOK:
            return ""
        if self.isLandscape:
            return "landscape"
        return "portrait"

    def thumbnail(self, width: int, height: int):
        im = self.im.copy()
        im.thumbnail((round(width), round(height)))
        return MyImage(im)

    @property
    def __name(self):
        if isinstance(self.__path_or_image, str):
            return self.__path_or_image
        return str(type(self.im))

    def save(self, filename: str, quality: float = None):
        dr = dirname(filename)
        if dr:
            makedirs(dr, exist_ok=True)
        try:
            self.im.save(filename, quality=quality)
        except IOError:
            logger.critical(f"No se pudo copiar {self.__name} a {filename}", exc_info=True)
            return None
        return MyImage(filename)


if __name__ == "__main__":
    import sys
    dwn = DwnImage(quality=90, max_width=500, max_height=400)
    dwn.dwn(sys.argv[1], "/tmp/a.jpg")
