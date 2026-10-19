"""Streaming Kinguin feed experiment. No Android or public hosting changes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import re
import time
import unicodedata
import urllib.request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

G = '{http://base.google.com/ns/1.0}'
MAX_FILE = 25 * 1024 * 1024
BUCKET_COUNT = 4096
PC_PLATFORMS = {'steam', 'gog', 'gog.com', 'epic games', 'epic games store', 'epic',
                'uplay', 'ubisoft connect', 'origin', 'ea app', 'ea', 'battle.net',
                'battlenet', 'rockstar', 'rockstar games launcher', 'bethesda',
                'windows store', 'microsoft store', 'other', 'pc'}


def identity(title):
    title = re.sub(r'(?<=\d)[,\u00a0\u202f](?=\d{3}(?:\D|$))', '', title)
    title = ''.join(c for c in unicodedata.normalize('NFD', title)
                    if unicodedata.category(c) != 'Mn').lower()
    title = re.sub("[’'™®©]", '', title).replace('&', ' and ')
    title = ''.join(c if c.isalnum() else ' ' for c in title)
    roman = {'ii':'2', 'iii':'3', 'iv':'4', 'v':'5', 'vi':'6', 'vii':'7', 'viii':'8', 'ix':'9', 'x':'10'}
    return ' '.join(roman.get(c, c) for c in title.split())


def game_name(title):
    # Only a key with an explicit PC storefront or PC label. Never account/gift/VPN offers.
    if re.search(r'\b(?:account|gift|vpn|activation service)\b', title, re.I):
        return None
    store = r'(?:Steam|GOG(?:\.com)?|Epic(?: Games(?: Store)?)?|Uplay|Ubisoft Connect|Origin|EA(?: App)?|Battle\.?net|Rockstar(?: Games Launcher)?|Bethesda|Windows Store|Microsoft Store)'
    suffix = r'\s+(?:(?:PC\s+)?' + store + r'|PC)(?:\s+(?:CD|Digital))?\s+Key\s*$'
    match = re.search(suffix, title, re.I)
    if not match:
        return None
    name = title[:match.start()].strip()
    # Geographic labels, not game editions, can be removed from the end.
    regions = r'(?:EU|EUROPE|EMEA|ASIA|LATAM|ROW|GLOBAL|WORLDWIDE|RU/CIS|CIS|NA|US|UK|DE|FR|IT|ES|PL|BR|TR|CN|JP|RU|AU|CA)'
    name = re.sub(r'\s+' + regions + r'\s*$', '', name, flags=re.I).strip()
    return name or None


def bucket_for(key):
    return int(hashlib.sha256(key.encode('utf-8')).hexdigest()[:3], 16)


def shard_name(bucket):
    return '%03x.json' % bucket


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def money(value):
    try:
        number = Decimal(value)
        return value if number.is_finite() and number >= 0 else None
    except (InvalidOperation, TypeError):
        return None


def offer(item):
    def g(name):
        return (item.findtext(G + name) or '').strip()
    steam = g('steam_id')
    title = (item.findtext('title') or '').strip()
    name = game_name(title)
    platform = g('platform')
    if (not name or g('product_type') != 'GAME' or platform.casefold() not in PC_PLATFORMS
            or (platform.casefold() in {'microsoft store','other','pc'} and not re.search(r'\bPC\b', title, re.I))):
        return None
    steam = str(int(steam)) if steam.isdigit() and int(steam) > 0 and g('steam_type') == 'app' else None
    prices = []
    for row in item.findall('./prices/price_details'):
        currency = (row.findtext('currency') or '').strip()
        price = money((row.findtext('price') or '').strip())
        link = (row.findtext('link') or '').strip()
        try:
            parsed = urlsplit(link)
            port = parsed.port
        except ValueError:
            continue
        if (len(currency) != 3 or not currency.isalpha() or price is None
                or parsed.scheme != 'https' or parsed.hostname != 'www.kinguin.net'
                or parsed.username or parsed.password or port not in (None, 443)
                or not re.fullmatch(r'/category/\d+/[a-zA-Z0-9_%-]+/?', parsed.path)):
            continue
        prices.append({'currency': currency, 'price': price,
                       'additionalCost': money((row.findtext('shipping') or '').strip()),
                       'priceCountry': (row.findtext('country') or '').strip() or None,
                       'url': link})
    if not prices or not g('id'):
        return None
    return {'steamId': steam, 'productId': g('id'), 'title': title,
            'gameName': name, 'identity': identity(name), 'platform': platform,
            'developer': g('developer'), 'publisher': g('publisher'),
            'region': g('region'), 'countryLimitationsRaw': g('country_limitations'),
            'availability': g('availability'), 'updatedTimestamp': g('updated_timestamp'),
            'prices': prices}


def convert(stream, output, source_label):
    started = time.monotonic()
    # New output only: a failed experiment must not replace a valid dataset.
    output.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(str(output / 'working.sqlite'))
    db.execute('CREATE TABLE offers (id TEXT PRIMARY KEY, steam TEXT, title TEXT, body TEXT)')
    db.execute('CREATE TABLE lookup (key TEXT, bucket INTEGER, product TEXT, PRIMARY KEY (key, product))')
    db.execute('CREATE INDEX lookup_product ON lookup(product)')
    counts = Counter()
    stack = []
    try:
        for event, element in ET.iterparse(stream, events=('start', 'end')):
            if event == 'start':
                stack.append(element)
                continue
            if element.tag == 'item':
                counts['itemsRead'] += 1
                result = offer(element)
                if result is not None:
                    db.execute('INSERT OR REPLACE INTO offers VALUES (?, ?, ?, ?)',
                               (result['productId'], result['steamId'], result['identity'], compact(result)))
                    db.execute('DELETE FROM lookup WHERE product=?', (result['productId'],))
                    keys = ['t:' + result['identity']]
                    if result['steamId']:
                        keys.append('s:' + result['steamId'])
                    for key in keys:
                        db.execute('INSERT INTO lookup VALUES (?, ?, ?)', (key, bucket_for(key), result['productId']))
                    counts['matchingRows'] += 1
                # Release the item AND its reference in channel (bounded XML memory).
                if len(stack) > 1:
                    stack[-2].remove(element)
                element.clear()
                if counts['itemsRead'] % 5000 == 0:
                    db.commit()
                    print(compact({'progress': dict(counts), 'seconds': round(time.monotonic()-started)}), flush=True)
            stack.pop()
        db.commit()
        unique = db.execute('SELECT COUNT(*), COUNT(DISTINCT title) FROM offers').fetchone()
        if not unique[0]:
            raise ValueError('No usable offers; dataset not publishable')
        shards = []
        db.execute('CREATE INDEX lookup_bucket ON lookup(bucket, key, product)')
        generated = datetime.now(timezone.utc).isoformat()
        for bucket in range(BUCKET_COUNT):
            path = output / shard_name(bucket)
            with path.open('w', encoding='utf-8', newline='\n') as f:
                f.write('{"schema":2,"generatedAt":' + compact(generated) + ',"entries":{')
                first_game = True
                previous = None
                for steam, body in db.execute('SELECT l.key, o.body FROM lookup l JOIN offers o ON o.id=l.product WHERE l.bucket=? ORDER BY l.key, l.product', (bucket,)):
                    if steam != previous:
                        if not first_game:
                            f.write('],')
                        f.write(compact(steam) + ':[')
                        previous = steam
                        first_game = False
                    else:
                        f.write(',')
                    f.write(body)
                if not first_game:
                    f.write(']')
                f.write('}}\n')
            size = path.stat().st_size
            if size > MAX_FILE:
                raise ValueError('Shard exceeds Cloudflare file limit: ' + path.name)
            shards.append({'file': path.name, 'bytes': size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        manifest = {'schema': 2, 'generatedAt': generated,
                    'source': source_label, 'status': 'prototype-not-published',
                    'itemsRead': counts['itemsRead'], 'offers': unique[0], 'games': unique[1],
                    'partition': 'first 3 lowercase SHA256 hex digits of UTF-8 lookup key; s:appid or t:normalized-title',
                    'seconds': round(time.monotonic()-started, 2),
                    'totalBytes': sum(s['bytes'] for s in shards),
                    'maxShardBytes': max(s['bytes'] for s in shards), 'shards': shards}
        (output / 'manifest.json').write_text(compact(manifest), encoding='utf-8')
        print(compact({k:v for k,v in manifest.items() if k != 'shards'}), flush=True)
        return manifest
    finally:
        db.close()
        # Work database is not part of the static export.
        (output / 'working.sqlite').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, help='Local XML path or public Kinguin HTTPS feed')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.source.startswith('https://'):
        url = urlsplit(args.source)
        if url.hostname != 'feeds.kinguin.net' or url.username or url.password:
            parser.error('Only the public feeds.kinguin.net source is supported')
        request = urllib.request.Request(args.source, headers={'User-Agent':'GameSentinel-FeedPrototype/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            if urlsplit(response.url).hostname != 'feeds.kinguin.net':
                raise ValueError('Unexpected feed redirect')
            convert(response, args.output, args.source)
    else:
        with open(args.source, 'rb') as stream:
            convert(stream, args.output, Path(args.source).name)


if __name__ == '__main__':
    main()
