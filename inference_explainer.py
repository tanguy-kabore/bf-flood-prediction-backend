"""
Module pour l'explication des inférences générées par l'ontologie.
"""

from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL

# Namespace de l'ontologie des inondations
FLOOD_NS = Namespace("http://www.semanticweb.org/ontologies/2025/ouagadougou-flood-prediction#")

class InferenceExplainer:
    """Classe pour expliquer les inférences de l'ontologie."""
    
    def __init__(self, ontology_explorer):
        """
        Initialise l'expliqueur d'inférences.
        
        Args:
            ontology_explorer: Instance de OntologyExplorer
        """
        self.ontology_explorer = ontology_explorer
    
    def explain_inference(self, zone_name, inferred_property):
        """
        Explique pourquoi une inférence particulière a été faite.
        
        Args:
            zone_name (str): Nom de la zone pour laquelle l'inférence a été faite
            inferred_property (str): Propriété inférée (ex: "HighRisk")
            
        Returns:
            dict: Explication de l'inférence avec les règles déclenchées et les faits utilisés
        """
        graph = self.ontology_explorer.graph
        rules = self.ontology_explorer.rules
        
        if not graph or not rules:
            return {"error": "Ontologie ou règles non chargées"}
        
        # Créer l'URI de la zone
        zone_uri = URIRef(f"{FLOOD_NS}{zone_name}")
        
        # Vérifier que la zone existe
        if (zone_uri, RDF.type, FLOOD_NS.Zone) not in graph:
            return {"error": f"La zone '{zone_name}' n'existe pas dans l'ontologie"}
        
        # Structure pour stocker l'explication
        explanation = {
            "entity": zone_name,
            "inferred_property": inferred_property,
            "triggered_rules": [],
            "contributing_facts": [],
            "path_of_inference": []
        }
        
        # Trouver la règle qui a été déclenchée pour cette inférence
        # Analyser chaque règle SWRL pour voir si elle pourrait avoir produit cette inférence
        relevant_rules = []
        
        # Adapter la recherche de règles pertinentes selon la propriété inférée
        property_mapping = {
            "HighRisk": ["HighRisk", "High_Risk", "High Risk"],
            "MediumRisk": ["MediumRisk", "Medium_Risk", "Medium Risk"],
            "LowRisk": ["LowRisk", "Low_Risk", "Low Risk"]
        }
        
        # Obtenir toutes les variantes possibles de la propriété inférée
        property_variants = property_mapping.get(inferred_property, [inferred_property])
        
        print(f"Recherche de règles pour la propriété: {inferred_property}")
        print(f"Variantes recherchées: {property_variants}")
        print(f"Nombre total de règles à vérifier: {len(rules)}")
        
        for rule in rules:
            rule_text = rule.get("rule_text", "")
            # Vérifier si la règle contient hasRiskLevel et une des variantes de la propriété
            if "hasRiskLevel" in rule_text and any(variant in rule_text for variant in property_variants):
                print(f"Règle trouvée: {rule.get('rule_id')}")
                relevant_rules.append(rule)
                explanation["triggered_rules"].append({
                    "rule_id": rule.get("rule_id"),
                    "rule_text": rule_text,
                    "description": rule.get("description")
                })
        
        print(f"Règles pertinentes trouvées: {len(relevant_rules)}")
        
        # Si aucune règle n'est trouvée avec la méthode stricte, essayons une approche plus souple
        if not relevant_rules:
            print("Aucune règle trouvée avec la méthode stricte, essai d'une méthode plus souple")
            for rule in rules:
                rule_text = rule.get("rule_text", "")
                # Chercher juste les règles qui mentionnent hasRiskLevel
                if "hasRiskLevel" in rule_text and "HighRisk" in rule_text:
                    print(f"Règle trouvée (méthode souple): {rule.get('rule_id')}")
                    explanation["triggered_rules"].append({
                        "rule_id": rule.get("rule_id"),
                        "rule_text": rule_text,
                        "description": rule.get("description")
                    })
        
        # Récupérer les faits concernant cette zone qui ont pu contribuer à l'inférence
        for s, p, o in graph.triples((zone_uri, None, None)):
            if p != URIRef(f"{FLOOD_NS}hasRiskLevel"): # Exclure la propriété inférée elle-même
                pred_name = str(p).split('#')[-1]
                obj_name = str(o).split('#')[-1] if isinstance(o, URIRef) else str(o)
                
                explanation["contributing_facts"].append({
                    "predicate": pred_name,
                    "object": obj_name
                })
        
        # Reconstituer le chemin d'inférence (simplifié)
        # Nous essayons de déterminer quels facteurs spécifiques ont conduit à la conclusion
        if inferred_property == "HighRisk":
            rainfall_data = self._get_fact_value(graph, zone_uri, FLOOD_NS.hasRainfall)
            drainage_data = self._get_fact_value(graph, zone_uri, FLOOD_NS.hasDrainageCapacity)
            elevation_data = self._get_fact_value(graph, zone_uri, FLOOD_NS.hasElevation)
            proximity_data = self._get_fact_value(graph, zone_uri, FLOOD_NS.hasProximityToWater)
            
            if rainfall_data:
                try:
                    if float(rainfall_data) > 100:
                        explanation["path_of_inference"].append({
                            "factor": "Précipitations élevées",
                            "value": str(rainfall_data),
                            "threshold": "100",
                            "contribution": "Forte"
                        })
                except (ValueError, TypeError):
                    pass
            
            if drainage_data:
                try:
                    if float(drainage_data) < 30:
                        explanation["path_of_inference"].append({
                            "factor": "Faible capacité de drainage",
                            "value": str(drainage_data),
                            "threshold": "30",
                            "contribution": "Forte"
                        })
                except (ValueError, TypeError):
                    pass
            
            if elevation_data:
                try:
                    if float(elevation_data) < 10:
                        explanation["path_of_inference"].append({
                            "factor": "Faible élévation",
                            "value": str(elevation_data),
                            "threshold": "10",
                            "contribution": "Moyenne"
                        })
                except (ValueError, TypeError):
                    pass
            
            if proximity_data:
                try:
                    if float(proximity_data) < 500:
                        explanation["path_of_inference"].append({
                            "factor": "Proximité d'un cours d'eau",
                            "value": str(proximity_data),
                            "threshold": "500",
                            "contribution": "Forte"
                        })
                except (ValueError, TypeError):
                    pass
        
        return explanation
    
    def _get_fact_value(self, graph, subject, predicate):
        """
        Récupère la valeur d'un fait (triplet) spécifique.
        
        Args:
            graph: Le graphe RDF
            subject (URIRef): Sujet du triplet
            predicate (URIRef): Prédicat du triplet
            
        Returns:
            str: Valeur du fait, ou None si le fait n'existe pas
        """
        for _, _, value in graph.triples((subject, predicate, None)):
            if isinstance(value, Literal):
                return str(value)
            elif isinstance(value, URIRef):
                return str(value).split('#')[-1]
        return None
