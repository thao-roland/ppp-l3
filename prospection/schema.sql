-- Schéma de la base SQLite de l'outil de prospection.
-- Les listes de valeurs autorisées (statut, intérêt, canal, version) sont
-- vérifiées dans modeles.py : une seule liste à modifier, pas de migration.
-- Les dates sont stockées au format ISO « AAAA-MM-JJ » (texte).

CREATE TABLE IF NOT EXISTS prospects (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    code                  TEXT NOT NULL UNIQUE,      -- P001, P002...
    nom_entreprise        TEXT NOT NULL,
    metier                TEXT,
    ville                 TEXT,
    canal                 TEXT,                      -- Messenger, Instagram...
    date_premier_message  TEXT,
    version_message       TEXT,                      -- 'A' ou 'B'
    texte_envoye          TEXT,
    date_reponse          TEXT,
    interet               TEXT NOT NULL DEFAULT 'aucun',
    tarif_propose         INTEGER,                   -- en euros
    acompte               INTEGER,                   -- en euros
    statut                TEXT NOT NULL DEFAULT 'contacté',
    a_deja_site           INTEGER,                   -- 1 = oui, 0 = non, vide = inconnu
    dates_estimees        INTEGER NOT NULL DEFAULT 0, -- 1 = dates reconstituées de mémoire
    conversation_fb       TEXT,                      -- identifiant de la conversation Facebook importée
    reponse_automatique   TEXT,                      -- 'oui', 'non', 'à vérifier' ; vide = pas de détection
    cree_le              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Une ligne par relance (un prospect peut en avoir plusieurs).
CREATE TABLE IF NOT EXISTS relances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id  INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    date         TEXT NOT NULL,
    texte        TEXT
);

CREATE INDEX IF NOT EXISTS idx_relances_prospect ON relances(prospect_id);
