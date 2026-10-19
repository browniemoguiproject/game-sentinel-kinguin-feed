"""Validate conversion output before exposing a new Pages deployment."""
import hashlib
import json
from pathlib import Path
import sys


def prepare(directory):
    directory = Path(directory).resolve()
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('offers', 0) <= 0:
        raise ValueError('Missing or empty catalog')
    if len(manifest['shards']) != 4096:
        raise ValueError('Incomplete shard set')
    names = set()
    for row in manifest['shards']:
        path = (directory / row['file']).resolve()
        if path.parent != directory or path.name in names:
            raise ValueError('Invalid or duplicate shard path')
        names.add(path.name)
        raw = path.read_bytes()
        if (len(raw) != row['bytes'] or len(raw) > 25 * 1024 * 1024
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError('Corrupt shard: ' + path.name)
    if names != {'%03x.json' % i for i in range(4096)}:
        raise ValueError('Unexpected shard names')
    manifest['status'] = 'ready'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (directory / '_headers').write_text(
        '/*\n  X-Content-Type-Options: nosniff\n  Cache-Control: public, max-age=300\n'
        '/manifest.json\n  Cache-Control: no-cache\n', encoding='utf-8')
    # Explicit 404 prevents Pages SPA fallback from disguising missing JSON files.
    (directory / '404.html').write_text('<!doctype html><title>Not found</title>Dataset not found.\n', encoding='utf-8')
    (directory / 'index.html').write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Game Sentinel data</title>'
        '<body><h1>Game Sentinel data</h1><p>Static Kinguin catalog.</p>'
        '<p><a href="manifest.json">Catalog status</a></p></body></html>\n', encoding='utf-8')
    print('Verified complete dataset: %d offers, %d games.' % (manifest['offers'], manifest['games']))


if __name__ == '__main__':
    prepare(sys.argv[1])
