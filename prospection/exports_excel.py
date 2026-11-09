"""Export Excel d'une période : chiffres et graphiques, jamais de nom ni de message.

Les comptages viennent de l'outil. Les taux et les intervalles de Wilson sont de
vraies formules, et chaque formule est écrite avec sa valeur déjà calculée :
le fichier s'affiche complet, même avant « Activer la modification ».
"""

from io import BytesIO

import xlsxwriter

import analyse
import tableau

POLICE = "Arial"
BLEU, VERT, ORANGE = "#2A78D6", "#1BAF7A", "#EB6834"   # couleurs contrôlées pour le daltonisme
GRIS_GRILLE = "#E8E8E4"
FORMAT_TAUX = "0.0%"

# Le z est lu par toutes les formules de Wilson : sa ligne ne doit pas bouger.
LIGNE_Z = 4
CELLULE_Z = f"'Résumé'!$B${LIGNE_Z}"
RESUME = "Résumé"

ENTETES = ("Contacts", "Vraies réponses", "Taux de réponse", "IC 95 % bas", "IC 95 % haut",
           "Automatiques", "À vérifier", "Intéressés", "Taux d'intérêt", "Signés",
           "Sans réponse", "Automatiques ou à vérifier")
# Numéros de colonnes à partir de 0, comme XlsxWriter.
COL_REPONSES, COL_TAUX, COL_SANS_REPONSE, COL_DOUTEUSES, COL_CONCLUSION = 2, 3, 11, 12, 13
ANCRE_GRAPHIQUE = "P2"


# --- Formats -------------------------------------------------------------------
def _formats(fichier):
    def creer(**options):
        return fichier.add_format({"font_name": POLICE, "font_size": 10, **options})
    return {
        "texte": creer(), "gras": creer(bold=True), "titre": creer(bold=True, font_size=14),
        "entete": creer(bold=True, bg_color="#EEF1F4", text_wrap=True, valign="vcenter"),
        "taux": creer(num_format=FORMAT_TAUX), "z": creer(num_format="0.000000"),
        "p": creer(num_format="0.000", align="left"),
        "taux_gauche": creer(num_format=FORMAT_TAUX, align="left"),
        "nombre_gauche": creer(align="left"),
        "long": creer(text_wrap=True, valign="top", align="left"),
    }


# --- Formules et leurs valeurs -------------------------------------------------
def _f_taux(numerateur, total):
    """Formule d'un taux ; cellule vide s'il n'y a aucun contact."""
    return f'=IF({total}=0,"",{numerateur}/{total})'


def _v_taux(numerateur, total):
    """Valeur calculée de _f_taux."""
    return numerateur / total if total else ""


def _f_wilson(reponses, total, borne):
    """Formule de la borne « bas » ou « haut » de l'intervalle de Wilson (voir analyse.py)."""
    z, p = CELLULE_Z, f"({reponses}/{total})"
    centre = f"{p}+{z}^2/(2*{total})"
    marge = f"{z}*SQRT({p}*(1-{p})/{total}+{z}^2/(4*{total}^2))"
    denominateur = f"(1+{z}^2/{total})"
    if borne == "bas":
        calcul = f"MAX(0,({centre}-{marge})/{denominateur})"
    else:
        calcul = f"MIN(1,({centre}+{marge})/{denominateur})"
    return f'=IF({total}=0,"",{calcul})'


def _v_wilson(reponses, total, borne):
    """Valeur calculée de _f_wilson."""
    intervalle = analyse.wilson(reponses, total)
    return "" if intervalle is None else intervalle[0 if borne == "bas" else 1]


# --- Les tableaux --------------------------------------------------------------
def _ecrire_entetes(feuille, f, premiere_colonne, avec_conclusion):
    entetes = (premiere_colonne, *ENTETES) + (("Conclusion",) if avec_conclusion else ())
    for colonne, titre in enumerate(entetes):
        feuille.write_string(0, colonne, titre, f["entete"])
    feuille.freeze_panes(1, 1)


