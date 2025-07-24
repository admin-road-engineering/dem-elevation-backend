"""
Dataset Management Endpoints - Phase 2 Enhancement
Provides transparency into the grouped dataset architecture
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
from ...campaign_dataset_selector import CampaignDatasetSelector
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/campaigns", summary="List all available campaigns (Phase 3)")
async def get_datasets() -> Dict[str, Any]:
    """
    Get comprehensive information about all available datasets in the grouped spatial index.
    
    This endpoint provides transparency into the Phase 2 Grouped Dataset Architecture,
    showing how the 631,556+ files are organized into distinct datasets for efficient querying.
    
    Returns:
        Dict containing dataset catalog with metadata, file counts, and performance metrics
    """
    try:
        config_dir = Path(__file__).parent.parent.parent / "config"
        smart_selector = CampaignDatasetSelector(config_dir)
        
        # Get performance statistics
        perf_stats = smart_selector.get_performance_stats()
        
        # Build detailed dataset information
        datasets = []
        if smart_selector.grouped_index and "datasets" in smart_selector.grouped_index:
            for dataset_id, dataset_info in smart_selector.grouped_index["datasets"].items():
                datasets.append({
                    "id": dataset_id,
                    "name": dataset_info.get("name", dataset_id),
                    "provider": dataset_info.get("provider", "Unknown"),
                    "data_type": dataset_info.get("data_type", "Unknown"),
                    "resolution_m": dataset_info.get("resolution_m"),
                    "accuracy": dataset_info.get("accuracy", "Unknown"),
                    "file_count": dataset_info.get("file_count", 0),
                    "priority": dataset_info.get("priority", 99),
                    "bounds": dataset_info.get("bounds", {}),
                    "metadata": {
                        "capture_date": dataset_info.get("metadata", {}).get("capture_date"),
                        "point_density": dataset_info.get("metadata", {}).get("point_density"),
                        "vertical_datum": dataset_info.get("metadata", {}).get("vertical_datum"),
                        "color": dataset_info.get("metadata", {}).get("color"),
                        "opacity": dataset_info.get("metadata", {}).get("opacity")
                    }
                })
        
        # Sort by priority (lower = higher priority) then by file count
        datasets.sort(key=lambda x: (x["priority"], -x["file_count"]))
        
        return {
            "phase": "Phase 2 - Grouped Dataset Architecture",
            "index_timestamp": smart_selector.grouped_index.get("index_timestamp"),
            "total_datasets": len(datasets),
            "total_files": perf_stats.get("total_files", 0),
            "performance_metrics": {
                "average_files_per_dataset": perf_stats.get("average_files_per_dataset", 0),
                "largest_dataset": perf_stats.get("largest_dataset"),
                "smallest_dataset": perf_stats.get("smallest_dataset"),
                "architecture_benefit": "O(k) targeted search vs O(n) flat search where k << n"
            },
            "datasets": datasets,
            "selection_logic": {
                "confidence_threshold": 0.8,
                "max_datasets_searched": 3,
                "confidence_factors": [
                    "Geographic bounds matching (0.4 base + up to 0.6 for specificity)",
                    "Distance from dataset center (up to 0.2 bonus)",
                    "Resolution preference (up to 0.2 bonus)",
                    "Data type quality (up to 0.1 bonus)",
                    "Provider reliability (up to 0.05 bonus)"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Error retrieving dataset information: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve dataset information: {str(e)}")

@router.get("/datasets/{dataset_id}", summary="Get detailed information about a specific dataset")
async def get_dataset_details(dataset_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific dataset.
    
    Args:
        dataset_id: The ID of the dataset to retrieve
        
    Returns:
        Detailed dataset information including sample files
    """
    try:
        config_dir = Path(__file__).parent.parent.parent / "config"
        smart_selector = CampaignDatasetSelector(config_dir)
        
        if not smart_selector.grouped_index or "datasets" not in smart_selector.grouped_index:
            raise HTTPException(status_code=404, detail="No dataset index available")
        
        dataset_info = smart_selector.grouped_index["datasets"].get(dataset_id)
        if not dataset_info:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
        
        # Get sample files (first 5)
        files = dataset_info.get("files", [])
        sample_files = files[:5] if len(files) > 5 else files
        
        return {
            "id": dataset_id,
            "name": dataset_info.get("name", dataset_id),
            "provider": dataset_info.get("provider", "Unknown"),
            "data_type": dataset_info.get("data_type", "Unknown"),
            "source_type": dataset_info.get("source_type", "Unknown"),
            "path": dataset_info.get("path", "Unknown"),
            "crs": dataset_info.get("crs", "Unknown"),
            "resolution_m": dataset_info.get("resolution_m"),
            "accuracy": dataset_info.get("accuracy", "Unknown"),
            "priority": dataset_info.get("priority", 99),
            "bounds": dataset_info.get("bounds", {}),
            "file_statistics": {
                "total_files": len(files),
                "sample_files_shown": len(sample_files),
                "coverage_area": f"Geographic bounds: {dataset_info.get('bounds', {})}"
            },
            "metadata": dataset_info.get("metadata", {}),
            "sample_files": sample_files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving dataset details for '{dataset_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve dataset details: {str(e)}")

@router.get("/datasets/performance/benchmark", summary="Get Phase 2 performance benchmark results")
async def get_performance_benchmark() -> Dict[str, Any]:
    """
    Get the latest Phase 2 performance benchmark results comparing grouped vs flat search.
    
    Returns:
        Performance benchmark results with speedup metrics and target achievements
    """
    try:
        config_dir = Path(__file__).parent.parent.parent / "config"
        benchmark_file = config_dir / "phase2_performance_benchmark.json"
        
        if not benchmark_file.exists():
            raise HTTPException(status_code=404, detail="Performance benchmark results not found")
        
        import json
        with open(benchmark_file, 'r') as f:
            benchmark_data = json.load(f)
        
        return {
            "phase": "Phase 2 - Grouped Dataset Architecture",
            "benchmark_summary": benchmark_data.get("overall_performance", {}),
            "test_locations": len(benchmark_data.get("individual_results", [])),
            "key_achievements": {
                "average_speedup": f"{benchmark_data.get('overall_performance', {}).get('average_speedup', 0)}x",
                "maximum_speedup": f"{benchmark_data.get('overall_performance', {}).get('max_speedup', 0)}x",
                "search_reduction": f"{benchmark_data.get('overall_performance', {}).get('average_search_reduction', 0)}x fewer files",
                "architecture_benefit": "Transformed from O(n) flat search to O(k) targeted search"
            },
            "target_assessment": benchmark_data.get("overall_performance", {}).get("target_achievements", {}),
            "detailed_results": benchmark_data.get("individual_results", []),
            "benchmark_timestamp": benchmark_data.get("benchmark_timestamp")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving performance benchmark: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve performance benchmark: {str(e)}")

@router.get("/datasets/performance/outliers", summary="Get performance outlier analysis")
async def get_performance_outlier_analysis() -> Dict[str, Any]:
    """
    Get comprehensive analysis of performance outliers and dataset selection patterns.
    
    This endpoint provides insights into why certain locations have different performance
    characteristics, helping identify optimization opportunities for Phase 3.
    
    Returns:
        Detailed analysis of performance patterns across key locations
    """
    try:
        config_dir = Path(__file__).parent.parent.parent / "config"
        analysis_file = config_dir / "performance_outlier_analysis.json"
        
        if not analysis_file.exists():
            raise HTTPException(status_code=404, detail="Performance outlier analysis not found. Run analyze_performance_outliers.py script first.")
        
        import json
        with open(analysis_file, 'r') as f:
            analysis_data = json.load(f)
        
        # Extract key patterns and insights
        excellent_performers = []
        poor_performers = []
        
        for location, data in analysis_data.items():
            speedup = data.get("performance_analysis", {}).get("speedup_factor", 0)
            if speedup >= 50:
                excellent_performers.append({
                    "location": location,
                    "speedup": speedup,
                    "reason": data.get("performance_analysis", {}).get("explanation", "")
                })
            elif speedup < 10:
                poor_performers.append({
                    "location": location,
                    "speedup": speedup,
                    "reason": data.get("performance_analysis", {}).get("explanation", ""),
                    "optimization_opportunity": data.get("optimization_opportunities", [""])[0]
                })
        
        return {
            "analysis_summary": {
                "total_locations_analyzed": len(analysis_data),
                "excellent_performers": excellent_performers,
                "poor_performers": poor_performers,
                "common_patterns": {
                    "excellent": "Small, geographically specific datasets (< 5k files)",
                    "poor": "Large datasets (>100k files) or multiple dataset searches"
                }
            },
            "phase3_recommendations": [
                "Subdivide large datasets (QLD, NSW) by metro regions",
                "Implement Brisbane/Sydney/Melbourne specific subdatasets", 
                "Add geographic proximity weighting to confidence scoring",
                "Consider population density as dataset subdivision factor"
            ],
            "detailed_analysis": analysis_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving outlier analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve outlier analysis: {str(e)}")

@router.post("/datasets/query/preview", summary="Preview which datasets would be selected for a coordinate")
async def preview_dataset_selection(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Preview which datasets would be selected for a given coordinate without executing the search.
    
    This is useful for understanding the smart selection logic and debugging performance.
    
    Args:
        latitude: Point latitude in WGS84
        longitude: Point longitude in WGS84
        
    Returns:
        Dataset selection preview with confidence scores and reasoning
    """
    try:
        config_dir = Path(__file__).parent.parent.parent / "config"
        smart_selector = CampaignDatasetSelector(config_dir)
        
        # Get dataset matches with confidence scores
        dataset_matches = smart_selector.select_datasets_for_coordinate(latitude, longitude)
        
        if not dataset_matches:
            return {
                "coordinate": {"latitude": latitude, "longitude": longitude},
                "selected_datasets": [],
                "selection_logic": "No datasets found for this coordinate",
                "performance_estimate": "No search would be performed"
            }
        
        # Build detailed response
        selected_datasets = []
        total_files_to_search = 0
        
        for match in dataset_matches[:3]:  # Show top 3
            dataset_info = {
                "dataset_id": match.dataset_id,
                "dataset_name": match.dataset_info.get("name", match.dataset_id),
                "confidence_score": round(match.confidence_score, 3),
                "priority": match.priority,
                "file_count": match.file_count,
                "would_be_searched": match.confidence_score > 0.8 if match == dataset_matches[0] else len(dataset_matches) <= 3
            }
            
            if dataset_info["would_be_searched"]:
                total_files_to_search += match.file_count
            
            selected_datasets.append(dataset_info)
        
        # Determine selection logic
        best_confidence = dataset_matches[0].confidence_score if dataset_matches else 0
        if best_confidence > 0.8:
            selection_logic = f"High confidence match (>{0.8}) - would search only best dataset"
        else:
            selection_logic = f"Moderate confidence - would search top {min(len(dataset_matches), 3)} datasets"
        
        return {
            "coordinate": {"latitude": latitude, "longitude": longitude},
            "selected_datasets": selected_datasets,
            "selection_logic": selection_logic,
            "performance_estimate": {
                "files_to_search": total_files_to_search,
                "vs_flat_search": 631556,
                "estimated_speedup": f"{631556 / total_files_to_search:.1f}x" if total_files_to_search > 0 else "∞x",
                "search_reduction": f"{631556 / total_files_to_search:.1f}x fewer files" if total_files_to_search > 0 else "All files avoided"
            }
        }
        
    except Exception as e:
        logger.error(f"Error previewing dataset selection for ({latitude}, {longitude}): {e}")
        raise HTTPException(status_code=500, detail=f"Failed to preview dataset selection: {str(e)}")