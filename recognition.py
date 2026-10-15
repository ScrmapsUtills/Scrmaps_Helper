"""Find green AUTH lines and their SCRMaps URL in an entire screenshot."""
from __future__ import annotations
import re
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


def color_masks(image):
    a = np.asarray(image, dtype=np.float32)
    red, green, blue = a[:,:,0], a[:,:,1], a[:,:,2]
    return (
        np.uint8((green > 95) & (green > red * 1.5) & (green > blue * 1.4)) * 255,
        np.uint8((green > 95) & (blue > 95) & (red < green * .6) & (red < blue * .6)) * 255,
    )


def line_boxes(mask, min_width=40):
    height,width = mask.shape
    scale = max(.55, min(3.0, min(width / 1280, height / 720)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT,(max(5,round(11*scale)),max(2,round(3*scale))))
    joined = cv2.dilate(mask,kernel)
    contours,_ = cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if not (max(5,5*scale) <= h <= 90*scale and min_width*scale <= w <= width*.95 and 1.8 <= w/h <= 80):
            continue
        density = np.count_nonzero(mask[y:y+h,x:x+w]) / (w*h)
        if .035 <= density <= .65:
            boxes.append((x,y,w,h))
    return sorted(boxes,key=lambda b:b[2],reverse=True)[:48]


def url_project(text):
    compact = re.sub(r"\s+", "", text)
    # The recognized string never chooses a network host.
    match = re.search(r"(?:https?://)?(?:www\.)?scrmaps\.com/([a-zA-Z0-9][a-zA-Z0-9_-]{0,99})(?![a-zA-Z0-9_/-])",compact,re.I)
    if not match:
        return ""
    start=match.start()
    if start and compact[start-1] not in ":|([":
        return ""
    end=match.end()
    if end < len(compact) and compact[end] not in ".,;:|)]":
        return ""
    try:
        return project_slug(match.group(1))
    except ValueError:
        return ""


def linked(code_box, url_box):
    x,y,w,h=code_box
    ux,uy,uw,uh=url_box
    gap = uy-(y+h)
    return max(h*1.4,uh*.8) <= gap <= max(h,uh)*16 and abs(x+w/2-(ux+uw/2)) <= max(uw*.42,w*.65)


class Reader:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)

    def line(self, mask, box, scale):
        x,y,w,h=box
        crop=Image.fromarray(255-mask[y:y+h,x:x+w]).convert("RGB")
        factor=min(scale,2500/max(w,h))
        crop=crop.resize((max(1,round(w*factor)),max(1,round(h*factor))))
        crop=ImageOps.expand(crop,border=max(4,round(h*factor*.16)),fill="white")
        result,_=self.engine(np.asarray(crop),use_det=False,use_cls=False,use_rec=True)
        if not result:
            return "",0.0
        text,score=max(result,key=lambda item:float(item[1]))
        return str(text).strip(),float(score)

    def read(self,path,_legacy_roi=None):
        with Image.open(path) as source:
            if source.width*source.height > 32_000_000:
                raise ValueError("이미지가 너무 큽니다. 게임 스크린샷을 선택하세요.")
            source=ImageOps.exif_transpose(source).convert("RGB")
        green,cyan=color_masks(source)
        urls=[]
        for box in line_boxes(cyan,min_width=85):
            text,score=self.line(cyan,box,3)
            slug=url_project(text)
            if not slug or score < .88:
                continue
            other,other_score=self.line(cyan,box,4)
            if url_project(other)==slug and other_score>=.88:
                urls.append((slug,box,min(score,other_score)))
        candidates=[]
        for box in line_boxes(green):
            text,score=self.line(green,box,3)
            normalized=code_text(text)
            if not CODE_RE.fullmatch(normalized) or score<.70:
                continue
            if text != text.upper() and not any(linked(box,entry[1]) for entry in urls):
                continue
            other,other_score=self.line(green,box,4)
            other_normalized=code_text(other)
            # Lowercase HUD labels such as Level are not uppercase AUTH codes.
            uppercase = text==text.upper() and other==other.upper()
            agreement=normalized==other_normalized and min(score,other_score)>=.90
            anchors=[entry for entry in urls if linked(box,entry[1])]
            slugs={entry[0] for entry in anchors}
            candidates.append(dict(code=normalized,score=min(score,other_score),box=box,
                project=next(iter(slugs)) if len(slugs)==1 else "",
                trusted=agreement and uppercase and len(slugs)==1 and any('A'<=c<='Z' for c in normalized),
                linked=bool(anchors)))
        anchored=[c for c in candidates if c["linked"]]
        pool=anchored or candidates
        if not pool:
            return Recognition(message="인증번호가 보이는 게임 스크린샷인지 확인해 주세요.")
        pool.sort(key=lambda c:(c["trusted"],c["score"]),reverse=True)
        best=pool[0]
        unique={(c["code"],c["project"]) for c in pool}
        certain=best["trusted"] and len(unique)==1
        reason="인증번호와 맵 주소를 자동으로 찾았어요." if certain else "번호 또는 맵 주소를 확정하지 못했어요. 내용을 확인해 주세요."
        return Recognition(best["code"],certain,best["score"],list(dict.fromkeys(c["code"] for c in pool)),best["project"],best["box"],reason)
