"""Green AUTH OCR with real preprocessing diversity and character verification.

RapidOCR 1.4.4's text_rec(..., return_word_box=True) retains per-character
confidence; its top-level use_det=False result drops that metadata.
"""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import dataclass, field
import cv2
import numpy as np
from PIL import Image, ImageOps
from core import CODE_RE, code_text, project_slug


@dataclass
class Recognition:
    code: str = ""
    confident: bool = False
    score: float = 0
    alternatives: list[str] = field(default_factory=list)
    project: str = ""
    box: tuple[int, int, int, int] | None = None
    message: str = ""
    uncertain_positions: list[int] = field(default_factory=list)  # 1-based


@dataclass(frozen=True)
class Reading:
    text: str
    score: float
    chars: tuple[float, ...] = ()

    @property
    def code(self):
        return code_text(self.text)

    def strong(self):
        return (self.text == self.text.upper() and self.score >= .95
                and len(self.chars) == len(self.code) and bool(self.chars)
                and min(self.chars) >= .90)


def color_masks(image):
    a = np.asarray(image, dtype=np.float32)
    red, green, blue = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (
        np.uint8((green > 95) & (green > red * 1.5) & (green > blue * 1.4)) * 255,
        np.uint8((green > 95) & (blue > 95) & (red < green * .6) & (red < blue * .6)) * 255,
    )


def line_boxes(mask, min_width=40):
    height, width = mask.shape
    scale = max(.55, min(3.0, min(width / 1280, height / 720)))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    glyph_heights = [h for x, y, w, h, area in stats[1:]
                     if 5 <= h <= 60*scale and .08 <= w/h <= 2.5 and area >= 3]
    text_height = float(np.median(glyph_heights)) if len(glyph_heights) >= 5 else 0.
    # Screenshot resolution alone does not determine game font size. Join
    # periods/slashes of an enlarged URL without cutting its hostname apart.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, round(11*scale), round(text_height*1.1)), max(2, round(3*scale))))
    joined = cv2.dilate(mask, kernel)
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (max(5, 5*scale) <= h <= 90*scale and min_width*scale <= w <= width*.95 and 1.8 <= w/h <= 80):
            continue
        density = np.count_nonzero(mask[y:y+h, x:x+w]) / (w*h)
        if .035 <= density <= .65:
            boxes.append((x, y, w, h))
    return sorted(boxes, key=lambda b: b[2], reverse=True)[:48]


def url_project(text):
    compact = re.sub(r"\s+", "", text)
    match = re.search(r"(?:https?://)?(?:www\.)?scrmaps\.com/([a-zA-Z0-9][a-zA-Z0-9_-]{0,99})(?![a-zA-Z0-9_/-])", compact, re.I)
    if not match:
        return ""
    start = match.start()
    if start and compact[start-1] not in ":|([":
        return ""
    end = match.end()
    if end < len(compact) and compact[end] not in ".,;:|)]":
        return ""
    try:
        return project_slug(match.group(1))
    except ValueError:
        return ""


def linked(code_box, url_box):
    x, y, w, h = code_box
    ux, uy, uw, uh = url_box
    gap = uy-(y+h)
    return max(h*1.4, uh*.8) <= gap <= max(h, uh)*16 and abs(x+w/2-(ux+uw/2)) <= max(uw*.42, w*.65)


def padded(image, pixel=False):
    image = Image.fromarray(np.uint8(image)).convert("RGB")
    factor = min(3., 2500/max(image.size))
    image = image.resize((max(1, round(image.width*factor)), max(1, round(image.height*factor))),
                         Image.Resampling.NEAREST if pixel else Image.Resampling.LANCZOS)
    return np.asarray(ImageOps.expand(image, border=max(4, round(image.height*.18)), fill="white"))


def code_views(source, mask, box):
    """Strict pixels, faint strokes, and soft green chroma; no forced stretching."""
    x, y, w, h = box
    a = np.asarray(source.crop((x,y,x+w,y+h)), dtype=np.float32)
    strict = mask[y:y+h, x:x+w]
    ys, xs = np.nonzero(strict)
    if not len(xs):
        return [], np.zeros((0, 0), np.uint8)
    top, bottom = max(0, int(ys.min())-1), min(h, int(ys.max())+2)
    left, right = max(0, int(xs.min())-1), min(w, int(xs.max())+2)
    a = a[top:bottom, left:right]
    strict = strict[top:bottom, left:right]
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    chroma = np.maximum(0, g-np.maximum(r, b))
    loose = np.uint8((g > 48) & (g-r > 24) & (g-b > 18))*255
    peak = max(1., float(np.percentile(chroma[strict > 0], 90)))
    soft = np.uint8(255-np.clip(chroma/peak, 0, 1)*255)
    return [(255-strict, True), (255-loose, True), (soft, False)], strict


