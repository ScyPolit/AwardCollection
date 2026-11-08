"""Local immutable font catalog and shared browser/PDF text layout."""
import hashlib
import io
import json
import math
import re
from functools import lru_cache
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from django.conf import settings
from fontTools.ttLib import TTFont as SourceFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ASSETS = Path(__file__).resolve().parent.parent / 'font-assets'
FIELDS = {'static', 'team_name', 'members', 'award_name', 'work_name', 'category', 'teachers', 'number'}
_resolved_files = ContextVar('certificate_font_files', default={})


def is_color(value):
    return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)


@contextmanager
def resolved_font_files(files):
    token = _resolved_files.set(files or {})
    try:
        yield
    finally:
        _resolved_files.reset(token)


def font_catalog(include_inactive=False):
    from .models import CertificateFont, SystemSetting
    result = [{**item, 'builtin': True, 'active': True, 'url': f"/api/v1/fonts/{item['id']}/file/?v={item['sha256']}"} for item in json.loads((ASSETS / 'manifest.json').read_text(encoding='utf8'))]
    result += [{'id': item.pk, 'name': item.name, 'sha256': item.pk, 'builtin': False,
                'active': item.active, 'license': item.license_note, 'url': f'/api/v1/fonts/{item.pk}/file/'} for item in CertificateFont.objects.filter(deleted_at__isnull=True, **({} if include_inactive else {'active': True}))]
    setting = SystemSetting.objects.filter(key='font_order').first()
    order = (setting.value.get('ids', []) if setting else [])
    positions = {key: index for index, key in enumerate(order)}
    def default_priority(item):
        name = item['name'].lower()
        if '华文行楷' in name or 'stxingkai' in name:
            return 0
        if name.strip() == '宋体' or 'simsun' in name:
            return 1
        if '宋体' in name and '仿宋' not in name:
            return 2
        return 3
    result.sort(key=lambda item: (0, positions[item['id']]) if item['id'] in positions else (1, default_priority(item)))
    return [{**item, 'sort_order': index + 1} for index, item in enumerate(result)]


def font_file(font_id):
    if not re.fullmatch(r'[a-z0-9-]{1,80}', str(font_id)):
        raise ValueError('字体编号无效')
    if font_id in _resolved_files.get():
        return Path(_resolved_files.get()[font_id])
    builtins = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf8'))
    for item in builtins:
        if item['id'] == font_id:
            persisted = Path(settings.MEDIA_ROOT) / 'protected/font-library/builtin' / (item['sha256'] + '.ttf')
            path=persisted if persisted.exists() else ASSETS / item['file']
            return verified_font(str(path),item['sha256'],path.stat().st_mtime_ns,path.stat().st_size)
    from .models import CertificateFont
    item = CertificateFont.objects.filter(pk=font_id).first()
    if not item:
        raise ValueError('所选字体不存在，请刷新字体库')
    path=Path(item.file.path)
    return verified_font(str(path),item.pk,path.stat().st_mtime_ns,path.stat().st_size)


@lru_cache(maxsize=128)
def verified_font(path,digest,modified,size):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError("字体文件完整性校验失败")
    return Path(path)


@lru_cache(maxsize=128)
def font_info(font_id):
    path = font_file(font_id)
    name = 'AC_' + font_id.replace('-', '_')
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    with SourceFont(path, lazy=True) as source:
        cmap = set(source.getBestCmap() or {})
    return name, cmap


@lru_cache(maxsize=100000)
def glyph(character, font_id):
    name, cmap = font_info(font_id)
    if ord(character) in cmap:
        return font_id, name
    fallback, coverage = font_info('hei')
    if ord(character) in coverage:
        return 'hei', fallback
    raise ValueError(f'字体缺少字形“{character}”(U+{ord(character):04X})，请导入支持此字符的字体')


@lru_cache(maxsize=200000)
def advance(character, name, size):
    return pdfmetrics.stringWidth(character, name, size)


def layout_text(text, layer):
    font_id = layer.get('fontFamily') or 'hei'
    chars = [(ch, *glyph(ch, font_id)) if ch != '\n' else ('\n', font_id, font_info(font_id)[0]) for ch in str(text)]
    width, height = float(layer.get('width', 680)), float(layer.get('height', 70))
    maximum = int(layer.get('fontSize', 24))
    minimum = int(layer.get('minFontSize', min(10, maximum)))
    line_height = float(layer.get('lineHeight', 1.35))
    if not (6 <= minimum <= maximum <= 120 and 1 <= line_height <= 3 and 1 <= width <= 2400 and 1 <= height <= 2400):
        raise ValueError('字号、行距或文本区域超出允许范围')
    for size in range(maximum, minimum - 1, -1):
        names = {item[2] for item in chars}
        bold_pad = size * .0125 if layer.get('bold') else 0
        italic_pad = .21255656 * max((pdfmetrics.getAscent(name, size) for name in names), default=size) if layer.get('italic') else 0
        available_width = width - bold_pad * 2 - italic_pad
        lines, current, used = [], [], 0.0
        for ch, family, name in chars:
            delta = advance(ch, name, size) if ch != '\n' else 0
            if delta > available_width:
                break
            if ch == '\n' or (current and used + delta > available_width + 0.001):
                lines.append((current, used)); current, used = [], 0.0
            if ch != '\n':
                current.append((ch, family, name, delta)); used += delta
        else:
            lines.append((current, used))
            leading = size * line_height
            descent = max((-pdfmetrics.getDescent(name, size) for name in names), default=0)
            if layer.get('underline'):
                descent = max(descent, size * .12 + max(.5, size * .04) / 2)
            if len(lines) * leading + descent <= height + 0.001:
                result = []
                for index, (line, length) in enumerate(lines):
                    x = bold_pad + {'left': 0, 'center': (available_width - length) / 2, 'right': available_width - length}.get(layer.get('align', 'center'), 0)
                    runs = []
                    for ch, family, name, delta in line:
                        if runs and runs[-1]['fontId'] == family:
                            runs[-1]['text'] += ch
                            runs[-1]['width'] += delta
                        else:
                            runs.append({'text': ch, 'fontId': family, 'fontName': name, 'x': x, 'width': delta})
                        x += delta
                    result.append({'baseline': (index + 1) * leading, 'runs': runs})
                return {'fontSize': size, 'leading': leading, 'lines': result}
    raise ValueError('文本在最小字号下仍然溢出，请扩大文本区域或减小字号')


