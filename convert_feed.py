"""Streaming Kinguin feed experiment. No Android or public hosting changes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import urllib.request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

G = '{http://base.google.com/ns/1.0}'
MAX_FILE = 25 * 1024 * 1024
BUCKET_COUNT = 4096


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
    # Preserve every Steam GAME variant, rather than guessing the base edition.
    if (not steam.isdigit() or int(steam) <= 0 or g('steam_type') != 'app'
            or g('platform').casefold() != 'steam' or g('product_type') != 'GAME'):
        return None
    prices = []
    for row in item.findall('./prices/price_details'):
        currency = (row.findtext('currency') or '').strip()
        price = money((row.findtext('price') or '').strip())
        link = (row.findtext('link') or '').strip()
        parsed = urlsplit(link)
        if (len(currency) != 3 or not currency.isalpha() or price is None
                or parsed.scheme != 'https' or parsed.hostname != 'www.kinguin.net'
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            continue
        prices.append({'currency': currency, 'price': price,
                       'additionalCost': money((row.findtext('shipping') or '').strip()),
                       'priceCountry': (row.findtext('country') or '').strip() or None,
                       'url': link})
    if not prices or not g('id'):
        return None
    return {'steamId': str(int(steam)), 'productId': g('id'),
            'title': (item.findtext('title') or '').strip(),
            'region': g('region'), 'countryLimitationsRaw': g('country_limitations'),
            'availability': g('availability'), 'updatedTimestamp': g('updated_timestamp'),
            'prices': prices}


def convert(stream, output, source_label):
    started = time.monotonic()
    # New output only: a failed experiment must not replace a valid dataset.
    output.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(str(output / 'working.sqlite'))
    db.execute('CREATE TABLE offers (id TEXT PRIMARY KEY, bucket INTEGER, steam TEXT, body TEXT)')
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
                               (result['productId'], int(result['steamId']) % BUCKET_COUNT,
                                result['steamId'], compact(result)))
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
        unique = db.execute('SELECT COUNT(*), COUNT(DISTINCT steam) FROM offers').fetchone()
        if not unique[0]:
            raise ValueError('No usable offers; dataset not publishable')
        shards = []
        db.execute('CREATE INDEX bucket_steam ON offers(bucket, steam, id)')
        for bucket in range(BUCKET_COUNT):
            path = output / shard_name(bucket)
            with path.open('w', encoding='utf-8', newline='\n') as f:
                f.write('{"schema":1,"games":{')
                first_game = True
                previous = None
                for steam, body in db.execute('SELECT steam, body FROM offers WHERE bucket=? ORDER BY steam, id', (bucket,)):
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
        manifest = {'schema': 1, 'generatedAt': datetime.now(timezone.utc).isoformat(),
                    'source': source_label, 'status': 'prototype-not-published',
                    'itemsRead': counts['itemsRead'], 'offers': unique[0], 'games': unique[1],
                    'partition': 'integer Steam app ID modulo 4096, lowercase three-digit hex',
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