def glyph_spans(mask):
    """Split only at blank columns; never cut a character in half."""
    if not mask.size:
        return []
    occupied = np.any(mask > 0, axis=0)
    edges = np.diff(np.r_[False, occupied, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def auth_boxes(mask, box):
    """Separate an adjacent Korean label at a real whitespace gap, not by ROI."""
    x, y, w, h = box
    crop = mask[y:y+h, x:x+w]
    spans = glyph_spans(crop)
    gaps = [b[0]-a[1] for a,b in zip(spans,spans[1:])]
    if not gaps:
        return [box]
    threshold = max(8., h*.45, float(np.median(gaps))*2.5)
    cuts = [0]+[i+1 for i,gap in enumerate(gaps) if gap >= threshold]+[len(spans)]
    if len(cuts) == 2:
        return [box]
    segments = []
    for first,last in zip(cuts,cuts[1:]):
        if last-first < 5:
            continue
        left,right = spans[first][0],spans[last-1][1]
        ys,xs = np.nonzero(crop[:,left:right])
        top,bottom = int(ys.min()),int(ys.max())+1
        if (right-left)/(bottom-top) >= 1.8:
            nx,ny = max(0,x+left-1),max(0,y+top-1)
            segments.append((nx,ny,min(mask.shape[1],x+right+1)-nx,min(mask.shape[0],y+bottom+1)-ny))
    return segments or [box]


def narrow(image, aspect):
    # A game's wide pixel font differs from the printed fonts the model saw.
    # This changes glyph proportions, rather than repeating a uniform resize.
    return cv2.resize(image,(max(1,round(image.shape[1]*aspect)),image.shape[0]),interpolation=cv2.INTER_AREA)


def rank_readings(readings):
    """Choose a complete observed string; never invent a character mixture."""
    valid = [r for r in readings if CODE_RE.fullmatch(r.code) and r.score >= .70]
    if not valid:
        return "", [], [], False, 0.
    count = Counter(r.code for r in valid)
    alternatives = sorted(count, key=lambda c: (sum(r.strong() for r in valid if r.code == c),
                                               count[c], sum(r.score for r in valid if r.code == c)), reverse=True)
    best = alternatives[0]
    support = [r for r in valid if r.code == best]
    uncertain = set()
    for r in readings:
        if r.score < .70 or not r.text:
            continue
        if len(r.code) != len(best):
            uncertain.update(range(1, len(best)+1))
        else:
            uncertain.update(i+1 for i, (a, b) in enumerate(zip(best, r.code)) if a != b)
    for i in range(len(best)):
        if not any(len(r.chars) == len(best) and r.chars[i] >= .90 for r in support):
            uncertain.add(i+1)
    unanimous = (len(readings) == 3 and len(support) == 3 and any(r.strong() for r in readings)
                 and all(r.text == r.text.upper() and r.score >= .95 for r in readings) and not uncertain)
    return best, alternatives, sorted(uncertain), unanimous, min(r.score for r in support)


class Reader:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)

    def observe(self, image):
        rows, _ = self.engine.text_rec(image, return_word_box=True)
        if not rows:
            return Reading("", 0.)
        text, score, *extra = rows[0]
        raw = str(text)
        # Pinned 1.4.4: [columns, words, word_columns, states, char_scores].
        chars = extra[0][4] if extra and len(extra[0]) >= 5 else []
        chars = tuple(float(s) for c, s in zip(raw, chars) if not c.isspace()) if len(chars) == len(raw) else ()
        return Reading(raw.strip(), float(score), chars)

    def line(self, mask, box, scale):
        # URL only. AUTH uses code_views and per-character checks.
        x, y, w, h = box
        crop = Image.fromarray(255-mask[y:y+h, x:x+w]).convert("RGB")
        factor = min(scale, 2500/max(w, h))
        crop = crop.resize((max(1, round(w*factor)), max(1, round(h*factor))), Image.Resampling.NEAREST)
        crop = ImageOps.expand(crop, border=max(4, round(h*factor*.16)), fill="white")
        reading = self.observe(np.asarray(crop))
        return reading.text, reading.score

    def verify_chunks(self, views, strict, code, aspects=None):
        spans = glyph_spans(strict)
        if len(spans) != len(code):
            return False, []
        starts = list(range(0, max(1, len(code)-5), 4))
        if starts[-1]+6 < len(code):
            starts.append(len(code)-6)
        windows = [(s, min(s+6, len(code))) for s in starts]
        uncertain = set()
        certain = True
        for start, end in windows:
            checks = [(views[2][0],False,a) for a in aspects] if aspects else [(views[0][0],True,1.),(views[2][0],False,1.)]
            for image, pixel, aspect in checks:
                left, right = spans[start][0], spans[end-1][1]
                image = image[:, max(0, left-1):right+1]
                chunk = self.observe(padded(narrow(image,aspect) if aspect != 1. else image, pixel))
                expected = code[start:end]
                if chunk.code != expected or not chunk.strong():
                    certain = False
                    if len(chunk.code) != len(expected) or len(chunk.chars) != len(expected):
                        uncertain.update(range(start+1, end+1))
                    else:
                        uncertain.update(start+i+1 for i, (a, b) in enumerate(zip(expected, chunk.code))
                                         if a != b or chunk.chars[i] < .90)
        return certain, sorted(uncertain)

    def read_code(self, source, mask, box):
        views, strict = code_views(source, mask, box)
        readings = [self.observe(padded(image, pixel)) for image, pixel in views]
        code, alternatives, uncertain, strong, score = rank_readings(readings)
        aspects = None
        if views and not strong:
            normalized = [self.observe(padded(narrow(views[2][0],a))) for a in (.55,.65,.75)]
            ncode,nalts,nuncertain,nstrong,nscore = rank_readings(normalized)
            combined,alternatives,cuncertain,_,cscore = rank_readings(readings+normalized)
            if combined == ncode and ncode and (nstrong or sum(r.strong() for r in normalized) > sum(r.strong() for r in readings)):
                code,score,uncertain,strong = ncode,nscore,nuncertain,nstrong
                aspects = (.65,.85)
            else:
                code,score,uncertain = combined,cscore,cuncertain
            # A strong contradictory observation cannot be silently outvoted.
            conflicts = [r for r in readings+normalized if r.strong() and r.code != code]
            if conflicts:
                strong = False
                uncertain = sorted(set(uncertain)|{i+1 for r in conflicts for i,(a,b) in enumerate(zip(code,r.code)) if a != b})
        verified = False
        if code:
            verified, chunk_uncertain = self.verify_chunks(views, strict, code, aspects)
            uncertain = sorted(set(uncertain) | set(chunk_uncertain))
        return dict(code=code, alternatives=alternatives, uncertain=uncertain,
                    trusted=strong and verified, score=score,
                    uppercase=any(r.text and r.text == r.text.upper() for r in readings))

    def read_code_fast(self, source, mask, box):
        views,_ = code_views(source,mask,box)
        if not views:
            return dict(code='',alternatives=[],uncertain=[],trusted=False,score=0.,uppercase=False)
        soft=views[2][0]
        readings=[self.observe(padded(narrow(soft,.65))),self.observe(padded(soft))]
        agree=(readings[0].code==readings[1].code and CODE_RE.fullmatch(readings[0].code)
               and min(r.score for r in readings)>=.80)
        if not agree:
            readings += [self.observe(padded(narrow(soft,.55))),self.observe(padded(views[0][0],True))]
        code,alternatives,uncertain,_,score=rank_readings(readings)
        return dict(code=code,alternatives=alternatives,uncertain=uncertain,trusted=bool(agree),score=score,
                    uppercase=any(r.text and r.text==r.text.upper() for r in readings))

    def read_fast(self,path):
        return self.read(path,_fast=True)

    def read(self, path, _legacy_roi=None, _fast=False):
        with Image.open(path) as source:
            if source.width*source.height > 32_000_000:
                raise ValueError("이미지가 너무 큽니다. 게임 스크린샷을 선택하세요.")
            source = ImageOps.exif_transpose(source).convert("RGB")
        green, cyan = color_masks(source)
        urls = []
        for box in line_boxes(cyan, min_width=85):
            text, score = self.line(cyan, box, 3)
            slug = url_project(text)
            if not slug or score < .88:
                continue
            other, other_score = (text,score) if _fast else self.line(cyan, box, 4)
            if url_project(other) == slug and other_score >= .88:
                urls.append((slug, box, min(score, other_score)))
        boxes = list(dict.fromkeys(part for box in line_boxes(green) for part in auth_boxes(green,box)))
        anchored_boxes = [b for b in boxes if any(linked(b, u[1]) for u in urls)]
        boxes = anchored_boxes if anchored_boxes else boxes
        candidates = []
        for box in boxes:
            row = self.read_code_fast(source,green,box) if _fast else self.read_code(source, green, box)
            if not row['code']:
                continue
            anchors = [entry for entry in urls if linked(box, entry[1])]
            if not anchors and not row.get('uppercase', False):
                continue
            slugs = {entry[0] for entry in anchors}
            row.update(box=box, project=next(iter(slugs)) if len(slugs) == 1 else "",
                       linked=bool(anchors), trusted=row['trusted'] and len(slugs) == 1
                       and any('A' <= c <= 'Z' for c in row['code']))
            candidates.append(row)
        if not candidates:
            return Recognition(message="인증번호가 보이는 게임 스크린샷인지 확인해 주세요.")
        candidates.sort(key=lambda c: (c['trusted'], c['score']), reverse=True)
        best = candidates[0]
        unique = {(c['code'], c['project']) for c in candidates}
        certain = best['trusted'] and len(unique) == 1
        alternatives = list(dict.fromkeys(code for c in candidates for code in c['alternatives']))
        reason = "번호 전체·글자별·부분 구간 검사가 일치했어요."
        if not certain:
            positions = ', '.join(map(str, best['uncertain']))
            reason = (f"왼쪽부터 {positions}번째 글자를 확인해 주세요." if positions else
                      "번호 또는 맵 주소를 확정하지 못했어요. 확대 원본과 비교해 주세요.")
        if _fast:reason="인식한 번호를 자동 제출해 세이브 코드를 가져옵니다."
        return Recognition(best['code'], certain, best['score'], alternatives, best['project'], best['box'], reason, best['uncertain'])
