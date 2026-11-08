"""Application locale d'extraction de fiches de paie PDF."""
import io
import json
import csv
import tempfile
from pathlib import Path

import streamlit as st
from pypdf import PdfReader
from extraction_fiche_paie import extraire_donnees

st.set_page_config(page_title="PaieScan · Analyse de fiches", page_icon="📄", layout="wide")
st.markdown("""<style>
.block-container {max-width: 1250px; padding-top: 2rem;}
[data-testid="stMetric"] {border: 1px solid #e5e7eb; border-radius: 14px; padding: 15px;}
h1 {letter-spacing: -1px;}
</style>""", unsafe_allow_html=True)

COLONNES = {
    "fichier": "Document",
    "document.periode": "Période",
    "document.etabli_le": "Établi le",
    "employeur.entreprise": "Employeur",
    "employe.nom": "Employé",
    "employe.statut": "Statut",
    "employe.fonction": "Fonction",
    "employe.emploi": "Régime de travail",
    "employe.date_entree": "Date d'entrée",
    "employe.date_sortie": "Date de sortie",
    "employe.lieu_travail": "Lieu de travail",
    "prestations.heures_ordinaires": "Heures ordinaires",
    "prestations.taux_horaire": "Taux horaire (€)",
    "prestations.montant_prestations_ordinaires": "Prestations ordinaires (€)",
    "prestations.heures_complementaires": "Heures complémentaires",
    "prestations.montant_heures_complementaires": "Complémentaires (€)",
    "prestations.heures_conge_disponibles": "Congés disponibles (h)",
    "montants.total_brut": "Brut (€)",
    "montants.onss_travailleur": "ONSS travailleur (€)",
    "montants.total_imposable": "Imposable (€)",
    "montants.transport_non_impose": "Transport non imposé (€)",
    "montants.total_net": "Net (€)",
    "montants.net_a_payer": "Net à payer (€)",
    "montants.cotisation_onss_patronale": "ONSS patronale (€)",
}


def aplatir(nom, donnees):
    resultat = {"fichier": nom}
    for section, champs in donnees.items():
        if isinstance(champs, dict):
            for cle, valeur in champs.items():
                resultat[f"{section}.{cle}"] = valeur
    return resultat


def parser_fichier(fichier):
    contenu = fichier.getvalue()
    if not contenu.startswith(b"%PDF"):
        raise ValueError("Le fichier ne semble pas être un PDF valide.")
    reader = PdfReader(io.BytesIO(contenu))
    texte = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not texte.strip():
        raise ValueError("PDF sans texte sélectionnable : OCR non pris en charge.")
    return extraire_donnees(texte)


def exporter_csv(lignes, champs):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[COLONNES[c] for c in champs], delimiter=";")
    writer.writeheader()
    for ligne in lignes:
        writer.writerow({COLONNES[c]: ligne.get(c) for c in champs})
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def exporter_excel(lignes, champs):
    """Crée un fichier XLSX minimal avec la bibliothèque standard Python.

    Aucun paquet externe d'export Excel nécessaire sur Windows.
    """
    from xml.sax.saxutils import escape
    import zipfile

    valeurs = [[COLONNES[c] for c in champs]] + [
        [ligne.get(c) for c in champs] for ligne in lignes
    ]

    def col_lettres(index):
        lettres = ""
        while index:
            index, reste = divmod(index - 1, 26)
            lettres = chr(65 + reste) + lettres
        return lettres

    lignes_xml = []
    for numero, ligne in enumerate(valeurs, 1):
        cellules = []
        for index, valeur in enumerate(ligne, 1):
            reference = f"{col_lettres(index)}{numero}"
            if valeur is None:
                continue
            if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
                cellules.append(f'<c r="{reference}"><v>{valeur}</v></c>')
            else:
                contenu = escape(str(valeur))
                cellules.append(f'<c r="{reference}" t="inlineStr"><is><t>{contenu}</t></is></c>')
        lignes_xml.append(f'<row r="{numero}">{"".join(cellules)}</row>')

    feuille = ("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<sheetData>""" + "".join(lignes_xml) + "</sheetData></worksheet>")
    fichiers_xlsx = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Fiches de paie" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        "xl/worksheets/sheet1.xml": feuille,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for nom, contenu in fichiers_xlsx.items():
            archive.writestr(nom, contenu.encode("utf-8"))
    return buffer.getvalue()


