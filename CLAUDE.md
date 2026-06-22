# CLAUDE.md — fruits-advisor

Outil d'aide à la décision pour l'optimisation des commandes de fruits et légumes frais dans un réseau de magasins bio.

---

## RÈGLE : MISE À JOUR DU README

**À chaque modification significative de l'application, mettre à jour `README.md` en conséquence.**

Cela inclut (liste non exhaustive) :
- Ajout d'un nouveau module ou fonctionnalité
- Nouveau fournisseur supporté
- Nouvelle commande CLI ou variable d'environnement
- Changement de structure de dossiers
- Ajout d'une étape dans la roadmap (cocher ✅ ou ajouter une ligne)

Ne pas attendre que l'utilisateur le demande — le README est toujours tenu à jour.

---

## RÔLE DU PROJET

Ingérer des données hétérogènes (ventes, stocks, météo, calendriers, mercuriales fournisseurs) pour :
- Calculer automatiquement les quantités à commander par produit
- Arbitrer le choix du meilleur fournisseur
- Réduire la démarque et maximiser les marges

---

## STACK TECHNIQUE

| Composant | Technologie | Notes |
|---|---|---|
| Backend | Python 3.11 + FastAPI | API async, validation Pydantic |
| Base de données | PostgreSQL 16 + TimescaleDB | Séries temporelles sur l'historique des ventes |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic | Migrations versionnées |
| Parsing CSV/Excel | pandas + openpyxl | `engine="openpyxl"` obligatoire pour `.xlsx` |
| Parsing PDF | pdfplumber (tableaux nets) + camelot (tableaux complexes) | |
| OCR fallback | pytesseract + Pillow | Uniquement si pdfplumber échoue |
| Matching SKU | rapidfuzz (lexical) + sentence-transformers (sémantique) | Seuil : score < 85 → fallback sémantique |
| API Météo | Open-Meteo | Gratuit, sans clé API, couverture France + DOM |
| Scheduler | Celery + Redis | File de traitement asynchrone |
| Frontend MVP | Streamlit | Interface upload + validation en magasin |
| Frontend prod | Next.js 14 (App Router) | Migration si multi-magasins + auth nécessaire |
| Infra | Docker + Docker Compose | VPS Hetzner CX21 (~6€/mois) |

### Dépendances Python (requirements.txt minimum)

```
fastapi>=0.111
uvicorn>=0.29
pandas>=2.0
openpyxl>=3.1
pdfplumber>=0.11
camelot-py[cv]>=0.11
pytesseract>=0.3
Pillow>=10.0
rapidfuzz>=3.0
sentence-transformers>=3.0
sqlalchemy>=2.0
alembic>=1.13
celery>=5.3
redis>=5.0
streamlit>=1.35
httpx>=0.27
workalendar>=17.0
```

---

## MODULE 1 : ETL & NORMALISATION

### Mapping SKU

Chaque produit fournisseur doit être mappé vers le référentiel interne du magasin (`SKU`).

- Format SKU interne : `BIO-{CATEGORIE}-{INDEX}` (ex: `BIO-BANANE-01`)
- Processus de matching en deux passes :
  1. **Rapide** : `rapidfuzz` sur le nom normalisé (minuscules, sans accents, sans stopwords). Seuil ≥ 85 → match accepté.
  2. **Sémantique** : `sentence-transformers` (modèle `paraphrase-multilingual-MiniLM-L12-v2`) si score < 85.
  3. **Alerte manuelle** si aucun match > 70.

### Normalisation des unités

Toutes les offres sont converties en unité de vente standard :
- **Kilogramme (kg)** ou **Pièce (pce)**
- Règle colis : `PUM (€/kg) = Prix colis HT / Poids net colis`
- Détecter et alerter si une unité est ambiguë (ex: "botte", "plateau", "filet")

### Alertes ETL à générer

- Prix HT anormalement bas ou élevé (> ±40% vs moyenne des 4 dernières semaines pour ce SKU)
- Unité non reconnue
- Produit sans mapping SKU
- Fichier illisible ou format inattendu

---

## MODULE 2 : MOTEUR DE PRÉVISION DES VENTES

### Formule

```
Ve = Vm * C_meteo * C_calendrier
Q_suggeree = Ve + S_s - S_i
```

Si `Q_suggeree <= 0` → forcer à `0`.

### Variables

**Vm — Vente Moyenne**
- Moyenne des ventes des 4 derniers jours identiques (ex: 4 derniers mardis si commande un mardi)
- Exclure les anomalies : écarter les valeurs à ±2 écarts-types de la moyenne

