"""Pure validation, durable history and new-file detection for SCRMaps Helper."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

BASE = "https://www.scrmaps.com"
APP_VERSION = "1.4.7"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".pcx", ".tga", ".webp"}
CODE_RE = re.compile(r"[A-HJ-NP-Z2-9]{5,64}\Z")
RESERVED = {"login", "logout", "dashboard", "api", "maps", "save-system", "terms", "privacy", "log", "users", "blog", "contact", "creator"}


def code_text(value: str) -> str:
    """Strip only layout whitespace; never guess a misread character."""
    return re.sub(r"\s+", "", value).upper()


def valid_code(value: str) -> str:
    result = code_text(value)
    if not CODE_RE.fullmatch(result):
        raise ValueError("코드는 영문 대문자와 2~9로 구성되어야 합니다. 0·1·I·O는 자동 교정하지 않습니다.")
    return result


def project_slug(value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in {"www.scrmaps.com", "scrmaps.com"} or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("https://www.scrmaps.com/맵주소 형식으로 입력하세요.")
        value = parsed.path.strip("/")
    else:
        value = value.strip("/")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value) or value.lower() in RESERVED:
        raise ValueError("맵 페이지 주소의 마지막 부분을 입력하세요. 예: theking")
    return value.lower()


def validate_roi(values) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = map(float, values)
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("인식 영역은 왼쪽·위·오른쪽·아래 순서이며 0~100% 범위여야 합니다.")
    return x1, y1, x2, y2


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


@dataclass(frozen=True)
class FileJob:
    path: Path
    signature: tuple[int, int]


class NewFiles:
    """Baseline old screenshots, wait for stable metadata, retry partial writes."""
    def __init__(self, folder: Path, recursive=False, clock=time.monotonic):
        self.folder, self.recursive, self.clock = folder, recursive, clock
        self.seen = self._snapshot()
        self.pending = {}

    def _snapshot(self):
        if not self.folder.is_dir():
            raise ValueError("스크린샷 폴더가 존재하지 않습니다.")
        paths = self.folder.rglob("*") if self.recursive else self.folder.iterdir()
        out = {}
        for path in paths:
            if path.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                if path.is_file():
                    stat = path.stat()
                    out[path] = (stat.st_size, stat.st_mtime_ns)
            except (OSError, PermissionError):
                continue
        return out

    def poll(self) -> list[FileJob]:
        now, jobs = self.clock(), []
        current = self._snapshot()
        for path in list(self.pending):
            if path not in current:
                self.pending.pop(path, None)
        for path, sig in current.items():
            if self.seen.get(path) == sig:
                continue
            old = self.pending.get(path)
            if not old or old[0] != sig:
                self.pending[path] = (sig, now)
                continue
            if not sig[0] or now - old[1] < 0.65:
                continue
            try:
                from PIL import Image
                with Image.open(path) as image:
                    image.verify()
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != sig:
                    continue
            except (OSError, ValueError, SyntaxError):
                continue
            self.seen[path] = sig
            self.pending.pop(path, None)
            jobs.append(FileJob(path, sig))
        self.seen = {p: sig for p, sig in self.seen.items() if p in current}
        return sorted(jobs, key=lambda job: job.signature[1])


class History:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, project TEXT NOT NULL, nickname TEXT NOT NULL,
            auth TEXT NOT NULL, save TEXT DEFAULT '', status TEXT NOT NULL,
            detail TEXT DEFAULT '', image_hash TEXT DEFAULT '', created TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(project,nickname,auth))""")
        self.db.commit()

    def get(self, project, nickname, auth):
        row = self.db.execute("SELECT * FROM runs WHERE project=? AND nickname=? AND auth=?", (project,nickname,auth)).fetchone()
        if row is None:
            row=self.db.execute('SELECT * FROM runs WHERE lower(project)=lower(?) AND nickname=? AND auth=? ORDER BY id DESC LIMIT 1',(project,nickname,auth)).fetchone()
        return dict(row) if row else None

    def put(self, project, nickname, auth, status, save="", detail="", image_hash=""):
        self.db.execute("""INSERT INTO runs(project,nickname,auth,status,save,detail,image_hash) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(project,nickname,auth) DO UPDATE SET status=excluded.status, save=excluded.save,
            detail=excluded.detail,image_hash=excluded.image_hash,created=datetime('now','localtime')""",
            (project,nickname,auth,status,save,detail[:1000],image_hash))
        self.db.commit()

    def list(self, project=None, nickname=None):
        if project is not None and nickname is not None:
            rows = self.db.execute("SELECT * FROM runs WHERE project=? AND nickname=? ORDER BY id DESC LIMIT 200", (project,nickname))
        else:
            rows = self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 200")
        return [dict(row) for row in rows]

    def close(self):
        self.db.close()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
