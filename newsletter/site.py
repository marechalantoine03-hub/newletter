"""Phase 3 : fabrique le site statique à partir des numéros de issues/.

Usage :
    python -m newsletter.site            # écrit le site dans _site/

Pages produites :
    index.html             le dernier numéro
    archives.html          la liste de tous les numéros
    numeros/AAAA-MM-JJ.html un numéro
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
TITLE = "Le monde, chaque matin"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

CSS = """
:root{--bg:#fbfaf7;--fg:#1f1d1a;--muted:#6b665e;--rule:#e4e0d8;--accent:#9a3412;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ebe7e0;--muted:#a39d93;--rule:#34312c;--accent:#f0a77a;--card:#1e1c19}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.65 Georgia,"Iowan Old Style","Times New Roman",serif;-webkit-text-size-adjust:100%}
header.site,footer.site{max-width:720px;margin:0 auto;padding:20px 16px;display:flex;justify-content:space-between;align-items:baseline;gap:16px;font-family:system-ui,-apple-system,sans-serif;font-size:15px}
header.site{border-bottom:1px solid var(--rule)}
header.site a.brand{font-weight:700;color:var(--fg);text-decoration:none;font-size:17px}
nav{white-space:nowrap}
nav a{color:var(--muted);text-decoration:none;margin-left:16px}
main p>strong:first-child{display:block;font-size:1.05em}
nav a:hover{color:var(--accent)}
main{max-width:720px;margin:0 auto;padding:8px 16px 48px}
h1{font-size:2.1em;line-height:1.15;margin:.8em 0 .3em}
h2{font-size:1.45em;line-height:1.25;margin:2.2em 0 .6em;padding-top:1.2em;border-top:1px solid var(--rule)}
h4{font-family:system-ui,-apple-system,sans-serif;font-size:.8em;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:1.8em 0 .4em}
a{color:var(--accent);text-underline-offset:2px}
p{margin:0 0 1em}
table{border-collapse:collapse;width:100%;font-size:.88em;margin:1em 0;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--rule);padding:6px 10px;text-align:left;vertical-align:top}
hr{border:0;border-top:1px solid var(--rule);margin:2.5em 0 1em}
main>p:first-of-type em{font-size:1.15em;color:var(--muted)}
ul{padding-left:1.2em}
.archives li{margin:.4em 0;list-style:none}
.archives{padding:0}
.archives a{font-size:1.1em}
.archives span{color:var(--muted);font-size:.85em;margin-left:8px}
footer.site{border-top:1px solid var(--rule);color:var(--muted)}
@media (max-width:520px){body{font-size:17px}h1{font-size:1.7em}header.site{flex-direction:column;gap:4px}nav a{margin:0 16px 0 0}}
"""


def date_fr(day: date) -> str:
    return f"{day.day} {MOIS[day.month - 1]} {day.year}"


def page(title: str, body: str, prefix: str = "") -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="site"><a class="brand" href="{prefix}index.html">{TITLE}</a>
<nav><a href="{prefix}index.html">Dernier numéro</a><a href="{prefix}archives.html">Archives</a></nav></header>
<main>
{body}
</main>
<footer class="site"><span>Newsletter d'actualité internationale, rédigée par une IA à partir des sources citées.</span></footer>
</body>
</html>
"""


def render(md_text: str) -> str:
    out = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    # les liens vers les sources s'ouvrent dans un nouvel onglet
    return re.sub(r'<a href="(https?://)', r'<a target="_blank" rel="noopener" href="\1', out)


def build(issues_dir: Path, out: Path) -> int:
    issues = sorted(issues_dir.glob("*.md"), reverse=True)
    if out.exists():
        shutil.rmtree(out)
    (out / "numeros").mkdir(parents=True)
    (out / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    entries = []
    for path in issues:
        day = date.fromisoformat(path.stem)
        text = path.read_text(encoding="utf-8")
        lead = re.search(r"^\*(.+)\*$", text, re.M)
        entries.append((day, lead.group(1) if lead else ""))
        title = f"{TITLE} · {date_fr(day)}"
        (out / "numeros" / f"{path.stem}.html").write_text(page(title, render(text), "../"), encoding="utf-8")

    if issues:
        latest = issues[0].read_text(encoding="utf-8")
        index_body = render(latest)
    else:
        index_body = "<h1>Premier numéro en préparation</h1><p>Revenez demain matin.</p>"
    (out / "index.html").write_text(page(TITLE, index_body), encoding="utf-8")

    items = "\n".join(
        f'<li><a href="numeros/{d.isoformat()}.html">{date_fr(d)}</a><span>{html.escape(lead)}</span></li>'
        for d, lead in entries
    ) or "<li>Aucun numéro pour l'instant.</li>"
    archive = f"<h1>Archives</h1>\n<ul class=\"archives\">\n{items}\n</ul>"
    (out / "archives.html").write_text(page(f"Archives · {TITLE}", archive), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site construit dans {out} : {len(issues)} numéro(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issues", type=Path, default=ROOT / "issues")
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    args = parser.parse_args(argv)
    return build(args.issues, args.out)


if __name__ == "__main__":
    sys.exit(main())
