# Système de Prédiction des Inondations à Ouagadougou - Backend

API backend pour le système de prévision des inondations à Ouagadougou, intégrant données météorologiques, hydrologiques et modèles de prédiction basés sur l'ontologie.

## 📋 Fonctionnalités clés

- Récupération des données météorologiques en temps réel (WIGOS avec repli sur Open-Meteo)
- Collecte des données hydrologiques (API FANFAR)
- Prédiction des risques d'inondation basée sur une ontologie et des règles SWRL
- Système de mise en cache pour optimiser les performances et la résilience
- Interface REST complète et documentée

## 🛠️ Prérequis

- Python 3.8+
- pip (gestionnaire de paquets Python)
- Accès à internet (pour les APIs externes)

## 📦 Installation

1. **Cloner le dépôt**
   ```bash
   git clone [URL_DU_DEPOT]
   cd bf-flood-prediction-backend
   ```

2. **Créer et activer un environnement virtuel**
   ```bash
   python -m venv venv
   # Sur Windows
   venv\Scripts\activate
   # Sur Linux/MacOS
   source venv/bin/activate
   ```

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurer les variables d'environnement** (optionnel)
   Créer un fichier `.env` à la racine du projet :
   ```
   DEBUG=True
   PORT=5000
   HOST=0.0.0.0
   ```

## 🚀 Démarrage

Pour lancer le serveur de développement :

```bash
python app.py
```

L'API sera disponible sur `http://127.0.0.1:5000/`.

## 📚 Documentation de l'API

L'API est divisée en deux grandes catégories d'endpoints :
1. **`/api/v1/`** - Endpoints principaux pour les données météo, hydrologiques et les prédictions
2. **`/api/ontology/`** - Endpoints pour l'exploration de l'ontologie et des règles d'inférence

### Endpoints principaux (`/api/v1/`)

#### 1. Santé de l'API
```
GET /api/v1/health
```
Vérifie l'état de fonctionnement de l'API.

**Réponse :**
```json
{
  "status": "ok",
  "service": "ouagadougou-flood-water-prediction"
}
```

#### 2. Météorologie

##### 2.1 Données météorologiques actuelles
```
GET /api/v1/meteo/current
```

**Paramètres :**
- `date` (optionnel) : Date spécifique au format ISO (YYYY-MM-DDTHH:MM:SSZ)

**Réponse :**
```json
{
  "status": "success",
  "data": {
    "dataTime": "2025-06-02T10:00:00Z",
    "measurements": {
      "air_temperature": {
        "value": 32.5,
        "unit": "Celsius"
      },
      "relative_humidity": {
        "value": 65,
        "unit": "%"
      },
      "wind_speed": {
        "value": 3.2,
        "unit": "m/s"
      },
      "wind_direction": {
        "value": 180,
        "unit": "deg"
      },
      "total_precipitation_or_total_water_equivalent": {
        "value": 0,
        "unit": "mm"
      }
    },
    "source": "WIGOS"
  },
  "timestamp": "2025-06-02T10:59:57Z"
}
```

##### 2.2 Historique et prévisions météorologiques
```
GET /api/v1/meteo/history
```

**Paramètres :**
- `days_before` (optionnel) : Nombre de jours d'historique à récupérer (défaut: 5, max: 10)
- `days_after` (optionnel) : Nombre de jours de prévision à récupérer (défaut: 5, max: 10)

**Réponse :**
```json
{
  "status": "success",
  "data": {
    "history": [
      {
        "dataTime": "2025-06-01T10:00:00Z",
        "temperature": 31.2,
        "humidity": 58,
        "precipitation": 0,
        "wind_speed": 2.8
      },
      {...}
    ],
    "forecast": [
      {
        "dataTime": "2025-06-03T10:00:00Z",
        "temperature": 33.1,
        "humidity": 62,
        "precipitation": 2.5,
        "wind_speed": 3.4
      },
      {...}
    ],
    "period": {
      "start": "2025-05-28T00:00:00Z",
      "end": "2025-06-07T23:59:59Z",
      "current": "2025-06-02T10:59:57Z"
    }
  },
  "timestamp": "2025-06-02T10:59:57Z"
}
```

#### 3. Hydrologie

##### 3.1 Données hydrologiques actuelles
```
GET /api/v1/hydro/current
```

**Paramètres :**
- `station_id` (optionnel) : ID de la station hydrologique (défaut: station de Wayen)
- `station_y` (optionnel) : Coordonnée Y de la station (défaut: station de Wayen)

**Réponse :**
```json
{
  "status": "success",
  "data": {
    "station_id": "208493",
    "station_name": "WAYEN",
    "last_updated": "2025-06-02T09:00:00Z",
    "water_level": 2.3,
    "discharge": 15.7,
    "location": {
      "lat": 12.41203,
      "lon": -1.4985
    }
  },
  "timestamp": "2025-06-02T10:59:57Z"
}
```

##### 3.2 Historique et prévisions hydrologiques
```
GET /api/v1/hydro/history
```

