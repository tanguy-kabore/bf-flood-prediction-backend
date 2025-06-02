"""
Module pour explorer l'ontologie des inondations à Ouagadougou.
Ce module fournit des fonctions pour extraire des informations de l'ontologie et les règles SWRL.
"""

from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
from rdflib.namespace import XSD
import owlrl
import os
import json
import re
import logging
from datetime import datetime
from inference_explainer import InferenceExplainer

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Namespace de l'ontologie des inondations
FLOOD_NS = Namespace("http://www.semanticweb.org/ontologies/2025/ouagadougou-flood-prediction#")

class OntologyExplorer:
    """Classe pour explorer l'ontologie des inondations à Ouagadougou."""
    
    def __init__(self, ontology_path, swrl_rules_path):
        """
        Initialise l'explorateur d'ontologie.
        
        Args:
            ontology_path (str): Chemin vers le fichier d'ontologie OWL
            swrl_rules_path (str): Chemin vers le fichier de règles SWRL
        """
        self.ontology_path = ontology_path
        self.swrl_rules_path = swrl_rules_path
        self.graph = None
        self.rules = None
        self.last_loaded = None
        self.inference_explainer = None
    
    def load_ontology(self, force_reload=False):
        """
        Charge l'ontologie en mémoire.
        
        Args:
            force_reload (bool): Force le rechargement de l'ontologie même si déjà chargée
            
        Returns:
            bool: True si l'ontologie a été chargée avec succès, False sinon
        """
        if self.graph is not None and not force_reload:
            return True
            
        try:
            start_time = datetime.now()
            logger.info(f"Chargement de l'ontologie depuis {self.ontology_path}...")
            
            self.graph = Graph()
            self.graph.parse(self.ontology_path, format="xml")
            
            # Appliquer le raisonnement OWL pour inférer des connaissances supplémentaires
            logger.info("Application du raisonnement OWL...")
            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(self.graph)
            
            end_time = datetime.now()
            load_duration = (end_time - start_time).total_seconds()
            logger.info(f"Ontologie chargée avec succès en {load_duration:.2f} secondes. {len(self.graph)} triplets.")
            
            self.last_loaded = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'ontologie: {str(e)}")
            return False
    
    def load_swrl_rules(self):
        """
        Charge les règles SWRL depuis le fichier.
        
        Returns:
            list: Liste des règles SWRL avec leurs descriptions
        """
        if self.rules is not None:
            return self.rules
            
        try:
            with open(self.swrl_rules_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extraire les règles et leurs descriptions à l'aide d'expressions régulières
            rules = []
            rule_blocks = re.split(r'#\s*Règle\s+\d+:', content)
            
            if len(rule_blocks) > 1:
                # Le premier bloc est l'en-tête, commencer à partir du second
                for i, block in enumerate(rule_blocks[1:], 1):
                    lines = block.strip().split('\n')
                    
                    # La première ligne est la description
                    description = lines[0].strip()
                    
                    # Les lignes suivantes jusqu'à la ligne vide constituent la règle
                    rule_text = []
                    for line in lines[1:]:
                        if line.strip():
                            rule_text.append(line.strip())
                        else:
                            break
                    
                    rule = {
                        "id": i,
                        "description": description,
                        "rule": " ".join(rule_text),
                        "explanation": self.explain_rule(i, description, " ".join(rule_text))
                    }
                    rules.append(rule)
            
            self.rules = rules
            return rules
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement des règles SWRL: {str(e)}")
            return []
    
    def explain_rule(self, rule_id, description, rule_text):
        """
        Génère une explication détaillée d'une règle SWRL.
        
        Args:
            rule_id (int): Identifiant de la règle
            description (str): Description de la règle
            rule_text (str): Texte de la règle
            
        Returns:
            str: Explication détaillée de la règle
        """
        # Générer des explications en fonction du type de règle
        if rule_id == 1:
            return ("Cette règle identifie un risque élevé d'inondation lorsque des précipitations importantes (>30mm) "
                    "coïncident avec des niveaux d'eau élevés (>2.5m) dans la même zone géographique. "
                    "Les fortes pluies combinées à des niveaux d'eau déjà élevés sont un indicateur fiable de risque imminent d'inondation.")
        elif rule_id == 2:
            return ("Cette règle attribue un risque modéré aux zones protégées par des barrages dont la capacité dépasse 85%. "
                    "Quand un barrage approche de sa capacité maximale, il peut être nécessaire de procéder à des lâchers d'eau, "
                    "ce qui augmente le risque d'inondation dans les zones en aval.")
        elif rule_id == 3:
            return ("Cette règle identifie les zones à haut risque d'inondation en fonction de leurs caractéristiques géographiques. "
                    "Les zones avec une faible pente (<1°) et des sols hydromorphes (qui retiennent l'eau) sont particulièrement "
                    "vulnérables même avec des précipitations modérées (>15mm).")
        elif rule_id == 4:
            return ("Cette règle spécifique surveille le débit de la rivière Massili à la station de Gonse. "
                    "Lorsque le débit dépasse 10m³/s, un risque modéré est attribué aux zones situées en aval de cette station, "
                    "car l'eau mettra un certain temps à atteindre ces zones.")
        elif rule_id == 5:
            return ("Cette règle déclenche une alerte précoce pour la ville de Ouagadougou lorsque le débit du Nakanbé "
                    "à la station de Wayen dépasse 50m³/s. La rivière Nakanbé est l'un des principaux cours d'eau "
                    "influençant le régime hydrologique de la région de Ouagadougou.")
        elif rule_id == 6:
            return ("Cette règle classifie automatiquement comme inondables toutes les zones dont l'altitude est inférieure à 290m. "
                    "Ces zones basses sont naturellement plus susceptibles de recevoir et d'accumuler l'eau en cas de précipitations importantes.")
        else:
            return f"Règle {rule_id}: {description}"
    
    def get_classes(self):
        """
        Récupère toutes les classes de l'ontologie.
        
        Returns:
            list: Liste des classes avec leurs informations
        """
        if not self.load_ontology():
            return []
            
        classes = []
        for cls in self.graph.subjects(RDF.type, OWL.Class):
            if isinstance(cls, URIRef) and cls.startswith(FLOOD_NS):
                class_info = {
                    "uri": str(cls),
                    "name": str(cls).split('#')[-1],
                    "label": self._get_label(cls),
                    "comment": self._get_comment(cls),
                    "subClassOf": [str(parent) for parent in self.graph.objects(cls, RDFS.subClassOf) 
                                  if isinstance(parent, URIRef)],
                    "individuals_count": len(list(self.graph.subjects(RDF.type, cls)))
                }
                classes.append(class_info)
        
        # Trier par nom
        classes.sort(key=lambda x: x["name"])
        return classes
    
    def get_object_properties(self):
        """
        Récupère toutes les propriétés d'objet de l'ontologie.
        
        Returns:
            list: Liste des propriétés d'objet avec leurs informations
        """
        if not self.load_ontology():
            return []
            
        properties = []
        for prop in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(prop, URIRef) and prop.startswith(FLOOD_NS):
                domains = [str(d) for d in self.graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
                ranges = [str(r) for r in self.graph.objects(prop, RDFS.range) if isinstance(r, URIRef)]
                
                prop_info = {
                    "uri": str(prop),
                    "name": str(prop).split('#')[-1],
                    "label": self._get_label(prop),
                    "comment": self._get_comment(prop),
                    "domain": domains,
                    "range": ranges,
                    "usage_count": len(list(self.graph.subject_objects(prop)))
                }
                properties.append(prop_info)
        
        # Trier par nom
        properties.sort(key=lambda x: x["name"])
        return properties
    
    def get_data_properties(self):
        """
        Récupère toutes les propriétés de données de l'ontologie.
        
        Returns:
            list: Liste des propriétés de données avec leurs informations
        """
        if not self.load_ontology():
            return []
            
        properties = []
        for prop in self.graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(prop, URIRef) and prop.startswith(FLOOD_NS):
                domains = [str(d) for d in self.graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
                ranges = [str(r) for r in self.graph.objects(prop, RDFS.range) if isinstance(r, URIRef)]
                
                prop_info = {
                    "uri": str(prop),
                    "name": str(prop).split('#')[-1],
                    "label": self._get_label(prop),
                    "comment": self._get_comment(prop),
                    "domain": domains,
                    "range": ranges,
                    "usage_count": len(list(self.graph.subject_objects(prop)))
                }
                properties.append(prop_info)
        
        # Trier par nom
        properties.sort(key=lambda x: x["name"])
        return properties
    
    def get_individuals(self, class_uri=None):
        """
        Récupère les individus de l'ontologie, éventuellement filtrés par classe.
        
        Args:
            class_uri (str, optional): URI de la classe pour filtrer les individus
            
        Returns:
            list: Liste des individus avec leurs informations
        """
        if not self.load_ontology():
            return []
            
        individuals = []
        
        if class_uri:
            # Filtrer par classe spécifique
            class_ref = URIRef(class_uri)
            for indiv in self.graph.subjects(RDF.type, class_ref):
                if isinstance(indiv, URIRef) and indiv.startswith(FLOOD_NS):
                    indiv_info = self._get_individual_info(indiv)
                    individuals.append(indiv_info)
        else:
            # Tous les individus, en excluant les classes
            for indiv in self.graph.subjects(RDF.type, None):
                if (isinstance(indiv, URIRef) and indiv.startswith(FLOOD_NS) and 
                    (indiv, RDF.type, OWL.Class) not in self.graph):
                    indiv_info = self._get_individual_info(indiv)
                    individuals.append(indiv_info)
        
        # Trier par nom
        individuals.sort(key=lambda x: x["name"])
        return individuals
    
    def get_inferred_knowledge(self):
        """
        Récupère les connaissances inférées de l'ontologie après raisonnement.
        
        Returns:
            dict: Statistiques et exemples de connaissances inférées
        """
        if not self.load_ontology():
            return {"error": "Impossible de charger l'ontologie"}
        
        # Exemples de types de connaissances inférées à rechercher
        inferred_flood_risks = []
        inferred_flood_prone = []
        inferred_early_warnings = []
        
        # Rechercher les triplets inférés liés aux risques d'inondation
        for subj, pred, obj in self.graph.triples((None, FLOOD_NS.hasFloodRisk, None)):
            if isinstance(subj, URIRef) and isinstance(obj, URIRef):
                risk_info = {
                    "area": str(subj).split('#')[-1],
                    "risk_level": str(obj).split('#')[-1]
                }
                inferred_flood_risks.append(risk_info)
        
        # Rechercher les zones classifiées comme inondables
        for subj, pred, obj in self.graph.triples((None, FLOOD_NS.isFloodProne, Literal(True))):
            if isinstance(subj, URIRef):
                area_info = {
                    "area": str(subj).split('#')[-1]
                }
                inferred_flood_prone.append(area_info)
        
        # Rechercher les alertes précoces
        for subj, pred, obj in self.graph.triples((None, FLOOD_NS.hasEarlyWarningStatus, None)):
            if isinstance(subj, URIRef) and isinstance(obj, URIRef):
                alert_info = {
                    "entity": str(subj).split('#')[-1],
                    "status": str(obj).split('#')[-1]
                }
                inferred_early_warnings.append(alert_info)
        
        # Construire le résultat
        result = {
            "flood_risks": {
                "count": len(inferred_flood_risks),
                "examples": inferred_flood_risks[:10]  # Limiter à 10 exemples
            },
            "flood_prone_areas": {
                "count": len(inferred_flood_prone),
                "examples": inferred_flood_prone[:10]
            },
            "early_warnings": {
                "count": len(inferred_early_warnings),
                "examples": inferred_early_warnings[:10]
            },
            "total_inferences": len(inferred_flood_risks) + len(inferred_flood_prone) + len(inferred_early_warnings)
        }
        
        return result
    
    def get_ontology_statistics(self):
        """
        Calcule des statistiques générales sur l'ontologie.
        
        Returns:
            dict: Statistiques de l'ontologie
        """
        if not self.load_ontology():
            return {"error": "Impossible de charger l'ontologie"}
        
        # Compter les différents éléments de l'ontologie
        class_count = len(list(self.graph.subjects(RDF.type, OWL.Class)))
        obj_prop_count = len(list(self.graph.subjects(RDF.type, OWL.ObjectProperty)))
        data_prop_count = len(list(self.graph.subjects(RDF.type, OWL.DatatypeProperty)))
        individual_count = len(list(self.graph.subjects(RDF.type, OWL.NamedIndividual)))
        
        # Compter les assertions
        obj_prop_assertions = 0
        data_prop_assertions = 0
        
        for s, p, o in self.graph:
            if p != RDF.type and isinstance(p, URIRef):
                if isinstance(o, URIRef):
                    obj_prop_assertions += 1
                elif isinstance(o, Literal):
                    data_prop_assertions += 1
        
        return {
            "classes": class_count,
            "object_properties": obj_prop_count,
            "data_properties": data_prop_count,
            "individuals": individual_count,
            "object_property_assertions": obj_prop_assertions,
            "data_property_assertions": data_prop_assertions,
            "total_triples": len(self.graph),
            "last_loaded": self.last_loaded.strftime("%Y-%m-%d %H:%M:%S") if self.last_loaded else None
        }
        
    def get_inference_explanation(self, zone_name, inferred_property):
        """
        Explique pourquoi une inférence particulière a été faite.
        
        Args:
            zone_name (str): Nom de la zone pour laquelle l'inférence a été faite
            inferred_property (str): Propriété inférée (ex: "HighRisk")
            
        Returns:
            dict: Explication de l'inférence avec les règles déclenchées et les faits utilisés
        """
        if not self.load_ontology() or not self.load_swrl_rules():
            return {"error": "Impossible de charger l'ontologie ou les règles"}
        
        # Initialiser l'expliqueur d'inférences si nécessaire
        if self.inference_explainer is None:
            self.inference_explainer = InferenceExplainer(self)
        
        # Appliquer les règles d'inférence pour s'assurer que toutes les inférences sont disponibles
        self._apply_rules()
        
        # Obtenir l'explication
        return self.inference_explainer.explain_inference(zone_name, inferred_property)
    
    def get_ontology_description(self):
        """
        Génère une description générale de l'ontologie.
        
        Returns:
            dict: Description de l'ontologie
        """
        if not self.load_ontology():
            return {"error": "Impossible de charger l'ontologie"}
        
        # Récupérer les informations de l'ontologie elle-même
        ontology_uri = None
        for s, p, o in self.graph.triples((None, RDF.type, OWL.Ontology)):
            if isinstance(s, URIRef):
                ontology_uri = s
                break
        
        if not ontology_uri:
            return {"error": "Informations sur l'ontologie non trouvées"}
        
        # Récupérer les métadonnées
        title = self._get_label(ontology_uri) or "Ontologie des inondations à Ouagadougou"
        description = self._get_comment(ontology_uri) or "Cette ontologie modélise les connaissances relatives aux inondations à Ouagadougou, Burkina Faso."
        
        # Description détaillée de l'ontologie
        details = (
            "Cette ontologie a été développée pour le système de prédiction des inondations à Ouagadougou. "
            "Elle modélise les connaissances sur les facteurs contribuant aux inondations, incluant les données "
            "météorologiques, hydrologiques et géographiques. L'ontologie permet d'intégrer ces informations "
            "et d'appliquer un raisonnement sémantique pour évaluer les risques d'inondation dans différentes "
            "zones de la ville et ses environs.\n\n"
            
            "Les principaux concepts modélisés comprennent:\n"
            "- Les entités géographiques (quartiers, zones à risque, cours d'eau)\n"
            "- Les phénomènes météorologiques (précipitations, humidité)\n"
            "- Les données hydrologiques (débits, niveaux d'eau)\n"
            "- Les infrastructures hydrauliques (barrages, stations de mesure)\n"
            "- Les niveaux de risque et les alertes d'inondation\n\n"
            
            "Cette ontologie est enrichie par un ensemble de règles SWRL qui permettent d'inférer "
            "automatiquement les niveaux de risque d'inondation en fonction des données disponibles."
        )
        
        return {
            "uri": str(ontology_uri),
            "title": title,
            "description": description,
            "details": details,
            "version": "1.0",
            "created": "2025-05-24"
        }
        
    def get_ontology_visualization_data(self):
        """
        Génère des données pour visualiser l'ontologie sous forme de graphe interactif.
        Inclut les classes, propriétés, individus et leurs relations.
        
        Returns:
            dict: Données pour la visualisation (nœuds et liens)
        """
        if not self.load_ontology():
            return {"error": "Impossible de charger l'ontologie"}
        
        nodes = []
        links = []
        node_ids = {}  # Pour éviter les doublons
        
        # Calculer l'importance des classes (pour la taille des nœuds)
        class_importance = {}
        for cls in self.graph.subjects(RDF.type, OWL.Class):
            if isinstance(cls, URIRef) and cls.startswith(FLOOD_NS):
                # Compter les sous-classes et les individus
                subclass_count = len(list(self.graph.subjects(RDFS.subClassOf, cls)))
                instances_count = len(list(self.graph.subjects(RDF.type, cls)))
                prop_count = len(list(self.graph.subjects(RDFS.domain, cls))) + len(list(self.graph.subjects(RDFS.range, cls)))
                
                # Calculer un score d'importance
                class_importance[cls] = 1 + (subclass_count * 0.5) + (instances_count * 0.3) + (prop_count * 0.2)
        
        # Ajouter les classes comme nœuds
        for cls in self.graph.subjects(RDF.type, OWL.Class):
            if isinstance(cls, URIRef) and cls.startswith(FLOOD_NS):
                class_name = str(cls).split('#')[-1]
                node_id = f"class_{class_name}"
                
                if node_id not in node_ids:
                    # Récupérer les informations supplémentaires
                    label = self._get_label(cls) or class_name
                    comment = self._get_comment(cls) or f"Classe {class_name}"
                    
                    # Déterminer l'importance (pour la taille visuelle)
                    importance = class_importance.get(cls, 1)
                    
                    nodes.append({
                        "id": node_id,
                        "name": class_name,
                        "label": label,
                        "description": comment,
                        "type": "class",
                        "value": importance  # Pour la taille du nœud
                    })
                    node_ids[node_id] = True
        
        # Ajouter les propriétés d'objet comme nœuds
        for prop in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(prop, URIRef) and prop.startswith(FLOOD_NS):
                prop_name = str(prop).split('#')[-1]
                node_id = f"prop_{prop_name}"
                
                if node_id not in node_ids:
                    # Récupérer les informations supplémentaires
                    label = self._get_label(prop) or prop_name
                    comment = self._get_comment(prop) or f"Propriété d'objet {prop_name}"
                    
                    nodes.append({
                        "id": node_id,
                        "name": prop_name,
                        "label": label,
                        "description": comment,
                        "type": "property",
                        "value": 0.7  # Taille plus petite que les classes
                    })
                    node_ids[node_id] = True
        
        # Ajouter un sous-ensemble d'individus (limiter pour éviter une surcharge visuelle)
        individuals_added = 0
        max_individuals = 30  # Limiter le nombre d'individus pour éviter un graphe trop dense
        
        for indiv in self.graph.subjects(RDF.type, OWL.NamedIndividual):
            if isinstance(indiv, URIRef) and indiv.startswith(FLOOD_NS) and individuals_added < max_individuals:
                indiv_name = str(indiv).split('#')[-1]
                node_id = f"indiv_{indiv_name}"
                
                if node_id not in node_ids:
                    # Trouver les types (classes) de cet individu
                    indiv_types = []
                    for type_uri in self.graph.objects(indiv, RDF.type):
                        if isinstance(type_uri, URIRef) and type_uri != OWL.NamedIndividual and type_uri.startswith(FLOOD_NS):
                            indiv_types.append(type_uri)
                    
                    # Ne l'ajouter que s'il a au moins un type intéressant
                    if indiv_types:
                        label = self._get_label(indiv) or indiv_name
                        comment = self._get_comment(indiv) or f"Individu {indiv_name}"
                        
                        nodes.append({
                            "id": node_id,
                            "name": indiv_name,
                            "label": label,
                            "description": comment,
                            "type": "individual",
                            "value": 0.5  # Plus petit que les classes et propriétés
                        })
                        node_ids[node_id] = True
                        individuals_added += 1
                        
                        # Ajouter les liens vers les classes (types)
                        for type_uri in indiv_types:
                            type_name = str(type_uri).split('#')[-1]
                            target_id = f"class_{type_name}"
                            
                            if target_id in node_ids:
                                links.append({
                                    "source": node_id,
                                    "target": target_id,
                                    "type": "instanceOf",
                                    "label": "est une instance de",
                                    "value": 1  # Épaisseur du lien
                                })
        
        # Ajouter les relations de sous-classe
        for cls, parent in self.graph.subject_objects(RDFS.subClassOf):
            if (isinstance(cls, URIRef) and isinstance(parent, URIRef) and 
                cls.startswith(FLOOD_NS) and parent.startswith(FLOOD_NS)):
                
                source_id = f"class_{str(cls).split('#')[-1]}"
                target_id = f"class_{str(parent).split('#')[-1]}"
                
                if source_id in node_ids and target_id in node_ids:
                    links.append({
                        "source": source_id,
                        "target": target_id,
                        "type": "subClassOf",
                        "label": "est un sous-type de",
                        "value": 2  # Lien plus épais pour les relations de hiérarchie
                    })
        
        # Ajouter les propriétés d'objet comme liens entre classes
        for prop in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(prop, URIRef) and prop.startswith(FLOOD_NS):
                prop_name = str(prop).split('#')[-1]
                prop_id = f"prop_{prop_name}"
                
                # Trouver le domaine et la plage de la propriété
                domains = list(self.graph.objects(prop, RDFS.domain))
                ranges = list(self.graph.objects(prop, RDFS.range))
                
                # Ajouter des liens du domaine à la propriété et de la propriété à la plage
                for domain in domains:
                    if isinstance(domain, URIRef) and domain.startswith(FLOOD_NS):
                        domain_id = f"class_{str(domain).split('#')[-1]}"
                        if domain_id in node_ids and prop_id in node_ids:
                            links.append({
                                "source": domain_id,
                                "target": prop_id,
                                "type": "hasDomain",
                                "label": "a pour domaine",
                                "value": 1.5
                            })
                
                for range_cls in ranges:
                    if isinstance(range_cls, URIRef) and range_cls.startswith(FLOOD_NS):
                        range_id = f"class_{str(range_cls).split('#')[-1]}"
                        if prop_id in node_ids and range_id in node_ids:
                            links.append({
                                "source": prop_id,
                                "target": range_id,
                                "type": "hasRange",
                                "label": "a pour co-domaine",
                                "value": 1.5
                            })
        
        # Ajouter des liens entre individus basés sur les propriétés d'objet
        for s, p, o in self.graph.triples((None, None, None)):
            if (isinstance(s, URIRef) and isinstance(p, URIRef) and isinstance(o, URIRef) and
                s.startswith(FLOOD_NS) and p.startswith(FLOOD_NS) and o.startswith(FLOOD_NS)):
                
                # Vérifier si s et o sont des individus et p est une propriété d'objet
                # Utiliser graph.triples() au lieu de graph.value() pour éviter l'erreur UnboundLocalError
                is_s_individual = len(list(self.graph.triples((s, RDF.type, OWL.NamedIndividual)))) > 0
                is_o_individual = len(list(self.graph.triples((o, RDF.type, OWL.NamedIndividual)))) > 0
                is_p_property = len(list(self.graph.triples((p, RDF.type, OWL.ObjectProperty)))) > 0
                
                if is_s_individual and is_o_individual and is_p_property:
                    
                    source_id = f"indiv_{str(s).split('#')[-1]}"
                    target_id = f"indiv_{str(o).split('#')[-1]}"
                    prop_name = str(p).split('#')[-1]
                    
                    if source_id in node_ids and target_id in node_ids:
                        links.append({
                            "source": source_id,
                            "target": target_id,
                            "type": "objectPropertyAssertion",
                            "label": prop_name,
                            "value": 1
                        })
        
        for s, p, o in self.graph.triples((None, RDF.type, OWL.Ontology)):
            if isinstance(s, URIRef):
                ontology_uri = s
                break
        
        if not ontology_uri:
            return {"error": "Informations sur l'ontologie non trouvées"}
        
        # Récupérer les métadonnées
        title = self._get_label(ontology_uri) or "Ontologie des inondations à Ouagadougou"
        description = self._get_comment(ontology_uri) or "Cette ontologie modélise les connaissances relatives aux inondations à Ouagadougou, Burkina Faso."
        
        # Description détaillée de l'ontologie
        details = (
            "Cette ontologie a été développée pour le système de prédiction des inondations à Ouagadougou. "
            "Elle modélise les connaissances sur les facteurs contribuant aux inondations, incluant les données "
            "météorologiques, hydrologiques et géographiques. L'ontologie permet d'intégrer ces informations "
            "et d'appliquer un raisonnement sémantique pour évaluer les risques d'inondation dans différentes "
            "zones de la ville et ses environs.\n\n"
            
            "Les principaux concepts modélisés comprennent:\n"
            "- Les entités géographiques (quartiers, zones à risque, cours d'eau)\n"
            "- Les phénomènes météorologiques (précipitations, humidité)\n"
            "- Les données hydrologiques (débits, niveaux d'eau)\n"
            "- Les infrastructures hydrauliques (barrages, stations de mesure)\n"
            "- Les niveaux de risque et les alertes d'inondation\n\n"
            
            "Cette ontologie est enrichie par un ensemble de règles SWRL qui permettent d'inférer "
            "automatiquement les niveaux de risque d'inondation en fonction des données disponibles."
        )
        
        return {
            "uri": str(ontology_uri),
            "title": title,
            "description": description,
            "details": details,
            "version": "1.0",
            "created": "2025-05-24"
        }
    
    def _get_label(self, uri):
        """Récupère le label d'un élément."""
        for label in self.graph.objects(uri, RDFS.label):
            return str(label)
        return None
    
    def _get_comment(self, uri):
        """Récupère le commentaire d'un élément."""
        for comment in self.graph.objects(uri, RDFS.comment):
            return str(comment)
        return None
    
    def _apply_rules(self):
        """
        Applique les règles SWRL pour inférer de nouvelles connaissances.
        
        Returns:
            bool: True si les règles ont été appliquées avec succès, False sinon
        """
        try:
            # Assurez-vous que l'ontologie est chargée
            if not self.load_ontology():
                return False
            
            # Applique le raisonnement OWL
            logger.info("Application du raisonnement sur l'ontologie...")
            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(self.graph)
            
            # Ici, vous pourriez éventuellement implémenter un moteur de règles SWRL personnalisé
            # Pour l'instant, nous nous reposons sur le raisonnement OWL de base
            
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'application des règles: {str(e)}")
            return False
    
    def _get_individual_info(self, indiv):
        """Récupère les informations d'un individu."""
        # Récupérer les types de l'individu
        types = []
        for type_uri in self.graph.objects(indiv, RDF.type):
            if isinstance(type_uri, URIRef) and type_uri != OWL.NamedIndividual:
                types.append(str(type_uri))
        
        # Récupérer les propriétés de l'individu
        properties = []
        for p, o in self.graph.predicate_objects(indiv):
            if isinstance(p, URIRef) and p not in [RDF.type, RDFS.label, RDFS.comment]:
                prop_value = str(o)
                if isinstance(o, Literal):
                    prop_value = o.value if hasattr(o, 'value') else str(o)
                elif isinstance(o, URIRef):
                    prop_value = str(o).split('#')[-1]
                
                properties.append({
                    "property": str(p).split('#')[-1],
                    "value": prop_value
                })
        
        return {
            "uri": str(indiv),
            "name": str(indiv).split('#')[-1],
            "label": self._get_label(indiv),
            "comment": self._get_comment(indiv),
            "types": types,
            "properties": properties
        }