def _ecrire_ligne(feuille, f, indice, ligne, avec_conclusion):
    """Écrit une ligne (`indice` part de 0 ; Excel numérote à partir de 1)."""
    numero = indice + 1
    n, r, i = f"B{numero}", f"C{numero}", f"I{numero}"
    contacts, reponses = ligne["contacts"], ligne["reponses"]
    feuille.write_string(indice, 0, ligne["libelle"], f["texte"])
    for colonne, valeur in ((1, contacts), (2, reponses), (6, ligne["automatiques"]), (7, ligne["a_verifier"]),
                            (8, ligne["interesses"]), (10, ligne["signes"]), (11, ligne["sans_reponse"]),
                            (12, ligne["automatiques"] + ligne["a_verifier"])):
        feuille.write_number(indice, colonne, valeur, f["texte"])
    for colonne, formule, valeur in (
            (3, _f_taux(r, n), _v_taux(reponses, contacts)),
            (4, _f_wilson(r, n, "bas"), _v_wilson(reponses, contacts, "bas")),
            (5, _f_wilson(r, n, "haut"), _v_wilson(reponses, contacts, "haut")),
            (9, _f_taux(i, n), _v_taux(ligne["interesses"], contacts))):
        feuille.write_formula(indice, colonne, formule, f["taux"], valeur)
    if avec_conclusion and contacts < analyse.MIN_CONTACTS_PAR_GROUPE:
        feuille.write_string(indice, COL_CONCLUSION, analyse.TROP_PEU, f["texte"])


def _table(feuille, f, premiere_colonne, lignes, avec_conclusion=True):
    _ecrire_entetes(feuille, f, premiere_colonne, avec_conclusion)
    for indice, ligne in enumerate(lignes, start=1):
        _ecrire_ligne(feuille, f, indice, ligne, avec_conclusion)
    feuille.set_column(0, 0, 16)
    feuille.set_column(1, 12, 12)
    feuille.set_column(COL_CONCLUSION, COL_CONCLUSION, 34)
    feuille.set_row(0, 42)


# --- Les graphiques ------------------------------------------------------------
def _barres(fichier, feuille, titre, titre_axe, derniere, series, empile=False, en_pourcent=False):
    """Graphique en barres. `series` = [(colonne, couleur), …] ; `derniere` à partir de 0."""
    options = {"type": "column", "subtype": "stacked"} if empile else {"type": "column"}
    graphique = fichier.add_chart(options)
    nom = feuille.get_name()
    for colonne, couleur in series:
        graphique.add_series({
            "name": [nom, 0, colonne], "categories": [nom, 1, 0, derniere, 0],
            "values": [nom, 1, colonne, derniere, colonne],
            "fill": {"color": couleur}, "border": {"none": True}, "gap": 60 if empile else 200,
        })
    police = {"name": POLICE, "size": 10, "bold": False}
    axe_y = {"name": titre_axe, "name_font": police, "num_font": police,
             "major_gridlines": {"visible": True, "line": {"color": GRIS_GRILLE, "width": 0.75}}}
    if en_pourcent:
        axe_y.update(num_format="0%", min=0, max=1)
    graphique.set_title({"name": titre, "name_font": {"name": POLICE, "size": 12, "bold": True}})
    graphique.set_x_axis({"num_font": police})
    graphique.set_y_axis(axe_y)
    graphique.set_legend({"position": "top", "font": police} if len(series) > 1 else {"none": True})
    graphique.set_size({"width": 830, "height": 340})
    feuille.insert_chart(ANCRE_GRAPHIQUE, graphique)


# --- Les feuilles --------------------------------------------------------------
def _texte_periode(debut, fin):
    return f"du {debut or 'début'} au {fin or 'dernier contact'}"


