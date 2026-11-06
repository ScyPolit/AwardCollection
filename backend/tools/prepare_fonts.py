"""Fetch pinned freely redistributable fonts; preserve upstream licensing."""
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request
import zipfile
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1] / "font-assets"
PACKAGES = {
    "hei": ("fonts-wqy-zenhei_0.9.45-8_all.deb", "黑体 · 文泉驿正黑", "fonts-wqy-zenhei"),
    "song": ("fonts-arphic-uming_0.2.20080216.2-11_all.deb", "宋体 · 文鼎明体", "fonts-arphic-uming"),
    "kai": ("fonts-arphic-ukai_0.2.20080216.2-5_all.deb", "楷体 · 文鼎楷体", "fonts-arphic-ukai"),
    "latin": ("fonts-liberation2_2.1.5-1_all.deb", "", "fonts-liberation2"),
}


def download(url):
    cache = ROOT.parent / '.tmp-font-downloads'
    cache.mkdir(exist_ok=True)
    target = cache / hashlib.sha256(url.encode()).hexdigest()
    if not target.exists():
        print('Downloading pinned font source: ' + url, flush=True)
        target.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AwardCollection-font-build"}), timeout=120).read())
        print('Downloaded font source bytes: ' + str(target.stat().st_size), flush=True)
    return target.read_bytes()


def extract_deb(data):
    assert data[:8] == b"!<arch>\n"
    offset = 8
    while offset < len(data):
        header = data[offset:offset + 60]
        size = int(header[48:58])
        content = data[offset + 60:offset + 60 + size]
        if header[:16].strip().startswith(b"data.tar"):
            return tarfile.open(fileobj=io.BytesIO(content))
        offset += 60 + size + size % 2
    raise ValueError("Missing Debian data archive")


def package(item):
    key, (filename, name, directory) = item
    url = f"https://deb.debian.org/debian/pool/main/f/{directory}/{filename}"
    data = download(url)
    entries = []
    with extract_deb(data) as archive:
        for member in archive.getmembers():
            if member.name.endswith('/copyright'):
                (ROOT / f"LICENSE-{directory}.txt").write_bytes(archive.extractfile(member).read())
            if not member.name.lower().endswith(('.ttf', '.ttc')):
                continue
            if key == 'latin' and not member.name.endswith('-Regular.ttf'):
                continue
            font = TTFont(io.BytesIO(archive.extractfile(member).read()), fontNumber=0, recalcTimestamp=False)
            font_id = key if key != 'latin' else Path(member.name).stem.lower()
            target = ROOT / f"{font_id}.ttf"
            original = archive.extractfile(member).read()
            if member.name.lower().endswith('.ttf'):
                target.write_bytes(original)
            else:
                notice = 'AwardCollection, 2026-11-06: extracted face 0 from the upstream TrueType collection for browser/PDF compatibility. Glyph outlines are unchanged. Original license and redistribution rights are retained; see the bundled license.'
                font['name'].setName(notice, 13, 3, 1, 0x409)
                font.save(target)
            label = name if key != 'latin' else Path(member.name).stem.replace('-Regular', '').replace('Liberation', 'Liberation ')
            entries.append({'id': font_id, 'name': label, 'file': target.name, 'source': url,
                            'source_sha256': hashlib.sha256(data).hexdigest(),
                            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'license': f"LICENSE-{directory}.txt"})
    return entries


def fangsong():
    url = 'https://github.com/TrionesType/zhuque/releases/download/v0.212/ZhuqueFangsong-v0.212.zip'
    data = download(url)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        fonts = [name for name in archive.namelist() if name.lower().endswith('.ttf')]
        if not fonts:
            raise ValueError('The pinned Zhuque archive has no TrueType font')
        chosen = next((name for name in fonts if 'regular' in name.lower()), fonts[0])
        (ROOT / 'fangsong.ttf').write_bytes(archive.read(chosen))
        license_file = next((name for name in archive.namelist() if Path(name).name.lower() in ('ofl.txt', 'license', 'license.txt')), None)
        license_data = archive.read(license_file) if license_file else download('https://raw.githubusercontent.com/TrionesType/zhuque/v0.212/LICENSE.txt')
        (ROOT / 'LICENSE-zhuque.txt').write_bytes(license_data)
    return [{'id': 'fangsong', 'name': '仿宋 · 朱雀仿宋（公文风格）', 'file': 'fangsong.ttf', 'source': url,
             'source_sha256': hashlib.sha256(data).hexdigest(), 'sha256': hashlib.sha256((ROOT / 'fangsong.ttf').read_bytes()).hexdigest(),
             'license': 'LICENSE-zhuque.txt'}]


if __name__ == '__main__':
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / 'manifest.json'
    expected = {entry['id']: entry for entry in json.loads(manifest_path.read_text(encoding='utf8'))} if manifest_path.exists() else {}
    if expected and all((ROOT / entry['file']).is_file() and hashlib.sha256((ROOT / entry['file']).read_bytes()).hexdigest() == entry['sha256'] for entry in expected.values()):
        print(f'{len(expected)} pinned fonts already present and verified; offline build', flush=True)
        raise SystemExit(0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(package, item) for item in PACKAGES.items()] + [pool.submit(fangsong)]
        entries = [entry for future in futures for entry in future.result()]
    for entry in entries:
        if expected and (entry['sha256'] != expected[entry['id']]['sha256'] or entry['source_sha256'] != expected[entry['id']]['source_sha256']):
            raise RuntimeError('Pinned font integrity check failed: ' + entry['id'])
    (ROOT / 'manifest.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf8')
    if not (ROOT / 'LICENSE-GPL-2.txt').exists():
        (ROOT / 'LICENSE-GPL-2.txt').write_bytes(download('https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt'))
    print('Prepared fonts:', [(entry['id'], (ROOT / entry['file']).stat().st_size) for entry in entries])
