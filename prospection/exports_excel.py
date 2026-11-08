"""Export Excel d'une période : chiffres et graphiques, jamais de nom ni de message.

Les comptages viennent de l'outil. Les taux et les intervalles de Wilson sont de
vraies formules Excel, pour pouvoir les relire et les vérifier dans le fichier.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Font, PatternFill

import analyse
import tableau

POLICE = "Arial"
BLEU, ORANGE = "2A78D6", "EB6834"       # couleurs contrôlées pour le daltonisme
GRIS_GRILLE = "E8E8E4"
FOND_ENTETE = PatternFill("solid", fgColor="EEF1F4")
FORMAT_TAUX = "0.0%"

LIGNE_Z = 4
CELLULE_Z = f"'Résumé'!$B${LIGNE_Z}"

ENTETES = ("Contacts", "Réponses", "Taux de réponse", "IC 95 % bas", "IC 95 % haut",
           "Intéressés", "Taux d'intérêt", "Signés", "Sans réponse")
COL_REPONSES, COL_TAUX, COL_SANS_REPONSE = 3, 4, 10


# --- Petits outils -------------------------------------------------------------
def _ecrire(feuille, ligne, colonne, valeur, gras=False, taille=10, format_nombre=None):
    cellule = feuille.cell(row=ligne, column=colonne, value=valeur)
    cellule.font = Font(name=POLICE, size=taille, bold=gras)
    if format_nombre:
        cellule.number_format = format_nombre
    return cellule


def _f_taux(numerateur, total):
    """Formule d'un taux ; cellule vide s'il n'y a aucun contact."""
    return f'=IF({total}=0,"",{numerateur}/{total})'


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


def _largeurs(feuille, largeurs):
    for lettre, largeur in largeurs.items():
        feuille.column_dimensions[lettre].width = largeur


# --- Les tableaux --------------------------------------------------------------
def _ecrire_entetes(feuille, premiere_colonne, avec_conclusion):
    entetes = (premiere_colonne, *ENTETES) + (("Conclusion",) if avec_conclusion else ())
    for colonne, titre in enumerate(entetes, start=1):
        cellule = _ecrire(feuille, 1, colonne, titre, gras=True)
        cellule.fill = FOND_ENTETE
        cellule.alignment = Alignment(wrap_text=True, vertical="center")
    feuille.freeze_panes = "B2"


def _ecrire_ligne(feuille, numero, ligne, avec_conclusion):
    n, r, i = f"B{numero}", f"C{numero}", f"G{numero}"
    contenu = (
        (ligne["libelle"], None), (ligne["contacts"], None), (ligne["reponses"], None),
        (_f_taux(r, n), FORMAT_TAUX), (_f_wilson(r, n, "bas"), FORMAT_TAUX),
        (_f_wilson(r, n, "haut"), FORMAT_TAUX), (ligne["interesses"], None),
        (_f_taux(i, n), FORMAT_TAUX), (ligne["signes"], None),
        (ligne["contacts"] - ligne["reponses"], None),
    )
    for colonne, (valeur, format_nombre) in enumerate(contenu, start=1):
        _ecrire(feuille, numero, colonne, valeur, format_nombre=format_nombre)
    if avec_conclusion and ligne["contacts"] < analyse.MIN_CONTACTS_PAR_GROUPE:
        _ecrire(feuille, numero, 11, analyse.TROP_PEU)


def _table(feuille, premiere_colonne, lignes, avec_conclusion=True):
    _ecrire_entetes(feuille, premiere_colonne, avec_conclusion)
    for numero, ligne in enumerate(lignes, start=2):
        _ecrire_ligne(feuille, numero, ligne, avec_conclusion)
    _largeurs(feuille, {"A": 16, **{c: 12 for c in "BCDEFGHIJ"}, "K": 34})


# --- Les graphiques ------------------------------------------------------------
def _aerer(graphique, nb_series):
    """Titre et légende hors du tracé, grille discrète (sinon Excel les superpose)."""
    graphique.title.overlay = False
    graphique.y_axis.title.overlay = False
    graphique.y_axis.majorGridlines.spPr = GraphicalProperties(
        ln=LineProperties(solidFill=GRIS_GRILLE, w=9525))
    if nb_series == 1:
        graphique.legend = None  # une seule série : le titre suffit
    else:
        graphique.legend.position, graphique.legend.overlay = "t", False


