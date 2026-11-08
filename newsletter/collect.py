"""Phase 1 : collecte des articles des dernières heures depuis les flux de sources.yaml.

Usage :
    python -m newsletter.collect               # dernières 24 heures
    python -m newsletter.collect --hours 36

Écrit :
    data/AAAA-MM-JJ/articles.json   les articles retenus, triés du plus récent au plus ancien
    data/AAAA-MM-JJ/sources.json    l'état de chaque source (ok, vide, en erreur)
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "Mozilla/5.0 (compatible; newsletter-collector/1.0; +https://github.com/)"
TIMEOUT_S = 20
SUMMARY_MAX_CHARS = 600


@dataclass
class Article:
    title: str
    url: str
    summary: str
    published: str  # ISO 8601, UTC
    source: str
    region: str
    type: str
    lang: str
    topics: list[str]


def load_sources(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [s for s in data["sources"] if s.get("enabled", True)]


def clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "…"
    return text


def entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def fetch(source: dict, since: datetime) -> tuple[dict, list[Article]]:
    report = {"name": source["name"], "url": source["url"], "status": "ok", "count": 0, "error": None}
    try:
        request = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = response.read()
        feed = feedparser.parse(body)
        if feed.bozo and not feed.entries:
            raise ValueError(f"flux illisible : {feed.bozo_exception}")
    except Exception as exc:  # une source en panne ne doit jamais bloquer les autres
        report.update(status="erreur", error=str(exc)[:200])
        return report, []

    articles = []
    for entry in feed.entries:
        published = entry_time(entry)
        if published is None or published < since:
            continue
        title = clean_text(entry.get("title", ""))
        link = entry.get("link", "")
        if not title or not link:
            continue
        articles.append(
            Article(
                title=title,
                url=link,
                summary=clean_text(entry.get("summary", "")),
                published=published.isoformat(),
                source=source["name"],
                region=source["region"],
                type=source["type"],
                lang=source["lang"],
                topics=list(source.get("topics", [])),
            )
        )
    report["count"] = len(articles)
    if not articles:
        report["status"] = "vide"
    return report, articles


def dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    unique = []
    for article in articles:
        key = article.url.split("?")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--sources", type=Path, default=ROOT / "sources.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    sources = load_sources(args.sources)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda s: fetch(s, since), sources))

    reports = [r for r, _ in results]
    articles = dedupe([a for _, batch in results for a in batch])
    articles.sort(key=lambda a: a.published, reverse=True)

    day_dir = args.out / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "articles.json").write_text(
        json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (day_dir / "sources.json").write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(r["status"] == "ok" for r in reports)
    print(f"{len(articles)} articles sur {args.hours} h, {ok}/{len(reports)} sources avec des articles.")
    for r in sorted(reports, key=lambda r: (r["status"] != "erreur", r["name"])):
        detail = r["error"] if r["status"] == "erreur" else f"{r['count']} articles"
        print(f"  [{r['status']:>6}] {r['name']}: {detail}")
    by_region: dict[str, int] = {}
    for a in articles:
        by_region[a.region] = by_region.get(a.region, 0) + 1
    print("Par région :", ", ".join(f"{k} {v}" for k, v in sorted(by_region.items())))
    return 0 if articles else 1


if __name__ == "__main__":
    sys.exit(main())