**C_meteo — Coefficient météo** (via Open-Meteo, prévision J+1)

| Profil produit | Condition | Coefficient |
|---|---|---|
| Estival (Tomate, Fraise, Courgette…) | T° prévue > normale +4°C | 1.25 |
| Estival | Pluie continue (> 6h) | 0.85 |
| Automnal (Poireau, Potimarron, Betterave…) | Baisse de T° > 3°C | 1.20 |
| Neutre (Banane, Citron, Avocat…) | Toute condition | 1.00 |

La "normale" de référence est la moyenne des T° du même jour sur les 5 dernières années (données Open-Meteo historical).

**C_calendrier — Coefficient calendrier** (via `workalendar`, France)

| Situation | Coefficient |
|---|---|
| Veille de jour férié | 1.40 |
| Vacances scolaires (zone à configurer par magasin) | 0.80 |
| Jour normal | 1.00 |

Note : si veille de jour férié ET vacances scolaires → appliquer uniquement `C_calendrier = 1.40` (pas de cumul).

**S_s — Stock de sécurité**
```
S_s = 0.5 * Vm
```

**S_i — Stock initial**
- Saisi manuellement en magasin ou importé depuis l'ERP

---

## MODULE 3 : ALGORITHME D'ARBITRAGE ACHAT

### Ordre de priorité strict

1. **Disponibilité** : Éliminer tout fournisseur en rupture sur le produit.
2. **Priorité Local** : Si le produit est tagué `local=true` ET que son PUM est ≤ 110% du PUM import le moins cher → sélectionner le fournisseur local.
3. **Prix Net Normalisé** : Sélectionner le fournisseur avec le PUM (€/kg ou €/pce) le plus bas.
4. **Optimisation Franco** : Si un fournisseur est à moins de 15% de son seuil de franco (ex: commande à 180€ pour un franco à 200€), réarbitrer des lignes non critiques vers ce fournisseur pour éviter des frais de port.

### Règles métier complémentaires

- Un fournisseur peut avoir un franco différent par magasin → stocker par couple `(fournisseur_id, magasin_id)`
- Les frais de port s'appliquent si le total commande < franco
- Journaliser chaque décision d'arbitrage avec sa justification (pour audit et apprentissage)

---

## FORMAT DE SORTIE (RÉPONSES ET RAPPORTS)

### Section 2 — Rapport ETL
- Liste des fichiers ingérés, statut du mapping SKU, alertes prix/unités

### Section 3 — Tableau d'arbitrage

```
Produit (SKU/Nom) | Qté Suggérée | Unité | Fournisseur | PUM (€) | Coût Total (€) | Justification
```

### Section 4 — Synthèse par fournisseur
- Montant total HT
- Statut franco (atteint / manque X€ / frais de port applicables)
- Alertes ruptures

---

## CONVENTIONS DE CODE

- Langue du code : **anglais** (variables, fonctions, classes, commentaires)
- Langue des logs et messages UI : **français**
- Noms des enseignes, écoles, entités spécifiques : toujours en **français** dans les outputs
- Pas de commentaires évidents — uniquement si la logique est non triviale
- Tests unitaires obligatoires pour les modules 2 et 3 (formules critiques)
- Valider les données entrantes avec **Pydantic** à chaque boundary (upload, API)

---

## STRUCTURE DU PROJET (CIBLE)

```
fruits-advisor/
├── api/                    # FastAPI routes
│   ├── routes/
│   └── main.py
├── core/
│   ├── etl/                # Parsing PDF, Excel, CSV + mapping SKU
│   ├── forecast/           # Module 2 : prévision des ventes
│   ├── arbitrage/          # Module 3 : sélection fournisseur
│   └── weather/            # Connecteur Open-Meteo
├── db/
│   ├── models.py           # SQLAlchemy models
│   └── migrations/         # Alembic
├── ui/                     # Streamlit (MVP)
├── tests/
├── requirements.txt
├── docker-compose.yml
└── CLAUDE.md
```

---

## PHASES DE DÉVELOPPEMENT

| Phase | Périmètre | Stack |
|---|---|---|
| MVP | 1 magasin, upload manuel CSV/Excel, tableau d'arbitrage | pandas + SQLite + Streamlit |
| V1 | FastAPI + PostgreSQL/TimescaleDB + Celery + PDF parsing | Stack complète |
| V2 | Multi-magasins, auth, historique, alertes automatiques | Next.js frontend |
