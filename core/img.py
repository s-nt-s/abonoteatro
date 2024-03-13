from PIL import Image, UnidentifiedImageError, ImageChops
import requests
from io import BytesIO
import logging
from os.path import dirname
from os import makedirs
from typing import List, Tuple, Any, NamedTuple

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
        except requests.exceptions.RequestException as e:
            logger.critical("No se pudo descargar la imagen "+str(url), exc_info=True)
        except UnidentifiedImageError:
            logger.critical("La URL no apunta a una imagen válida "+str(url), exc_info=True)
        except IOError as e:
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


if __name__ == "__main__":
    import sys
    dwn = DwnImage(quality=90, max_width=500, max_height=400)
    dwn.dwn(sys.argv[1], "/tmp/a.jpg")
