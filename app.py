from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
import requests
import logging
import threading
import time
import os
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
from rdflib.namespace import XSD
import owlrl

# Import du module d'exploration d'ontologie
from ontology_explorer import OntologyExplorer

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation de l'application Flask
app = Flask(__name__)

# Configuration CORS pour permettre toutes les origines, y compris localhost:4200
CORS(app, resources={r"/api/*": {"origins": "*", "allow_headers": "*", "expose_headers": "*"}})

# Configuration
# API principale (WIGOS)
METEO_API_BASE_URL = "https://wis2.meteoburkina.bf/oapi/collections/urn:wmo:md:bf-anam:mx2w8y/items"
WIGOS_STATION_ID = "0-854-0-090"
DEFAULT_LIMIT = 6

# Chemin vers l'ontologie et les règles SWRL
ONTOLOGY_PATH = os.path.join(os.path.dirname(__file__), "data", "ontologie_inondations_ouagadougou_fixed.owl")
SWRL_RULES_PATH = os.path.join(os.path.dirname(__file__), "data", "swrl_rules_final.txt")

# API alternative (Open-Meteo)
OPENMETEO_API_URL = "https://api.open-meteo.com/v1/forecast"
# Coordonnées de Ouagadougou (station de Somgandé)
OUAGA_LAT = 12.4052
OUAGA_LON = -1.5063

# Configuration API FANFAR pour les données hydrologiques
FANFAR_API_BASE_URL = "https://hypewebapp.smhi.se/fanfar/server/point"
FANFAR_MODEL = "wa-hype1.2_hgfd3.2_ecoper_noEOWL_INSITU-AR"
# Station de WAYEN sur la Volta Blanche
WAYEN_STATION_SUBID = 208493
WAYEN_STATION_Y = 12.41203

# Paramètres météo à récupérer
METEO_PARAMETERS = [
    "air_temperature",
    "non_coordinate_pressure",
    "relative_humidity",
    "wind_direction",
    "wind_speed",
    "total_precipitation_or_total_water_equivalent"
]

# Mapping entre les paramètres WIGOS et Open-Meteo
OPENMETEO_PARAM_MAPPING = {
    "air_temperature": "temperature_2m",
    "non_coordinate_pressure": "surface_pressure",
    "relative_humidity": "relative_humidity_2m",
    "wind_direction": "wind_direction_10m",
    "wind_speed": "wind_speed_10m",
    "total_precipitation_or_total_water_equivalent": "precipitation"
}

# Unités par défaut pour Open-Meteo
OPENMETEO_UNITS = {
    "air_temperature": "Celsius",
    "non_coordinate_pressure": "hPa",
    "relative_humidity": "%",
    "wind_direction": "deg",
    "wind_speed": "m/s",
    "total_precipitation_or_total_water_equivalent": "mm"
}

# Cache global pour stocker les données
cache = {
    "meteo": None,
    "meteo_timestamp": None,
    "meteo_history": None,
    "meteo_history_timestamp": None,
    "hydro": None,
    "hydro_timestamp": None,
    "hydro_history": None,
    "hydro_history_timestamp": None,
    "flood_prediction": None,
    "flood_prediction_timestamp": None,
    "cache_lifetime": 300  # 5 minutes en secondes
}

# Initialisation de l'explorateur d'ontologie
ontology_explorer = OntologyExplorer(ONTOLOGY_PATH, SWRL_RULES_PATH)

