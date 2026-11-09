# prospection

> **Statut : les 6 étapes et l'amélioration de l'étape 7 sont réalisées.**

Petit outil (appli web **en local**) pour suivre ma prospection de sites web auprès de petites entreprises, surtout via Facebook / Messenger, et en sortir de vraies données pour mes rapports de PPP.

Il est fait avec l'aide de **Claude Code**, étape par étape : chaque étape est testée, puis validée par moi avant de passer à la suivante.

## Les 6 étapes

| # | Étape | État |
| --- | --- | --- |
| 1 | Base SQLite + ajout / modification manuelle d'un prospect | ✅ fait |
| 2 | Import de l'export officiel Facebook (« Télécharger vos informations », JSON) | ✅ fait |
| 3 | Scoring sur 100 + liste des relances à faire | ✅ fait |
| 4 | Tableau de bord (contacts, taux de réponse, A/B, canaux, évolution par semaine) | ✅ fait |
| 5 | Analyse statistique (intervalle de Wilson, test de Fisher) | ✅ fait |
| 6 | Export CSV anonymisé + export Excel avec graphiques | ✅ fait |
| 7 | Réponses automatiques, écran « Qualifier », exports enrichis | ✅ fait |

## Lancer l'outil

```bash
cd prospection
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # puis ouvrir http://127.0.0.1:5000
```

Lancer les tests : `python -m pytest` (dans le dossier `prospection/`).

## Où sont les données ? (hors du dépôt)

**Règle : le dépôt ne contient que le code, les tests (avec de FAUSSES données), la documentation et les CSV anonymisés. Toutes les données réelles sont dans un dossier séparé, à côté du dépôt.**

```
.../
├── ppp-l3/               le dépôt (public sur GitHub)
└── crm-donnees/          mes données réelles (JAMAIS sur GitHub)
    ├── crm.db            la base SQLite
    ├── exports_facebook/ les exports Facebook (dézippés)
    └── exports_prives/   les exports qui contiennent des noms
```

- Le dossier est lu dans la variable d'environnement **`CRM_DONNEES`**. Par défaut : `../crm-donnees` (à côté du dépôt). Un chemin relatif part de la racine du dépôt. Aucun chemin personnel n'est écrit dans le code.
- Au premier lancement, la base de l'étape 1 (`prospection/data/prospection.db`) est **déplacée** automatiquement vers `crm-donnees/crm.db`. Une base déjà présente dans `crm-donnees/` n'est jamais écrasée.
- Les tests n'utilisent **jamais** ce dossier : ils travaillent dans un dossier temporaire jeté après chaque test.

**Pourquoi un dossier séparé plutôt qu'un simple `.gitignore` ?** Mon tuteur relit tout l'historique du dépôt public, et un commit qui contient une donnée personnelle reste visible même s'il est supprimé ensuite. Avec un `.gitignore` seul, une erreur suffit (`git add -f`, un fichier renommé, un nouveau type de fichier oublié). Avec un dossier hors du dépôt, git ne voit tout simplement pas ces fichiers. Plusieurs protections s'ajoutent :

1. **Dossier hors dépôt** : l'outil refuse de démarrer si `CRM_DONNEES` pointe à l'intérieur du dépôt.
2. **`.gitignore`** : bases (`*.db`), exports, `.env`, clés et zip sont ignorés, au cas où un fichier serait copié dans le dépôt par erreur.
3. **Un test automatique** (`tests/test_depot_propre.py`) examine tous les fichiers qui seraient commités et échoue s'il trouve une base, un export Facebook, un fichier `.env`, une clé ou un mot de passe en clair.
4. **Une vérification manuelle avant chaque commit** (`git status` puis `git diff --cached`).

*Alternatives écartées :* garder la base dans `prospection/data/` avec seulement le `.gitignore` (une seule protection) ; chiffrer la base (complique tout pour un outil qui tourne déjà en local) ; un dépôt privé (le tuteur doit pouvoir lire le dépôt).

## Importer un export Facebook (étape 2)

