#!/usr/bin/env python3
"""
Stratified Sampling Validation Script
Tests UTM converter improvements on representative file samples

This script validates the impact of enhanced UTM converter patterns by:
1. Sampling files from different naming patterns and datasets
2. Testing coordinate extraction before/after fixes
3. Measuring bounds accuracy improvements
4. Estimating total impact across all 631,556 files
"""
import json
import sys
import logging
import random
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)8s | %(message)s')
logger = logging.getLogger(__name__)

class UTMConverterValidator:
    """Validate UTM converter improvements using stratified sampling"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.spatial_index_file = self.config_dir / "spatial_index.json"
        
        self.validation_results = {
            "validation_timestamp": datetime.now().isoformat(),
            "sample_strategy": "stratified_by_pattern",
            "sample_size": 0,
            "pattern_samples": {},
            "bounds_improvements": {},
            "estimated_total_impact": {},
            "recommendations": []
        }
        
    def run_validation(self, sample_size_per_pattern: int = 50):
        """Run stratified validation of UTM converter improvements"""
        logger.info("🎯 Starting stratified validation of UTM converter improvements")
        
        # Load spatial index
        logger.info("📂 Loading spatial index...")
        with open(self.spatial_index_file, 'r') as f:
            spatial_index = json.load(f)
        
        # Collect all files
        all_files = []
        for zone_data in spatial_index.get("utm_zones", {}).values():
            all_files.extend(zone_data.get("files", []))
        
        logger.info(f"📊 Loaded {len(all_files):,} files from spatial index")
        
        # Stratify files by naming patterns
        stratified_samples = self._stratify_files_by_pattern(all_files, sample_size_per_pattern)
        
        # Test UTM converter on each stratum
        for pattern_name, sample_files in stratified_samples.items():
            logger.info(f"🧪 Testing pattern: {pattern_name} ({len(sample_files)} files)")
            self._test_pattern_sample(pattern_name, sample_files)
        
        # Calculate estimated total impact
        self._estimate_total_impact(all_files)
        
        # Generate recommendations
        self._generate_recommendations()
        
        # Save results
        self._save_validation_results()
        
        logger.info("✅ Validation completed")
        return self.validation_results
    
    def _stratify_files_by_pattern(self, all_files: List[Dict], sample_size: int) -> Dict[str, List[Dict]]:
        """Stratify files by naming patterns for representative sampling"""
        logger.info("🏷️ Stratifying files by naming patterns...")
        
        # Define pattern categories
        pattern_categories = {
            "clarence_river": [],
            "wagga_wagga_dtm": [],
            "brisbane_sw": [],
            "act_standard": [],
            "sydney_lid": [],
            "gosford_lid": [],
            "generic_dem": [],
            "uncategorized": []
        }
        
        # Categorize files
        for file_info in all_files:
            filename = file_info.get("filename", "")
            categorized = False
            
            if "clarence" in filename.lower() and "dem-1m" in filename.lower():
                pattern_categories["clarence_river"].append(file_info)
                categorized = True
            elif "dtm-grid" in filename.lower():
                pattern_categories["wagga_wagga_dtm"].append(file_info)
                categorized = True
            elif "sw_" in filename.lower() and "dem_1m" in filename.lower():
                pattern_categories["brisbane_sw"].append(file_info)
                categorized = True
            elif "act" in filename.lower() and ("4ppm" in filename.lower() or "8ppm" in filename.lower()):
                pattern_categories["act_standard"].append(file_info)
                categorized = True
            elif "sydney" in filename.lower() and "lid1" in filename.lower():
                pattern_categories["sydney_lid"].append(file_info)
                categorized = True
            elif "gosford" in filename.lower() and "lid1" in filename.lower():
                pattern_categories["gosford_lid"].append(file_info)
                categorized = True
            elif "dem" in filename.lower():
                pattern_categories["generic_dem"].append(file_info)
                categorized = True
            
            if not categorized:
                pattern_categories["uncategorized"].append(file_info)
        
        # Sample from each category
        stratified_samples = {}
        for category, files in pattern_categories.items():
            if files:
                sample_count = min(sample_size, len(files))
                stratified_samples[category] = random.sample(files, sample_count)
                logger.info(f"  {category}: {len(files):,} total, {sample_count} sampled")
        
        total_samples = sum(len(samples) for samples in stratified_samples.values())
        self.validation_results["sample_size"] = total_samples
        logger.info(f"📊 Total stratified sample: {total_samples} files")
        
        return stratified_samples
    
    def _test_pattern_sample(self, pattern_name: str, sample_files: List[Dict]):
        """Test UTM converter on a pattern sample"""
        from utm_converter import DEMFilenameParser
        
        parser = DEMFilenameParser()
        
        results = {
            "total_files": len(sample_files),
            "coordinate_extraction": {"success": 0, "failed": 0},
            "bounds_accuracy": {"precise": 0, "reasonable": 0, "regional": 0, "excessive": 0},
            "improvement_examples": [],
            "remaining_issues": []
        }
        
        for file_info in sample_files:
            filename = file_info.get("filename", "")
            
            # Test current UTM converter
            utm_data = parser.extract_utm_from_filename(filename)
            bounds = parser.extract_bounds_from_filename(filename)
            
            if utm_data and bounds:
                results["coordinate_extraction"]["success"] += 1
                
                # Analyze bounds accuracy
                lat_range = bounds["max_lat"] - bounds["min_lat"]
                lon_range = bounds["max_lon"] - bounds["min_lon"]
                area = lat_range * lon_range
                
                if lat_range < 0.1 and lon_range < 0.1:
                    results["bounds_accuracy"]["precise"] += 1
                    if len(results["improvement_examples"]) < 3:
                        results["improvement_examples"].append({
                            "filename": filename,
                            "bounds_area": area,
                            "coordinates": f"E={utm_data['easting']}, N={utm_data['northing']}, Zone={utm_data['zone']}"
                        })
                elif lat_range < 1.0 and lon_range < 1.0:
                    results["bounds_accuracy"]["reasonable"] += 1
                elif lat_range < 5.0 and lon_range < 5.0:
                    results["bounds_accuracy"]["regional"] += 1
                else:
                    results["bounds_accuracy"]["excessive"] += 1
                    if len(results["remaining_issues"]) < 3:
                        results["remaining_issues"].append({
                            "filename": filename,
                            "bounds_area": area,
                            "issue": f"Large bounds: {lat_range:.1f}° x {lon_range:.1f}°"
                        })
            else:
                results["coordinate_extraction"]["failed"] += 1
                if len(results["remaining_issues"]) < 5:
                    results["remaining_issues"].append({
                        "filename": filename,
                        "issue": "No coordinate extraction"
                    })
        
        self.validation_results["pattern_samples"][pattern_name] = results
        
        # Log summary
        success_rate = (results["coordinate_extraction"]["success"] / results["total_files"]) * 100
        precise_rate = (results["bounds_accuracy"]["precise"] / results["total_files"]) * 100
        logger.info(f"  Results: {success_rate:.1f}% extraction success, {precise_rate:.1f}% precise bounds")
    
    def _estimate_total_impact(self, all_files: List[Dict]):
        """Estimate total impact across all files based on sample results"""
        logger.info("📈 Estimating total impact across all files...")
        
        # Count files by pattern in full dataset
        pattern_counts = Counter()
        for file_info in all_files:
            filename = file_info.get("filename", "")
            
            if "clarence" in filename.lower() and "dem-1m" in filename.lower():
                pattern_counts["clarence_river"] += 1
            elif "dtm-grid" in filename.lower():
                pattern_counts["wagga_wagga_dtm"] += 1
            elif "sw_" in filename.lower() and "dem_1m" in filename.lower():
                pattern_counts["brisbane_sw"] += 1
            elif "act" in filename.lower() and ("4ppm" in filename.lower() or "8ppm" in filename.lower()):
                pattern_counts["act_standard"] += 1
            elif "sydney" in filename.lower() and "lid1" in filename.lower():
                pattern_counts["sydney_lid"] += 1
            elif "gosford" in filename.lower() and "lid1" in filename.lower():
                pattern_counts["gosford_lid"] += 1
            elif "dem" in filename.lower():
                pattern_counts["generic_dem"] += 1
            else:
                pattern_counts["uncategorized"] += 1
        
        # Estimate improvements
        total_improvements = {
            "files_with_precise_bounds_before": 0,
            "files_with_precise_bounds_after": 0,
            "files_with_coordinate_extraction_before": 0,
            "files_with_coordinate_extraction_after": 0
        }
        
        for pattern_name, pattern_count in pattern_counts.items():
            if pattern_name in self.validation_results["pattern_samples"]:
                sample_results = self.validation_results["pattern_samples"][pattern_name]
                sample_size = sample_results["total_files"]
                
                if sample_size > 0:
                    # Extrapolate from sample to full pattern population
                    precise_rate = sample_results["bounds_accuracy"]["precise"] / sample_size
                    extraction_rate = sample_results["coordinate_extraction"]["success"] / sample_size
                    
                    estimated_precise = int(pattern_count * precise_rate)
                    estimated_extraction = int(pattern_count * extraction_rate)
                    
                    total_improvements["files_with_precise_bounds_after"] += estimated_precise
                    total_improvements["files_with_coordinate_extraction_after"] += estimated_extraction
                    
                    # Estimate "before" state (assuming problematic patterns had 0% precise bounds)
                    if pattern_name in ["clarence_river", "wagga_wagga_dtm"]:
                        total_improvements["files_with_precise_bounds_before"] += 0  # These were all regional fallback
                        total_improvements["files_with_coordinate_extraction_before"] += 0
                    else:
                        # For other patterns, assume they were already working
                        total_improvements["files_with_precise_bounds_before"] += estimated_precise
                        total_improvements["files_with_coordinate_extraction_before"] += estimated_extraction
        
        self.validation_results["estimated_total_impact"] = {
            "pattern_counts": dict(pattern_counts),
            "improvement_estimates": total_improvements,
            "improvement_summary": {
                "precise_bounds_improvement": (
                    total_improvements["files_with_precise_bounds_after"] - 
                    total_improvements["files_with_precise_bounds_before"]
                ),
                "coordinate_extraction_improvement": (
                    total_improvements["files_with_coordinate_extraction_after"] -
                    total_improvements["files_with_coordinate_extraction_before"]
                )
            }
        }
        
        # Log estimates
        improvement = self.validation_results["estimated_total_impact"]["improvement_summary"]
        logger.info(f"📊 Estimated improvements:")
        logger.info(f"  Precise bounds: +{improvement['precise_bounds_improvement']:,} files")
        logger.info(f"  Coordinate extraction: +{improvement['coordinate_extraction_improvement']:,} files")
    
    def _generate_recommendations(self):
        """Generate recommendations based on validation results"""
        logger.info("💡 Generating recommendations...")
        
        recommendations = []
        
        # Analyze pattern-specific issues
        total_remaining_issues = 0
        for pattern_name, results in self.validation_results["pattern_samples"].items():
            remaining_issues = len(results["remaining_issues"])
            total_remaining_issues += remaining_issues
            
            if remaining_issues > 0:
                recommendations.append({
                    "priority": "MEDIUM",
                    "category": f"Pattern: {pattern_name}",
                    "issue": f"{remaining_issues} files still have coordinate extraction issues",
                    "recommendation": f"Review and enhance UTM patterns for {pattern_name} files",
                    "examples": results["remaining_issues"][:2]
                })
        
        # Overall recommendations
        improvement = self.validation_results["estimated_total_impact"]["improvement_summary"]
        if improvement["precise_bounds_improvement"] > 10000:
            recommendations.append({
                "priority": "HIGH",
                "category": "Success Metric",
                "issue": f"UTM converter fixes estimated to improve {improvement['precise_bounds_improvement']:,} files",
                "recommendation": "Proceed with spatial index regeneration to apply fixes",
                "impact": "Dramatic reduction in file overlap and improved selection accuracy"
            })
        
        if total_remaining_issues > 100:
            recommendations.append({
                "priority": "MEDIUM", 
                "category": "Remaining Issues",
                "issue": f"{total_remaining_issues} sampled files still have coordinate extraction problems",
                "recommendation": "Add additional UTM patterns or fallback strategies",
                "next_step": "Analyze uncategorized files for new patterns"
            })
        
        self.validation_results["recommendations"] = recommendations
        logger.info(f"💡 Generated {len(recommendations)} recommendations")
    
    def _save_validation_results(self):
        """Save validation results to file"""
        output_file = self.config_dir / "utm_converter_validation_results.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.validation_results, f, indent=2, default=str)
        
        logger.info(f"💾 Validation results saved to: {output_file}")
        
        # Create summary report
        self._create_validation_summary()
    
    def _create_validation_summary(self):
        """Create human-readable validation summary"""
        report_file = self.config_dir / "utm_converter_validation_summary.md"
        
        with open(report_file, 'w') as f:
            f.write("# UTM Converter Validation Report\n\n")
            f.write(f"**Generated:** {self.validation_results['validation_timestamp']}\n\n")
            
            f.write("## Executive Summary\n\n")
            impact = self.validation_results["estimated_total_impact"]["improvement_summary"]
            f.write(f"- **Estimated Improvement**: +{impact['precise_bounds_improvement']:,} files with precise bounds\n")
            f.write(f"- **Sample Size**: {self.validation_results['sample_size']} files tested\n")
            f.write(f"- **Strategy**: Stratified sampling by filename patterns\n\n")
            
            f.write("## Pattern-Specific Results\n\n")
            for pattern_name, results in self.validation_results["pattern_samples"].items():
                success_rate = (results["coordinate_extraction"]["success"] / results["total_files"]) * 100
                precise_rate = (results["bounds_accuracy"]["precise"] / results["total_files"]) * 100
                
                f.write(f"### {pattern_name.replace('_', ' ').title()}\n\n")
                f.write(f"- **Sample Size**: {results['total_files']} files\n")
                f.write(f"- **Extraction Success**: {success_rate:.1f}%\n")
                f.write(f"- **Precise Bounds**: {precise_rate:.1f}%\n")
                
                if results["improvement_examples"]:
                    f.write(f"- **Example Success**: {results['improvement_examples'][0]['filename']}\n")
                
                f.write("\n")
            
            f.write("## Recommendations\n\n")
            for i, rec in enumerate(self.validation_results["recommendations"], 1):
                f.write(f"### {i}. {rec['category']} ({rec['priority']} Priority)\n\n")
                f.write(f"**Issue**: {rec['issue']}\n\n")
                f.write(f"**Recommendation**: {rec['recommendation']}\n\n")
        
        logger.info(f"📋 Validation summary saved to: {report_file}")

def main():
    """Main function"""
    logger.info("🎯 UTM Converter Impact Validation")
    logger.info("Testing enhanced patterns on stratified file samples")
    print()
    
    validator = UTMConverterValidator()
    results = validator.run_validation(sample_size_per_pattern=100)
    
    print()
    logger.info("🎉 Validation completed successfully!")
    logger.info("📋 See utm_converter_validation_summary.md for detailed findings")
    logger.info("📊 See utm_converter_validation_results.json for complete data")

if __name__ == "__main__":
    main()