def validate_canvas(canvas):
    if not isinstance(canvas, dict):
        raise ValueError('模板画布必须为对象')
    if canvas.get('engine')=='pptist':
        from .presentation import validate_presentation
        return validate_presentation(canvas)
    page = canvas.get('page') or {'width': 842, 'height': 595}
    def number(value, low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('模板尺寸、坐标或字号无效')
    for key in ('width', 'height'):
        number(page.get(key), 100, 2400)
    background = canvas.get('background', '')
    if background:
        if not isinstance(background, str) or len(background) > 8 * 1024 * 1024 or not background.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
            raise ValueError('背景必须为上传的 PNG、JPEG 或 WebP 图片')
    layers = canvas.get('layers', [])
    if not isinstance(layers, list) or len(layers) > 80:
        raise ValueError('模板最多 80 个图层')
    for layer in layers:
        if not isinstance(layer, dict) or layer.get('type') not in ('text', 'seal', 'shape'):
            raise ValueError('图层类型无效')
        number(layer.get('x', 0), 0, page['width'])
        number(layer.get('y', 0), 0, page['height'])
        if layer['type'] == 'text':
            if layer.get('field') not in FIELDS or layer.get('align', 'center') not in ('left', 'center', 'right'):
                raise ValueError('文本字段或对齐方式无效')
            number(layer.get('fontSize', 24), 6, 120)
            number(layer.get('minFontSize', 10), 6, layer.get('fontSize', 24))
            number(layer.get('lineHeight', 1.35), 1, 3)
            for flag in ('bold', 'italic', 'underline'):
                if flag in layer and not isinstance(layer[flag], bool):
                    raise ValueError('文字样式必须为布尔值')
            if not is_color(layer.get('color', '#1f2937')):
                raise ValueError('文字颜色无效')
            font_file(layer.get('fontFamily') or 'hei')
            width, height = layer.get('width', 680), layer.get('height', 70)
            number(width, 1, page['width']); number(height, 1, page['height'])
            if len(str(layer.get('text', ''))) > 10000:
                raise ValueError('固定文本过长')
        elif layer['type'] == 'seal':
            width = height = layer.get('size', 100)
            number(width, 10, min(page.values()))
        else:
            if layer.get('kind') not in ('rect', 'ellipse', 'line', 'freehand'):
                raise ValueError('图形类型无效')
            number(layer.get('x'), 0, page['width']); number(layer.get('y'), 0, page['height'])
            width, height = layer.get('width'), layer.get('height')
            number(width, 1, page['width']); number(height, 1, page['height'])
            number(layer.get('strokeWidth'), 0, min(20, width, height))
            if not is_color(layer.get('stroke')):
                raise ValueError('图形线条颜色无效')
            if layer.get('fill') != 'none' and not is_color(layer.get('fill')):
                raise ValueError('图形填充颜色无效')
            if layer['kind'] in ('line', 'freehand'):
                points = layer.get('points', [])
                if not isinstance(points, list) or not 2 <= len(points) <= 1000 or (layer['kind'] == 'line' and len(points) != 2):
                    raise ValueError('线条需要有效的绘制点（每条最多 1000 点）')
                for point in points:
                    if not isinstance(point, (list, tuple)) or len(point) != 2:
                        raise ValueError('绘制点无效')
                    number(point[0], 0, 1); number(point[1], 0, 1)
        if layer.get('x', 0) + width > page['width'] + 0.001 or layer.get('y', 0) + height > page['height'] + 0.001:
            raise ValueError('图层超出画布，请调整位置或尺寸')
    if sum(len(layer.get('points', [])) for layer in layers if layer.get('type') == 'shape' and layer.get('kind') in ('line', 'freehand')) > 5000:
        raise ValueError('模板绘制点总数不能超过 5000')
    return canvas


def import_font(content):
    if len(content) > 40 * 1024 * 1024:
        raise ValueError('字体文件不能超过 40 MB')
    try:
        source = SourceFont(io.BytesIO(content), fontNumber=0, recalcTimestamp=False)
        if 'glyf' not in source or 'fvar' in source or not source.getBestCmap():
            raise ValueError('请上传静态 TrueType 字体（TTF，或包含 TrueType 的 TTC）')
        name = source['name'].getDebugName(1) or '自定义字体'
        output = io.BytesIO()
        if content[:4] == b'ttcf':
            source.save(output)
            data = output.getvalue()
        else:
            data = content
        source.close()
        # Ensure the exact bytes can also be embedded by the PDF renderer.
        digest = hashlib.sha256(data).hexdigest()
        TTFont('Uploaded_' + digest, io.BytesIO(data))
        return data, name, digest
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('字体文件无法解析或嵌入，请使用有效的 TTF/TTC 字体') from exc
