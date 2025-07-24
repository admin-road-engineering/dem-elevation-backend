"""
Policy-Based Dataset Selector - Phase 3 Foundation
Extends Phase 2 with configurable selection policies for different use cases
"""
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .smart_dataset_selector import SmartDatasetSelector, DatasetMatch

logger = logging.getLogger(__name__)

class SelectionPolicy(Enum):
    """Available dataset selection policies"""
    FASTEST = "fastest"      # Prioritize resolution and local sources (current Phase 2 behavior)
    CHEAPEST = "cheapest"    # Prioritize lowest cost_per_query sources
    BALANCED = "balanced"    # Balance cost and performance
    QUALITY = "quality"      # Prioritize highest accuracy regardless of cost

@dataclass
class PolicyWeights:
    """Configurable weights for confidence scoring"""
    bounds_overlap: float = 0.4      # Base geographic bounds matching
    bounds_specificity: float = 0.4  # Bonus for tight, specific bounds
    center_proximity: float = 0.2    # Distance from dataset center
    resolution_preference: float = 0.2  # Resolution quality
    data_type_quality: float = 0.1   # LiDAR vs DEM preference
    provider_reliability: float = 0.05  # Provider trust score
    cost_efficiency: float = 0.0     # Cost consideration (varies by policy)
    
    def normalize(self) -> 'PolicyWeights':
        """Ensure weights don't exceed 1.0 total"""
        total = (self.bounds_overlap + self.bounds_specificity + 
                self.center_proximity + self.resolution_preference + 
                self.data_type_quality + self.provider_reliability + 
                self.cost_efficiency)
        
        if total > 1.0:
            # Scale down proportionally
            factor = 1.0 / total
            return PolicyWeights(
                bounds_overlap=self.bounds_overlap * factor,
                bounds_specificity=self.bounds_specificity * factor,
                center_proximity=self.center_proximity * factor,
                resolution_preference=self.resolution_preference * factor,
                data_type_quality=self.data_type_quality * factor,
                provider_reliability=self.provider_reliability * factor,
                cost_efficiency=self.cost_efficiency * factor
            )
        return self

