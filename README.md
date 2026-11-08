# Newsletter internationale quotidienne

Programme qui fabrique chaque matin une newsletter d'actualité internationale
(géopolitique, économie, tech, fiche pays) d'environ 30 minutes de lecture,
la publie sur un site et l'envoie par mail. Gratuit, et indépendant de tout service payant.

## Où en est le projet

| Phase | Contenu | État |
| --- | --- | --- |
| 1 | Collecte des sources (flux RSS) | fait |
| 2 | Rédaction du numéro par une IA gratuite | en cours |
| 3 | Site (GitHub Pages) et envoi par mail | en cours |
| 4 | Exécution automatique chaque matin | à faire |

## Les sources

Toutes les sources sont listées dans [`sources.yaml`](sources.yaml), classées par région,
type et thème. Pour en ajouter ou en retirer une, il suffit de modifier ce fichier.

## Lancer la collecte

Sur GitHub : onglet **Actions** > **Collecte des sources** > **Run workflow**.
Le journal affiche l'état de chaque source, et les articles sont téléchargeables
en fin de page (« Artifacts »).

En local :

```
pip install -r requirements.txt
python -m newsletter.collect --hours 24
```

## Rédiger un numéro

Il faut une clé gratuite de l'API Gemini, enregistrée dans les secrets du dépôt sous le nom
`GEMINI_API_KEY` (Settings > Secrets and variables > Actions). Pour changer de modèle, créer
une variable `GEMINI_MODEL` au même endroit (par défaut, le plus récent modèle « flash » stable est choisi automatiquement).

Sur GitHub : onglet **Actions** > **Numéro du jour** > **Run workflow**. Le numéro est
enregistré dans le dossier [`issues/`](issues/).

Le numéro contient 10 à 12 brèves, trois dossiers (géopolitique, économie, tech), une fiche
pays (les 197 pays passent chacun leur tour) et une liste de sujets à surveiller, pour environ
30 minutes de lecture. Les analyses et newsletters sont prises sur 7 jours, le reste sur 24 heures.

## Le site

Adresse : https://marechalantoine03-hub.github.io/newletter/

Le site est reconstruit après chaque numéro : le dernier numéro en page d'accueil, et tous les
anciens dans « Archives ». Réglage à faire une fois : Settings > Pages > Source : **GitHub Actions**.
Pour le voir en local : `python -m newsletter.site` puis ouvrir `_site/index.html`.
