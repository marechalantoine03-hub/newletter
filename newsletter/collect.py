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
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 newsletter-collector/1.0"
)
GOOGLE_NEWS = "https://news.google.com/rss/search?q=site:{site}+when:1d&hl=en-US&gl=US&ceid=US:en"
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


def candidate_urls(source: dict) -> list[str]:
    """Adresse principale, puis adresses de secours, puis Google News limité au site."""
    urls = [source["url"], *source.get("fallback_urls", [])]
    if source.get("site"):
        urls.append(GOOGLE_NEWS.format(site=source["site"]))
    return urls


def read_feed(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        body = response.read()
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise ValueError(f"flux illisible : {feed.bozo_exception}")
    return feed


def recent_articles(feed, source: dict, since: datetime) -> tuple[list[Article], int]:
    articles, undated = [], 0
    for entry in feed.entries:
        published = entry_time(entry)
        if published is None:
            undated += 1
            continue
        if published < since:
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
    return articles, undated


def fetch(source: dict, since: datetime) -> tuple[dict, list[Article]]:
    """Essaie chaque adresse jusqu'à obtenir des articles récents. Une panne ne bloque jamais les autres sources."""
    report = {"name": source["name"], "url": source["url"], "status": "vide", "count": 0, "error": None, "detail": ""}
    attempts = []
    for url in candidate_urls(source):
        try:
            feed = read_feed(url)
        except Exception as exc:
            attempts.append(f"{url} -> {str(exc)[:120]}")
            continue
        articles, undated = recent_articles(feed, source, since)
        attempts.append(f"{url} -> {len(feed.entries)} entrées, {len(articles)} récentes, {undated} sans date")
        if articles:
            report.update(status="ok", count=len(articles), url=url)
            if url != source["url"]:
                report["status"] = "secours"
            report["detail"] = attempts[-1]
            return report, articles
    if all("->" in a and "entrées" not in a for a in attempts):
        report["status"] = "erreur"
    report["error"] = " | ".join(attempts)
    return report, []


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

    ok = sum(r["count"] > 0 for r in reports)
    print(f"{len(articles)} articles sur {args.hours} h, {ok}/{len(reports)} sources avec des articles.")
    order = {"erreur": 0, "vide": 1, "secours": 2, "ok": 3}
    for r in sorted(reports, key=lambda r: (order[r["status"]], r["name"])):
        detail = r["error"] if r["count"] == 0 else f"{r['count']} articles"
        if r["status"] == "secours":
            detail += f" (via {r['url']})"
        print(f"  [{r['status']:>7}] {r['name']}: {detail}")
    by_region: dict[str, int] = {}
    for a in articles:
        by_region[a.region] = by_region.get(a.region, 0) + 1
    print("Par région :", ", ".join(f"{k} {v}" for k, v in sorted(by_region.items())))
    return 0 if articles else 1


if __name__ == "__main__":
    sys.exit(main())
