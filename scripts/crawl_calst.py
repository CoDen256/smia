"""Throwaway crawler: NTNU CALST (testcalst.hf.ntnu.no) -> one raw-ish JSON dump.

Private research use only. Metadata only: no audio is downloaded.

    python -m scripts.crawl_calst                 # full crawl
    python -m scripts.crawl_calst --limit 5       # smoke test: first 5 exercises
    python -m scripts.crawl_calst --types AXB MP  # restrict exercise types

Walk:  /Home/Lessons -> /Home/Lesson/N -> (/Exercise/no/ID?wrid=N
                                           | /Home/LessonGroup/G -> /Exercise/no/ID?wrid=G)
       -> POST /Exercises/Details {ExerciseId, wrid, vwrid, Type}

Every HTTP response is cached gzipped under providers/calst/.cache/, so a
re-run (or Ctrl-C and restart) costs no network for finished requests. The
output keeps everything each exercise returns, per Type, untouched:
    {AXB: {status, variable, data: [...]}, MP: ..., LAC: ..., LAS: ..., LAW: ...}
The exercise data variable differs by type (MPExerciseData for AXB/MP,
VocabExerciseData for LAS/LAW); the name is recorded next to the data.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests

BASE = "https://testcalst.hf.ntnu.no"
COOKIE = "IL1=en; L1=61; L2_Dialect=1; L2_LanguageId=1; L2_Id=552"
UA = "smia-research-crawler/0.1 (private research)"
ALL_TYPES = ["AXB", "MP", "LAC", "LAS", "LAW"]
OUT_DIR = Path(__file__).resolve().parent.parent / "providers" / "calst"
CACHE_DIR = OUT_DIR / ".cache"
OUT_FILE = OUT_DIR / "calst_manifest.json"

DATA_VARS = ("MPExerciseData", "VocabExerciseData", "VocabWordList")


# ---------------------------------------------------------------- HTTP + cache
class Client:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update({"Cookie": COOKIE, "User-Agent": UA})
        self.last = 0.0
        self.network_calls = 0

    def _sleep(self) -> None:
        wait = random.uniform(0.1, 0.3) - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)

    def request(self, method: str, path: str, data: dict | None = None) -> dict:
        """Returns {status, location, body}. Cached by (method, path, data)."""
        key = hashlib.sha256(
            json.dumps([method, path, data], sort_keys=True).encode()
        ).hexdigest()[:32]
        cf = CACHE_DIR / f"{key}.json.gz"
        if cf.exists():
            return json.loads(gzip.decompress(cf.read_bytes()))

        url = urljoin(BASE, path)
        for attempt in range(6):
            self._sleep()
            try:
                r = self.s.request(
                    method, url, data=data, timeout=30, allow_redirects=False
                )
            except requests.RequestException as e:
                self.last = time.monotonic()
                backoff = 2 ** attempt
                print(f"  ! {e.__class__.__name__}, retry in {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                continue
            self.last = time.monotonic()
            self.network_calls += 1
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                print(f"  ! HTTP {r.status_code}, retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            rec = {
                "status": r.status_code,
                "location": r.headers.get("Location"),
                "body": r.text,
            }
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = cf.with_suffix(".tmp")
            tmp.write_bytes(gzip.compress(json.dumps(rec).encode()))
            tmp.replace(cf)
            return rec
        raise RuntimeError(f"giving up on {method} {url}")


# ------------------------------------------------------------------ HTML walk
TOKEN_RE = re.compile(
    r"<h(?P<lvl>[1-3])[^>]*>(?P<h>.*?)</h(?P=lvl)>"
    r"|<a\s[^>]*?href=\"(?P<href>[^\"]+)\"[^>]*>(?P<a>.*?)</a>",
    re.S | re.I,
)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_page(page: str) -> list[dict]:
    """Document-order stream of links, each tagged with the headings above it."""
    heads = {"1": "", "2": "", "3": ""}
    out = []
    for m in TOKEN_RE.finditer(page):
        if m["lvl"]:
            heads[m["lvl"]] = _text(m["h"])
            for deeper in "23"[int(m["lvl"]) - 1 :]:  # h1 resets h2/h3, h2 resets h3
                if deeper > m["lvl"]:
                    heads[deeper] = ""
        else:
            out.append(
                {
                    "href": html.unescape(m["href"]),
                    "title": _text(m["a"]),
                    "h1": heads["1"],
                    "h2": heads["2"],
                    "h3": heads["3"],
                }
            )
    return out


def get_page(c: Client, path: str) -> list[dict]:
    rec = c.request("GET", path)
    if rec["status"] != 200:
        raise RuntimeError(f"GET {path} -> {rec['status']}")
    return parse_page(rec["body"])


# ----------------------------------------------------- JS literal -> JSON
def _extract_array(js: str, var: str) -> str | None:
    m = re.search(rf"Calst\.{var}\s*=\s*\[", js)
    if not m:
        return None
    start = m.end() - 1
    depth, i, in_str, esc = 0, start, False, False
    while i < len(js):
        ch = js[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return js[start : i + 1]
        i += 1
    return None


def _quote_keys(lit: str) -> str:
    """Quote bare object keys outside string literals: {a:1} -> {"a":1}."""
    out, i, n = [], 0, len(lit)
    while i < n:
        ch = lit[i]
        if ch == '"':
            j, esc = i + 1, False
            while j < n:
                if esc:
                    esc = False
                elif lit[j] == "\\":
                    esc = True
                elif lit[j] == '"':
                    break
                j += 1
            out.append(lit[i : j + 1])
            i = j + 1
        elif ch.isalpha() or ch == "_":
            j = i
            while j < n and (lit[j].isalnum() or lit[j] == "_"):
                j += 1
            word = lit[i:j]
            k = j
            while k < n and lit[k] in " \t\r\n":
                k += 1
            if k < n and lit[k] == ":":
                out.append(f'"{word}"')
            else:
                out.append(word)  # true / false / null / undefined
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_details(body: str) -> dict:
    """Pull every Calst.*ExerciseData / VocabWordList array out of the page."""
    found, errors = {}, {}
    for var in DATA_VARS:
        lit = _extract_array(body, var)
        if lit is None:
            continue
        if var == "VocabWordList":  # `shuffle(Calst.VocabExerciseData...)`, not a literal
            continue
        try:
            found[var] = json.loads(_quote_keys(lit))
        except json.JSONDecodeError as e:
            errors[var] = f"{e} :: {lit[:120]}"
    return {"variables": found, "parse_errors": errors}


# ------------------------------------------------------------------- crawl
def discover(c: Client) -> tuple[list[dict], dict]:
    """Returns (lessons, exercise_index). exercise_index is keyed by
    (exercise_id, wrid, vwrid) so an exercise linked twice is fetched once."""
    lessons, index = [], {}

    def add_exercise(link: dict, lesson: dict, group: dict | None) -> None:
        u = urlparse(link["href"])
        m = re.match(r"^/Exercise/([^/]+)/(\d+)$", u.path, re.I)
        if not m:
            return
        q = parse_qs(u.query)
        key = (int(m[2]), int(q.get("wrid", ["0"])[0]), int(q.get("vwrid", ["0"])[0]))
        entry = index.setdefault(
            key,
            {
                "exercise_id": key[0],
                "wrid": key[1],
                "vwrid": key[2],
                "language": m[1],
                "href": link["href"],
                "appearances": [],
            },
        )
        entry["appearances"].append(
            {
                "lesson_id": lesson["lesson_id"],
                "lesson_title": lesson["title"],
                "lesson_level": lesson["level"],
                "group_id": group["group_id"] if group else None,
                "group_title": group["title"] if group else None,
                "part": link["h2"],
                "section": link["h3"],
                "title": link["title"],
            }
        )

    for ln in get_page(c, "/Home/Lessons"):
        m = re.match(r"^/Home/Lesson/(\d+)$", ln["href"], re.I)
        if m:
            lessons.append(
                {"lesson_id": int(m[1]), "title": ln["title"], "level": ln["h1"], "groups": []}
            )
    print(f"lessons: {len(lessons)}")

    for lesson in lessons:
        for ln in get_page(c, f"/Home/Lesson/{lesson['lesson_id']}"):
            gm = re.match(r"^/Home/LessonGroup/(\d+)$", ln["href"], re.I)
            if gm:
                g = {
                    "group_id": int(gm[1]),
                    "title": ln["title"],
                    "part": ln["h2"],
                    "section": ln["h3"],
                }
                lesson["groups"].append(g)
                for gl in get_page(c, f"/Home/LessonGroup/{g['group_id']}"):
                    add_exercise(gl, lesson, g)
            else:
                add_exercise(ln, lesson, None)
        print(
            f"  lesson {lesson['lesson_id']:>3} {lesson['title']!r}: "
            f"{len(lesson['groups'])} groups, {len(index)} exercises so far"
        )
    return lessons, index


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only fetch details for first N exercises")
    ap.add_argument("--types", nargs="+", default=ALL_TYPES, choices=ALL_TYPES)
    args = ap.parse_args()

    c = Client()
    lessons, index = discover(c)
    todo = sorted(index.values(), key=lambda e: (e["wrid"], e["exercise_id"], e["vwrid"]))
    if args.limit:
        todo = todo[: args.limit]
    print(f"exercises: {len(index)} (fetching {len(todo)} x {len(args.types)} types)")

    exercises = []
    for n, ex in enumerate(todo, 1):
        results = {}
        for t in args.types:
            rec = c.request(
                "POST",
                "/Exercises/Details",
                {
                    "ExerciseId": ex["exercise_id"],
                    "wrid": ex["wrid"],
                    "vwrid": ex["vwrid"],
                    "Type": t,
                },
            )
            res = {"status": rec["status"], "location": rec["location"], "bytes": len(rec["body"])}
            if rec["status"] == 200:
                res.update(parse_details(rec["body"]))
                if not res["variables"]:
                    res["body_head"] = rec["body"][:300]  # unexpected shape, keep a hint
            results[t] = res
        exercises.append({**ex, "types": results})
        got = {t: sum(len(v) for v in r.get("variables", {}).values()) for t, r in results.items()}
        print(f"[{n}/{len(todo)}] ex={ex['exercise_id']} wrid={ex['wrid']} {got}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "meta": {
            "source": BASE,
            "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cookie": COOKIE,
            "types_requested": args.types,
            "note": "private research; metadata only",
        },
        "lessons": lessons,
        "exercises": exercises,
    }
    tmp = OUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT_FILE)
    print(f"wrote {OUT_FILE} ({OUT_FILE.stat().st_size / 1e6:.1f} MB); network calls: {c.network_calls}")


if __name__ == "__main__":
    main()
