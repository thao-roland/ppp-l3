# prospection

> **Statut : en cours de réalisation, étape 1 sur 6 terminée.**

Petit outil (appli web **en local**) pour suivre ma prospection de sites web auprès de petites entreprises, surtout via Facebook / Messenger, et en sortir de vraies données pour mes rapports de PPP.

Il est fait avec l'aide de **Claude Code**, étape par étape : chaque étape est testée, puis validée par moi avant de passer à la suivante.

## Les 6 étapes

| # | Étape | État |
| --- | --- | --- |
| 1 | Base SQLite + ajout / modification manuelle d'un prospect | ✅ fait |
| 2 | Import de l'export officiel Facebook (« Télécharger vos informations », JSON) | à faire |
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

## Ce que contient un prospect

Code (`P001`, `P002`…), nom d'entreprise, métier, ville, canal, date du 1er message, version du message (A ou B), texte envoyé, réponse (date), intérêt (aucun / curieux / demande de prix), tarif proposé, acompte, statut (contacté / relancé / a répondu / intéressé / signé / perdu), a déjà un site (oui / non / inconnu).

Les **relances** (date + texte) sont dans une table à part : un prospect peut en avoir plusieurs.

J'ai ajouté une case **« dates estimées »** : certaines dates de mon début de prospection sont reconstituées de mémoire, et je dois pouvoir le signaler dans mes rapports.

## Confidentialité

- **Tout reste en local** : le serveur n'écoute que sur `127.0.0.1` (mon ordinateur), rien n'est mis en ligne.
- La base (`data/`), les exports Facebook et tout fichier avec des noms ou des messages sont dans le `.gitignore` du dépôt. Seuls le code, les tests, la doc et les CSV anonymisés sont publiés.
- Les tests n'utilisent que des données inventées.

## Choix techniques (et pourquoi)

**Python.** C'est le langage que je connais le mieux, et c'est celui qui sert pour l'analyse de données (statistiques, Excel) dans les étapes 5 et 6. *Écarté :* JavaScript / Node, qui aurait obligé à utiliser un second langage pour les statistiques.

**Flask.** Un micro-framework web : une application tient en un seul fichier et on comprend tout ce qui se passe. *Écarté :* Django, trop lourd pour un outil à un seul utilisateur (administration, comptes, migrations dont je n'ai pas besoin) ; FastAPI, pensé pour faire des API, alors que je veux surtout des pages HTML.

**SQLite.** La base est un simple fichier, sans serveur à installer, et sait très bien gérer quelques centaines ou milliers de prospects. Python l'intègre déjà. *Écarté :* PostgreSQL / MySQL (un serveur à installer et à gérer pour rien) ; un fichier CSV ou Excel comme base (pas de relations propres prospect → relances, risque d'erreurs de saisie, difficile à interroger).

**SQL écrit à la main avec `sqlite3`.** Les requêtes sont courtes et lisibles, et je comprends ce qui part en base. Toutes les valeurs passent par des paramètres `?` (jamais collées dans le texte de la requête), ce qui empêche les injections SQL. *Écarté :* un ORM comme SQLAlchemy, qui ajoute une couche à apprendre pour un schéma de deux tables.

**Pages HTML avec Jinja (fourni avec Flask) + un peu de CSS, sans JavaScript.** Rapide à faire et rien à installer côté navigateur. Jinja protège les affichages (un nom contenant `<script>` s'affiche tel quel, il ne s'exécute pas). *Écarté :* React ou Vue, qui demandent un outil de compilation et une seconde appli pour un simple formulaire.

**Deux tables (`prospects` et `relances`).** Une relance = une ligne, donc autant de relances que nécessaire et un calcul simple de « sans réponse depuis X jours » à l'étape 3. *Écarté :* mettre les relances dans une colonne de texte du prospect (impossible à compter ou à filtrer proprement).

**Règles de validation dans le code Python (`modeles.py`), pas dans la base.** Les listes de statuts, canaux, etc. sont à un seul endroit : pour en changer une, je modifie une ligne, sans migration de base. *Écarté :* les contraintes `CHECK` de SQLite, qui dupliqueraient les listes.

**Dates au format `AAAA-MM-JJ` (texte).** SQLite n'a pas de vrai type date ; ce format se trie et se compare correctement tel quel, et c'est ce que produit le champ date du navigateur.

**Codes `P001`, `P002`… générés par l'outil.** Le code est l'identifiant visible, sans lien avec le vrai nom : il servira dans les CSV anonymisés (étape 6).

**Montants en euros entiers.** Mes tarifs et acomptes sont des montants ronds ; ça évite les erreurs d'arrondi des nombres à virgule.

**Pas de mot de passe ni de comptes.** L'outil ne sert qu'à moi, sur mon ordinateur. La seule protection ajoutée : un envoi de formulaire venant d'un autre site est refusé (contrôle de l'en-tête `Origin`), pour qu'une page web piégée ne puisse pas écrire dans ma base pendant que l'outil tourne. *Écarté :* un système de connexion, inutile ici.

**Tests avec pytest.** Chaque test utilise une base temporaire jetable ; je vérifie les ajouts, les modifications, les refus de données incorrectes et la sécurité. *Écarté :* `unittest`, plus verbeux.

## Organisation du dossier

```
prospection/
├── app.py            application Flask (pages et routes)
├── db.py             connexion à la base SQLite
├── modeles.py        règles, validation, lecture/écriture des prospects
├── schema.sql        structure de la base
├── templates/        pages HTML
├── static/           CSS
├── tests/            tests pytest
├── donnees/          CSV anonymisés (publiés)
└── data/             base SQLite locale (JAMAIS publiée, dans .gitignore)
```

## Les données publiées : un export CSV anonymisé par période (étape 6)

Les CSV déposés dans [`donnees/`](donnees/) contiendront seulement : code (`P001`…), dates, canal, version du message (A/B), type de réponse, intérêt et statut. **Aucun** nom, nom d'entreprise, e-mail, numéro de téléphone ni texte de message.
