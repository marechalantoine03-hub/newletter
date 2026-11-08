# Newsletter internationale quotidienne

Programme qui fabrique chaque matin une newsletter d'actualité internationale
(géopolitique, économie, tech, fiche pays) d'environ 30 minutes de lecture,
la publie sur un site et l'envoie par mail. Gratuit, et indépendant de tout service payant.

## Où en est le projet

| Phase | Contenu | État |
| --- | --- | --- |
| 1 | Collecte des sources (flux RSS) | en cours |
| 2 | Rédaction du numéro par une IA gratuite | à faire |
| 3 | Site (GitHub Pages) et envoi par mail | à faire |
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
