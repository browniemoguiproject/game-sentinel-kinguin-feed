import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from convert_feed import convert, offer


ITEM = '''<item xmlns:g="http://base.google.com/ns/1.0">
<title>Example GAME EU Steam CD Key</title><g:id>12</g:id>
<g:product_type>GAME</g:product_type><g:platform>Steam</g:platform>
<g:steam_type>app</g:steam_type><g:steam_id>1903340</g:steam_id>
<g:region>EU</g:region><g:country_limitations>US,JP</g:country_limitations>
<g:availability>in stock</g:availability><prices>
<price_details><currency>EUR</currency><price>24.88</price><shipping>3.72</shipping>
<country>DE</country><link>https://www.kinguin.net/category/12/example?currency=EUR</link></price_details>
<price_details><currency>USD</currency><price>29.12</price><shipping>4.35</shipping>
<link>https://www.kinguin.net/category/12/example?currency=USD</link></price_details>
</prices></item>'''


class ConverterTest(unittest.TestCase):
    def test_preserves_native_prices_costs_and_region_without_conversion(self):
        row = offer(ET.fromstring(ITEM))
        self.assertEqual(row['steamId'], '1903340')
        self.assertEqual(row['countryLimitationsRaw'], 'US,JP')
        self.assertEqual(row['prices'][0]['price'], '24.88')
        self.assertEqual(row['prices'][0]['additionalCost'], '3.72')
        self.assertEqual(row['prices'][0]['priceCountry'], 'DE')
        self.assertEqual(row['prices'][1]['price'], '29.12')

    def test_console_product_cannot_be_assigned_to_steam_game(self):
        console = ITEM.replace('<g:platform>Steam</g:platform>', '<g:platform>Xbox</g:platform>')
        self.assertIsNone(offer(ET.fromstring(console)))

    def test_variants_for_same_game_survive_round_trip(self):
        variant = ITEM.replace('<g:id>12</g:id>', '<g:id>13</g:id>').replace('GAME EU', 'GAME Deluxe EU')
        feed = ('<rss><channel>' + ITEM + variant + '</channel></rss>').encode()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'dataset'
            manifest = convert(io.BytesIO(feed), out, 'test')
            shard = json.loads((out / ('%03x.json' % (1903340 % 4096))).read_text(encoding='utf-8'))
            self.assertEqual(len(shard['games']['1903340']), 2)
            self.assertEqual(manifest['games'], 1)
            self.assertEqual(manifest['offers'], 2)
            self.assertFalse((out / 'working.sqlite').exists())

    def test_truncated_feed_never_gets_publishable_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'dataset'
            with self.assertRaises(ET.ParseError):
                convert(io.BytesIO(('<rss><channel>' + ITEM).encode()), out, 'truncated')
            self.assertFalse((out / 'manifest.json').exists())

    def test_invalid_price_and_external_link_are_not_accepted(self):
        invalid = ITEM.replace('24.88', 'NaN').replace('www.kinguin.net', 'unrelated.example')
        self.assertIsNone(offer(ET.fromstring(invalid)))


if __name__ == '__main__':
    unittest.main()
