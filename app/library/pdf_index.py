"""Local PDFium extraction in a bounded child process; no JavaScript or network."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

try:
    from .logical_text import normalized_map, text_hash
except ImportError:
    from logical_text import normalized_map, text_hash

EXTRACTOR = 'pdfium-5.13.0/nfc-whitespace-v1'
MAX_PAGES = 500
MAX_CHARS = 2_000_000


def extract(path):
    import pypdfium2 as pdfium
    raw = pdfium.raw
    pages, total = [], 0
    with pdfium.PdfDocument(path) as doc:
        if len(doc) > MAX_PAGES:
            raise ValueError('PDF 超过 500 页的本地文字索引上限。')
        for page_index in range(len(doc)):
            page = doc[page_index]
            textpage = page.get_textpage()
            count = textpage.count_chars(); total += count
            if total > MAX_CHARS:
                raise ValueError('PDF 文字索引超过 200 万字符。')
            chars, boxes = [], []
            for i in range(count):
                code = raw.FPDFText_GetUnicode(textpage.raw, i)
                char = chr(code) if code and code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else '\ufffd'
                if char in '\x00\ufffe\uffff':
                    char = ' '
                try:
                    box = [round(float(x), 4) for x in textpage.get_charbox(i)]
                    if not all(math.isfinite(x) for x in box) or box[0] >= box[2] or box[1] >= box[3]:
                        box = None
                except (ValueError, RuntimeError):
                    box = None
                chars.append(char); boxes.append(box)
            original = ''.join(chars)
            text, reverse = normalized_map(original)
            geometry = []
            for start, end in reverse:
                good = [b for b in boxes[start:end] if b]
                geometry.append([min(b[0] for b in good), min(b[1] for b in good),
                                 max(b[2] for b in good), max(b[3] for b in good)] if good else None)
            pages.append({'page_index': page_index, 'page_label': doc.get_page_label(page_index) or str(page_index+1),
                          'view_box': list(page.get_bbox()), 'rotation': page.get_rotation(),
                          'raw_text': original, 'text': text, 'text_hash': text_hash(text),
                          'reverse_map': reverse, 'boxes': geometry})
            textpage.close(); page.close()
    return {'schema_version': 1, 'extractor_version': EXTRACTOR,
            'coordinate_system': 'pdf-user-space', 'pdf_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'pages': pages, 'status': 'ready'}


def index_pdf(folder):
    path = folder / 'original.pdf'
    if not path.exists():
        return {'schema_version': 1, 'pages': [], 'status': 'absent', 'pdf_sha256': ''}
    output = folder / 'pdf-index.json'
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path), str(output)],
                                capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('PDF 文字索引未能建立；可查看原版，暂不能可靠跨视图定位。')
        return json.loads(output.read_text(encoding='utf-8'))
    except (subprocess.TimeoutExpired, ValueError):
        index = {'schema_version': 1, 'pages': [], 'status': 'unavailable',
                 'pdf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'extractor_version': EXTRACTOR,
                 'reason': '本地文字提取失败或达到处理上限；没有执行 OCR。'}
        output.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
        return index


def quads_for(page, start, end):
    """Merge adjacent glyph boxes only within a line. Never bridge PDF columns."""
    rects = []
    for box in page['boxes'][start:end]:
        if not box:
            continue
        left, bottom, right, top = box
        previous = rects[-1] if rects else None
        height = top-bottom
        if previous and abs(previous[1]-bottom) < max(2, height*.35) and abs(previous[3]-top) < max(2, height*.35) and -1 <= left-previous[2] <= max(4, height*.8):
            previous[0] = min(previous[0], left); previous[1] = min(previous[1], bottom)
            previous[2] = max(previous[2], right); previous[3] = max(previous[3], top)
        else:
            rects.append([left, bottom, right, top])
    return [[l, t, r, t, r, b, l, b] for l, b, r, t in rects]


if __name__ == '__main__':
    data = extract(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
