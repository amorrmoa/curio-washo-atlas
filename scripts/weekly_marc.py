#!/usr/bin/env python3
"""奇想和書航路: JAPAN/MARC(M/S)週次ZIPの差分をローカル処理する。

外部の検索APIは使わない。出典: 国立国会図書館書誌データ。
初回は指定した最大週数のみ遡り、以後は未処理の配布ZIPだけを扱う。
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = "https://www.ndl.go.jp/data/data_service/jnb_product"
BOOKS_FILE = ROOT / "docs/data/books.json"
STATE_FILE = ROOT / "docs/data/processed_archives.json"
TAX_FILE = ROOT / "scripts/takayama_ja_taxonomy.json"
MAX_ZIP_BYTES = 22_000_000
MAX_EXPANDED = 120_000_000
DEFAULT_INITIAL_WEEKS = 8
MAX_NEW_PER_UPDATE = 16
MAX_NEW_PER_PUBLISHER = 2
MIN_SCORE = 55
MIN_PUBLICATION = "2026-06"
MAX_PUBLICATION = "2028-12"
USER_AGENT = "CurioWashoAtlas/1.0 (weekly bibliographic ZIP ingestion; public github repository)"
TITLE_STRONG_CUES = (
    "マニエリスム", "アルチンボルド", "アナモルフォーズ", "驚異の部屋", "ヴンダーカンマー",
    "錬金術", "観相学", "蝋解剖", "エンブレム", "ピラネージ", "キルヒャー", "ベスティアリ",
    "博物誌", "幻灯", "オートマタ", "記憶術", "グロテスク", "博物画", "妖怪画", "だまし絵",
)
SCHOLARLY_CUES = ("美術", "図像", "視覚", "歴史", "研究", "文化", "芸術", "図譜", "博物", "ルネサンス", "光学", "建築", "装飾", "思想", "版画", "絵画", "図説", "考古", "文献", "医学", "写真", "図説", "蒐集", "博物館", "百科", "庭園")
AMBIGUOUS_TITLE_TERMS = ("変身", "変容", "幻想", "色彩", "迷宮", "玩具", "音楽", "模型", "標本", "魔術")

# v2.0: Research-oriented editorial filter. This is NOT a semantic classifier:
# ambiguous records are handled conservatively, using bibliographic evidence.
ACADEMIC_TITLE_MARKERS = (
    "美術史", "図像学", "図像史", "文化史", "思想史", "芸術史", "書物史", "出版史",
    "視覚文化", "光学史", "研究", "論考", "論集", "考証", "史料", "資料集",
    "歴史", "理論", "図録", "展覧会", "作品集", "画集", "図譜", "図説",
    "写真史", "版画家", "博物誌", "論理学", "図像", "考古学", "記憶術",
    "書誌学", "蒐集史", "解剖学", "ルネサンス", "バロック", "明代", "清代",
)
ACADEMIC_SUBJECT_MARKERS = (
    "美術", "図像", "視覚文化", "美術史", "絵画", "版画", "博物誌", "記憶術",
    "文献", "論理学", "思想史", "芸術", "建築史", "宗教史", "出版史", "文化史",
    "歴史", "書誌", "博物館", "博物学", "科学史", "文学史", "医学史", "写真史",
    "考古学", "風俗史", "色彩論", "修辞学", "図書館", "歴史学",
)
# Broad terms or names in creative works are not, by themselves, evidence of scholarship.
HIGH_SPECIFICITY_CUES = (
    "マニエリスム", "アルチンボルド", "アナモルフォーズ", "驚異の部屋",
    "ヴンダーカンマー", "クンストカンマー", "エンブレム", "キルヒャー",
    "ベスティアリ", "博物誌", "記憶術", "図像学", "観相学", "蝋解剖",
    "ピラネージ", "ヒエログリフ", "幻灯史", "自然史", "科学図像", "寓意画",
    "カメラ・オブスクラ", "トロンプ・ルイユ", "グロテスク美術",
)
# Fiction/entertainment plot formulas; apply only unless the title is clearly critical scholarship.
STORY_TITLE_MARKERS = (
    "異世界", "転生", "追放", "魔王", "勇者", "スキル", "最強", "無双",
    "皇子", "令嬢", "ダンジョン", "チート", "スローライフ", "溺愛", "冒険者",
    "辺境を開拓", "俺は", "私が", "ゆるふわ", "暗殺術", "錬金術師カレン",
    "錬金術師は", "錬金術師、", "錬金術師?", "錬金術師？", "錬金術師の",
)
LIGHT_NOVEL_SERIES = (
    "電撃文庫", "角川スニーカー文庫", "mf文庫j", "ga文庫", "ファンタジア文庫",
    "オーバーラップ文庫", "アルファポリスきずな文庫", "hj文庫", "ファミ通文庫",
    "ガガガ文庫", "モンスター文庫", "アース・スターノベル", "カドカワbooks",
)
HOBBY_FORMAT_MARKERS = (
    "年賀状", "ぬりえ", "塗り絵", "下絵集", "素材集", "手帳", "カレンダー",
    "練習帳", "ドリル", "シールブック", "ワークブック", "まちがいさがし",
    "攻略本", "パズルブック", "切り絵キット",
)


def selection_reason(item: dict, taxonomy: dict) -> str:
    """Return empty string for eligible books; otherwise a precise rejection reason.

    Do not reject research ABOUT literature/comics, but reject records of comics
    and entertainment fiction themselves. Publishers are not used as blacklists.
    """
    title = norm(item.get("title", ""))
    subject = norm(item.get("subjects", ""))
    genres = norm(item.get("genres", ""))
    series = norm(item.get("series", ""))
    if not title:
        return "missing_title"

    academic_title = any(norm(x) in title for x in ACADEMIC_TITLE_MARKERS)
    academic_subject = any(norm(x) in subject for x in ACADEMIC_SUBJECT_MARKERS)
    academic = academic_title or academic_subject

    # If a tag identifies the FORMAT as manga or fiction, not merely its subject,
    # it is not a bibliographic study; a scholarly book about manga is still allowed.
    if any(x in genres for x in ("漫画", "コミック", "ライトノベル", "小説", "フィクション")):
        return "fiction_or_comic_format"
    if any(x in series for x in (norm(y) for y in LIGHT_NOVEL_SERIES)):
        return "light_novel_series"
    if re.search(r"(?:@comic|(?:^|[^a-z])comic(?:$|[^a-z])|コミックス|コミック版|マンガでわかる|漫画版)", title, re.I):
        if not academic:
            return "comic_title"
    if ("漫画" in subject or "コミック" in subject) and not academic_title:
        return "comic_subject"
    if "コンピュータゲーム" in subject and not academic_title:
        return "game_subject"
    if any(norm(x) in title for x in HOBBY_FORMAT_MARKERS) and not academic:
        return "hobby_activity"
    if any(norm(x) in title for x in STORY_TITLE_MARKERS) and not academic:
        return "fiction_plot"
    if re.search(r"\b(?:vol|volume)\.?\s*\d+\b", title, re.I) and not academic:
        return "serial_fiction"

    # For a bare keyword like '錬金術師' in a novel title, discount the keyword.
    stripped = title.replace("錬金術師", "").replace("ニーアオートマタ", "")
    core_title = set()
    core_subject = set()
    for family in taxonomy.get("families", []):
        for term in family.get("core", []) + family.get("english_core", []):
            token = norm(term)
            if token and token in stripped:
                core_title.add((family["label"], token))
            if token and token in subject:
                core_subject.add((family["label"], token))
    if not core_title and not core_subject:
        return "no_distinctive_topic"

    # Specific art-historical terminology remains eligible even with sparse NDL subjects.
    strong = any(norm(x) in stripped for x in HIGH_SPECIFICITY_CUES)
    if not strong and not academic:
        return "insufficient_scholarly_context"
    # Most other books must mention a topic in their title, not merely a vague subject.
    if not core_title and not (academic_title and core_subject):
        return "topic_not_in_title"
    return ""


def split_existing_catalog(books: list[dict], taxonomy: dict) -> tuple[list[dict], list[dict]]:
    """Move only automatically discovered, clearly out-of-scope books to archive.

    No manual entry is removed. Archived records remain inside books.json under
    excluded_books, making the editorial decision reversible without Git rewrites.
    """
    keep, hidden = [], []
    for item in books:
        if (not item.get("ndl_id") or
                item.get("source") != "国立国会図書館 JAPAN/MARC(M/S)" or
                item.get("manual_override") is True or
                item.get("editorial_status") in {"approved", "verified"}):
            keep.append(item)
            continue
        reason = selection_reason(item, taxonomy)
        if reason:
            hidden.append({**item, "excluded_reason": reason})
        else:
            keep.append(item)
    return keep, hidden



def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s or "")).lower())


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class ArchiveIndexParser(HTMLParser):
    """JAPAN/MARC(M/S)欄にあるjmo*.zipだけを抽出する。"""
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            url = urljoin(INDEX_URL, self._href)
            p = urlparse(url)
            if p.scheme == "https" and p.hostname in {"www.ndl.go.jp", "ndl.go.jp"} and re.search(r"/jmo\d+\.zip$", p.path, flags=re.I):
                label = " ".join(" ".join(self._text).split())
                self.links.append({"url": url, "label": label})
            self._href = None
            self._text = []


def parse_index(html: str) -> list[dict]:
    parser = ArchiveIndexParser()
    parser.feed(html)
    seen = set()
    out = []
    for item in parser.links:
        if item["url"] not in seen:
            seen.add(item["url"])
            date_m = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", item["label"])
            item["date"] = f"{date_m[1]}-{int(date_m[2]):02d}-{int(date_m[3]):02d}" if date_m else ""
            out.append(item)
    return out


def download(url: str, max_size: int, retries: int = 3) -> bytes:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in {"www.ndl.go.jp", "ndl.go.jp"}:
        raise ValueError("Unexpected download host")
    last_err = None
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/zip,*/*;q=0.5"})
            with urlopen(req, timeout=40) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in {"www.ndl.go.jp", "ndl.go.jp"}:
                    raise ValueError("Unexpected redirect host")
                data = response.read(max_size + 1)
                if len(data) > max_size:
                    raise ValueError("Download exceeds configured size limit")
                return data
        except HTTPError as e:
            last_err = e
            if e.code not in {429, 500, 502, 503, 504} or i == retries-1:
                raise
            retry_after = e.headers.get("Retry-After", "")
            delay = min(30, int(retry_after)) if retry_after.isdecimal() else 4 * (i+1)
            print(f"HTTP {e.code}, retrying after {delay}s", file=sys.stderr)
            time.sleep(delay)
        except (TimeoutError, URLError) as e:
            last_err = e
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))
    raise last_err or RuntimeError("Download failed")


def field_values(record: dict, tag: str, code: str = "a") -> list[str]:
    return [val.strip(" /;:.,\t") for fld in record.get(tag, []) for c, val in fld.get("subfields", []) if c == code and val.strip()]


def first_field(record: dict, tags: list[str], code: str = "a") -> str:
    for tag in tags:
        vals = field_values(record, tag, code)
        if vals:
            return vals[0]
    return ""


def parse_subfields(raw: str) -> list[tuple[str, str]]:
    parts = list(re.finditer(r"\|([a-z0-9])\s*", raw))
    return [(m.group(1), raw[m.end():parts[i+1].start() if i+1 < len(parts) else len(raw)].strip()) for i, m in enumerate(parts)]


def parse_tagged(text: str):
    """視認用のMARCタグ形式: LDR/001/24500などがタグごとに1行。"""
    rec = {}
    for line in text.splitlines():
        m = re.match(r"^(LDR|\d{3}[ 0-9A-Za-z]{2})\s{2,}(.*)$", line)
        if not m:
            continue
        code, val = m[1], m[2].strip()
        tag = code[:3]
        if tag == "LDR":
            if rec:
                yield rec
            rec = {"leader": val}
        elif tag.isdigit() and int(tag) < 10:
            rec.setdefault(tag, []).append({"value": val, "subfields": []})
        else:
            rec.setdefault(tag, []).append({"value": val, "subfields": parse_subfields(val)})
    if rec:
        yield rec


def parse_marc21(raw: bytes):
    """ISO2709 MARC21: directory + subfield delimiter 0x1f. UTF-8. """
    offset = 0
    while offset < len(raw):
        # Skip leading CR/LF, but not MARC leader bytes.
        while offset < len(raw) and raw[offset:offset+1] in (b"\n", b"\r"):
            offset += 1
        if offset >= len(raw):
            break
        head = raw[offset:offset+5]
        if not head.isdigit():
            raise ValueError(f"Invalid ISO2709 record length near byte {offset}")
        length = int(head)
        if length < 30 or length > 2_000_000 or offset + length > len(raw):
            raise ValueError("Invalid MARC record size")
        chunk = raw[offset:offset+length]
        if chunk[-1:] != b"\x1d":
            raise ValueError("MARC record terminator missing")
        offset += length
        leader = chunk[:24].decode("ascii", "replace")
        if not chunk[12:17].isdigit():
            raise ValueError("Invalid MARC base address")
        base = int(chunk[12:17])
        if not (25 <= base <= length-1):
            raise ValueError("Invalid MARC directory start")
        rec = {"leader": leader}
        directory = chunk[24:base-1]
        if len(directory) % 12:
            raise ValueError("MARC directory not aligned")
        for i in range(0, len(directory), 12):
            ent = directory[i:i+12]
            if not (ent[3:7].isdigit() and ent[7:12].isdigit()):
                raise ValueError("Invalid MARC directory entry")
            tag = ent[:3].decode("ascii", "replace")
            size, start = int(ent[3:7]), int(ent[7:12])
            raw_field = chunk[base+start:base+start+size]
            if len(raw_field) != size or not raw_field.endswith(b"\x1e"):
                raise ValueError("Invalid MARC field boundaries")
            val = raw_field[:-1]
            if tag.isdigit() and int(tag) < 10:
                field = {"value": val.decode("utf-8", "replace"), "subfields": []}
            else:
                bits = val[2:].split(b"\x1f")
                fields = []
                for bit in bits[1:]:
                    if bit:
                        fields.append((chr(bit[0]), bit[1:].decode("utf-8", "replace")))
                field = {"value": val.decode("utf-8", "replace"), "subfields": fields}
            rec.setdefault(tag, []).append(field)
        yield rec


def records_from_zip(data: bytes) -> list[dict]:
    if not zipfile.is_zipfile(BytesIO(data)):
        raise ValueError("Not a ZIP file")
    with zipfile.ZipFile(BytesIO(data)) as archive:
        files = [i for i in archive.infolist() if not i.is_dir() and not i.filename.startswith("__MACOSX")]
        if len(files) > 15 or sum(i.file_size for i in files) > MAX_EXPANDED:
            raise ValueError("Unexpectedly large ZIP archive")
        files = [f for f in files if f.filename.lower().endswith((".txt", ".dat", ".marc", ".mrc")) or re.search(r"/jmo\d+$", "/" + f.filename.lower())]
        # Prefer machine-readable MARC; fallback to the tagged confirmation text.
        primary = [f for f in files if "_confirmation" not in f.filename.lower()]
        tagged = [f for f in files if "_confirmation" in f.filename.lower()]
        errors = []
        for candidates, parser in ((primary, parse_marc21), (tagged, lambda b: parse_tagged(b.decode("utf-8-sig")))):
            for file in candidates:
                try:
                    recs = list(parser(archive.read(file)))
                    if recs and any(x.get("001") for x in recs):
                        return recs
                except (ValueError, UnicodeDecodeError) as exc:
                    errors.append(f"{file.filename}: {exc}")
    raise ValueError("No valid bibliographic MARC file in ZIP: " + "; ".join(errors[:3]))


def get_publication(record: dict) -> str:
    publication = first_field(record, ["264", "260"], "c")
    match = re.search(r"(?<!\d)(20\d{2})(?:[./年-](\d{1,2}))?", publication)
    if match:
        year, month = match[1], match[2]
        return year + (f"-{int(month):02d}" if month and 1 <= int(month) <= 12 else "-00")
    for field in record.get("008", []):
        s = field.get("value", "")
        if len(s) >= 11 and re.fullmatch(r"20\d{2}", s[7:11]):
            return s[7:11] + "-00"
    return ""


def record_to_book(record: dict, archive_date: str = "") -> dict | None:
    leader = record.get("leader", "")
    if len(leader) < 8 or leader[7] != "m" or leader[6] not in {"a"}:
        return None
    ndl_id = (record.get("001") or [{}])[0].get("value", "").strip()
    title = " ".join((field_values(record, "245", "a") + field_values(record, "245", "b")))
    title = re.sub(r"\s+", " ", title).strip(" /;:.,")
    if not ndl_id or not title:
        return None
    authors = []
    for tag in ("100", "110", "700", "710"):
        for author in field_values(record, tag):
            if author not in authors:
                authors.append(author)
            if len(authors) >= 4:
                break
    publisher = first_field(record, ["264", "260"], "b")
    # 650/651/653 are formal/free subject headings, not unconstrained web descriptions.
    subjects = []
    for tag in ("650", "651", "653", "655"):
        for code in ("a", "x", "v"):
            subjects += field_values(record, tag, code)
    genres = " / ".join(dict.fromkeys(field_values(record, "655", "a")))[:200]
    series = " / ".join(dict.fromkeys(field_values(record, "490", "a") + field_values(record, "830", "a")))[:300]
    isbn = re.sub(r"[^0-9Xx]", "", first_field(record, ["020"]))
    if len(isbn) not in {10, 13}:
        isbn = ""
    return {
        "id": f"ndl-{ndl_id}", "ndl_id": ndl_id, "title": title,
        "authors": authors, "publisher": publisher, "published": get_publication(record),
        "isbn": isbn, "subjects": " / ".join(dict.fromkeys(subjects))[:700],
        "genres": genres, "series": series,
        "description": "", "source": "国立国会図書館 JAPAN/MARC(M/S)",
        "source_url": "https://ndlsearch.ndl.go.jp/search?keyword=" + quote(isbn or title),
        "source_archive_date": archive_date,
    }


def is_deletion(record: dict) -> bool:
    return record.get("leader", "")[5:6].lower() == "d"


def score_book(item: dict, config: dict) -> tuple[int, list[str]]:
    title = norm(item.get("title", ""))
    subject = norm(item.get("subjects", ""))
    ranked = []
    for family in config["families"]:
        cores = [norm(x) for x in family.get("core", []) + family.get("english_core", []) if x]
        bridges = [norm(x) for x in family.get("bridge", []) if x]
        core_title = [w for w in cores if w in title]
        core_subject = [w for w in cores if w in subject]
        bridge_title = [w for w in bridges if w in title]
        bridge_subject = [w for w in bridges if w in subject]
        if not (core_title or core_subject or bridge_title or bridge_subject):
            continue
        points = (62 if core_title else 0) + (25 if core_subject else 0) + min(2,len(bridge_title))*10 + min(2,len(bridge_subject))*7
        ranked.append((points, family["label"], bool(core_title)))
    if not ranked:
        return 0, []
    ranked.sort(reverse=True)
    # Carry over all 43 editorial search directions as multi-term discovery signals.
    contextual = title + subject
    matched_query_topics = set()
    for query in config.get("queries", []):
        parts = [norm(part) for part in str(query.get("term", "")).split() if part]
        if parts and all(part in contextual for part in parts):
            matched_query_topics.add(query.get("topic", ""))
    score = min(100, ranked[0][0] + min(3,len(ranked)-1)*8 + min(3,len(matched_query_topics))*4)
    strong = any(norm(cue) in title for cue in TITLE_STRONG_CUES)
    scholarly = any(norm(cue) in title for cue in SCHOLARLY_CUES)
    # Generic keyword matches alone (fictional "変身", etc.) do not become scholarly picks.
    if not strong and not scholarly and len(ranked) == 1:
        score = min(score, 40)
    if not strong and not scholarly and any(title == norm(x) for x in AMBIGUOUS_TITLE_TERMS):
        score = min(score, 30)
    return score, [x[1] for x in ranked[:4]]


def valid_book(item: dict, start=MIN_PUBLICATION, end=MAX_PUBLICATION) -> bool:
    when = item.get("published", "")
    if not when:
        return False
    if when.endswith("-00"):
        if not (start[:4] <= when[:4] <= end[:4]):
            return False
    elif not start <= when <= end:
        return False
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", item.get("title", "")))


def apply_updates(books: list[dict], records_by_archive: list[tuple[str, list[dict]]], taxonomy: dict, max_new=MAX_NEW_PER_UPDATE) -> tuple[list[dict], dict]:
    by_id = {x["ndl_id"]: dict(x) for x in books if x.get("ndl_id")}
    additions = {}
    removed = set()
    scanned = 0
    for date, records in records_by_archive:
        for rec in records:
            scanned += 1
            ndl_id = (rec.get("001") or [{}])[0].get("value", "").strip()
            if not ndl_id:
                continue
            if is_deletion(rec):
                removed.add(ndl_id)
                additions.pop(ndl_id, None)
                by_id.pop(ndl_id, None)
                continue
            item = record_to_book(rec, date)
            if not item:
                continue
            if ndl_id in by_id:
                # A corrected bibliographic record should update the existing item.
                prev = by_id[ndl_id]
                by_id[ndl_id] = {**prev, **item, "tags": prev.get("tags", []), "score": prev.get("score", 0)}
                if valid_book(item):
                    score, tags = score_book(item, taxonomy)
                    by_id[ndl_id].update(score=score, tags=tags)
                continue
            if not valid_book(item):
                additions.pop(ndl_id, None)
                continue
            score, tags = score_book(item, taxonomy)
            if score < MIN_SCORE or selection_reason(item, taxonomy):
                additions.pop(ndl_id, None)
                continue
            item.update(score=score, tags=tags)
            additions[ndl_id] = item
            removed.discard(ndl_id)

    # Preserve only still-active identifiers.
    for ndl_id in removed:
        by_id.pop(ndl_id, None)
        additions.pop(ndl_id, None)
    existing_isbns = {b.get("isbn") for b in by_id.values() if b.get("isbn")}
    existing_titles = {(norm(b.get("title")), norm(b.get("publisher"))) for b in by_id.values()}
    publisher_counts = Counter()
    selected = []
    today = datetime.now(timezone.utc).date().isoformat()
    # First take the highest scoring book from each distinct publisher; limit each to 2.
    for item in sorted(additions.values(), key=lambda x: (-x["score"], x["publisher"], x["title"])):
        if len(selected) >= max_new:
            break
        publisher = norm(item["publisher"]) or "出版社不明"
        if publisher_counts[publisher] >= MAX_NEW_PER_PUBLISHER:
            continue
        if item["isbn"] and item["isbn"] in existing_isbns:
            continue
        key = (norm(item["title"]), norm(item["publisher"]))
        if key in existing_titles:
            continue
        publisher_counts[publisher] += 1
        existing_titles.add(key)
        if item["isbn"]:
            existing_isbns.add(item["isbn"])
        item["discovered_at"] = today
        selected.append(item)
        by_id[item["ndl_id"]] = item
    final = sorted(by_id.values(), key=lambda b: (b.get("discovered_at", ""), b.get("score", 0)), reverse=True)
    return final, {"scanned_records": scanned, "matched_candidates": len(additions), "found_last_run": len(selected), "deleted_known": len(removed)}


def run(initial_weeks: int, dry_run: bool = False, zip_paths: list[str] | None = None) -> int:
    taxonomy = load_json(TAX_FILE, {})
    if len(taxonomy.get("families", [])) != 18 or len(taxonomy.get("queries", [])) != 43:
        raise RuntimeError("Taxonomy configuration is missing or incomplete")
    initial = {"meta": {"title": "奇想和書航路", "updated_at": None}, "books": []}
    saved = load_json(BOOKS_FILE, initial)
    # Re-audit past auto-discoveries. Move false positives to an archive inside
    # books.json rather than deleting them; manually entered records are kept.
    active_books, freshly_excluded = split_existing_catalog(saved.get("books", []), taxonomy)
    excluded_by_id = {b.get("ndl_id", b.get("id")): b for b in saved.get("excluded_books", [])}
    for book in freshly_excluded:
        excluded_by_id[book.get("ndl_id", book.get("id"))] = book
    state = load_json(STATE_FILE, {"processed_urls": [], "last_run": None})
    processed = set(state.get("processed_urls", []))
    if zip_paths:
        discovered = [{"url": f"local:{Path(p).name}", "date": "", "path": p} for p in zip_paths]
    else:
        html = download(INDEX_URL, 2_000_000).decode("utf-8", "replace")
        discovered = parse_index(html)
        if not discovered:
            raise RuntimeError("No weekly MARC ZIP found on official NDL index: please check the page structure")
        discovered = [a for a in discovered[:max(2, initial_weeks if not processed else 5)] if a["url"] not in processed]
        discovered.reverse()  # apply older archives before newer archives to respect corrections/deletions
    batch = []
    failures = []
    newly_processed = []
    for i, obj in enumerate(discovered):
        url = obj["url"]
        if url in processed:
            continue
        try:
            if obj.get("path"):
                data = Path(obj["path"]).read_bytes()
            else:
                data = download(url, MAX_ZIP_BYTES)
            records = records_from_zip(data)
            batch.append((obj.get("date", ""), records))
            newly_processed.append(url)
            print(f"Processed {url}: {len(records)} bibliographic records")
        except Exception as exc:
            failures.append(f"{url}: {exc}")
            print(f"ERROR {failures[-1]}", file=sys.stderr)
        if not obj.get("path") and i < len(discovered) - 1:
            time.sleep(1.5)
    # No new archives is a normal idempotent weekly no-op.
    if not discovered:
        if freshly_excluded and not dry_run:
            saved["books"] = active_books
            saved["excluded_books"] = list(excluded_by_id.values())
            meta = dict(saved.get("meta", {}))
            meta.update(total=len(active_books), excluded_total=len(excluded_by_id),
                        updated_at=now_iso(), editorial_filter="takayama-v2.0",
                        found_last_run=0, weeks_processed=0, queries_attempted=0,
                        queries_failed=0, scanned_records=0, matched_candidates=0)
            saved["meta"] = meta
            atomic_json(BOOKS_FILE, saved)
            print(f"No new weekly archives. Reclassified {len(freshly_excluded)} existing titles (recoverable).")
        else:
            print(f"No new JAPAN/MARC weekly archives. Editorial reclassification: {len(freshly_excluded)} titles (dry run={dry_run}).")
        return 0
    # No successful downloads -> prevent replacing good data or recording false success.
    if not batch:
        print("No archive processed; existing published data preserved.", file=sys.stderr)
        return 1
    books, stats = apply_updates(active_books, batch, taxonomy)
    books, after_run_excluded = split_existing_catalog(books, taxonomy)
    for book in after_run_excluded:
        excluded_by_id[book.get("ndl_id", book.get("id"))] = book
    meta = dict(saved.get("meta", {}))
    meta.update({
        "title": "奇想和書航路", "edition": "2026–2028", "updated_at": now_iso(),
        "status": "partial" if failures else "ok", "source": "国立国会図書館 JAPAN/MARC(M/S) 週次ファイル",
        "source_url": INDEX_URL, "total": len(books), "weeks_processed": len(batch),
        "archives_total": len(processed | set(newly_processed)), "queries_attempted": len(discovered),
        "queries_failed": len(failures), "data_notice": "国立国会図書館書誌データを加工して作成。書誌に基づく自動発見候補であり、内容確認済みの推薦ではありません。",
        "editorial_filter": "takayama-v2.0", "excluded_total": len(excluded_by_id),
        "excluded_this_run": len(freshly_excluded) + len(after_run_excluded),
        **stats,
    })
    if dry_run:
        print(f"DRY RUN: {stats}; current total={len(books)}, archives={len(newly_processed)}, failures={len(failures)}")
        return 0 if not failures else 2
    # Save both only after parsing: data is a cumulative archive; re-run is idempotent.
    atomic_json(BOOKS_FILE, {"meta": meta, "books": books, "excluded_books": list(excluded_by_id.values())})
    atomic_json(STATE_FILE, {"processed_urls": sorted(processed | set(newly_processed)), "last_run": meta["updated_at"]})
    print(f"Result: +{stats['found_last_run']} titles, {len(books)} total, {len(batch)} archives processed")
    return 0 if not failures else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-weeks", type=int, default=DEFAULT_INITIAL_WEEKS, help="First-run backfill weeks (default 8; max 12)")
    parser.add_argument("--dry-run", action="store_true", help="Print result without modifying files")
    parser.add_argument("--archive", action="append", help="Local JAPAN/MARC weekly ZIP for offline validation (repeatable)")
    args = parser.parse_args()
    if not 1 <= args.initial_weeks <= 12:
        parser.error("--initial-weeks must be 1–12")
    return run(args.initial_weeks, args.dry_run, args.archive)


if __name__ == "__main__":
    sys.exit(main())
