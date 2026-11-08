import re
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

from pypdf import PdfReader


def extraire_texte_pdf(pdf_path: str) -> str:
    """Extrait le texte de toutes les pages d'un PDF texte."""
    reader = PdfReader(pdf_path)
    pages = []

    for page in reader.pages:
        texte = page.extract_text() or ""
        pages.append(texte)

    texte_complet = "\n".join(pages)

    if not texte_complet.strip():
        raise ValueError(
            "Aucun texte détecté dans le PDF. "
            "Le document est peut-être scanné et nécessiterait un OCR."
        )

    return texte_complet


def nettoyer_texte(texte: str) -> str:
    """Normalise les espaces sans casser les lignes utiles."""
    lignes = []
    for ligne in texte.splitlines():
        ligne = re.sub(r"[ \t]+", " ", ligne).strip()
        if ligne:
            lignes.append(ligne)
    return "\n".join(lignes)


def montant_vers_float(valeur: Optional[str]) -> Optional[float]:
    """Convertit '1 226,64' ou '1226,64' en float Python."""
    if valeur is None:
        return None

    valeur = valeur.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(valeur)
    except ValueError:
        return None


def rechercher(pattern: str, texte: str, flags=re.IGNORECASE | re.MULTILINE) -> Optional[str]:
    match = re.search(pattern, texte, flags)
    return match.group(1).strip() if match else None


def extraire_donnees(texte: str) -> Dict[str, Any]:
    """
    Extrait les informations principales d'une fiche de paie Acerta / Gamestate.
    Les regex peuvent être facilement adaptées pour d'autres modèles.
    """

    texte = nettoyer_texte(texte)

    # -----------------------------
    # Informations générales
    # -----------------------------
    periode = rechercher(
        r"p[ée]riode\s*:\s*(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4})",
        texte,
    )

    etabli_le = rechercher(
        r"[ée]tabli\s+le\s*:\s*(\d{2}/\d{2}/\d{4})",
        texte,
    )

    entreprise = rechercher(
        r"^(SRL\s+GAMESTATE\s+BRUXELLES)\b",
        texte,
    )

    employe = rechercher(
        r"SRL\s+GAMESTATE\s+BRUXELLES\s+([^\n]+)",
        texte,
    )

    statut = rechercher(
        r"statut\s*:\s*([^\n]+?)(?=\s+fonction\s*:|$)",
        texte,
    )

    fonction = rechercher(
        r"fonction\s*:\s*([^\n]+)",
        texte,
    )

    emploi = rechercher(
        r"emploi\s*:\s*([0-9,.]+\s*/\s*[0-9,.]+)",
        texte,
    )

    date_entree = rechercher(
        r"date d['’]entr[ée]e\s*:\s*(\d{2}/\d{2}/\d{4})",
        texte,
    )

    date_sortie = rechercher(
        r"date de sortie\s*:\s*(\d{2}/\d{2}/\d{4})",
        texte,
    )

    lieu_travail = rechercher(
        r"lieu de travail\s*:\s*([^\n]+)",
        texte,
    )

    # -----------------------------
    # Prestations
    # -----------------------------
    heures_ordinaires = rechercher(
        r"([0-9]+,[0-9]+)\s+14,[0-9]+\s+[0-9]+,[0-9]+\s+100\s+prestations ordinaires",
        texte,
    )

    taux_horaire = rechercher(
        r"[0-9]+,[0-9]+\s+(14,[0-9]+)\s+[0-9]+,[0-9]+\s+100\s+prestations ordinaires",
        texte,
    )

    montant_prestations = rechercher(
        r"[0-9]+,[0-9]+\s+14,[0-9]+\s+([0-9]+,[0-9]+)\s+100\s+prestations ordinaires",
        texte,
    )

    heures_complementaires = rechercher(
        r"([0-9]+,[0-9]+)\s+14,[0-9]+\s+[0-9]+,[0-9]+\s+1917\s+Heures complémentaires",
        texte,
    )

    montant_heures_complementaires = rechercher(
        r"[0-9]+,[0-9]+\s+14,[0-9]+\s+([0-9]+,[0-9]+)\s+1917\s+Heures complémentaires",
        texte,
    )

    # -----------------------------
    # Montants
    # -----------------------------
    total_brut = rechercher(
        r"([0-9]+,[0-9]+)\s+\*{4}\s+TOTAL BRUT",
        texte,
    )

    onss_travailleur = rechercher(
        r"13,07\s+-\s+([0-9]+,[0-9]+)\s+9000\s+ONSS travailleur",
        texte,
    )

    total_imposable = rechercher(
        r"([0-9]+,[0-9]+)\s+\*{4}\s+TOTAL IMPOSABLE",
        texte,
    )

    transport_non_impose = rechercher(
        r"([0-9]+,[0-9]+)\s+9420\s+autre transport non impos[ée]",
        texte,
    )

    total_net = rechercher(
        r"([0-9]+,[0-9]+)\s+\*{4}\s+TOTAL NET",
        texte,
    )

    net_a_payer = rechercher(
        r"([0-9]+,[0-9]+)\s+\*{4}\s+NET A PAYER",
        texte,
    )

    cotisation_patronale = rechercher(
        r"[0-9]+,[0-9]+\s+26,98\s+([0-9]+,[0-9]+)\s+Cotisation ONSS patronale totale",
        texte,
    )

    heures_conge = rechercher(
        r"Heures de cong[ée]\s+H\s+([0-9]+,[0-9]+)",
        texte,
    )

    # -----------------------------
    # Résultat structuré
    # -----------------------------
    resultat = {
        "document": {
            "periode": periode,
            "etabli_le": etabli_le,
        },
        "employeur": {
            "entreprise": entreprise,
        },
        "employe": {
            "nom": employe,
            "statut": statut,
            "fonction": fonction,
            "emploi": emploi,
            "date_entree": date_entree,
            "date_sortie": date_sortie,
            "lieu_travail": lieu_travail,
        },
        "prestations": {
            "heures_ordinaires": montant_vers_float(heures_ordinaires),
            "taux_horaire": montant_vers_float(taux_horaire),
            "montant_prestations_ordinaires": montant_vers_float(montant_prestations),
            "heures_complementaires": montant_vers_float(heures_complementaires),
            "montant_heures_complementaires": montant_vers_float(
                montant_heures_complementaires
            ),
            "heures_conge_disponibles": montant_vers_float(heures_conge),
        },
        "montants": {
            "total_brut": montant_vers_float(total_brut),
            "onss_travailleur": montant_vers_float(onss_travailleur),
            "total_imposable": montant_vers_float(total_imposable),
            "transport_non_impose": montant_vers_float(transport_non_impose),
            "total_net": montant_vers_float(total_net),
            "net_a_payer": montant_vers_float(net_a_payer),
            "cotisation_onss_patronale": montant_vers_float(cotisation_patronale),
        },
    }

    return resultat


def main():
    parser = argparse.ArgumentParser(
        description="Extrait automatiquement des informations d'une fiche de paie PDF."
    )
    parser.add_argument("pdf", help="Chemin vers le fichier PDF")
    parser.add_argument(
        "--json",
        dest="json_output",
        help="Chemin facultatif vers un fichier JSON de sortie",
    )

    args = parser.parse_args()

    texte = extraire_texte_pdf(args.pdf)
    donnees = extraire_donnees(texte)

    sortie = json.dumps(donnees, ensure_ascii=False, indent=2)
    print(sortie)

    if args.json_output:
        Path(args.json_output).write_text(sortie, encoding="utf-8")
        print(f"\nFichier JSON créé : {args.json_output}")


if __name__ == "__main__":
    main()
