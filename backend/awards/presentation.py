"""Validation for the pinned PPTist document format used by certificate templates."""

import base64
import copy
import html
import json
import math
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import bleach
from bleach.css_sanitizer import CSSSanitizer
from .fonts import font_file, font_info, glyph

TYPES = {"text", "image", "shape", "line", "chart", "table", "latex", "video", "audio"}
CSS = CSSSanitizer(
    allowed_css_properties=[
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "text-decoration",
        "text-decoration-line",
        "color",
        "background-color",
        "text-align",
        "text-indent",
        "line-height",
        "letter-spacing",
        "vertical-align",
        "padding-left",
        "padding-right",
        "margin-left",
        "margin-right",
        "white-space",
    ]
)
TAGS = {
    "p",
    "span",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "strike",
    "sub",
    "sup",
    "br",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "a",
}


def clean_html(value):
    if not isinstance(value, str) or len(value) > 200000:
        raise ValueError("富文本内容过长")
    result = bleach.clean(
        value,
        tags=TAGS,
        attributes={
            "*": ["style", "data-indent"],
            "a": ["href", "title", "target", "rel"],
        },
        css_sanitizer=CSS,
        strip=True,
        protocols={"http", "https", "mailto"},
    )
    if re.search(
        r"(?:url\s*\(|expression\s*\(|javascript\s*:)", html.unescape(result), re.I
    ):
        raise ValueError("文本不能包含外部样式资源")
    return result


def _finite(value, low, high, label):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"{label}无效")


def _image(value):
    if (
        not isinstance(value, str)
        or len(value) > 16 * 1024 * 1024
        or not value.startswith("data:")
    ):
        raise ValueError("图片和媒体必须先从本地导入")
    if not re.match(
        r"^data:(image/(png|jpeg|jpg|webp|gif|svg\+xml)|audio/[a-z0-9.+-]+|video/[a-z0-9.+-]+);base64,",
        value,
        re.I,
    ):
        raise ValueError("不支持此媒体格式")
    if value.startswith("data:image/svg+xml"):
        try:
            data = base64.b64decode(value.split(",", 1)[1], validate=True)
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                raise ValueError("SVG不允许XML实体")
            root = ET.fromstring(data)
            if root.tag.split("}")[-1] != "svg":
                raise ValueError("SVG图像无效")
            for node in root.iter():
                if node.tag.split("}")[-1].lower() in {
                    "script",
                    "foreignobject",
                    "iframe",
                    "object",
                    "embed",
                    "animate",
                    "set",
                }:
                    raise ValueError("SVG包含不安全内容")
                for key, text in node.attrib.items():
                    name = key.split("}")[-1].lower()
                    if name.startswith("on") or (
                        name in {"href", "src"} and not text.startswith("#")
                    ):
                        raise ValueError("SVG包含外部资源")
                    if re.search(r"url\((?!\s*[\"\']?#)", text, re.I):
                        raise ValueError("SVG包含外部资源")
        except (ET.ParseError, TypeError, base64.binascii.Error) as exc:
            raise ValueError("SVG图像无法解析") from exc
    return value


def validate_presentation(canvas):
    if len(json.dumps(canvas, ensure_ascii=False).encode()) > 24 * 1024 * 1024:
        raise ValueError("模板资源总量不能超过24MB")
    result = copy.deepcopy(canvas)
    document = result.get("presentation")
    if not isinstance(document, dict):
        raise ValueError("PPT模板文档无效")
    page = result.get("page", {})
    _finite(page.get("width"), 100, 2400, "页面宽度")
    _finite(page.get("height"), 100, 2400, "页面高度")
    slides = document.get("slides", [])
    if not isinstance(slides, list) or not 1 <= len(slides) <= 100:
        raise ValueError("模板需要1～100张工作页面")
    _finite(document.get("viewportSize"), 100, 4000, "编辑画布宽度")
    _finite(document.get("viewportRatio"), 0.1, 10, "画布比例")
    index = result.get("slideIndex", 0)
    if not isinstance(index, int) or not 0 <= index < len(slides):
        raise ValueError("请选择要签发的页面")
    total = 0

    def visit(value, depth=0):
        if depth > 35:
            raise ValueError("模板嵌套层级过深")
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key in {"__proto__", "prototype", "constructor"}:
                    raise ValueError("模板属性无效")
                if key in {"content", "text"} and isinstance(item, str):
                    value[key] = clean_html(item)
                elif key in {"fontName", "defaultFontName", "fontname"} and isinstance(
                    item, str
                ):
                    if item and not re.fullmatch(r"AC_[a-zA-Z0-9_]{1,80}", item):
                        raise ValueError("请从本地字体库选择字体后保存")
                elif (
                    key == "link"
                    and isinstance(item, dict)
                    and item.get("type") == "web"
                ):
                    if not re.match(
                        r"^https?://[^\s<>]+$", str(item.get("target", "")), re.I
                    ):
                        raise ValueError("链接仅支持HTTP/HTTPS地址")
                elif (
                    key in {"src", "poster", "pattern"}
                    and item
                    and isinstance(item, str)
                ):
                    value[key] = _image(item)
                else:
                    visit(item, depth + 1)
        elif isinstance(value, list):
            if len(value) > 20000:
                raise ValueError("模板数据项过多")
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("模板不能含无效数值")
        elif isinstance(value, str) and len(value) > 16 * 1024 * 1024:
            raise ValueError("模板资源过大")

    visit(document)
    for slide in slides:
        elements = slide.get("elements", [])
        if not isinstance(elements, list) or len(elements) > 500:
            raise ValueError("每页最多500个元素")
        ids = set()
        total += len(elements)
        for element in elements:
            if not isinstance(element, dict) or element.get("type") not in TYPES:
                raise ValueError("PPT元素类型无效")
            if not isinstance(element.get("id"), str) or element["id"] in ids:
                raise ValueError("PPT元素编号必须唯一")
            ids.add(element["id"])
            _finite(element.get("left"), -10000, 10000, "元素横坐标")
            _finite(element.get("top"), -10000, 10000, "元素纵坐标")
            if element["type"] != "line":
                _finite(element.get("width"), 1, 10000, "元素宽度")
                _finite(element.get("height"), 1, 10000, "元素高度")
            _finite(element.get("rotate", 0), -36000, 36000, "元素角度")
    if total > 2000:
        raise ValueError("模板元素总数不能超过2000")
    for font_id in presentation_fonts(result):
        font_file(font_id)
    return result


def presentation_fonts(canvas):
    data = json.dumps(canvas.get("presentation", {}), ensure_ascii=False)
    result = {"hei"}
    for value in re.findall(r"AC_([0-9a-f]{64}|[a-z][a-z_]*)(?![a-zA-Z0-9_])", data):
        result.add(value.replace("_", "-"))
    return result


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = _Text()
    parser.feed(value)
    return "".join(parser.parts)
