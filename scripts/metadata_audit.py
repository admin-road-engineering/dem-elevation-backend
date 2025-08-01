#!/usr/bin/env python3
"""
Comprehensive Metadata Audit Script
Catalogs all file properties from spatial index and sample S3 files for analysis

Based on reviewer feedback to enhance metadata handling before Phase 1 implementation.
"""
import json
import sys
import logging
import asyncio
import re
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)8s | %(message)s')
logger = logging.getLogger(__name__)

class DemMetadataAuditor:
    """Comprehensive audit of DEM file metadata and naming patterns"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.spatial_index_file = self.config_dir / "spatial_index.json"
        self.audit_results = {
            "audit_timestamp": datetime.now().isoformat(),
            "total_files": 0,
            "naming_patterns": {},
            "resolution_distribution": Counter(),
            "year_distribution": Counter(),
            "dataset_distribution": Counter(),
            "file_size_stats": {},
            "bounds_accuracy": {},
            "uncovered_patterns": [],
            "quality_metrics": {}
        }
        
    def run_comprehensive_audit(self):
        """Run complete metadata audit"""
        logger.info("🔍 Starting comprehensive DEM metadata audit...")
        
        # Load spatial index
        with open(self.spatial_index_file, 'r') as f:
            spatial_index = json.load(f)
        
        self.audit_results["total_files"] = spatial_index.get("file_count", 0)
        logger.info(f"📊 Auditing {self.audit_results['total_files']} files from spatial index")
        
        all_files = []
        for zone_data in spatial_index.get("utm_zones", {}).values():
            all_files.extend(zone_data.get("files", []))
        
        # 1. Analyze naming patterns
        self._analyze_naming_patterns(all_files)
        
        # 2. Extract metadata from filenames
        self._extract_filename_metadata(all_files)
        
        # 3. Analyze bounds accuracy
        self._analyze_bounds_accuracy(all_files)
        
        # 4. Calculate quality metrics
        self._calculate_quality_metrics(all_files)
        
        # 5. Generate recommendations
        self._generate_recommendations()
        
        # Save audit results
        self._save_audit_results()
        
        logger.info("✅ Comprehensive audit completed")
        return self.audit_results
    
    def _analyze_naming_patterns(self, files: List[Dict]):
        """Analyze and categorize filename patterns"""
        logger.info("🏷️ Analyzing filename patterns...")
        
        pattern_counts = Counter()
        pattern_examples = defaultdict(list)
        uncovered_files = []
        
        # Define known patterns with regex
        known_patterns = {
            "brisbane_sw": r"Brisbane_\d{4}_.*SW_\d+_\d+_1[kK]?_DEM_1m\.tif",
            "clarence_grid": r"Clarence\d{4}-DEM-1m_\d{7}_GDA2020_\d{2}\.tif", 
            "act_4ppm": r"ACT\d{4}_4ppm_\d{7}_\d{2}_\d{4}_\d{4}_1m\.tif",
            "sydney_lid": r"Sydney\d{6}-LID1-AHD_\d{7}_\d{2}_\d{4}_\d{4}_1m\.tif",
            "gosford_lid": r"Gosford\d{6}-LID1-AHD_\d{7}_\d{2}_\d{4}_\d{4}_1m\.tif",
            "standard_grid": r"\w+_\d{7}_\d{2}_\d{4}_\d{4}",
            "generic_dem": r"\w+.*DEM.*\.tif",
        }
        
        for file_info in files:
            filename = file_info.get("filename", "")
            matched = False
            
            for pattern_name, pattern_regex in known_patterns.items():
                if re.match(pattern_regex, filename, re.IGNORECASE):
                    pattern_counts[pattern_name] += 1
                    if len(pattern_examples[pattern_name]) < 5:  # Keep 5 examples
                        pattern_examples[pattern_name].append(filename)
                    matched = True
                    break
            
            if not matched:
                uncovered_files.append(filename)
        
        self.audit_results["naming_patterns"] = {
            "pattern_counts": dict(pattern_counts),
            "pattern_examples": dict(pattern_examples),
            "uncovered_count": len(uncovered_files),
            "uncovered_examples": uncovered_files[:20]  # First 20 examples
        }
        
        logger.info(f"📋 Pattern analysis:")
        for pattern, count in pattern_counts.most_common():
            logger.info(f"  {pattern}: {count:,} files")
        logger.info(f"  uncovered: {len(uncovered_files):,} files")
    
    def _extract_filename_metadata(self, files: List[Dict]):
        """Extract metadata from filenames"""
        logger.info("📝 Extracting metadata from filenames...")
        
        resolution_patterns = {
            "25cm": [r"25cm", r"0\.25m"],
            "50cm": [r"50cm", r"0\.5m"],
            "1m": [r"1m", r"_1m", r"1M"],
            "5m": [r"5m", r"_5m"],
            "25m": [r"25m", r"_25m"]
        }
        
        year_pattern = r"(20\d{2})"
        dataset_patterns = {
            "Brisbane": r"Brisbane",
            "Sydney": r"Sydney", 
            "Clarence": r"Clarence",
            "ACT": r"ACT",
            "Gosford": r"Gosford",
            "Tasmania": r"tas|tasmania",
            "Queensland": r"qld|queensland",
            "NSW": r"nsw"
        }
        
        for file_info in files:
            filename = file_info.get("filename", "")
            
            # Extract resolution
            for res_name, res_patterns in resolution_patterns.items():
                if any(re.search(pattern, filename, re.IGNORECASE) for pattern in res_patterns):
                    self.audit_results["resolution_distribution"][res_name] += 1
                    break
            else:
                self.audit_results["resolution_distribution"]["unknown"] += 1
            
            # Extract year
            year_match = re.search(year_pattern, filename)
            if year_match:
                year = year_match.group(1)
                self.audit_results["year_distribution"][year] += 1
            else:
                self.audit_results["year_distribution"]["unknown"] += 1
            
            # Extract dataset
            for dataset_name, dataset_pattern in dataset_patterns.items():
                if re.search(dataset_pattern, filename, re.IGNORECASE):
                    self.audit_results["dataset_distribution"][dataset_name] += 1
                    break
            else:
                self.audit_results["dataset_distribution"]["other"] += 1
        
        # Calculate file size statistics
        file_sizes = [f.get("size_mb", 0) for f in files if f.get("size_mb")]
        if file_sizes:
            self.audit_results["file_size_stats"] = {
                "min_mb": min(file_sizes),
                "max_mb": max(file_sizes),
                "avg_mb": sum(file_sizes) / len(file_sizes),
                "median_mb": sorted(file_sizes)[len(file_sizes) // 2],
                "total_gb": sum(file_sizes) / 1024
            }
        
        logger.info(f"📊 Metadata extraction complete:")
        logger.info(f"  Resolution: {dict(self.audit_results['resolution_distribution'])}")
        logger.info(f"  Years: {dict(sorted(self.audit_results['year_distribution'].items()))}")
        logger.info(f"  Datasets: {dict(self.audit_results['dataset_distribution'])}")
    
    def _analyze_bounds_accuracy(self, files: List[Dict]):
        """Analyze spatial bounds accuracy"""
        logger.info("📐 Analyzing bounds accuracy...")
        
        bounds_categories = {
            "precise": 0,      # < 0.1° range
            "reasonable": 0,   # 0.1° - 1.0° range  
            "regional": 0,     # 1.0° - 5.0° range
            "excessive": 0     # > 5.0° range
        }
        
        problem_bounds = []
        
        for file_info in files:
            bounds = file_info.get("bounds", {})
            if not bounds:
                continue
                
            lat_range = bounds.get("max_lat", 0) - bounds.get("min_lat", 0)
            lon_range = bounds.get("max_lon", 0) - bounds.get("min_lon", 0)
            area = lat_range * lon_range
            
            if lat_range < 0.1 and lon_range < 0.1:
                bounds_categories["precise"] += 1
            elif lat_range < 1.0 and lon_range < 1.0:
                bounds_categories["reasonable"] += 1
            elif lat_range < 5.0 and lon_range < 5.0:
                bounds_categories["regional"] += 1
            else:
                bounds_categories["excessive"] += 1
                problem_bounds.append({
                    "filename": file_info.get("filename"),
                    "lat_range": lat_range,
                    "lon_range": lon_range,
                    "area_deg2": area
                })
        
        # Sort problem bounds by area
        problem_bounds.sort(key=lambda x: x["area_deg2"], reverse=True)
        
        self.audit_results["bounds_accuracy"] = {
            "categories": bounds_categories,
            "problem_bounds_count": len(problem_bounds),
            "worst_offenders": problem_bounds[:10]  # Top 10 worst
        }
        
        logger.info(f"📐 Bounds accuracy analysis:")
        for category, count in bounds_categories.items():
            percentage = (count / len(files)) * 100 if files else 0
            logger.info(f"  {category}: {count:,} files ({percentage:.1f}%)")
    
    def _calculate_quality_metrics(self, files: List[Dict]):
        """Calculate various quality metrics"""
        logger.info("⭐ Calculating quality metrics...")
        
        # Resolution quality score (higher resolution = better)
        resolution_scores = {"25cm": 1.0, "50cm": 0.8, "1m": 0.6, "5m": 0.4, "25m": 0.2, "unknown": 0.1}
        
        # Temporal quality score (newer = better)
        current_year = datetime.now().year
        
        quality_scores = []
        for file_info in files:
            filename = file_info.get("filename", "")
            
            # Resolution score
            res_score = 0.1  # Default
            for res_name, score in resolution_scores.items():
                if res_name in self.audit_results["resolution_distribution"]:
                    res_score = score
                    break
            
            # Temporal score
            year_match = re.search(r"(20\d{2})", filename)
            if year_match:
                file_year = int(year_match.group(1))
                age = current_year - file_year
                temporal_score = max(0, 1.0 - (age / 15))  # Decay over 15 years
            else:
                temporal_score = 0.1  # Unknown age
            
            # Bounds precision score
            bounds = file_info.get("bounds", {})
            if bounds:
                lat_range = bounds.get("max_lat", 0) - bounds.get("min_lat", 0)
                lon_range = bounds.get("max_lon", 0) - bounds.get("min_lon", 0)
                area = lat_range * lon_range
                bounds_score = max(0, 1.0 - (area / 1.0))  # Penalty for large areas
            else:
                bounds_score = 0
            
            # Combined quality score
            quality_score = (res_score * 0.4 + temporal_score * 0.3 + bounds_score * 0.3)
            quality_scores.append(quality_score)
        
        if quality_scores:
            self.audit_results["quality_metrics"] = {
                "avg_quality_score": sum(quality_scores) / len(quality_scores),
                "min_quality_score": min(quality_scores),
                "max_quality_score": max(quality_scores),
                "high_quality_files": sum(1 for score in quality_scores if score > 0.8),
                "low_quality_files": sum(1 for score in quality_scores if score < 0.3)
            }
        
        metrics = self.audit_results["quality_metrics"]
        logger.info(f"⭐ Quality metrics:")
        logger.info(f"  Average quality score: {metrics.get('avg_quality_score', 0):.3f}")
        logger.info(f"  High quality files (>0.8): {metrics.get('high_quality_files', 0):,}")
        logger.info(f"  Low quality files (<0.3): {metrics.get('low_quality_files', 0):,}")
    
    def _generate_recommendations(self):
        """Generate recommendations based on audit findings"""
        logger.info("💡 Generating recommendations...")
        
        recommendations = []
        
        # Bounds accuracy recommendations
        bounds_acc = self.audit_results["bounds_accuracy"]
        excessive_count = bounds_acc["categories"]["excessive"]
        if excessive_count > 1000:
            recommendations.append({
                "priority": "HIGH",
                "category": "Bounds Accuracy",
                "issue": f"{excessive_count:,} files have excessive bounds (>5° range)",
                "recommendation": "Implement enhanced UTM converter patterns to fix fallback bounds",
                "estimated_impact": f"Reduce Brisbane coverage from 31,809 to ~{excessive_count // 100}-{excessive_count // 50} files"
            })
        
        # Pattern coverage recommendations
        patterns = self.audit_results["naming_patterns"]
        uncovered_count = patterns["uncovered_count"]
        if uncovered_count > 1000:
            recommendations.append({
                "priority": "MEDIUM", 
                "category": "Pattern Coverage",
                "issue": f"{uncovered_count:,} files don't match known patterns",
                "recommendation": "Add new regex patterns for uncovered filename formats",
                "estimated_impact": "Improve coordinate extraction accuracy"
            })
        
        # Data quality recommendations
        quality = self.audit_results["quality_metrics"]
        low_quality_count = quality.get("low_quality_files", 0)
        if low_quality_count > quality.get("high_quality_files", 0):
            recommendations.append({
                "priority": "MEDIUM",
                "category": "Data Quality",
                "issue": f"{low_quality_count:,} files have low quality scores",
                "recommendation": "Implement quality-based file prioritization in selection algorithm",
                "estimated_impact": "Improve elevation data accuracy for engineering applications"
            })
        
        self.audit_results["recommendations"] = recommendations
        
        logger.info(f"💡 Generated {len(recommendations)} recommendations")
        for rec in recommendations:
            logger.info(f"  {rec['priority']}: {rec['issue']}")
    
    def _save_audit_results(self):
        """Save audit results to file"""
        output_file = self.config_dir / "metadata_audit_results.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.audit_results, f, indent=2, default=str)
        
        logger.info(f"💾 Audit results saved to: {output_file}")
        
        # Also create a summary report
        self._create_summary_report()
    
    def _create_summary_report(self):
        """Create human-readable summary report"""
        report_file = self.config_dir / "metadata_audit_summary.md"
        
        with open(report_file, 'w') as f:
            f.write("# DEM Metadata Audit Summary Report\n\n")
            f.write(f"**Generated:** {self.audit_results['audit_timestamp']}\n\n")
            
            f.write("## Overview\n\n")
            f.write(f"- **Total Files:** {self.audit_results['total_files']:,}\n")
            f.write(f"- **Total Storage:** {self.audit_results['file_size_stats'].get('total_gb', 0):.1f} GB\n\n")
            
            f.write("## Naming Patterns\n\n")
            for pattern, count in self.audit_results['naming_patterns']['pattern_counts'].items():
                f.write(f"- **{pattern}:** {count:,} files\n")
            f.write(f"- **uncovered:** {self.audit_results['naming_patterns']['uncovered_count']:,} files\n\n")
            
            f.write("## Resolution Distribution\n\n")
            for res, count in self.audit_results['resolution_distribution'].most_common():
                f.write(f"- **{res}:** {count:,} files\n")
            f.write("\n")
            
            f.write("## Bounds Accuracy\n\n")
            for category, count in self.audit_results['bounds_accuracy']['categories'].items():
                percentage = (count / self.audit_results['total_files']) * 100
                f.write(f"- **{category}:** {count:,} files ({percentage:.1f}%)\n")
            f.write("\n")
            
            f.write("## Recommendations\n\n")
            for i, rec in enumerate(self.audit_results['recommendations'], 1):
                f.write(f"### {i}. {rec['category']} ({rec['priority']} Priority)\n\n")
                f.write(f"**Issue:** {rec['issue']}\n\n")
                f.write(f"**Recommendation:** {rec['recommendation']}\n\n")
                f.write(f"**Impact:** {rec['estimated_impact']}\n\n")
        
        logger.info(f"📋 Summary report saved to: {report_file}")

def main():
    """Main function"""
    logger.info("🔍 DEM Metadata Comprehensive Audit")
    logger.info("Cataloging all file properties for enhanced selection strategy")
    print()
    
    auditor = DemMetadataAuditor()
    results = auditor.run_comprehensive_audit()
    
    print()
    logger.info("🎉 Audit completed successfully!")
    logger.info("📋 See metadata_audit_summary.md for detailed findings")
    logger.info("📊 See metadata_audit_results.json for complete data")

if __name__ == "__main__":
    main()