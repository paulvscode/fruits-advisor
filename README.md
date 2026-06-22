# Fruits Advisor

Outil d'aide à la décision pour l'optimisation des commandes de fruits et légumes frais dans un réseau de magasins bio.

Ingère les mercuriales fournisseurs (XLSX, PDF, email), calcule un Prix Unitaire Moyen (PUM) normalisé par produit, stocke l'historique en base et prépare l'arbitrage multi-fournisseurs.

---

## Prérequis

- Python 3.11 ou supérieur
- pip

---

## Installation

```bash
git clone <url-du-repo>
cd fruits-advisor
pip install -r requirements.txt
```

---

## Lancer l'application

```bash
streamlit run ui/app.py
```

L'interface s'ouvre à **http://localhost:8501**

---

## Utilisation

### 0. Navigation

L'application comporte deux pages accessibles via le menu latéral gauche :
- **Fruits Advisor** — import, analyse et enregistrement des mercuriales fournisseurs
- **Statistiques** — visualisation de l'historique des ventes

---

### 1. Importer une mercuriale

Le panneau de gauche propose deux modes d'import :

#### Onglet Fichier

Sélectionne un fichier fournisseur :

| Format | Fournisseur supporté | Notes |
|---|---|---|
| `.xlsx` | Presto'Bio | Source principale — colonnes bien structurées |
| `.pdf` | Presto'Bio | Fallback — parsing moins précis |

#### Onglet Email

Colle directement le texte d'un email fournisseur. Format attendu (une ligne par produit) :

```
Carotte : 1.9 €/bts
Betterave : 2.2 €/kg
Feuille de chêne rouge : 0.95 €/p
```

Les lignes d'en-tête et de salutation sont ignorées automatiquement.

Unités reconnues : `kg`, `bts` (botte), `p` / `pce` (pièce), `barq`, `sachet`, `pot`, `filet`, `plateau`, `bouquet`.

#### Date du tarif

Pour chaque mode d'import, un champ **"Date du tarif"** permet de dater la mercuriale. La date la plus récente par fournisseur est considérée comme le tarif en vigueur.

---

### 2. Lire les résultats

Après import, l'application affiche :

- **En-tête** : fournisseur, date du tarif, dates de validité (si disponibles dans le fichier)
- **Onglet "Fruits & Légumes frais"** : tous les produits frais avec leur PUM calculé
- **Onglet "Épicerie"** : fruits secs, boissons, épicerie

### 3. Filtrer les produits

Dans chaque onglet, un panneau **Filtres** permet de :
- Rechercher un produit par nom
- Filtrer par certification (BIO / EQ)
- Afficher uniquement les produits locaux (origine France)

### 4. Enregistrer en base

Le bouton **"Enregistrer en base"** sauvegarde la mercuriale (fournisseur + date + tous les produits) dans la base SQLite locale (`data/fruits_advisor.db`).

L'historique de tous les imports est visible sur la page d'accueil quand aucune mercuriale n'est chargée.

### 5. Exporter

Bouton **"Exporter CSV"** en bas de chaque tableau pour télécharger les données filtrées.

---

### 6. Page Statistiques

#### Format du fichier CSV de ventes

| Colonne | Description |
|---|---|
| `Code` | Code produit (EAN ou code interne) |
| `Designation` | Nom du produit |
| `MM AA` | Une colonne par mois (ex: `06 26` = juin 2026) |

Les valeurs peuvent contenir l'unité directement dans la cellule (ex: `30,515 kg`) — elle est automatiquement extraite.

**Séparateur** : auto-détecté (tabulation, point-virgule ou virgule).

#### Graphiques disponibles

- **Vue globale** : classement des produits sur 3 / 6 / 12 mois, en valeur brute ou par jour
- **Détail produit** : sélection mono ou multi-produits, sélection groupée par mot-clé, bar chart mensuel, KPIs, highlights meilleurs mois
- **Météo & Calendrier** : ventes vs température (axe dual), précipitations, jours fériés français, vacances scolaires par zone (A/B/C)

#### Localisation météo

Dans le panneau de gauche, configure la **ville**, la **latitude/longitude** et la **zone scolaire**. Par défaut : Le Havre (49.4938, 0.1077), Zone B.

---

## Colonnes du tableau F&L frais

| Colonne | Description |
|---|---|
| Produit | Nom complet tel que fourni par le fournisseur |
| Origine | Pays / région de production |
| Local (FR) | `True` si origine France |
| Colisage | Nombre d'unités ou kg par colis |
| Unité | `KG` ou `UN` (pièce / barquette) |
| Certif. | `BIO` ou `EQ` (Équitable) |
| Prix/colis (1-4) | Prix HT par colis pour 1 à 4 colis commandés |
| Prix/colis (5+) | Prix HT par colis à partir de 5 colis (remise ~5%) |
| PUM | Prix Unitaire Moyen normalisé |
| Unité PUM | `€/kg` si le poids est connu, `€/pce` sinon |

---

## Alertes ETL

Le panneau **"Alertes ETL"** signale les anomalies détectées lors du parsing :

| Type d'alerte | Cause | Impact |
|---|---|---|
| Poids unitaire inconnu | Format non reconnu dans le nom produit | PUM en €/pce au lieu de €/kg — non comparable entre fournisseurs |
| Unité inconnue | Valeur hors `KG`/`UN` | Normalisé automatiquement en `UN` |
| Prix ou colisage manquant | Ligne incomplète dans le fichier source | Ligne ignorée |
| Aucun produit reconnu | Format email non conforme | Vérifier le format `Nom : prix €/unité` |