1. Sur Facebook : *Paramètres → Vos informations → Télécharger vos informations*, format **JSON**, type de données **Messages**.
2. Dézipper l'export dans `crm-donnees/exports_facebook/` (un dossier par export).
3. Dans l'outil, cliquer sur **« Importer un export Facebook »**, choisir l'export, puis **Importer**.

Pas de scraping : on lit seulement les fichiers de l'export, sur mon ordinateur. On peut aussi y déposer seulement le dossier `messages` de l'export (avec `inbox/` dedans) : il est reconnu.

**En ligne de commande**, avec des résultats qui ne montrent que des nombres (jamais de noms ni de messages) :

```bash
python importer_cli.py --simuler   # compte tout, sans rien enregistrer
python importer_cli.py             # importe pour de bon
```

Options : `--export NOM` (si plusieurs exports sont dans `exports_facebook/`) et `--mon-nom "Prénom Nom"` (si mon nom n'est pas deviné).

**Règles de l'import** (une conversation entre deux personnes = un prospect) :

| Donnée | Comment elle est calculée |
| --- | --- |
| Code | `P00X` automatique, à la suite des codes existants |
| Nom | le nom de l'autre personne dans la conversation |
| Date du 1er message | mon premier message dans la conversation |
| Texte envoyé | le texte de ce premier message |
| Réponse (date) | le premier message de l'autre **après** mon premier message |
| Relances | mes messages suivants restés sans réponse (avant la réponse de l'autre) |
| Statut | `a répondu` s'il y a une réponse, sinon `relancé` s'il y a des relances, sinon `contacté` |
| Canal | Messenger |
| Dates « estimées » | non : ces dates viennent de Facebook, elles sont exactes |

- Une conversation où **je n'ai écrit aucun message**, ou une **conversation de groupe**, est ignorée.
- **Jamais deux fois la même conversation** : l'identifiant Facebook de la conversation est enregistré et la base refuse les doublons (index unique). Réimporter un export donne « déjà importées ».
- L'import est **tout ou rien** : en cas d'erreur, rien n'est enregistré.
- Un fichier abîmé ne bloque pas le reste : la conversation est comptée comme « illisible ».
- Les dates sont calculées à l'**heure de Paris**.
- Mon nom est **deviné** (c'est le nom présent dans presque toutes les conversations) ; on peut aussi le taper dans le formulaire.
- Les prospects importés n'ont ni version de message (A/B), ni métier, ni ville, ni intérêt : à compléter à la main.
- Réglage possible dans `facebook.py` : `DELAI_MIN_RELANCE_HEURES` (0 par défaut : tous mes messages sans réponse comptent comme relances ; mettre 12 pour ignorer les messages envoyés d'affilée le même jour).

Le rapport affiché après l'import ne contient que des nombres et des codes `P00X`, jamais de noms ni de messages.

## Score de priorité et relances à faire (étape 3)

La page d'accueil affiche un **score sur 100** et classe les prospects du plus prioritaire au moins prioritaire. La page **« Relances à faire »** donne la liste de ceux à recontacter. Tous les réglages sont dans [`scoring.toml`](scoring.toml) ; un changement s'applique à la page suivante, sans relancer l'outil.

| Critère | Points |
| --- | --- |
| A répondu | +30 |
| Intérêt : aucun / curieux / demande de prix | 0 / +20 / +40 |
| Pas de site / inconnu / a déjà un site | +20 / +10 / 0 |
| Dernier échange il y a moins de 14 jours | +10 |
| Chaque relance restée sans réponse | −5 |

- Le score reste entre 0 et 100. Un prospect **signé ou perdu** n'a pas de score (« — ») et n'est jamais à relancer.
- Une relance est « sans réponse » s'il n'y a aucune réponse, ou si elle est **postérieure** à la réponse. Une relance du même jour que la réponse compte comme ayant reçu une réponse, car on ne connaît que les dates, pas les heures.
- **À relancer** : mon dernier message date d'au moins **7 jours**, personne n'y a répondu, et il y a moins de **2 relances** sans réponse. La liste va du meilleur score au moins bon, puis de l'attente la plus longue à la plus courte.

**Limites à garder en tête :**

- L'import n'enregistre que la **première** réponse. Le « dernier échange » ne voit donc pas la suite d'une conversation.
- Un prospect importé n'a pas d'intérêt renseigné, et son site est « inconnu ». Tant que je ne les complète pas, le score ne distingue presque que « a répondu » ou non, et la date.
- Avec `DELAI_MIN_RELANCE_HEURES = 0` (import), plusieurs messages envoyés d'affilée comptent comme plusieurs relances.

## Tableau de bord (étape 4)

La page **« Tableau de bord »** n'affiche que des totaux : aucun nom ni texte de message.

| Indicateur | Définition |
| --- | --- |
| Contacts | tous les prospects de la base |
| Vraies réponses | une date de réponse ou un statut qui en suppose une, **sauf** si la réponse est marquée automatique ou à vérifier. Un prospect intéressé ou signé compte toujours. |
| Automatiques / À vérifier | affichées à côté, hors du taux de réponse (voir « Réponses automatiques ») |
| Intéressés | intérêt « curieux » ou « demande de prix », ou statut intéressé / signé |
| Signés | statut « signé » |

- Tous les taux sont calculés **sur le nombre de contacts**. Sans contact dans un groupe, le taux affiche « — », pas « 0 % ».
- **Par semaine** (du lundi au dimanche), une réponse est rattachée à la semaine de **mon premier message**, pas à celle où elle est arrivée. On compare ainsi les contacts de chaque semaine. Les dernières semaines paraissent plus basses, car les prospects ont eu moins de temps pour répondre.
- Les semaines sans contact restent visibles, pour ne pas donner l'impression d'une activité continue.
- La comparaison A/B ne prouve rien à elle seule : le test est sur la page « Analyse » (étape 5).

## Analyse statistique (étape 5)

La page **« Analyse »** n'affiche que des totaux. Elle utilise les mêmes définitions de « réponse » que le tableau de bord : Wilson et Fisher portent sur les **vraies réponses**.

- **Intervalle de Wilson à 95 %** : la fourchette plausible du vrai taux de réponse, au global, par version et par canal.
- **Test exact de Fisher** (bilatéral) : compare les réponses de la version A et de la version B. Plus la valeur *p* est petite, moins l'écart s'explique par le hasard.

| Situation | Ce qui s'affiche |
| --- | --- |
| Moins de **30 contacts** dans A ou dans B | « Trop peu de données pour conclure » |
| 30 contacts ou plus, *p* < 0,05 | la version qui obtient plus de réponses, écart significatif |
| 30 contacts ou plus, *p* ≥ 0,05 | pas de différence démontrée (ce qui ne prouve pas que les versions se valent) |

Les seuils sont en haut de `analyse.py` (`MIN_CONTACTS_PAR_GROUPE`, `SEUIL_P`). Le seuil de 30 est une règle de prudence que j'ai choisie : ce n'est pas une loi statistique. Il s'applique même si l'écart paraît énorme, pour éviter de conclure sur quelques messages. La valeur *p* reste affichée pour la transparence.

**Limites à garder en tête :**

- Ces calculs supposent des contacts comparables. Si A et B n'ont pas été envoyées aux mêmes périodes ou aux mêmes métiers, un écart peut venir d'autre chose que du message.
- Une vraie réponse peut être un refus poli. Les réponses à vérifier non corrigées sont hors du taux, qui peut donc être un peu sous-estimé.
- Sans version renseignée dans les fiches, la comparaison A/B reste vide.

## Exports (étape 6)

La page **« Exports »** télécharge deux fichiers pour une période choisie, selon la date du **premier message**. Sans période, tout est exporté ; avec une période, un prospect sans date est écarté. L'outil n'écrit rien dans le dépôt : c'est moi qui dépose le CSV dans `donnees/`, après l'avoir relu.

**CSV anonymisé** : une ligne par prospect, trié par date.

| Colonne | Contenu |
| --- | --- |
| `code` | `P001`, `P002`… |
| `date_premier_message`, `date_reponse` | dates au format AAAA-MM-JJ |
| `dates_estimees` | `oui` si la date est reconstituée de mémoire |
| `canal`, `version_message`, `interet`, `statut` | comme dans la fiche |
| `type_reponse` | `aucune`, `automatique`, `à vérifier`, `réponse`, `intéressé` ou `signé` (même définition que le tableau de bord) |
| `reponse_automatique` | `oui`, `non`, `à vérifier`, ou vide si aucune détection |
| `nb_relances` | nombre de relances (pas leurs dates) |
| `a_deja_site` | `oui`, `non` ou `inconnu` |

Aucun nom, ville, métier, tarif, identifiant de conversation ni texte de message.

**Excel** : des totaux et des graphiques seulement (feuilles Résumé, Semaines, Versions AB, Canaux), aucune ligne par prospect. Il reste hors du dépôt. Chaque formule est écrite avec sa valeur déjà calculée : tout s'affiche, même en mode protégé.

## Réponses automatiques (étape 7)

**Pourquoi.** Beaucoup de Pages Facebook envoient un message automatique dès qu'on leur écrit. Sans tri, chaque message automatique compte comme une réponse et gonfle le taux de réponse : mes rapports diraient que des entreprises m'ont répondu alors que personne n'a lu mon message.

**Comment.** À l'import, chaque première réponse reçoit deux signaux possibles :

1. elle arrive **moins de 2 minutes** après mon dernier message ;
2. son texte contient une **formule type** : « merci pour votre message », « nous vous répondrons », « notre équipe », « réponse automatique », « horaires » (sans tenir compte des accents ni des majuscules).

| Signaux | `reponse_automatique` | Dans le taux de réponse ? |
| --- | --- | --- |
| Aucun | `non` | oui |
| Un seul | `à vérifier` | non, affichée à côté |
| Les deux | `oui` | non, affichée à côté |

- Si la première réponse est suspecte mais qu'un **message suivant** de l'autre personne n'a aucun signal, quelqu'un a écrit à la main : le résultat est `non`.
- Un prospect marqué **intéressé ou signé** compte toujours comme vraie réponse.
- Le texte de la réponse est lu pendant l'import pour chercher les formules, puis oublié : il n'est **jamais enregistré ni affiché**.
- Réimporter un export complète les fiches sans détection, et ne remplace **jamais** une valeur déjà présente, donc jamais une correction à la main.
- Les réglages sont en haut de `facebook.py` : `DELAI_REPONSE_AUTO_SECONDES` et `FORMULES_AUTO`.

**Limites :**

- **Faux positifs** : une personne devant son téléphone peut répondre en moins de 2 minutes, ou parler d'« horaires » naturellement. C'est pour ça qu'un seul signal donne `à vérifier`, et pas `oui`.
- **Faux négatifs** : une réponse automatique programmée plus tard, ou formulée autrement, passe pour une vraie réponse.
- **Les seuils sont des choix** : ni les 2 minutes ni la liste de formules n'ont été mesurés sur un échantillon relu à la main. Le résultat est une estimation.
- Tant que les réponses `à vérifier` ne sont pas corrigées, elles sont hors du taux, qui peut être sous-estimé.
- Le score et la liste des relances n'utilisent pas cette détection : ils voient toujours la date de réponse.

## Écran « Qualifier » (étape 7)

L'écran **« Qualifier »** liste les prospects qui ont répondu, les réponses à vérifier en premier. Chaque clic enregistre un seul champ, sans recharger la page : réponse automatique, intérêt, version, signé. Le tarif et l'acompte s'enregistrent en quittant la case. Un second clic sur une version ou sur « Signé » annule ; retirer « Signé » remet le statut à « a répondu ».

## Ce que contient un prospect

Code (`P001`, `P002`…), nom d'entreprise, métier, ville, canal, date du 1er message, version du message (A ou B), texte envoyé, réponse (date), intérêt (aucun / curieux / demande de prix), tarif proposé, acompte, statut (contacté / relancé / a répondu / intéressé / signé / perdu), a déjà un site (oui / non / inconnu).

Les **relances** (date + texte) sont dans une table à part : un prospect peut en avoir plusieurs.

J'ai ajouté une case **« dates estimées »** : certaines dates de mon début de prospection sont reconstituées de mémoire, et je dois pouvoir le signaler dans mes rapports.

## Choix techniques (et pourquoi)

**Python.** C'est le langage que je connais le mieux, et c'est celui qui sert pour l'analyse de données (statistiques, Excel) dans les étapes 5 et 6. *Écarté :* JavaScript / Node, qui aurait obligé à utiliser un second langage pour les statistiques.

**Flask.** Un micro-framework web : une application tient en quelques fichiers et on comprend tout ce qui se passe. *Écarté :* Django, trop lourd pour un outil à un seul utilisateur (administration, comptes, migrations dont je n'ai pas besoin) ; FastAPI, pensé pour faire des API, alors que je veux surtout des pages HTML.

**SQLite.** La base est un simple fichier, sans serveur à installer, et sait très bien gérer quelques centaines ou milliers de prospects. Python l'intègre déjà. *Écarté :* PostgreSQL / MySQL (un serveur à installer et à gérer pour rien) ; un fichier CSV ou Excel comme base (pas de relations propres prospect → relances, risque d'erreurs de saisie, difficile à interroger).

**SQL écrit à la main avec `sqlite3`.** Les requêtes sont courtes et lisibles, et je comprends ce qui part en base. Toutes les valeurs passent par des paramètres `?` (jamais collées dans le texte de la requête), ce qui empêche les injections SQL. *Écarté :* un ORM comme SQLAlchemy, qui ajoute une couche à apprendre pour un schéma de deux tables.

**Pages HTML avec Jinja (fourni avec Flask) + un peu de CSS, sans JavaScript.** Rapide à faire et rien à installer côté navigateur. Jinja protège les affichages (un nom contenant `<script>` s'affiche tel quel, il ne s'exécute pas). *Écarté :* React ou Vue, qui demandent un outil de compilation et une seconde appli pour un simple formulaire.

**Deux tables (`prospects` et `relances`).** Une relance = une ligne, donc autant de relances que nécessaire et un calcul simple de « sans réponse depuis X jours » à l'étape 3. *Écarté :* mettre les relances dans une colonne de texte du prospect (impossible à compter ou à filtrer proprement).

**Règles de validation dans le code Python (`modeles.py`), pas dans la base.** Les listes de statuts, canaux, etc. sont à un seul endroit : pour en changer une, je modifie une ligne, sans migration de base. *Écarté :* les contraintes `CHECK` de SQLite, qui dupliqueraient les listes.

**Dates au format `AAAA-MM-JJ` (texte).** SQLite n'a pas de vrai type date ; ce format se trie et se compare correctement tel quel, et c'est ce que produit le champ date du navigateur.

**Codes `P001`, `P002`… générés par l'outil.** Le code est l'identifiant visible, sans lien avec le vrai nom : il servira dans les CSV anonymisés (étape 6).

**Montants en euros entiers.** Mes tarifs et acomptes sont des montants ronds ; ça évite les erreurs d'arrondi des nombres à virgule.

**Pas de mot de passe ni de comptes.** L'outil ne sert qu'à moi, sur mon ordinateur, et le serveur n'écoute que sur `127.0.0.1`. La seule protection ajoutée : un envoi de formulaire venant d'un autre site est refusé (contrôle de l'en-tête `Origin`), pour qu'une page web piégée ne puisse pas écrire dans ma base pendant que l'outil tourne. *Écarté :* un système de connexion, inutile ici.

**Import : lecture d'un dossier dézippé, pas de téléversement.** L'export Facebook peut peser plusieurs Go (photos, vidéos). Plutôt que de l'envoyer par le navigateur, je le dézippe dans `crm-donnees/exports_facebook/` et l'outil le lit sur place. Le formulaire n'accepte que les noms de dossiers présents dans cette liste : impossible de viser un autre dossier de l'ordinateur. *Écarté :* le téléversement de zip (lourd, et il faut décompresser en sécurité).

**Import : la bibliothèque standard (`json`, `zoneinfo`), rien de plus.** Le JSON de Facebook est simple ; pas besoin de pandas. *Écarté :* pandas, une grosse dépendance pour lire quelques fichiers.

**Encodage cassé de Facebook.** Facebook écrit les accents en UTF-8 mais mal déclaré : « é » devient « Ã© ». L'outil répare chaque texte en le relisant correctement (`texte.encode("latin-1").decode("utf-8")`) et laisse tel quel un texte déjà correct. *Écarté :* demander à Facebook un autre format (le HTML a le même problème et est plus dur à lire).

**Doublons : un identifiant de conversation + index unique.** La partie numérique du nom de dossier de la conversation est enregistrée dans la base, qui refuse d'en avoir deux identiques. Même si le code de l'import avait un défaut, la base empêcherait le doublon. *Écarté :* comparer les noms ou les dates (deux entreprises peuvent avoir le même nom, et un nom peut changer).

**Règles du score dans un fichier TOML (`scoring.toml`).** Python sait le lire sans rien installer (`tomllib`), et on peut y écrire des commentaires pour expliquer chaque réglage. *Écarté :* JSON (pas de commentaires) ; YAML (une dépendance en plus) ; des constantes dans le code (il faudrait modifier le programme pour changer une règle).

**Le maximum des points est contrôlé.** Si les points modifiés ne totalisent plus 100 au mieux, l'outil affiche un message clair au lieu d'un faux « score sur 100 ». *Écarté :* ramener tous les scores à 100 par un calcul, qui rendrait les points du fichier impossibles à relire.

**Score calculé à l'affichage, pas enregistré.** Il dépend de la date du jour (échange récent) et des règles : un score enregistré serait vite périmé. Pour quelques centaines de prospects, le calcul est immédiat. *Écarté :* une colonne `score` en base, qu'il faudrait recalculer chaque jour et après chaque changement de règle.

**Graphique dessiné en SVG par le serveur, sans JavaScript.** Python calcule la position des barres et la page les dessine ; l'infobulle au survol est celle du navigateur (`<title>`). Rien à télécharger et l'outil fonctionne sans Internet. *Écarté :* Chart.js ou Plotly (une bibliothèque de plus, pour un seul graphique) ; matplotlib (une image fixe, sans survol, et une grosse dépendance).

**Barres empilées « ont répondu / sans réponse ».** Une seule échelle montre à la fois le volume de contacts et la part de réponses. *Écarté :* une courbe de taux sur un second axe, qui se lit mal et peut faire croire à un lien entre les deux courbes. Le détail chiffré reste disponible dans un tableau sous le graphique.

**Une seule définition de « réponse » et d'« intérêt » (`tableau.py`).** Une fiche complétée à la main peut être « signée » sans date de réponse : elle compte quand même comme réponse. Tous les chiffres restent ainsi cohérents entre eux (jamais plus de signés que de réponses). *Écarté :* compter seulement la colonne `date_reponse`, qui oublierait ces fiches.

**Intervalle de Wilson.** Il reste correct avec peu de contacts ou avec un taux proche de 0 ou de 100 %, et ne sort jamais de 0–100 %. *Écarté :* l'intervalle classique « taux ± 1,96 × erreur type » (Wald), qui donne par exemple une marge nulle pour 0 réponse sur 10.

**Test exact de Fisher.** Il calcule une probabilité exacte, sans hypothèse sur la taille des groupes. *Écarté :* le test du khi-deux, qui est une approximation et devient fragile avec de petits effectifs.

**Calculs écrits dans `analyse.py`, avec la bibliothèque standard.** Les deux formules tiennent en quelques lignes, se relisent, et les tests les comparent à des valeurs de référence. *Écarté :* SciPy, une grosse dépendance pour deux calculs.

**CSV construit à partir d'une liste fermée de colonnes.** Une colonne non listée dans `COLONNES_CSV` ne peut pas sortir, même si la base gagne un nouveau champ sensible. *Écarté :* exporter toute la table en retirant les colonnes sensibles, où un oubli suffirait à publier un nom.

**CSV à virgules, en UTF-8.** C'est le format standard, et GitHub l'affiche directement comme un tableau pour mon tuteur. *Écarté :* le point-virgule, plus pratique dans Excel en français, mais moins bien lu ailleurs (et l'export Excel existe pour ça).

**Fichiers téléchargés, pas écrits dans le dépôt.** Un export ne peut pas se retrouver dans `git status` sans geste de ma part. Un test vérifie en plus qu'aucun Excel n'est sous `prospection/` et qu'un CSV n'y est accepté que dans `donnees/`, avec exactement les bonnes colonnes. *Écarté :* une écriture automatique dans `donnees/`, qui publierait sans relecture.

**Excel avec `XlsxWriter`.** C'est le seul des deux outils Python courants à écrire dans une même cellule une formule **et** sa valeur calculée : le fichier s'affiche complet dès l'ouverture, même en mode protégé. `openpyxl` reste utilisé dans les tests pour relire le fichier. *Écarté :* `openpyxl` seul (utilisé à l'étape 6 : sans valeurs calculées, les taux restaient vides avant « Activer la modification ») ; des images matplotlib collées dans la feuille (non modifiables).

**Taux et intervalles en formules Excel.** On peut cliquer sur une cellule et vérifier le calcul. Les comptages et la valeur *p* de Fisher sont écrits par l'outil : Excel n'a pas de fonction simple pour ce test. *Écarté :* écrire tous les résultats en valeurs figées, impossibles à relire dans le fichier.

**Détection à l'import, avec trois niveaux.** L'heure exacte et le texte de la réponse ne sont connus qu'à ce moment-là, et je ne veux stocker ni l'un ni l'autre. Le niveau `à vérifier` évite de décider seul quand il n'y a qu'un indice. *Écarté :* un simple oui / non (trop de vraies réponses rapides seraient retirées sans contrôle) ; stocker le texte des réponses pour les relire (donnée personnelle en plus, sans nécessité).

**Un peu de JavaScript, seulement pour Qualifier.** Enregistrer un clic sans recharger la page ne peut pas se faire en HTML seul. Le fichier `static/qualifier.js` est petit, sans bibliothèque ni compilation. Le serveur n'accepte que du JSON, sur une liste fermée de champs, et refuse les requêtes venant d'un autre site. *Écarté :* htmx ou React (une dépendance pour un seul écran) ; un formulaire par ligne (la page se recharge à chaque clic et on perd sa place dans la liste).

**Tests avec pytest.** Chaque test

**Tests avec pytest.** Chaque test utilise une base temporaire jetable ; je vérifie les ajouts, les modifications, les refus de données incorrectes, la sécurité et l'import. *Écarté :* `unittest`, plus verbeux.

## Organisation du dossier

```
prospection/
├── app.py            application Flask (pages et routes)
├── db.py             dossier de données (hors dépôt) et connexion SQLite
├── modeles.py        règles, validation, lecture/écriture des prospects
├── facebook.py       lecture de l'export Facebook et règles de transformation
├── importation.py    enregistrement de l'import dans la base
├── pages_import.py   page « Importer un export Facebook »
├── importer_cli.py   import en ligne de commande (nombres seulement)
├── scoring.py        calcul du score et liste des relances à faire
├── scoring.toml      règles du score et délais (modifiable)
├── tableau.py        chiffres du tableau de bord (totaux seulement)
├── analyse.py        statistiques (intervalle de Wilson, test de Fisher)
├── pages_tableau.py  pages « Tableau de bord » et « Analyse »
├── exports.py        période et CSV anonymisé
├── exports_excel.py  fichier Excel avec graphiques
├── pages_exports.py  page « Exports » (téléchargements)
├── pages_qualifier.py  écran « Qualifier » (un clic = un champ)
├── schema.sql        structure de la base
├── templates/        pages HTML
├── static/           CSS
├── tests/            tests pytest
│   └── faux_export_facebook/   FAUX export (noms et messages inventés)
└── donnees/          CSV anonymisés (publiés)
```

## Les données publiées : un export CSV anonymisé par période (étape 6)

Les CSV déposés dans [`donnees/`](donnees/) contiennent seulement les colonnes décrites dans « Exports (étape 6) ». **Aucun** nom, nom d'entreprise, e-mail, numéro de téléphone ni texte de message.