class PolicyBasedSelector:
    """
    Enhanced dataset selector with configurable policies for different use cases.
    
    Builds on Phase 2 smart selection with policy-driven optimization:
    - FASTEST: Current Phase 2 behavior (resolution + performance priority)
    - CHEAPEST: Cost-optimized selection for budget-conscious queries  
    - BALANCED: Optimal cost/performance trade-off
    - QUALITY: Highest accuracy regardless of cost
    """
    
    def __init__(self, config_dir: Path = None, policy: SelectionPolicy = SelectionPolicy.FASTEST):
        self.config_dir = config_dir or Path(__file__).parent.parent / "config"
        self.policy = policy
        self.smart_selector = SmartDatasetSelector(self.config_dir)
        self.policy_weights = self._get_policy_weights(policy)
        
        logger.info(f"Initialized policy-based selector with {policy.value} policy")
    
    def _get_policy_weights(self, policy: SelectionPolicy) -> PolicyWeights:
        """Get optimized weights for the specified policy"""
        if policy == SelectionPolicy.FASTEST:
            return PolicyWeights(
                bounds_overlap=0.4,
                bounds_specificity=0.4,
                center_proximity=0.2,
                resolution_preference=0.2,
                data_type_quality=0.1,
                provider_reliability=0.05,
                cost_efficiency=0.0
            ).normalize()
        
        elif policy == SelectionPolicy.CHEAPEST:
            return PolicyWeights(
                bounds_overlap=0.3,
                bounds_specificity=0.2,
                center_proximity=0.1,
                resolution_preference=0.05,
                data_type_quality=0.05,
                provider_reliability=0.05,
                cost_efficiency=0.25  # Major cost consideration
            ).normalize()
        
        elif policy == SelectionPolicy.BALANCED:
            return PolicyWeights(
                bounds_overlap=0.35,
                bounds_specificity=0.3,
                center_proximity=0.15,
                resolution_preference=0.15,
                data_type_quality=0.08,
                provider_reliability=0.05,
                cost_efficiency=0.12  # Moderate cost consideration
            ).normalize()
        
        elif policy == SelectionPolicy.QUALITY:
            return PolicyWeights(
                bounds_overlap=0.3,
                bounds_specificity=0.2,
                center_proximity=0.1,
                resolution_preference=0.3,  # High resolution priority
                data_type_quality=0.2,     # Strong data type preference
                provider_reliability=0.1,  # Provider reliability important
                cost_efficiency=0.0        # Cost not a factor
            ).normalize()
        
        else:
            # Default to FASTEST
            return self._get_policy_weights(SelectionPolicy.FASTEST)
    
    def calculate_enhanced_confidence(self, latitude: float, longitude: float, 
                                    dataset_info: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        """
        Calculate confidence score using policy-specific weights with detailed breakdown.
        
        Returns:
            Tuple of (total_confidence, score_breakdown)
        """
        scores = {}
        
        # 1. Geographic bounds matching
        bounds = dataset_info.get("bounds", {})
        if bounds and bounds.get("type") == "bbox":
            min_lat = bounds.get("min_lat", 999)
            max_lat = bounds.get("max_lat", -999)
            min_lon = bounds.get("min_lon", 999)
            max_lon = bounds.get("max_lon", -999)
            
            if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
                # Base bounds score
                scores["bounds_overlap"] = self.policy_weights.bounds_overlap
                
                # Specificity bonus
                lat_range = max_lat - min_lat
                lon_range = max_lon - min_lon
                if lat_range < 2.0 and lon_range < 2.0:
                    scores["bounds_specificity"] = self.policy_weights.bounds_specificity
                elif lat_range < 5.0 and lon_range < 5.0:
                    scores["bounds_specificity"] = self.policy_weights.bounds_specificity * 0.5
                else:
                    scores["bounds_specificity"] = 0.0
                
                # Center proximity bonus
                center_lat = (min_lat + max_lat) / 2
                center_lon = (min_lon + max_lon) / 2
                lat_distance = abs(latitude - center_lat)
                lon_distance = abs(longitude - center_lon)
                
                if lat_distance < lat_range * 0.25 and lon_distance < lon_range * 0.25:
                    scores["center_proximity"] = self.policy_weights.center_proximity
                elif lat_distance < lat_range * 0.5 and lon_distance < lon_range * 0.5:
                    scores["center_proximity"] = self.policy_weights.center_proximity * 0.5
                else:
                    scores["center_proximity"] = 0.0
            else:
                # Outside bounds - no confidence
                return 0.0, {"reason": "coordinate_outside_bounds"}
        else:
            scores["bounds_overlap"] = 0.0
            scores["bounds_specificity"] = 0.0
            scores["center_proximity"] = 0.0
        
        # 2. Resolution preference
        resolution_m = dataset_info.get("resolution_m", 30)
        if resolution_m <= 1.0:
            scores["resolution_preference"] = self.policy_weights.resolution_preference
        elif resolution_m <= 5.0:
            scores["resolution_preference"] = self.policy_weights.resolution_preference * 0.5
        else:
            scores["resolution_preference"] = 0.0
        
        # 3. Data type quality
        data_type = dataset_info.get("data_type", "").lower()
        if "lidar" in data_type:
            scores["data_type_quality"] = self.policy_weights.data_type_quality
        elif "dem" in data_type:
            scores["data_type_quality"] = self.policy_weights.data_type_quality * 0.5
        else:
            scores["data_type_quality"] = 0.0
        
        # 4. Provider reliability
        provider = dataset_info.get("provider", "").lower()
        if any(trusted in provider for trusted in ["elvis", "ga", "linz"]):
            scores["provider_reliability"] = self.policy_weights.provider_reliability
        else:
            scores["provider_reliability"] = 0.0
        
        # 5. Cost efficiency (policy-dependent)
        if self.policy_weights.cost_efficiency > 0:
            cost_per_query = dataset_info.get("cost_per_query", 0.1)  # Default moderate cost
            if cost_per_query <= 0.001:
                scores["cost_efficiency"] = self.policy_weights.cost_efficiency
            elif cost_per_query <= 0.01:
                scores["cost_efficiency"] = self.policy_weights.cost_efficiency * 0.5
            else:
                scores["cost_efficiency"] = 0.0
        else:
            scores["cost_efficiency"] = 0.0
        
        total_confidence = sum(scores.values())
        return min(total_confidence, 1.0), scores
    
    def select_datasets_with_policy(self, latitude: float, longitude: float) -> List[Dict[str, Any]]:
        """
        Select datasets using policy-based confidence scoring with detailed explanations.
        
        Returns enhanced dataset matches with confidence breakdowns and policy explanations.
        """
        if not self.smart_selector.grouped_index or "datasets" not in self.smart_selector.grouped_index:
            logger.warning("No grouped index available for policy-based selection")
            return []
        
        enhanced_matches = []
        datasets = self.smart_selector.grouped_index["datasets"]
        
        for dataset_id, dataset_info in datasets.items():
            confidence, score_breakdown = self.calculate_enhanced_confidence(
                latitude, longitude, dataset_info
            )
            
            if confidence > 0.0:
                enhanced_matches.append({
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_info.get("name", dataset_id),
                    "confidence_score": confidence,
                    "score_breakdown": score_breakdown,
                    "priority": dataset_info.get("priority", 99),
                    "file_count": dataset_info.get("file_count", 0),
                    "cost_per_query": dataset_info.get("cost_per_query", 0.0),
                    "resolution_m": dataset_info.get("resolution_m"),
                    "accuracy": dataset_info.get("accuracy", "Unknown"),
                    "policy_recommendation": self._get_policy_recommendation(confidence, dataset_info)
                })
        
        # Sort by confidence score (highest first), then by priority (lowest first)
        enhanced_matches.sort(key=lambda x: (-x["confidence_score"], x["priority"]))
        
        logger.info(f"Policy-based selection ({self.policy.value}) found {len(enhanced_matches)} datasets for ({latitude}, {longitude})")
        
        return enhanced_matches
    
    def _get_policy_recommendation(self, confidence: float, dataset_info: Dict[str, Any]) -> str:
        """Generate policy-specific recommendation text"""
        if self.policy == SelectionPolicy.FASTEST:
            if confidence > 0.8:
                return "Excellent choice - high resolution, trusted provider, precise geographic match"
            elif confidence > 0.6:
                return "Good choice - adequate resolution and geographic coverage"
            else:
                return "Acceptable fallback - limited geographic specificity"
        
        elif self.policy == SelectionPolicy.CHEAPEST:
            cost = dataset_info.get("cost_per_query", 0.1)
            if cost <= 0.001:
                return f"Cost-optimal choice - ${cost}/query with acceptable quality"
            else:
                return f"Higher cost option - ${cost}/query but better coverage"
        
        elif self.policy == SelectionPolicy.BALANCED:
            cost = dataset_info.get("cost_per_query", 0.1)
            resolution = dataset_info.get("resolution_m", 30)
            return f"Balanced choice - {resolution}m resolution at ${cost}/query"
        
        elif self.policy == SelectionPolicy.QUALITY:
            accuracy = dataset_info.get("accuracy", "Unknown")
            resolution = dataset_info.get("resolution_m", 30)
            return f"Quality-focused choice - {accuracy} accuracy, {resolution}m resolution"
        
        return "Standard selection"
    
    def get_policy_explanation(self) -> Dict[str, Any]:
        """Get detailed explanation of current policy and weights"""
        return {
            "current_policy": self.policy.value,
            "description": self._get_policy_description(),
            "confidence_weights": {
                "bounds_overlap": self.policy_weights.bounds_overlap,
                "bounds_specificity": self.policy_weights.bounds_specificity,
                "center_proximity": self.policy_weights.center_proximity,
                "resolution_preference": self.policy_weights.resolution_preference,
                "data_type_quality": self.policy_weights.data_type_quality,
                "provider_reliability": self.policy_weights.provider_reliability,
                "cost_efficiency": self.policy_weights.cost_efficiency
            },
            "confidence_threshold": 0.8,
            "use_case": self._get_use_case_examples()
        }
    
    def _get_policy_description(self) -> str:
        """Get human-readable policy description"""
        descriptions = {
            SelectionPolicy.FASTEST: "Optimizes for query speed and data quality, prioritizing high-resolution local sources",
            SelectionPolicy.CHEAPEST: "Minimizes cost per query while maintaining acceptable data quality",
            SelectionPolicy.BALANCED: "Balances cost efficiency with performance and quality",
            SelectionPolicy.QUALITY: "Prioritizes highest accuracy and resolution regardless of cost"
        }
        return descriptions.get(self.policy, "Standard dataset selection")
    
    def _get_use_case_examples(self) -> List[str]:
        """Get example use cases for current policy"""
        use_cases = {
            SelectionPolicy.FASTEST: [
                "Real-time engineering applications",
                "Interactive mapping and visualization", 
                "High-frequency API usage",
                "Performance-critical integrations"
            ],
            SelectionPolicy.CHEAPEST: [
                "Batch processing large areas",
                "Cost-sensitive applications",
                "Educational or research use",
                "Budget-constrained projects"
            ],
            SelectionPolicy.BALANCED: [
                "General-purpose applications",
                "Mixed usage patterns",
                "Production systems with cost awareness",
                "Default recommendation for most users"
            ],
            SelectionPolicy.QUALITY: [
                "Precision engineering calculations",
                "Scientific research",
                "Regulatory compliance",
                "Mission-critical applications"
            ]
        }
        return use_cases.get(self.policy, ["General dataset selection"])