def get_openmeteo_data(date_iso=None):
    """
    Récupère les données météorologiques depuis l'API Open-Meteo comme alternative
    
    Args:
        date_iso (str, optional): Date spécifique au format ISO (YYYY-MM-DDTHH:MM:SSZ).
    
    Returns:
        dict: Données météorologiques formatées ou dict avec une clé 'error' en cas d'erreur
    """
    try:
        # Déterminer la date de début et de fin
        if date_iso:
            target_date = datetime.fromisoformat(date_iso.replace('Z', '+00:00'))
        else:
            # Utiliser l'heure actuelle
            target_date = datetime.now(timezone.utc)
        
        # Formater les dates pour Open-Meteo (format YYYY-MM-DD)
        date_str = target_date.strftime('%Y-%m-%d')
        
        # Préparer les paramètres pour Open-Meteo
        params = {
            "latitude": OUAGA_LAT,
            "longitude": OUAGA_LON,
            "hourly": ",".join(OPENMETEO_PARAM_MAPPING.values()),  # Tous les paramètres nécessaires
            "start_date": date_str,
            "end_date": date_str,
            "timezone": "UTC"
        }
        
        logger.info(f"Tentative avec API alternative Open-Meteo: {OPENMETEO_API_URL}")
        response = requests.get(OPENMETEO_API_URL, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Erreur API Open-Meteo: {response.status_code}, {response.text}")
            return {"error": "API Open-Meteo indisponible"}
            
        data = response.json()
        
        # Vérifier que les données sont complètes
        if "hourly" not in data or not all(param in data["hourly"] for param in OPENMETEO_PARAM_MAPPING.values()):
            logger.error("API Open-Meteo: données incomplètes")
            return {"error": "Données météorologiques incomplètes depuis Open-Meteo"}
        
        # Trouver l'heure la plus proche de la date cible
        target_hour = target_date.hour
        hourly_data = data["hourly"]
        
        # Organiser les données dans le même format que les données WIGOS
        result = [{
            "reportId": f"openmeteo-{date_str}-{target_hour:02d}",
            "timestamp": f"{date_str}T{target_hour:02d}:00:00Z",
            "reportTime": f"{date_str}T{target_hour:02d}:00:00Z",
            "station": "open-meteo-ouagadougou",
            "measurements": {}
        }]
        
        # Convertir chaque paramètre Open-Meteo en format WIGOS
        for wigos_param, openmeteo_param in OPENMETEO_PARAM_MAPPING.items():
            if openmeteo_param in hourly_data and len(hourly_data[openmeteo_param]) > target_hour:
                value = hourly_data[openmeteo_param][target_hour]
                result[0]["measurements"][wigos_param] = {
                    "value": value,
                    "unit": OPENMETEO_UNITS[wigos_param]
                }
        
        logger.info("Données météo récupérées avec succès depuis Open-Meteo")
        return result
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des données Open-Meteo: {str(e)}")
        return {"error": f"Erreur avec l'API Open-Meteo: {str(e)}"}

def get_current_meteo(specific_date=None):
    """
    Récupère les données météorologiques actuelles depuis l'API Météo Burkina
    ou depuis Open-Meteo en cas d'échec
    
    Args:
        specific_date (str, optional): Date spécifique au format ISO (YYYY-MM-DDTHH:MM:SSZ).
            Si non spécifiée, utilise l'heure pleine précédente.
    """
    # Vérifier si les données en cache sont encore valides
    current_time = time.time()
    if cache["meteo"] and cache["meteo_timestamp"] and (current_time - cache["meteo_timestamp"] < cache["cache_lifetime"]):
        logger.info("Utilisation des données météo en cache")
        return cache["meteo"]
    
    # Déterminer la date cible
    if specific_date:
        date_iso = specific_date
    else:
        # Utiliser l'heure pleine précédente (HH:00:00Z)
        now = datetime.now(timezone.utc)
        # Récupérer l'heure précédente (arrondi à l'heure inférieure)
        previous_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        date_iso = previous_hour.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Tentative avec l'API WIGOS
    try:
        # Préparer les paramètres de la requête
        params = {
            "f": "json",  # Format JSON explicite
            "datetime": f"{date_iso}/..",
            "wigos_station_identifier": WIGOS_STATION_ID,
            "limit": DEFAULT_LIMIT
        }
        
        logger.info(f"Appel API WIGOS: {METEO_API_BASE_URL}?datetime={params['datetime']}&wigos_station_identifier={params['wigos_station_identifier']}&limit={params['limit']}")
        
        response = requests.get(METEO_API_BASE_URL, params=params, timeout=10)
        
        # Vérifier la réponse de l'API
        if response.status_code == 200:
            data = response.json()
            
            # Vérifier que nous avons bien des données
            if "features" in data and data["features"]:
                logger.info(f"Données météo récupérées avec succès de WIGOS pour la date: {date_iso}")
                
                # Continuer avec le traitement des données WIGOS
                # [Le reste du code de traitement reste inchangé]
            
                # Organiser les données par reportId pour regrouper les mesures
                meteo_data = {}
                for feature in data["features"]:
                    if "properties" not in feature:
                        continue
                        
                    props = feature["properties"]
                    report_id = props.get("reportId")
                    
                    if report_id not in meteo_data:
                        meteo_data[report_id] = {
                            "reportId": report_id,
                            "timestamp": props.get("phenomenonTime"),
                            "reportTime": props.get("reportTime"),
                            "station": props.get("wigos_station_identifier"),
                            "measurements": {}
                        }
                    
                    # Ajouter la mesure au groupe correspondant
                    parameter = props.get("name")
                    if parameter:
                        meteo_data[report_id]["measurements"][parameter] = {
                            "value": props.get("value"),
                            "unit": props.get("units")
                        }
                
                # Convertir le dictionnaire en liste et trier par timestamp (le plus récent en premier)
                result = list(meteo_data.values())
                result.sort(key=lambda x: x["reportTime"] if x["reportTime"] else "", reverse=True)
                
                # Mettre à jour le cache
                cache["meteo"] = result
                cache["meteo_timestamp"] = time.time()
                
                return result
            else:
                logger.warning(f"API WIGOS: aucune donnée disponible pour la date {date_iso}, tentative avec Open-Meteo")
        else:
            logger.warning(f"Erreur API WIGOS: {response.status_code}, tentative avec Open-Meteo")
        
        # Si nous arrivons ici, c'est que l'API WIGOS n'a pas fonctionné
        # Tentative avec l'API Open-Meteo
        logger.info("Tentative de récupération des données via Open-Meteo")
        openmeteo_result = get_openmeteo_data(date_iso)
        
        if not isinstance(openmeteo_result, dict) or "error" not in openmeteo_result:
            # Succès avec Open-Meteo
            logger.info("Données météo récupérées avec succès depuis Open-Meteo (API alternative)")
            
            # Mettre à jour le cache
            cache["meteo"] = openmeteo_result
            cache["meteo_timestamp"] = time.time()
            
            return openmeteo_result
        else:
            # Échec avec les deux APIs
            logger.error("Les deux APIs météo (WIGOS et Open-Meteo) sont indisponibles")
            return {"error": "Les données météorologiques ne sont pas disponibles actuellement. Veuillez réessayer plus tard."}
            
    except requests.exceptions.RequestException as e:
        # Erreur de requête HTTP avec WIGOS, essayer Open-Meteo
        logger.error(f"Erreur lors de l'appel à l'API WIGOS: {str(e)}, tentative avec Open-Meteo")
        
        openmeteo_result = get_openmeteo_data(date_iso)
        
        if not isinstance(openmeteo_result, dict) or "error" not in openmeteo_result:
            # Succès avec Open-Meteo
            logger.info("Données météo récupérées avec succès depuis Open-Meteo (API alternative)")
            
            # Mettre à jour le cache
            cache["meteo"] = openmeteo_result
            cache["meteo_timestamp"] = time.time()
            
            return openmeteo_result
        else:
            # Échec avec les deux APIs
            logger.error("Les deux APIs météo (WIGOS et Open-Meteo) sont indisponibles")
            return {"error": "Les données météorologiques ne sont pas disponibles actuellement. Veuillez réessayer plus tard."}
            
    except Exception as e:
        logger.error(f"Erreur inattendue: {str(e)}")
        return {"error": f"Une erreur inattendue s'est produite: {str(e)}"}

def get_meteo_history_forecast(days_before=5, days_after=5):
    """
    Récupère l'historique météorologique des derniers jours et les prévisions pour les prochains jours
    
    Args:
        days_before (int): Nombre de jours d'historique à récupérer
        days_after (int): Nombre de jours de prévisions à récupérer
    """
    # Vérifier si les données en cache sont encore valides
    current_time = time.time()
    if cache["meteo_history"] and cache["meteo_history_timestamp"] and (current_time - cache["meteo_history_timestamp"] < cache["cache_lifetime"]):
        logger.info("Utilisation des données d'historique météo en cache")
        return cache["meteo_history"]
    
    try:
        # Calculer les dates de début et de fin de la période
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days_before)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (now + timedelta(days=days_after)).replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Formater les dates au format ISO 8601
        start_date_iso = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_date_iso = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        logger.info(f"Récupération des données météo du {start_date_iso} au {end_date_iso}")
        
        # Récupérer les données pour chaque paramètre météo
        all_data = {}
        for param in METEO_PARAMETERS:
            # Paramètres de la requête
            params = {
                "f": "json",
                "name": param,
                "datetime": f"{start_date_iso}/{end_date_iso}",
                "wigos_station_identifier": WIGOS_STATION_ID,
                # Utiliser une limite plus grande pour récupérer suffisamment de données
                "limit": days_before * 24 + days_after * 24  # Approximativement 1 mesure par heure
            }
            
            logger.info(f"Appel API météo historique pour {param}: {METEO_API_BASE_URL}?name={param}&datetime={params['datetime']}&wigos_station_identifier={params['wigos_station_identifier']}&limit={params['limit']}")
            
            response = requests.get(METEO_API_BASE_URL, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Erreur API météo historique pour {param}: {response.status_code}")
                continue
            
            data = response.json()
            
            if "features" not in data or not data["features"]:
                logger.warning(f"Aucune donnée d'historique disponible pour {param}")
                continue
                
            # Organiser les données par date/heure
            for feature in data["features"]:
                if "properties" not in feature:
                    continue
                    
                props = feature["properties"]
                report_time = props.get("reportTime")
                phenomenon_time = props.get("phenomenonTime")
                
                # Utiliser reportTime comme clé de regroupement
                time_key = report_time if report_time else phenomenon_time
                if not time_key:
                    continue
                    
                if time_key not in all_data:
                    all_data[time_key] = {
                        "timestamp": time_key,
                        "parameters": {}
                    }
                
                # Ajouter la mesure au groupe correspondant
                all_data[time_key]["parameters"][param] = {
                    "value": props.get("value"),
                    "unit": props.get("units")
                }
        
        # Convertir le dictionnaire en liste et trier par timestamp
        result = list(all_data.values())
        result.sort(key=lambda x: x["timestamp"])
        
        # Séparer les données en historique (avant maintenant) et prévisions (après maintenant)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        history = [item for item in result if item["timestamp"] <= now_str]
        forecast = [item for item in result if item["timestamp"] > now_str]
        
        final_result = {
            "history": history,
            "forecast": forecast,
            "period": {
                "start": start_date_iso,
                "end": end_date_iso,
                "current": now_str
            }
        }
        
        # Mettre à jour le cache
        cache["meteo_history"] = final_result
        cache["meteo_history_timestamp"] = time.time()
        
        return final_result
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'historique météo: {str(e)}")
        return {"error": f"Erreur lors de la récupération de l'historique météo: {str(e)}"}

def get_current_hydro(station_subid=WAYEN_STATION_SUBID, station_y=WAYEN_STATION_Y):
    """
    Récupère les données hydrologiques actuelles depuis l'API FANFAR
    
    Args:
        station_subid (int, optional): ID de la sous-station à utiliser. Par défaut, station de WAYEN.
        station_y (float, optional): Coordonnée Y de la station. Par défaut, station de WAYEN.
    """
    # Vérifier si les données en cache sont encore valides
    current_time = time.time()
    if cache["hydro"] and cache["hydro_timestamp"] and (current_time - cache["hydro_timestamp"] < cache["cache_lifetime"]):
        logger.info("Utilisation des données hydro en cache")
        return cache["hydro"]
    
    try:
        # Construire l'URL de l'API FANFAR
        url = f"{FANFAR_API_BASE_URL}/{FANFAR_MODEL}?x=undefined&y={station_y}&subid={station_subid}"
        
        logger.info(f"Appel API FANFAR: {url}")
        
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Erreur API FANFAR: {response.status_code}, {response.text}")
            return {"error": "API FANFAR indisponible", "status_code": response.status_code}
        
        data = response.json()
        
        # Vérifier que nous avons bien des données
        if "chartData" not in data or "forecast" not in data["chartData"]:
            logger.error("API FANFAR: aucune donnée disponible")
            return {"error": "Aucune donnée hydrologique disponible"}
        
        # Extraire les informations pertinentes
        station_info = data.get("station", {})
        
        # Récupérer la dernière valeur de prévision (qui correspond au débit actuel)
        forecast_data = data["chartData"]["forecast"]
        current_flow = None
        current_timestamp = None
        
        if forecast_data and len(forecast_data) > 0:
            # La première valeur de prévision est la plus récente
            current_timestamp = forecast_data[0][0]  # Timestamp en millisecondes
            current_flow = forecast_data[0][1]       # Débit en m³/s
        
        # Extraire également les seuils d'alerte
        thresholds = {
            "hq2": data["chartData"].get("hq2"),   # Crue biennale
            "hq5": data["chartData"].get("hq5"),   # Crue quinquennale
            "hq30": data["chartData"].get("hq30")  # Crue trentennale
        }
        
        # Formater les données de sortie
        result = {
            "station": {
                "id": station_info.get("subid"),
                "name": station_info.get("name"),
                "river": station_info.get("river"),
                "country": station_info.get("country"),
                "coordinates": data.get("poiCenter", {}).get("geometry", {}).get("coordinates", [])
            },
            "current": {
                "timestamp": current_timestamp,
                "datetime": datetime.fromtimestamp(current_timestamp / 1000).strftime("%Y-%m-%dT%H:%M:%SZ") if current_timestamp else None,
                "discharge": current_flow,  # Débit en m³/s
                "unit": "m³/s"
            },
            "thresholds": thresholds
        }
        
        # Mettre à jour le cache
        cache["hydro"] = result
        cache["hydro_timestamp"] = time.time()
        
        logger.info(f"Données hydrologiques récupérées avec succès pour la station {station_info.get('name')}")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de l'appel à l'API FANFAR: {str(e)}")
        return {"error": f"Impossible de récupérer les données hydrologiques: {str(e)}"}
    except Exception as e:
        logger.error(f"Erreur inattendue: {str(e)}")
        return {"error": f"Une erreur inattendue s'est produite: {str(e)}"}

def get_hydro_history_forecast(station_subid=WAYEN_STATION_SUBID, station_y=WAYEN_STATION_Y):
    """
    Récupère l'historique et les prévisions hydrologiques depuis l'API FANFAR
    
    Args:
        station_subid (int, optional): ID de la sous-station à utiliser. Par défaut, station de WAYEN.
        station_y (float, optional): Coordonnée Y de la station. Par défaut, station de WAYEN.
    """
    # Vérifier si les données en cache sont encore valides
    current_time = time.time()
    if cache["hydro_history"] and cache["hydro_history_timestamp"] and (current_time - cache["hydro_history_timestamp"] < cache["cache_lifetime"]):
        logger.info("Utilisation des données d'historique hydro en cache")
        return cache["hydro_history"]
    
    try:
        # Construire l'URL de l'API FANFAR
        url = f"{FANFAR_API_BASE_URL}/{FANFAR_MODEL}?x=undefined&y={station_y}&subid={station_subid}"
        
        logger.info(f"Appel API FANFAR pour historique et prévisions: {url}")
        
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Erreur API FANFAR: {response.status_code}, {response.text}")
            return {"error": "API FANFAR indisponible", "status_code": response.status_code}
        
        data = response.json()
        
        # Vérifier que nous avons bien des données
        if "chartData" not in data or "hindcast" not in data["chartData"] or "forecast" not in data["chartData"]:
            logger.error("API FANFAR: aucune donnée d'historique disponible")
            return {"error": "Aucune donnée d'historique hydrologique disponible"}
        
        # Extraire les informations pertinentes
        station_info = data.get("station", {})
        hindcast_data = data["chartData"]["hindcast"]  # Données historiques
        forecast_data = data["chartData"]["forecast"]  # Données de prévision
        
        # Convertir les données en format plus lisible
        history = []
        for item in hindcast_data:
            if len(item) >= 2:
                timestamp = item[0]  # Timestamp en millisecondes
                flow = item[1]       # Débit en m³/s
                history.append({
                    "timestamp": timestamp,
                    "datetime": datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "discharge": flow,
                    "unit": "m³/s"
                })
        
        forecast = []
        for item in forecast_data:
            if len(item) >= 2:
                timestamp = item[0]  # Timestamp en millisecondes
                flow = item[1]       # Débit en m³/s
                forecast.append({
                    "timestamp": timestamp,
                    "datetime": datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "discharge": flow,
                    "unit": "m³/s"
                })
        
        # Extraire les informations sur les ticks d'échelle
        scale_ticks = {}
        if "scaleticks" in data["chartData"]:
            for tick in data["chartData"]["scaleticks"]:
                if len(tick) >= 2:
                    scale_ticks[tick[0]] = tick[1]  # timestamp -> label
        
        # Extraire également les seuils d'alerte
        thresholds = {
            "hq2": data["chartData"].get("hq2"),   # Crue biennale
            "hq5": data["chartData"].get("hq5"),   # Crue quinquennale
            "hq30": data["chartData"].get("hq30")  # Crue trentennale
        }
        
        # Formater les données de sortie
        result = {
            "station": {
                "id": station_info.get("subid"),
                "name": station_info.get("name"),
                "river": station_info.get("river"),
                "country": station_info.get("country"),
                "coordinates": data.get("poiCenter", {}).get("geometry", {}).get("coordinates", [])
            },
            "history": history,
            "forecast": forecast,
            "thresholds": thresholds,
            "scale_ticks": scale_ticks
        }
        
        # Mettre à jour le cache
        cache["hydro_history"] = result
        cache["hydro_history_timestamp"] = time.time()
        
        logger.info(f"Données d'historique et de prévisions hydrologiques récupérées avec succès pour la station {station_info.get('name')}")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de l'appel à l'API FANFAR pour l'historique: {str(e)}")
        return {"error": f"Impossible de récupérer les données d'historique hydrologiques: {str(e)}"}
    except Exception as e:
        logger.error(f"Erreur inattendue: {str(e)}")
        return {"error": f"Une erreur inattendue s'est produite: {str(e)}"}

def predict_flood():
    """
    Effectue une prédiction de risque d'inondation en utilisant l'ontologie et les règles SWRL
    
    Returns:
        dict: Résultat de la prédiction avec niveau de risque et explications
    """
    # Vérifier si les prédictions en cache sont encore valides
    current_time = time.time()
    if cache["flood_prediction"] and cache["flood_prediction_timestamp"] and (current_time - cache["flood_prediction_timestamp"] < cache["cache_lifetime"]):
        logger.info("Utilisation des prédictions d'inondation en cache")
        return cache["flood_prediction"]
    
    try:
        # Récupérer les données météo et hydro actuelles
        meteo_data = get_current_meteo()
        hydro_data = get_current_hydro()
        
        # Vérifier que nous avons bien des données valides
        if isinstance(meteo_data, dict) and "error" in meteo_data:
            return {"error": f"Impossible de prédire les inondations: données météo indisponibles - {meteo_data['error']}"}
        
        if isinstance(hydro_data, dict) and "error" in hydro_data:
            return {"error": f"Impossible de prédire les inondations: données hydro indisponibles - {hydro_data['error']}"}
        
        # Charger l'ontologie
        g = Graph()
        logger.info(f"Chargement de l'ontologie depuis {ONTOLOGY_PATH}")
        g.parse(ONTOLOGY_PATH, format="xml")
        
        # Définir les espaces de noms
        FLOOD = Namespace("http://www.semanticweb.org/ontologies/2025/ouagadougou-flood-prediction#")
        SWRLB = Namespace("http://www.w3.org/2003/11/swrlb#")
        g.bind("flood", FLOOD)
        g.bind("swrlb", SWRLB)
        
        # Créer des instances pour les données météo et hydro
        now = datetime.now(timezone.utc)
        current_time_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Créer un identifiant unique pour la session d'analyse
        analysis_id = f"analysis_{int(time.time())}"
        analysis_uri = URIRef(FLOOD + analysis_id)
        g.add((analysis_uri, RDF.type, FLOOD.FloodRiskAnalysis))
        g.add((analysis_uri, FLOOD.hasTime, Literal(current_time_str, datatype=XSD.dateTime)))
        
        # Ajouter la zone géographique (Ouagadougou)
        ouaga_uri = URIRef(FLOOD + "Ouagadougou")
        g.add((ouaga_uri, RDF.type, FLOOD.City))
        g.add((ouaga_uri, FLOOD.hasName, Literal("Ouagadougou")))
        
        # Ajouter les stations de mesure
        meteo_station_uri = URIRef(FLOOD + "Station_Ouaga_Meteo")
        g.add((meteo_station_uri, RDF.type, FLOOD.MeteorologicalStation))
        g.add((meteo_station_uri, FLOOD.hasName, Literal("Ouagadougou_Meteo")))
        g.add((meteo_station_uri, FLOOD.isLocatedIn, ouaga_uri))
        
        hydro_station_uri = URIRef(FLOOD + "Station_Wayen")
        g.add((hydro_station_uri, RDF.type, FLOOD.HydrologicalStation))
        g.add((hydro_station_uri, FLOOD.hasName, Literal("Wayen")))
        g.add((ouaga_uri, FLOOD.isDownstreamOf, hydro_station_uri))
        
        # Ajouter les données météo
        meteo_uri = URIRef(FLOOD + f"MeteoData_{int(time.time())}")
        g.add((meteo_uri, RDF.type, FLOOD.MeteorologicalData))
        g.add((meteo_uri, FLOOD.occursAtTime, Literal(current_time_str, datatype=XSD.dateTime)))
        g.add((meteo_uri, FLOOD.measuredAt, meteo_station_uri))
        
        # Extraire les mesures météo
        precipitation = None
        if len(meteo_data) > 0 and "measurements" in meteo_data[0]:
            measurements = meteo_data[0]["measurements"]
            
            # Précipitation (paramètre clé pour les inondations)
            if "total_precipitation_or_total_water_equivalent" in measurements:
                precip_value = measurements["total_precipitation_or_total_water_equivalent"]["value"]
                if precip_value is not None:
                    precipitation = float(precip_value)
                    g.add((meteo_uri, FLOOD.hasPrecipitation, Literal(precipitation, datatype=XSD.float)))
            
            # Autres paramètres météo
            if "air_temperature" in measurements:
                temp_value = measurements["air_temperature"]["value"]
                if temp_value is not None:
                    g.add((meteo_uri, FLOOD.hasTemperature, Literal(float(temp_value), datatype=XSD.float)))
            
            if "relative_humidity" in measurements:
                humidity_value = measurements["relative_humidity"]["value"]
                if humidity_value is not None:
                    g.add((meteo_uri, FLOOD.hasHumidity, Literal(float(humidity_value), datatype=XSD.float)))
        
        # Ajouter les données hydro
        hydro_uri = URIRef(FLOOD + f"HydroData_{int(time.time())}")
        g.add((hydro_uri, RDF.type, FLOOD.HydrologicalData))
        g.add((hydro_uri, FLOOD.occursAtTime, Literal(current_time_str, datatype=XSD.dateTime)))
        g.add((hydro_uri, FLOOD.measuredAt, hydro_station_uri))
        
        # Extraire les mesures hydro
        discharge = None
        water_level = None  # Estimation basée sur le débit
        
        if "current" in hydro_data and "discharge" in hydro_data["current"]:
            discharge_value = hydro_data["current"]["discharge"]
            if discharge_value is not None:
                discharge = float(discharge_value)
                g.add((hydro_uri, FLOOD.hasDischarge, Literal(discharge, datatype=XSD.float)))
                
                # Estimer le niveau d'eau basé sur le débit (relation approximative)
                # Cette estimation est simplifiée et devrait être affinée avec des données réelles
                water_level = discharge / 20  # Relation approximative
                g.add((hydro_uri, FLOOD.hasWaterLevel, Literal(water_level, datatype=XSD.float)))
        
        # Ajouter les seuils d'alerte hydrologiques
        if "thresholds" in hydro_data:
            thresholds = hydro_data["thresholds"]
            if "hq2" in thresholds and thresholds["hq2"] is not None:
                g.add((hydro_station_uri, FLOOD.hasHQ2Threshold, Literal(float(thresholds["hq2"]), datatype=XSD.float)))
            if "hq5" in thresholds and thresholds["hq5"] is not None:
                g.add((hydro_station_uri, FLOOD.hasHQ5Threshold, Literal(float(thresholds["hq5"]), datatype=XSD.float)))
            if "hq30" in thresholds and thresholds["hq30"] is not None:
                g.add((hydro_station_uri, FLOOD.hasHQ30Threshold, Literal(float(thresholds["hq30"]), datatype=XSD.float)))
        
        # Appliquer les règles d'inférence OWL
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
        
        # Déterminer le risque d'inondation en appliquant les règles SWRL
        # Puisque SWRL n'est pas directement supporté par rdflib, nous allons appliquer manuellement
        # les règles basées sur les données collectées et la logique des règles SWRL
        
        risk_level = "Faible"  # Niveau par défaut
        risk_reasons = []
        
        # Appliquer la Règle 1: Risque élevé basé sur fortes précipitations et niveaux d'eau
        if precipitation is not None and water_level is not None:
            if precipitation > 30.0 and water_level > 2.5:
                risk_level = "Élevé"
                risk_reasons.append(f"Précipitations élevées ({precipitation} mm) et niveau d'eau élevé ({water_level} m)")
        
        # Appliquer la Règle 4: Risque pour les quartiers spécifiques près du Massili
        if discharge is not None and discharge > 10.0:
            if risk_level != "Élevé":  # Ne pas déclasser un risque déjà élevé
                risk_level = "Modéré"
            risk_reasons.append(f"Débit élevé à la station de Wayen ({discharge} m³/s)")
        
        # Appliquer la Règle 5: Alerte précoce basée sur débit élevé du Nakanbé
        alert_status = "Normal"
        if discharge is not None and discharge > 50.0:
            alert_status = "Alerte"
            if risk_level != "Élevé":  # Ne pas déclasser un risque déjà élevé
                risk_level = "Modéré"
            risk_reasons.append(f"Débit très élevé du Nakanbé à Wayen ({discharge} m³/s)")
        
        # Ajouter une règle supplémentaire pour les précipitations
        if precipitation is not None:
            if precipitation > 15.0 and precipitation <= 30.0:
                if risk_level == "Faible":  # Ne pas déclasser un risque déjà plus élevé
                    risk_level = "Modéré"
                risk_reasons.append(f"Précipitations modérées ({precipitation} mm)")
            elif precipitation > 30.0:
                risk_level = "Élevé"
                risk_reasons.append(f"Précipitations très élevées ({precipitation} mm)")
        
        # Si aucune raison n'a été déterminée, ajouter une explication par défaut
        if not risk_reasons:
            risk_reasons.append("Conditions météorologiques et hydrologiques stables")
        
        # Construire la réponse
        result = {
            "analysis_id": analysis_id,
            "timestamp": current_time_str,
            "city": "Ouagadougou",
            "risk_level": risk_level,
            "alert_status": alert_status,
            "reasons": risk_reasons,
            "data_sources": {
                "meteo": {
                    "station": "Ouagadougou",
                    "precipitation": precipitation,
                    "timestamp": meteo_data[0]["timestamp"] if len(meteo_data) > 0 else None
                },
                "hydro": {
                    "station": "Wayen",
                    "discharge": discharge,
                    "water_level": water_level,
                    "timestamp": hydro_data["current"]["datetime"] if "current" in hydro_data else None,
                    "thresholds": hydro_data.get("thresholds", {})
                }
            },
            "recommendations": []
        }
        
        # Ajouter des recommandations en fonction du niveau de risque
        if risk_level == "Faible":
            result["recommendations"] = [
                "Aucune action spécifique requise",
                "Rester informé des bulletins météorologiques"
            ]
        elif risk_level == "Modéré":
            result["recommendations"] = [
                "Surveiller les niveaux d'eau dans les zones à risque",
                "Préparer les équipements d'urgence",
                "Limiter les déplacements dans les zones sensibles en cas de pluie"
            ]
        else:  # Élevé
            result["recommendations"] = [
                "Évacuer les zones à haut risque",
                "Activer les centres d'urgence locaux",
                "Suivre strictement les consignes des autorités",
                "Éviter tout déplacement non essentiel"
            ]
        
        # Mettre à jour le cache
        cache["flood_prediction"] = result
        cache["flood_prediction_timestamp"] = time.time()
        
        logger.info(f"Prédiction d'inondation effectuée avec succès: niveau de risque {risk_level}")
        return result
        
    except Exception as e:
        logger.error(f"Erreur lors de la prédiction des inondations: {str(e)}")
        return {"error": f"Une erreur est survenue lors de la prédiction des inondations: {str(e)}"}

def refresh_cache():
    """Fonction pour rafraîchir périodiquement le cache"""
    while True:
        logger.info("Rafraîchissement du cache")
        try:
            # Rafraîchir les données météo actuelles
            get_current_meteo()
            
            # Rafraîchir les données hydro actuelles
            get_current_hydro()
            
            # Rafraîchir les prédictions d'inondation
            predict_flood()
            
            # Rafraîchir également l'historique et les prévisions (moins fréquemment)
            if not cache["meteo_history"] or not cache["meteo_history_timestamp"] or \
               (time.time() - cache["meteo_history_timestamp"] > cache["cache_lifetime"] * 2):
                get_meteo_history_forecast()
            
            if not cache["hydro_history"] or not cache["hydro_history_timestamp"] or \
               (time.time() - cache["hydro_history_timestamp"] > cache["cache_lifetime"] * 2):
                get_hydro_history_forecast()
                
            logger.info("Cache rafraîchi avec succès")
        except Exception as e:
            logger.error(f"Erreur lors du rafraîchissement du cache: {str(e)}")
        
        # Attendre avant le prochain rafraîchissement
        time.sleep(cache["cache_lifetime"] - 10)  # Rafraîchir 10 secondes avant l'expiration

# Routes API
@app.route('/api/v1/meteo/current', methods=['GET'])
def current_meteo_endpoint():
    """Endpoint pour récupérer les données météorologiques actuelles"""
    # Récupérer la date spécifiée dans les paramètres de la requête, si présente
    specific_date = request.args.get('date')
    # L'option force=true n'est plus nécessaire car nous n'utilisons plus de date de secours
        
    meteo_data = get_current_meteo(specific_date)
    
    if isinstance(meteo_data, dict) and "error" in meteo_data:
        # Si une erreur est survenue
        status_code = meteo_data.get("status_code", 503)  # Par défaut 503 Service Unavailable
        return jsonify({
            "status": "error",
            "message": meteo_data["error"]
        }), status_code
    
    return jsonify({
        "status": "success",
        "data": meteo_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

@app.route('/api/v1/meteo/history', methods=['GET'])
def meteo_history_endpoint():
    """Endpoint pour récupérer l'historique météorologique et les prévisions"""
    # Récupérer les paramètres de la requête
    days_before = request.args.get('days_before', default=5, type=int)
    days_after = request.args.get('days_after', default=5, type=int)
    
    # Limiter les valeurs pour éviter des requêtes trop lourdes
    days_before = min(max(1, days_before), 10)  # Entre 1 et 10 jours
    days_after = min(max(1, days_after), 10)    # Entre 1 et 10 jours
    
    meteo_history = get_meteo_history_forecast(days_before, days_after)
    
    if isinstance(meteo_history, dict) and "error" in meteo_history:
        return jsonify({
            "status": "error",
            "message": meteo_history["error"]
        }), 503
    
    return jsonify({
        "status": "success",
        "data": meteo_history,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

@app.route('/api/v1/hydro/current', methods=['GET'])
def current_hydro_endpoint():
    """Endpoint pour récupérer les données hydrologiques actuelles"""
    # Récupérer les paramètres de la requête
    station_id = request.args.get('station_id', default=WAYEN_STATION_SUBID, type=int)
    station_y = request.args.get('station_y', default=WAYEN_STATION_Y, type=float)
    
    hydro_data = get_current_hydro(station_id, station_y)
    
    if isinstance(hydro_data, dict) and "error" in hydro_data:
        status_code = hydro_data.get("status_code", 503)  # Par défaut 503 Service Unavailable
        return jsonify({
            "status": "error",
            "message": hydro_data["error"]
        }), status_code
    
    return jsonify({
        "status": "success",
        "data": hydro_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

@app.route('/api/v1/hydro/history', methods=['GET'])
def hydro_history_endpoint():
    """Endpoint pour récupérer l'historique et les prévisions hydrologiques"""
    # Récupérer les paramètres de la requête
    station_id = request.args.get('station_id', default=WAYEN_STATION_SUBID, type=int)
    station_y = request.args.get('station_y', default=WAYEN_STATION_Y, type=float)
    
    hydro_history = get_hydro_history_forecast(station_id, station_y)
    
    if isinstance(hydro_history, dict) and "error" in hydro_history:
        status_code = hydro_history.get("status_code", 503)  # Par défaut 503 Service Unavailable
        return jsonify({
            "status": "error",
            "message": hydro_history["error"]
        }), status_code
    
    return jsonify({
        "status": "success",
        "data": hydro_history,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

@app.route('/api/v1/prediction/flood', methods=['GET'])
def flood_prediction_endpoint():
    """Endpoint pour la prédiction des inondations basée sur l'ontologie"""
    prediction = predict_flood()
    
    if isinstance(prediction, dict) and "error" in prediction:
        return jsonify({
            "status": "error",
            "message": prediction["error"]
        }), 503
    
    return jsonify({
        "status": "success",
        "data": prediction,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """Endpoint de vérification de l'état de l'API"""
    return jsonify({
        "status": "ok",
        "service": "ouagadougou-flood-water-prediction"
    }), 200

# ===== Routes pour l'explorateur d'ontologie =====

@app.route("/api/ontology/statistics", methods=["GET"])
def get_ontology_statistics():
    """Renvoie des statistiques générales sur l'ontologie."""
    stats = ontology_explorer.get_ontology_statistics()
    return jsonify(stats)

@app.route("/api/ontology/description", methods=["GET"])
def get_ontology_description():
    """Renvoie une description générale de l'ontologie."""
    description = ontology_explorer.get_ontology_description()
    return jsonify(description)

@app.route("/api/ontology/classes", methods=["GET"])
def get_ontology_classes():
    """Renvoie la liste des classes de l'ontologie."""
    classes = ontology_explorer.get_classes()
    return jsonify(classes)

@app.route("/api/ontology/object-properties", methods=["GET"])
def get_ontology_object_properties():
    """Renvoie la liste des propriétés d'objet de l'ontologie."""
    properties = ontology_explorer.get_object_properties()
    return jsonify(properties)

@app.route("/api/ontology/data-properties", methods=["GET"])
def get_ontology_data_properties():
    """Renvoie la liste des propriétés de données de l'ontologie."""
    properties = ontology_explorer.get_data_properties()
    return jsonify(properties)

@app.route("/api/ontology/individuals", methods=["GET"])
def get_ontology_individuals():
    """Renvoie la liste des individus de l'ontologie."""
    class_uri = request.args.get('class')
    individuals = ontology_explorer.get_individuals(class_uri)
    return jsonify(individuals)

@app.route("/api/ontology/inferred", methods=["GET"])
def get_inferred_knowledge():
    """Renvoie les connaissances inférées par l'ontologie."""
    inferred = ontology_explorer.get_inferred_knowledge()
    return jsonify(inferred)

@app.route("/api/ontology/visualization", methods=["GET"])
def get_ontology_visualization():
    """Renvoie les données pour visualiser l'ontologie."""
    try:
        logger.info("Début de la récupération des données de visualisation")
        visualization_data = ontology_explorer.get_ontology_visualization_data()
        logger.info(f"Données récupérées : {len(visualization_data.get('nodes', []))} nœuds et {len(visualization_data.get('links', []))} liens")
        return jsonify(visualization_data)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des données de visualisation: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/ontology/rules", methods=["GET"])
def get_swrl_rules():
    """Renvoie la liste des règles SWRL avec leurs explications."""
    rules = ontology_explorer.load_swrl_rules()
    return jsonify(rules)

@app.route("/api/ontology/inference-explanation", methods=["GET"])
def get_inference_explanation():
    """Renvoie l'explication d'une inférence spécifique."""
    zone = request.args.get('zone')
    inferred_property = request.args.get('property')
    
    if not zone or not inferred_property:
        return jsonify({"error": "Les paramètres 'zone' et 'property' sont requis"}), 400
    
    try:
        explanation = ontology_explorer.get_inference_explanation(zone, inferred_property)
        return jsonify(explanation)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'explication: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/ontology/reload", methods=["POST"])
def reload_ontology():
    """Force le rechargement de l'ontologie."""
    success = ontology_explorer.load_ontology(force_reload=True)
    return jsonify({"success": success, "message": "Ontologie rechargée avec succès" if success else "Échec du rechargement de l'ontologie"})

if __name__ == '__main__':
    # Démarrer le thread de rafraîchissement du cache
    refresh_thread = threading.Thread(target=refresh_cache, daemon=True)
    refresh_thread.start()
    
    # Démarrer le serveur Flask
    app.run(debug=True, host='0.0.0.0', port=5000)
