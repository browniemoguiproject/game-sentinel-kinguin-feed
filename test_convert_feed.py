import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from convert_feed import convert, offer, bucket_for, game_name, identity


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


# Metadata and one EUR price from the public feed, sampled 2026-10-23.
REAL_SAMPLES = '<rss xmlns:ns0="http://base.google.com/ns/1.0"><channel><item><title>AI War 2 PC Steam Account</title>\n      <ns0:id>321393</ns0:id>\n      <ns0:product_type>GAME_ACCOUNT</ns0:product_type>\n      <ns0:platform>Steam</ns0:platform>\n      <ns0:steam_type>app</ns0:steam_type>\n      <ns0:steam_id>573410</ns0:steam_id>\n      <ns0:region>Steam REGION FREE</ns0:region>\n      <ns0:developer>Arcen Games, LLC</ns0:developer>\n      <ns0:publisher>Arcen Games, LLC</ns0:publisher>\n      <ns0:availability>in stock</ns0:availability>\n      <ns0:country_limitations />\n      <prices><price_details>\n          <currency>EUR</currency>\n          <country>DE</country>\n          <price>13.21</price>\n          <shipping>2.69</shipping>\n          <link>https://www.kinguin.net/category/321393/ai-war-2-pc-steam-account?nosalesbooster=1&amp;currency=EUR</link>\n        </price_details>\n        </prices></item><item><title>Trine 2: Complete Story South America Steam Gift</title>\n      <ns0:id>24132</ns0:id>\n      <ns0:product_type>GAME</ns0:product_type>\n      <ns0:platform>Steam</ns0:platform>\n      <ns0:steam_type>app</ns0:steam_type>\n      <ns0:steam_id>35720</ns0:steam_id>\n      <ns0:region>Steam OTHER</ns0:region>\n      <ns0:developer>Frozenbyte</ns0:developer>\n      <ns0:publisher>Atlus</ns0:publisher>\n      <ns0:availability>in stock</ns0:availability>\n      <ns0:country_limitations>AO,BF,BI,BJ,BW,CD,CF,CG,CI,CM,CV,DJ,DZ,EG,EH,ER,ET,GA,GH,GM,GN,GQ,GW,KE,KM,LR,LS,LY,MA,MG,ML,MR,MU,MW,MZ,NA,NE,NG,RE,RW,SC,SD,SH,SL,SN,SO,ST,SZ,TD,TG,TN,TZ,UG,YT,ZA,ZM,ZW,AG,AI,AN,AW,BB,BL,BM,BS,BZ,CA,CR,CU,DM,DO,GD,GL,GP,GT,HN,HT,JM,KN,KY,LC,MF,MQ,MS,MX,NI,PA,PM,PR,SV,TC,TT,US,VC,VG,VI,AS,AU,CK,FJ,FM,GU,KI,MH,MP,NC,NF,NR,NU,NZ,PF,PG,PN,PW,SB,TK,TO,TV,VU,WF,WS,AE,AF,AM,AZ,BD,BH,BN,BT,CN,CY,GE,HK,ID,IL,IN,IQ,IR,JO,JP,KG,KH,KP,KR,KW,KZ,LA,LB,LK,MM,MN,MO,MV,MY,NP,NT,OM,PH,PK,PS,QA,SA,SG,SY,TH,TJ,TL,TM,TR,TW,UZ,VN,YD,YE,AD,AL,AT,AX,BA,BE,BG,BY,CH,CS,CZ,DD,DE,DK,EE,ES,FI,FO,FR,FX,GB,GG,GI,GR,HR,HU,IE,IM,IM,IS,IT,JE,LI,LT,LU,LV,MC,MD,ME,MK,MT,NL,NO,PL,PT,RO,RS,RU,SE,SI,SJ,SK,SM,SU,UA,VA,AQ,BV,TF,HM,GS</ns0:country_limitations>\n      <prices><price_details>\n          <currency>EUR</currency>\n          <country>DE</country>\n          <price>2.42</price>\n          <shipping>0.88</shipping>\n          <link>https://www.kinguin.net/category/24132/trine-2-complete-story-south-america-steam-gift?nosalesbooster=1&amp;currency=EUR</link>\n        </price_details>\n        </prices></item><item><title>Prodeus Steam Altergift</title>\n      <ns0:id>79225</ns0:id>\n      <ns0:product_type>ALTERGIFT</ns0:product_type>\n      <ns0:platform>Steam</ns0:platform>\n      <ns0:steam_type>app</ns0:steam_type>\n      <ns0:steam_id>964800</ns0:steam_id>\n      <ns0:region>Steam REGION FREE</ns0:region>\n      <ns0:developer>Bounding Box Software</ns0:developer>\n      <ns0:publisher>Humble Bundle</ns0:publisher>\n      <ns0:availability>in stock</ns0:availability>\n      <ns0:country_limitations />\n      <prices><price_details>\n          <currency>EUR</currency>\n          <country>DE</country>\n          <price>26.42</price>\n          <shipping>3.63</shipping>\n          <link>https://www.kinguin.net/category/79225/prodeus-steam-altergift?nosalesbooster=1&amp;currency=EUR</link>\n        </price_details>\n        </prices></item></channel></rss>'


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
            shard = json.loads((out / ('%03x.json' % bucket_for('s:1903340'))).read_text(encoding='utf-8'))
            self.assertEqual(len(shard['entries']['s:1903340']), 2)
            self.assertEqual(manifest['games'], 2)
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

    def test_gog_key_without_steam_id_is_included(self):
        gog = ITEM.replace('Steam CD Key', 'GOG CD Key').replace('<g:platform>Steam</g:platform>', '<g:platform>GOG.com</g:platform>').replace('<g:steam_id>1903340</g:steam_id>', '')
        row = offer(ET.fromstring(gog))
        self.assertIsNone(row['steamId'])
        self.assertEqual(row['identity'], 'example game')
        self.assertEqual(row['platform'], 'GOG.com')

    def test_accounts_and_gifts_have_explicit_delivery_types(self):
        for suffix, source_type, delivery in (('Account', 'GAME_ACCOUNT', 'ACCOUNT'), ('Gift', 'GAME', 'GIFT'), ('Altergift', 'ALTERGIFT', 'ALTERGIFT')):
            raw = ITEM.replace('Example GAME EU Steam CD Key', 'Example GAME EU PC Steam ' + suffix).replace('<g:product_type>GAME</g:product_type>', '<g:product_type>' + source_type + '</g:product_type>')
            row = offer(ET.fromstring(raw))
            self.assertEqual(row['gameName'], 'Example GAME')
            self.assertEqual(row['deliveryType'], delivery)
            self.assertIsNone(offer(ET.fromstring(raw.replace('<g:product_type>' + source_type + '</g:product_type>', '<g:product_type>INGAME_ACCOUNT</g:product_type>'))))
        for title in ('Game VPN PC Steam CD Key', 'Steam Gift Card EUR 20', 'Game Activation Service'):
            self.assertIsNone(game_name(title))

    def test_real_feed_account_and_gift_samples(self):
        rows = [offer(item) for item in ET.fromstring(REAL_SAMPLES).findall('./channel/item')]
        self.assertEqual([row['deliveryType'] for row in rows], ['ACCOUNT', 'GIFT', 'ALTERGIFT'])
        self.assertEqual([row['gameName'] for row in rows], ['AI War 2', 'Trine 2: Complete Story', 'Prodeus'])
        self.assertEqual([row['steamId'] for row in rows], ['573410', '35720', '964800'])

    def test_wrong_product_kind_and_console_accounts_are_excluded(self):
        raw = ITEM.replace('Steam CD Key', 'Steam Account')
        self.assertIsNone(offer(ET.fromstring(raw)))
        console = raw.replace('<g:product_type>GAME</g:product_type>', '<g:product_type>GAME_ACCOUNT</g:product_type>').replace('<g:platform>Steam</g:platform>', '<g:platform>Xbox</g:platform>')
        self.assertIsNone(offer(ET.fromstring(console)))

    def test_legacy_index_contains_only_keys_and_offer_index_keeps_delivery_types(self):
        account = ITEM.replace('Steam CD Key', 'Steam Account').replace('<g:id>12</g:id>', '<g:id>13</g:id>').replace('<g:product_type>GAME</g:product_type>', '<g:product_type>GAME_ACCOUNT</g:product_type>')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'dataset'
            convert(io.BytesIO(('<rss><channel>' + ITEM + account + '</channel></rss>').encode()), out, 'test')
            def rows(key):
                block = json.loads((out / ('%03x.json' % bucket_for(key))).read_text(encoding='utf8'))
                return block['entries'][key]
            self.assertEqual([r['deliveryType'] for r in rows('s:1903340')], ['KEY'])
            self.assertEqual({r['deliveryType'] for r in rows('o:s:1903340')}, {'KEY', 'ACCOUNT'})

    def test_normalization_keeps_sequels_and_editions_distinct(self):
        self.assertEqual(identity(game_name('Warhammer 40,000: Boltgun II EU PC Steam CD Key')), 'warhammer 40000 boltgun 2')
        self.assertNotEqual(identity(game_name('Game Deluxe Edition PC GOG CD Key')), identity('Game'))
        self.assertEqual(game_name('Doom II PC Steam CD Key'), 'Doom II')


if __name__ == '__main__':
    unittest.main()