st.title("📄 PaieScan")
st.caption("Analyse locale de plusieurs fiches de paie PDF · Extraction avec ton script Python")
st.info("Les documents sont analysés dans l'application exécutée sur ton ordinateur. Aucun service d'IA externe n'est utilisé. Ne déploie pas cette interface publiquement avec des fiches de paie réelles.")

fichiers = st.file_uploader(
    "Glisse tes fiches de paie ici ou clique pour parcourir",
    type=["pdf"],
    accept_multiple_files=True,
    help="Tu peux sélectionner plusieurs PDF en une seule fois.",
)

if "resultats" not in st.session_state:
    st.session_state.resultats = []
if "erreurs" not in st.session_state:
    st.session_state.erreurs = []

bouton1, bouton2 = st.columns([1, 5])
with bouton1:
    analyser = st.button("🔍 Analyser les PDF", type="primary", disabled=not fichiers, use_container_width=True)
with bouton2:
    if st.button("🗑️ Effacer les résultats"):
        st.session_state.resultats = []
        st.session_state.erreurs = []
        st.rerun()

if analyser:
    bons = []
    erreurs = []
    progression = st.progress(0)
    for index, fichier in enumerate(fichiers):
        try:
            donnees = parser_fichier(fichier)
            bons.append({"nom": fichier.name, "donnees": donnees})
        except Exception as exc:
            erreurs.append({"fichier": fichier.name, "erreur": str(exc)})
        progression.progress((index + 1) / len(fichiers))
    st.session_state.resultats = bons
    st.session_state.erreurs = erreurs
    progression.empty()

resultats = st.session_state.resultats
erreurs = st.session_state.erreurs
if erreurs:
    with st.expander(f"⚠️ {len(erreurs)} fichier(s) non analysé(s)", expanded=True):
        for erreur in erreurs:
            st.error(f"{erreur['fichier']} : {erreur['erreur']}")

if resultats:
    lignes = [aplatir(r["nom"], r["donnees"]) for r in resultats]
    montant_net = sum((r["donnees"].get("montants", {}).get("net_a_payer") or 0) for r in resultats)
    montant_brut = sum((r["donnees"].get("montants", {}).get("total_brut") or 0) for r in resultats)
    docs_sans_net = sum(r["donnees"].get("montants", {}).get("net_a_payer") is None for r in resultats)
    x, y, z = st.columns(3)
    x.metric("PDF analysés", len(resultats))
    y.metric("Total brut extrait", f"{montant_brut:,.2f} €".replace(",", " "))
    z.metric("Total net à payer extrait", f"{montant_net:,.2f} €".replace(",", " "))
    if docs_sans_net:
        st.warning(f"{docs_sans_net} document(s) sans net à payer détecté : les totaux peuvent être incomplets.")
    st.caption("Les totaux additionnent les documents chargés, même si plusieurs fiches concernent la même période. Vérifie les doublons.")

    st.subheader("📊 Tableau comparatif")
    selection = st.multiselect(
        "Choisis les informations à afficher et à exporter",
        options=list(COLONNES),
        default=["fichier", "document.periode", "employe.nom", "prestations.heures_ordinaires", "montants.total_brut", "montants.total_net", "montants.net_a_payer"],
        format_func=lambda c: COLONNES[c],
    )
    if selection:
        st.dataframe(
            [{COLONNES[c]: r.get(c) for c in selection} for r in lignes],
            hide_index=True, use_container_width=True,
        )
        a, b, c = st.columns(3)
        a.download_button("⬇️ Exporter CSV (Excel)", exporter_csv(lignes, selection), "analyse_fiches.csv", "text/csv", use_container_width=True)
        b.download_button("⬇️ Exporter JSON", json.dumps(resultats, ensure_ascii=False, indent=2).encode("utf-8"), "analyse_fiches.json", "application/json", use_container_width=True)
        try:
            excel = exporter_excel(lignes, selection)
            c.download_button("⬇️ Exporter Excel .xlsx", excel, "analyse_fiches.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except Exception as exc:
            c.warning(f"Export Excel indisponible : {exc}. CSV disponible.")
    else:
        st.warning("Sélectionne au moins un champ.")

    st.subheader("🔎 Détails de chaque document")
    for entree in resultats:
        with st.expander(entree["nom"]):
            st.json(entree["donnees"], expanded=True)
else:
    st.markdown("**Mode d'emploi :** importe plusieurs PDF, puis clique sur **Analyser les PDF**. Tu verras ici un tableau avec les données extraites et les boutons d'export.")
    st.caption("Optimisé pour les fiches Acerta / Gamestate similaires à ton exemple. Les autres formats peuvent nécessiter une adaptation des expressions régulières.")
