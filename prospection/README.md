# prospection

> **Statut : en cours de réalisation, étapes 1 et 2 sur 6 terminées.**

Petit outil (appli web **en local**) pour suivre ma prospection de sites web auprès de petites entreprises, surtout via Facebook / Messenger, et en sortir de vraies données pour mes rapports de PPP.

Il est fait avec l'aide de **Claude Code**, étape par étape : chaque étape est testée, puis validée par moi avant de passer à la suivante.

## Les 6 étapes

| # | Étape | État |
| --- | --- | --- |
| 1 | Base SQLite + ajout / modification manuelle d'un prospect | ✅ fait |
| 2 | Import de l'export officiel Facebook (« Télécharger vos informations », JSON) | ✅ fait |
| 3 | Scoring sur 100 + liste des relances à faire | à faire |
| 4 | Tableau de bord (contacts, taux de réponse, A/B, canaux, évolution par semaine) | à faire |
| 5 | Analyse statistique (intervalle de Wilson, test de Fisher) | à faire |
| 6 | Export CSV anonymisé + export Excel avec graphiques | à faire |

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

Pas de scraping : on lit seulement les fichiers de l'export, sur mon ordinateur.

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
├── schema.sql        structure de la base
├── templates/        pages HTML
├── static/           CSS
├── tests/            tests pytest
│   └── faux_export_facebook/   FAUX export (noms et messages inventés)
└── donnees/          CSV anonymisés (publiés)
```

## Les données publiées : un export CSV anonymisé par période (étape 6)

Les CSV déposés dans [`donnees/`](donnees/) contiendront seulement : code (`P001`…), dates, canal, version du message (A/B), type de réponse, intérêt et statut. **Aucun** nom, nom d'entreprise, e-mail, numéro de téléphone ni texte de message.