def _barres(feuille, titre, titre_axe, derniere_ligne, series, ancre, empile=False, en_pourcent=False):
    """Graphique en barres. `series` = [(colonne, couleur), …]."""
    graphique = BarChart()
    graphique.type, graphique.title, graphique.y_axis.title = "col", titre, titre_axe
    graphique.height, graphique.width = 9, 22
    graphique.gapWidth = 60 if empile else 200
    if empile:
        graphique.grouping, graphique.overlap = "stacked", 100
    for colonne, couleur in series:
        donnees = Reference(feuille, min_col=colonne, min_row=1, max_row=derniere_ligne)
        graphique.add_data(donnees, titles_from_data=True)
        serie = graphique.series[-1]
        serie.graphicalProperties.solidFill = couleur
        serie.graphicalProperties.line.solidFill = couleur
    graphique.set_categories(Reference(feuille, min_col=1, min_row=2, max_row=derniere_ligne))
    graphique.x_axis.delete = graphique.y_axis.delete = False  # sinon les axes disparaissent
    _aerer(graphique, len(series))
    if en_pourcent:
        graphique.y_axis.number_format = "0%"
        graphique.y_axis.scaling.min, graphique.y_axis.scaling.max = 0, 1
    feuille.add_chart(graphique, ancre)


# --- Les feuilles --------------------------------------------------------------
def _texte_periode(debut, fin):
    return f"du {debut or 'début'} au {fin or 'dernier contact'}"


def _lignes_resume(total, stats, chiffres, debut, fin):
    n, r, i, s = "$B$5", "$B$6", "$B$10", "$B$12"
    p = stats["conclusion_ab"]["p"]
    return [
        ("Période (date du premier message)", _texte_periode(debut, fin), None),
        ("z pour un intervalle à 95 %", analyse.Z_95, "0.000000"),
        ("Contacts", total["contacts"], None),
        ("Réponses", total["reponses"], None),
        ("Taux de réponse", _f_taux(r, n), FORMAT_TAUX),
        ("IC 95 % (Wilson) : bas", _f_wilson(r, n, "bas"), FORMAT_TAUX),
        ("IC 95 % (Wilson) : haut", _f_wilson(r, n, "haut"), FORMAT_TAUX),
        ("Intéressés", total["interesses"], None),
        ("Taux d'intérêt", _f_taux(i, n), FORMAT_TAUX),
        ("Signés", total["signes"], None),
        ("Taux de signature", _f_taux(s, n), FORMAT_TAUX),
        ("Comparaison A/B", stats["conclusion_ab"]["texte"], None),
        ("Test exact de Fisher, valeur p (calculée par l'outil)", "—" if p is None else p, "0.000"),
        ("Minimum de contacts par groupe pour conclure", analyse.MIN_CONTACTS_PAR_GROUPE, None),
        ("Prospects aux dates estimées", chiffres["nb_dates_estimees"], None),
        ("Prospects sans date (hors graphique par semaine)", chiffres["nb_sans_date"], None),
    ]


def _feuille_resume(feuille, chiffres, stats, debut, fin):
    _ecrire(feuille, 1, 1, "Prospection : rapport de la période", gras=True, taille=14)
    _ecrire(feuille, 2, 1, "Totaux uniquement : aucun nom ni texte de message. "
                           "Si des taux restent vides, cliquer sur « Activer la modification ».")
    for numero, (libelle, valeur, format_nombre) in enumerate(
            _lignes_resume(chiffres["total"], stats, chiffres, debut, fin), start=LIGNE_Z - 1):
        _ecrire(feuille, numero, 1, libelle, gras=True)
        cellule = _ecrire(feuille, numero, 2, valeur, format_nombre=format_nombre)
        cellule.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
    _largeurs(feuille, {"A": 50, "B": 70})


def _feuille_semaines(feuille, semaines):
    _table(feuille, "Semaine du", semaines, avec_conclusion=False)
    if semaines:
        _barres(feuille, "Contacts par semaine", "Contacts", len(semaines) + 1,
                [(COL_REPONSES, BLEU), (COL_SANS_REPONSE, ORANGE)], "M2", empile=True)


def _feuille_versions(feuille, chiffres, stats):
    lignes = chiffres["versions"]
    _table(feuille, "Version", lignes)
    _ecrire(feuille, len(lignes) + 3, 1, stats["conclusion_ab"]["texte"], gras=True)
    if chiffres["nb_version_renseignee"]:
        _barres(feuille, "Taux de réponse par version", "Taux de réponse", 3,
                [(COL_TAUX, BLEU)], "M2", en_pourcent=True)


def _feuille_canaux(feuille, canaux):
    _table(feuille, "Canal", canaux)
    if canaux:
        _barres(feuille, "Taux de réponse par canal", "Taux de réponse", len(canaux) + 1,
                [(COL_TAUX, BLEU)], "M2", en_pourcent=True)


def classeur(prospects, debut, fin):
    """Contenu du fichier .xlsx pour ces prospects (déjà filtrés sur la période)."""
    chiffres, stats = tableau.construire(prospects), analyse.construire(prospects)
    fichier = Workbook()
    resume = fichier.active
    resume.title = "Résumé"
    _feuille_resume(resume, chiffres, stats, debut, fin)
    _feuille_semaines(fichier.create_sheet("Semaines"), chiffres["semaines"])
    _feuille_versions(fichier.create_sheet("Versions AB"), chiffres, stats)
    _feuille_canaux(fichier.create_sheet("Canaux"), chiffres["canaux"])
    sortie = BytesIO()
    fichier.save(sortie)
    return sortie.getvalue()
