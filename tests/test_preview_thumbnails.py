import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

from PIL import Image
from tools.equipment.preview import render


class Pictures(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.images = []
        self.links = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.images.append(dict(attrs))
        if tag == 'a':
            self.links.append(dict(attrs)['href'])


class PreviewThumbnails(unittest.TestCase):
    def test_card_image_can_link_to_a_wiki_page_or_disable_its_file_link(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            images = directory / 'images'
            images.mkdir()
            Image.new('RGBA', (16, 8)).save(images / '原版.png')
            markup = '[[File:原版.png|link=顶级武器-警用 M4|alt=警用 M4]] [[File:原版.png|link=]]'
            page = Pictures(render(markup, directory, {'顶级武器-警用 M4': 'police-m4.html'}))
            self.assertEqual(page.links, ['police-m4.html'])
            self.assertEqual(len(page.images), 2)
            self.assertEqual(page.images[0]['alt'], '警用 M4')

    def test_intrinsic_pixels_fit_requested_box_and_original_art_keeps_its_link(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            images = directory / 'images'
            images.mkdir()
            source = images / '图 A.png'
            Image.new('RGBA', (320, 200), (248, 96, 20, 128)).save(source)
            original = source.read_bytes()
            sizes = ['', '|128px', '|128x128px', '|x40px', '|640px']
            links = ' '.join('[[File:图 A.png' + size + '|alt=图]]' for size in sizes)
            page = Pictures(render(links, directory, {}))
            self.assertEqual(len(page.images), len(sizes))
            for img, expected in zip(page.images, [(320, 200), (128, 80), (128, 80), (64, 40), (320, 200)]):
                with Image.open(directory / unquote(img['src'].lstrip('/'))) as pixels:
                    self.assertEqual(pixels.size, expected)
                if 'width' in img:
                    self.assertEqual((int(img['width']), int(img['height'])), expected)
            self.assertEqual(set(map(unquote, page.links)), {'/images/图 A.png'})
            self.assertEqual(page.images[0]['src'], page.images[-1]['src'])
            self.assertEqual(source.read_bytes(), original)
