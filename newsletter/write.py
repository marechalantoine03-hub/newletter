"""Phase 2 : rédaction du numéro du jour à partir des articles collectés.

Usage :
    python -m newsletter.write                     # utilise data/<aujourd'hui>/articles.json
    python -m newsletter.write --date 2026-11-08

Écrit issues/AAAA-MM-JJ.md (le numéro) et data/AAAA-MM-JJ/plan.json (les choix de l'IA).
Il faut la variable GEMINI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from . import country, llm

ROOT = Path(__file__).resolve().parent.parent
WORDS_PER_MINUTE = 230
PAUSE_S = 6  # entre deux appels, pour rester sous le quota gratuit par minute
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
THEMES = {"geopolitique": "Géopolitique", "economie": "Économie", "tech": "Tech"}

SYSTEM = """Tu es le rédacteur en chef d'une newsletter quotidienne d'actualité internationale,
écrite en français pour un lecteur cultivé qui veut comprendre le monde en 30 minutes.
Règles absolues :
- Les faits d'actualité viennent UNIQUEMENT des articles fournis. N'invente aucun chiffre,
  aucune citation, aucune date, aucun nom.
- Tu peux ajouter du contexte de fond (histoire, géographie, institutions) tiré de tes
  connaissances générales, sans chiffres précis non sourcés.
- Quand les sources divergent, dis-le et attribue chaque point de vue à sa source.
- Cite les sources sous forme de liens Markdown [Nom de la source](url), uniquement avec
  les url fournies.
- Ton sobre, clair, factuel. Phrases courtes. Pas de sensationnalisme, pas d'emoji."""


def date_fr(day: date) -> str:
    return f"{day.day} {MOIS[day.month - 1]} {day.year}"


def load_articles(day_dir: Path) -> list[dict]:
    articles = json.loads((day_dir / "articles.json").read_text(encoding="utf-8"))
    for i, article in enumerate(articles):
        article["id"] = i
    return articles


def article_line(a: dict) -> str:
    summary = a["summary"][:160]
    return f'{a["id"]} | {a["source"]} ({a["region"]}, {a["type"]}) | {a["title"]} — {summary}'


def article_block(a: dict) -> str:
    return (f'- Source : {a["source"]} ({a["region"]}, {a["type"]}), {a["published"][:10]}\n'
            f'  Titre : {a["title"]}\n  Résumé : {a["summary"]}\n  Lien : {a["url"]}')


def pick(articles: list[dict], ids: list) -> list[dict]:
    by_id = {a["id"]: a for a in articles}
    return [by_id[i] for i in ids if isinstance(i, int) and i in by_id]


# ---------- 1. Choix des sujets ----------

def plan_issue(articles: list[dict]) -> dict:
    listing = "\n".join(article_line(a) for a in articles)
    prompt = f"""Voici les articles collectés (format : id | source (région, type) | titre — résumé).

{listing}

Construis le sommaire du numéro du jour. Critères : importance internationale, nombre de
sources indépendantes qui couvrent le sujet, diversité des régions du monde. Écarte le sport,
les faits divers sans portée internationale et la vie des célébrités.

Réponds en JSON exactement sous cette forme :
{{
  "a_la_une": "une phrase qui résume la journée",
  "dossiers": [
    {{"theme": "geopolitique", "titre": "...", "angle": "la question à laquelle le dossier répond", "ids": [..]}},
    {{"theme": "economie", "titre": "...", "angle": "...", "ids": [..]}},
    {{"theme": "tech", "titre": "...", "angle": "...", "ids": [..]}}
  ],
  "breves": [{{"theme": "geopolitique|economie|tech", "titre": "...", "ids": [..]}}],
  "a_surveiller": [{{"titre": "...", "ids": [..]}}]
}}
Contraintes : exactement 3 dossiers (un par thème), chacun avec 4 à 10 articles venant si
possible d'au moins 2 régions ; 10 à 12 brèves sur des sujets différents des dossiers, chacune
avec 1 à 4 articles ; 3 sujets « à surveiller » dans les jours qui viennent. Les titres sont en
français. N'utilise que des ids de la liste."""
    return llm.generate_json(prompt, system=SYSTEM)


# ---------- 2. Rédaction ----------

def write_breves(plan: dict, articles: list[dict]) -> str:
    blocks = []
    for i, breve in enumerate(plan["breves"], 1):
        sources = "\n".join(article_block(a) for a in pick(articles, breve.get("ids", [])))
        blocks.append(f"BRÈVE {i} ({breve.get('theme', '')}) : {breve['titre']}\n{sources}")
    prompt = """Rédige les brèves suivantes. Pour chacune : un titre en gras sur sa propre ligne,
puis un paragraphe de 90 à 130 mots qui dit ce qui s'est passé, pourquoi c'est important, et qui
se termine par les liens vers ses sources. Sépare les brèves par une ligne vide. Pas de titre
général, pas de numérotation.

""" + "\n\n".join(blocks)
    return llm.generate(prompt, system=SYSTEM)