**Formats reconnus automatiquement (sans alerte) :**
- `BARQ.125G`, `BARQ 125G`, `(BARQ.125G)` → poids par unité en grammes → PUM en €/kg
- `x 27 PIECES`, `x 6 PCS`, `× 24 UNITÉS` → nombre de pièces par colis → PUM en €/pce

---

## Structure du projet

```
fruits-advisor/
├── core/
│   ├── etl/
│   │   ├── parsers.py       # Parsing XLSX, PDF (Presto'Bio) et email texte libre
│   │   └── normalizer.py    # Calcul PUM, extraction poids unitaire
│   ├── stats/
│   │   └── sales.py         # Parser CSV ventes
│   ├── weather/
│   │   └── open_meteo.py    # Connecteur Open-Meteo (météo historique)
│   ├── calendar/
│   │   └── fr_calendar.py   # Jours fériés + vacances scolaires France
│   ├── forecast/            # Module 2 : prévision des ventes (à venir)
│   └── arbitrage/           # Module 3 : sélection fournisseur (à venir)
├── db/
│   ├── models.py            # Modèles SQLAlchemy (Fournisseur, Mercuriale, ProduitTarif)
│   ├── database.py          # Engine SQLite + init_db()
│   └── repository.py        # save_mercuriale, get_latest_prices, list_mercuriales
├── ui/
│   ├── app.py               # Page principale (import + enregistrement)
│   └── pages/
│       └── 1_Statistiques.py
├── data/                    # Base SQLite locale (gitignorée)
├── tests/
├── requirements.txt
├── CLAUDE.md
└── README.md
```

---

## Glossaire des acronymes

| Acronyme | Forme complète | Définition |
|---|---|---|
| **PUM** | Prix Unitaire Moyen | Prix ramené à l'unité de vente standard (€/kg ou €/pce). Permet de comparer des offres fournisseurs conditionnées différemment. |
| **ETL** | Extract, Transform, Load | Pipeline d'ingestion des fichiers fournisseurs : extraction des données brutes, normalisation, chargement en base. |
| **SKU** | Stock Keeping Unit | Identifiant interne unique d'un produit dans le référentiel du magasin (ex: `BIO-BANANE-01`). |
| **F&L** | Fruits & Légumes | Catégorie de produits frais (par opposition à l'épicerie sèche). |
| **BIO** | Agriculture Biologique | Certification indiquant que le produit respecte le cahier des charges de l'agriculture biologique (label UE). |
| **EQ** | Équitable | Certification commerce équitable (ex: Max Havelaar, Fairtrade). Distinct du label BIO. |
| **HT** | Hors Taxes | Prix avant application de la TVA. Toutes les mercuriales fournisseurs sont exprimées en HT. |
| **Vm** | Vente Moyenne | Moyenne des ventes historiques sur les 4 derniers jours identiques (ex: 4 derniers mardis), utilisée dans le moteur de prévision. |
| **Ve** | Vente Estimée | Vente prévisionnelle calculée : `Ve = Vm × C_meteo × C_calendrier`. |
| **C_meteo** | Coefficient Météo | Multiplicateur appliqué à Vm selon les prévisions météo et le profil climatique du produit. |
| **C_calendrier** | Coefficient Calendrier | Multiplicateur appliqué à Vm selon le calendrier (veille de jour férié, vacances scolaires). |
| **S_s** | Stock de Sécurité | Quantité tampon maintenue en magasin : `S_s = 0.5 × Vm`. |
| **S_i** | Stock Initial | Quantité disponible en magasin au moment du calcul de la commande. |
| **Franco** | Franco de port | Seuil de commande (en €) à partir duquel les frais de port sont offerts par le fournisseur. |
| **MVP** | Minimum Viable Product | Version minimale fonctionnelle de l'application, suffisante pour valider les règles métier sur un magasin pilote. |

---

## Roadmap

### MVP (en cours)
- [x] Parser mercuriale Presto'Bio XLSX
- [x] Parser mercuriale Presto'Bio PDF (fallback)
- [x] Parser mercuriale email texte libre
- [x] Calcul PUM normalisé (€/kg)
- [x] Date du tarif sur chaque import
- [x] Base SQLite : stockage par fournisseur / date (Fournisseur, Mercuriale, ProduitTarif)
- [x] Interface Streamlit upload + tableau + filtres + export CSV + historique
- [x] Page Statistiques : import CSV ventes, vue globale + détail produit
- [x] Onglet Météo & Calendrier : Open-Meteo + jours fériés + vacances scolaires

### V1 (à venir)
- [ ] Moteur de prévision des ventes (Vm, C_meteo, C_calendrier)
- [ ] Migration PostgreSQL + TimescaleDB
- [ ] Support multi-fournisseurs + arbitrage automatique (Module 3)
- [ ] Mapping SKU (rapidfuzz + sentence-transformers)
- [ ] Alertes ETL automatiques (prix anormal, rupture)

### V2 (à venir)
- [ ] Interface multi-magasins avec authentification
- [ ] Alertes automatiques (franco critique, démarque prévue)
- [ ] API FastAPI exposée pour intégration ERP