def _lignes_resume(total, stats, chiffres, debut, fin):
    """(libellé, valeur, formule ou None, format). La 1re ligne est la ligne 3 d'Excel."""
    n, r, i, s = "$B$5", "$B$6", "$B$12", "$B$14"
    nb, rep, inter, sig = total["contacts"], total["reponses"], total["interesses"], total["signes"]
    p = stats["conclusion_ab"]["p"]
    return [
        ("Période (date du premier message)", _texte_periode(debut, fin), None, "long"),
        ("z pour un intervalle à 95 %", analyse.Z_95, None, "z"),
        ("Contacts", nb, None, "nombre_gauche"),
        ("Vraies réponses", rep, None, "nombre_gauche"),
        ("Taux de vraies réponses", _v_taux(rep, nb), _f_taux(r, n), "taux_gauche"),
        ("IC 95 % (Wilson) : bas", _v_wilson(rep, nb, "bas"), _f_wilson(r, n, "bas"), "taux_gauche"),
        ("IC 95 % (Wilson) : haut", _v_wilson(rep, nb, "haut"), _f_wilson(r, n, "haut"), "taux_gauche"),
        ("Réponses automatiques (hors taux)", total["automatiques"], None, "nombre_gauche"),
        ("Réponses à vérifier (hors taux)", total["a_verifier"], None, "nombre_gauche"),
        ("Intéressés", inter, None, "nombre_gauche"),
        ("Taux d'intérêt", _v_taux(inter, nb), _f_taux(i, n), "taux_gauche"),
        ("Signés", sig, None, "nombre_gauche"),
        ("Taux de signature", _v_taux(sig, nb), _f_taux(s, n), "taux_gauche"),
        ("Comparaison A/B", stats["conclusion_ab"]["texte"], None, "long"),
        ("Test exact de Fisher, valeur p (calculée par l'outil)", "—" if p is None else p, None, "p"),
        ("Minimum de contacts par groupe pour conclure", analyse.MIN_CONTACTS_PAR_GROUPE, None, "nombre_gauche"),
        ("Prospects aux dates estimées", chiffres["nb_dates_estimees"], None, "nombre_gauche"),
        ("Prospects sans date (hors graphique par semaine)", chiffres["nb_sans_date"], None, "nombre_gauche"),
    ]


def _feuille_resume(feuille, f, chiffres, stats, debut, fin):
    feuille.write_string(0, 0, "Prospection : rapport de la période", f["titre"])
    feuille.write_string(1, 0, "Totaux uniquement : aucun nom ni texte de message.", f["texte"])
    lignes = _lignes_resume(chiffres["total"], stats, chiffres, debut, fin)
    for indice, (libelle, valeur, formule, cle_format) in enumerate(lignes, start=LIGNE_Z - 2):
        feuille.write_string(indice, 0, libelle, f["gras"])
        if formule:
            feuille.write_formula(indice, 1, formule, f[cle_format], valeur)
        else:
            feuille.write(indice, 1, valeur, f[cle_format])
    feuille.set_column(0, 0, 50)
    feuille.set_column(1, 1, 70)


def _feuille_semaines(fichier, feuille, f, semaines):
    _table(feuille, f, "Semaine du", semaines, avec_conclusion=False)
    if semaines:
        _barres(fichier, feuille, "Contacts par semaine", "Contacts", len(semaines),
                [(COL_REPONSES, BLEU), (COL_DOUTEUSES, VERT), (COL_SANS_REPONSE, ORANGE)], empile=True)


def _feuille_versions(fichier, feuille, f, chiffres, stats):
    lignes = chiffres["versions"]
    _table(feuille, f, "Version", lignes)
    feuille.write_string(len(lignes) + 2, 0, stats["conclusion_ab"]["texte"], f["gras"])
    if chiffres["nb_version_renseignee"]:
        _barres(fichier, feuille, "Taux de vraies réponses par version", "Taux de réponse", 2,
                [(COL_TAUX, BLEU)], en_pourcent=True)


def _feuille_canaux(fichier, feuille, f, canaux):
    _table(feuille, f, "Canal", canaux)
    if canaux:
        _barres(fichier, feuille, "Taux de vraies réponses par canal", "Taux de réponse", len(canaux),
                [(COL_TAUX, BLEU)], en_pourcent=True)


def classeur(prospects, debut, fin):
    """Contenu du fichier .xlsx pour ces prospects (déjà filtrés sur la période)."""
    chiffres, stats = tableau.construire(prospects), analyse.construire(prospects)
    sortie = BytesIO()
    fichier = xlsxwriter.Workbook(sortie, {"in_memory": True})
    f = _formats(fichier)
    _feuille_resume(fichier.add_worksheet(RESUME), f, chiffres, stats, debut, fin)
    _feuille_semaines(fichier, fichier.add_worksheet("Semaines"), f, chiffres["semaines"])
    _feuille_versions(fichier, fichier.add_worksheet("Versions AB"), f, chiffres, stats)
    _feuille_canaux(fichier, fichier.add_worksheet("Canaux"), f, chiffres["canaux"])
    fichier.close()
    return sortie.getvalue()