**Paramètres :**
- `station_id` (optionnel) : ID de la station hydrologique (défaut: station de Wayen)
- `station_y` (optionnel) : Coordonnée Y de la station (défaut: station de Wayen)

**Réponse :**
```json
{
  "status": "success",
  "data": {
    "station": {
      "id": "208493",
      "name": "WAYEN",
      "location": {
        "lat": 12.41203,
        "lon": -1.4985
      }
    },
    "history": [
      {
        "date": "2025-06-01T00:00:00Z",
        "discharge": 14.2,
        "water_level": 2.1
      },
      {...}
    ],
    "forecast": [
      {
        "date": "2025-06-03T00:00:00Z",
        "discharge": 17.8,
        "water_level": 2.5
      },
      {...}
    ]
  },
  "timestamp": "2025-06-02T10:59:57Z"
}
```

#### 4. Prédiction des inondations
```
GET /api/v1/prediction/flood
```

**Paramètres :** Aucun

**Réponse :**
```json
{
  "status": "success",
  "data": {
    "risk_level": "moderate",
    "confidence": 0.75,
    "timestamp": "2025-06-02T10:59:57Z",
    "risk_zones": [
      {
        "name": "Zone_Pissy",
        "risk_level": "high",
        "risk_score": 8.2
      },
      {
        "name": "Zone_Tanghin",
        "risk_level": "moderate",
        "risk_score": 5.4
      }
    ],
    "reasons": [
      "Précipitations récentes élevées",
      "Niveau d'eau de la rivière Nakambé en augmentation",
      "Saturation des sols importante"
    ],
    "recommendations": [
      "Surveiller les zones vulnérables",
      "Contrôle régulier des niveaux d'eau",
      "Informer les populations des zones à risque"
    ]
  },
  "timestamp": "2025-06-02T10:59:57Z"
}
```

### Endpoints d'exploration de l'ontologie (`/api/ontology/`)

#### 1. Statistiques de l'ontologie
```
GET /api/ontology/statistics
```
Renvoie des statistiques générales sur l'ontologie.

#### 2. Description de l'ontologie
```
GET /api/ontology/description
```
Renvoie une description générale de l'ontologie.

#### 3. Classes de l'ontologie
```
GET /api/ontology/classes
```
Renvoie la liste des classes de l'ontologie.

#### 4. Propriétés d'objet
```
GET /api/ontology/object-properties
```
Renvoie la liste des propriétés d'objet de l'ontologie.

#### 5. Propriétés de données
```
GET /api/ontology/data-properties
```
Renvoie la liste des propriétés de données de l'ontologie.

#### 6. Individus de l'ontologie
```
GET /api/ontology/individuals
```
Renvoie la liste des individus de l'ontologie.

**Paramètres :**
- `class` (optionnel) : URI de la classe pour filtrer les individus

#### 7. Connaissances inférées
```
GET /api/ontology/inferred
```
Renvoie les connaissances inférées par l'ontologie.

#### 8. Visualisation de l'ontologie
```
GET /api/ontology/visualization
```
Renvoie les données pour visualiser l'ontologie.

#### 9. Règles SWRL
```
GET /api/ontology/rules
```
Renvoie la liste des règles SWRL avec leurs explications.

#### 10. Explication d'inférence
```
GET /api/ontology/inference-explanation
```
Renvoie l'explication d'une inférence spécifique.

**Paramètres :**
- `zone` (requis) : Zone géographique
- `property` (requis) : Propriété inférée

#### 11. Rechargement de l'ontologie
```
POST /api/ontology/reload
```
Force le rechargement de l'ontologie.

## 🔄 Système de mise en cache

Le système implémente un mécanisme de mise en cache pour optimiser les performances et réduire les appels aux APIs externes :

- Durée de vie du cache : 300 secondes (5 minutes) par défaut
- Rafraîchissement automatique : un thread dédié actualisé les données en arrière-plan
- Basculement automatique : en cas d'indisponibilité de l'API WIGOS, le système bascule automatiquement vers Open-Meteo

## 🔍 Dépendances principales

- **Flask** : Framework web pour l'API REST
- **Flask-CORS** : Gestion des requêtes cross-origin
- **requests** : Client HTTP pour les appels aux APIs externes
- **rdflib** : Manipulation des ontologies RDF
- **owlrl** : Moteur d'inférence pour OWL
- **datetime, threading** : Utilitaires Python standards

## 📡 APIs externes utilisées

- **WIGOS** (https://wis2.meteoburkina.bf/) : API météorologique principale
- **Open-Meteo** (https://api.open-meteo.com/) : API météorologique alternative
- **FANFAR** (https://hypewebapp.smhi.se/fanfar/) : API pour les données hydrologiques

## 📝 Notes de développement

- Le serveur démarre sur le port 5000 par défaut (modifiable via variable d'environnement)
- L'API utilise l'heure UTC pour toutes les dates et heures
- Le système de prédiction des inondations est basé sur les règles SWRL définies dans l'ontologie