def write_dossier(dossier: dict, articles: list[dict]) -> str:
    sources = "\n".join(article_block(a) for a in pick(articles, dossier.get("ids", [])))
    prompt = f"""Rédige un dossier approfondi de 1 300 à 1 600 mots.
Titre : {dossier['titre']}
Angle : {dossier.get('angle', '')}

Structure, avec des intertitres Markdown de niveau 4 (####) :
#### Ce qui s'est passé
#### Le contexte
#### Les points de vue (compare ce que disent les sources selon leur région ou leur type)
#### Les enjeux
#### Ce qu'il faut surveiller
Cite les sources dans le texte avec des liens. Ne répète pas le titre en tête.

Articles disponibles :
{sources}"""
    return llm.generate(prompt, system=SYSTEM)


def write_country(ctx: dict) -> str:
    indicators = "\n".join(f"- {k} : {v}" for k, v in ctx["indicateurs"].items()) or "(aucune donnée)"
    news = "\n".join(article_block(a) for a in ctx["articles"]) or "(aucun article récent)"
    prompt = f"""Rédige la fiche pays du jour sur : {ctx['nom']}. Entre 900 et 1 100 mots.

Structure, avec des intertitres Markdown de niveau 4 (####) :
#### Carte d'identité (un tableau Markdown : capitale, langues, régime politique, chef de l'État
ou du gouvernement si tu le sais avec certitude, puis les indicateurs ci-dessous avec leur année)
#### En bref (3 phrases pour situer le pays)
#### Histoire
#### Politique
#### Économie
#### Place dans le monde
#### Dans l'actualité (à partir des articles fournis ; s'il n'y en a pas, dis-le en une phrase)
Pour les indicateurs, reprends exactement les valeurs fournies. Termine par une ligne :
« Sources : Wikipédia, Banque mondiale » suivie des liens des articles cités.
Ne répète pas le nom du pays en titre.

Résumé Wikipédia :
{ctx['wikipedia']}

Indicateurs Banque mondiale (dernière année connue) :
{indicators}

Articles récents qui mentionnent le pays :
{news}"""
    return llm.generate(prompt, system=SYSTEM)


def write_watchlist(plan: dict, articles: list[dict]) -> str:
    lines = []
    for item in plan.get("a_surveiller", []):
        links = ", ".join(f"[{a['source']}]({a['url']})" for a in pick(articles, item.get("ids", []))[:3])
        lines.append(f"- {item['titre']}" + (f" ({links})" if links else ""))
    return "\n".join(lines)


# ---------- 3. Assemblage ----------

def word_count(text: str) -> int:
    text = re.sub(r"\]\([^)]*\)", "]", text)  # les url ne se lisent pas
    return len(re.findall(r"\w+", text))


def assemble(day: date, plan: dict, breves: str, dossiers: list[tuple[dict, str]],
             pays: tuple[str, str], watchlist: str, n_articles: int, n_sources: int) -> str:
    body = ["## Les brèves\n", breves.strip(), ""]
    for dossier, text in dossiers:
        body += [f"## {THEMES.get(dossier['theme'], dossier['theme'])} : {dossier['titre']}\n", text.strip(), ""]
    body += [f"## Fiche pays : {pays[0]}\n", pays[1].strip(), ""]
    body += ["## À surveiller\n", watchlist, ""]
    body_text = "\n".join(body)
    minutes = round(word_count(body_text) / WORDS_PER_MINUTE)

    sommaire = ["- Les brèves"]
    sommaire += [f"- {THEMES.get(d['theme'], d['theme'])} : {d['titre']}" for d, _ in dossiers]
    sommaire += [f"- Fiche pays : {pays[0]}", "- À surveiller"]

    head = [
        f"# Le monde, le {date_fr(day)}",
        "",
        f"*{plan.get('a_la_une', '').strip()}*",
        "",
        f"Environ {minutes} minutes de lecture · {n_articles} articles de {n_sources} sources lus pour ce numéro.",
        "",
        "**Au sommaire**",
        "",
        *sommaire,
        "",
    ]
    footer = [
        "---",
        "",
        "Rédigé automatiquement par une IA à partir des sources citées. "
        "Les faits viennent des articles liés ; en cas de doute, la source fait foi.",
    ]
    return "\n".join(head + [body_text] + footer) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "issues")
    args = parser.parse_args(argv)

    day_dir = args.data / args.date.isoformat()
    articles = load_articles(day_dir)
    n_sources = len({a["source"] for a in articles})
    print(f"{len(articles)} articles de {n_sources} sources.")

    print("1/6 Choix des sujets…")
    plan = plan_issue(articles)
    (day_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"    {len(plan['dossiers'])} dossiers, {len(plan['breves'])} brèves.")

    time.sleep(PAUSE_S)
    print("2/6 Brèves…")
    breves = write_breves(plan, articles)

    dossiers = []
    for i, dossier in enumerate(plan["dossiers"], 3):
        time.sleep(PAUSE_S)
        print(f"{i}/6 Dossier : {dossier['titre']}…")
        dossiers.append((dossier, write_dossier(dossier, articles)))

    time.sleep(PAUSE_S)
    pick_country = country.country_of_the_day(args.date)
    print(f"6/6 Fiche pays : {pick_country['nom']}…")
    ctx = country.country_context(pick_country, articles)
    pays = (pick_country["nom"], write_country(ctx))

    issue = assemble(args.date, plan, breves, dossiers, pays, write_watchlist(plan, articles),
                     len(articles), n_sources)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.date.isoformat()}.md"
    path.write_text(issue, encoding="utf-8")
    words = word_count(issue)
    print(f"Numéro écrit : {path} ({words} mots, environ {round(words / WORDS_PER_MINUTE)} min).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
