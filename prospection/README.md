# prospection

> **Statut : Pas encore réalisé. Mise en place prévue pour le rapport de décembre 2026. Aucune donnée pour l'instant.**

Ce dossier accueillera l'outil de suivi de ma prospection freelance et, plus tard, les données anonymisées qui en sortiront.

## L'outil prévu

Une petite application web pour suivre ma prospection :

- **prospects** : les personnes ou entreprises que je contacte ;
- **relances** : quand et comment je les recontacte ;
- **réponses** : ce qu'elles me répondent ;
- **score de priorité de 0 à 100** : pour savoir qui contacter en premier.

## Comment il sera fait et utilisé

- Il sera réalisé avec l'aide de **Claude Code**.
- Il tournera **en local, sur mon ordinateur**. Les données de mes prospects (noms, entreprises, coordonnées) restent chez moi et ne sont jamais publiées dans ce dépôt.

## Les données publiées : un export CSV anonymisé par mois

Une fois par mois, j'exporterai les données de la période dans un fichier CSV **anonymisé**, que je déposerai dans [`donnees/`](donnees/).

Ce fichier contiendra seulement :

| Colonne | Contenu |
| --- | --- |
| identifiant | `P001`, `P002`… (sans lien visible avec la vraie personne) |
| date | date de l'action |
| canal | moyen utilisé pour le contact |
| type de réponse | la nature de la réponse reçue |
| version du message | A ou B, pour comparer deux façons d'écrire |
| taille d'entreprise | catégorie de taille |
| source | d'où vient le contact |
| budget | une tranche, jamais un montant exact |

Ce fichier ne contiendra **aucun** nom, nom d'entreprise, e-mail, numéro de téléphone ni note libre.
