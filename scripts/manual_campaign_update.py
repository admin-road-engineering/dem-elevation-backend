#!/usr/bin/env python3
"""
Manual Campaign Update System - Phase 3 Enhancement
On-demand campaign detection and index updates when S3 data is manually updated
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from analyze_campaign_structure import extract_campaign_from_path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ManualCampaignUpdater:
    """
    Manual campaign update system for when S3 data is updated.
    
    Features:
    - On-demand campaign detection when you update S3
    - Incremental index updates for new campaigns
    - Validation of existing campaign structure
    - Performance-optimized updates that maintain Phase 3 speed
    """
    
    def __init__(self, config_dir: Path = None):
        self.config_dir = config_dir or Path(__file__).parent.parent / "config"
        self.campaign_index_file = self.config_dir / "phase3_campaign_populated_index.json"
        self.grouped_index_file = self.config_dir / "grouped_spatial_index.json"
        self.tiled_index_file = self.config_dir / "phase3_brisbane_tiled_index.json"
    
    def analyze_new_campaigns_from_grouped_index(self) -> Dict[str, Any]:
        """
        Analyze the grouped spatial index to find new campaigns that aren't in the campaign index.
        This runs against your existing data without S3 scanning.
        """
        logger.info("Analyzing grouped index for new campaigns...")
        
        # Load existing campaign index
        existing_campaigns = set()
        if self.campaign_index_file.exists():
            with open(self.campaign_index_file, 'r') as f:
                campaign_index = json.load(f)
            existing_campaigns = set(campaign_index.get('datasets', {}).keys())
            logger.info(f"Found {len(existing_campaigns)} existing campaigns")
        
        # Load grouped spatial index
        if not self.grouped_index_file.exists():
            logger.error(f"Grouped spatial index not found: {self.grouped_index_file}")
            return {}
        
        with open(self.grouped_index_file, 'r') as f:
            grouped_index = json.load(f)
        
        # Analyze each dataset for campaign structure
        new_campaigns = {}
        total_new_files = 0
        
        for dataset_id, dataset_info in grouped_index.get('datasets', {}).items():
            logger.info(f"Analyzing dataset: {dataset_id}")
            
            files = dataset_info.get('files', [])
            if not files:
                continue
            
            # Extract campaigns from this dataset
            campaign_files = {}
            for file_info in files:
                s3_path = file_info.get('key', '')
                campaign_id = extract_campaign_from_path(s3_path)
                
                if campaign_id == 'unknown':
                    continue
                
                # Create full campaign ID with dataset context
                full_campaign_id = f"{dataset_id}_{campaign_id}"
                
                if full_campaign_id not in campaign_files:
                    campaign_files[full_campaign_id] = []
                campaign_files[full_campaign_id].append(file_info)
            
            # Check for new campaigns
            for campaign_id, files_list in campaign_files.items():
                if campaign_id not in existing_campaigns and len(files_list) >= 10:  # Min 10 files
                    new_campaigns[campaign_id] = {
                        'source_dataset': dataset_id,
                        'file_count': len(files_list),
                        'files': files_list,
                        'sample_paths': [f.get('key', '') for f in files_list[:3]]
                    }
                    total_new_files += len(files_list)
                    logger.info(f"New campaign found: {campaign_id} ({len(files_list)} files)")
        
        analysis_results = {
            'timestamp': datetime.now().isoformat(),
            'existing_campaigns': len(existing_campaigns),
            'new_campaigns_found': len(new_campaigns),
            'total_new_files': total_new_files,
            'new_campaigns': new_campaigns,
            'action_required': len(new_campaigns) > 0
        }
        
        logger.info(f"Analysis complete: {len(new_campaigns)} new campaigns found with {total_new_files} total files")
        return analysis_results
    
    def extract_campaign_metadata(self, campaign_files: List[Dict[str, Any]], campaign_id: str) -> Dict[str, Any]:
        """Extract metadata for a campaign from its file list"""
        if not campaign_files:
            return {}
        
        # Calculate bounds from file bounds
        bounds = {
            'min_lat': float('inf'),
            'max_lat': float('-inf'),
            'min_lon': float('inf'),
            'max_lon': float('-inf'),
            'type': 'bbox'
        }
        
        valid_bounds_count = 0
        for file_info in campaign_files:
            file_bounds = file_info.get('bounds', {})
            if file_bounds:
                min_lat = file_bounds.get('min_lat')
                max_lat = file_bounds.get('max_lat')
                min_lon = file_bounds.get('min_lon')
                max_lon = file_bounds.get('max_lon')
                
                if all(coord is not None for coord in [min_lat, max_lat, min_lon, max_lon]):
                    bounds['min_lat'] = min(bounds['min_lat'], min_lat)
                    bounds['max_lat'] = max(bounds['max_lat'], max_lat)
                    bounds['min_lon'] = min(bounds['min_lon'], min_lon)
                    bounds['max_lon'] = max(bounds['max_lon'], max_lon)
                    valid_bounds_count += 1
        
        # Clean up infinite bounds
        if bounds['min_lat'] == float('inf'):
            bounds = {'type': 'bbox', 'min_lat': None, 'max_lat': None, 'min_lon': None, 'max_lon': None}
        
        # Extract metadata from campaign ID and file paths
        sample_path = campaign_files[0].get('key', '') if campaign_files else ''
        
        # Extract year
        import re
        year_match = re.search(r'20\d{2}', campaign_id)
        campaign_year = year_match.group() if year_match else 'unknown'
        
        # Extract provider
        provider = 'unknown'
        if 'elvis' in campaign_id.lower() or 'elvis' in sample_path.lower():
            provider = 'elvis'
        elif 'ga' in campaign_id.lower() or 'geoscience' in sample_path.lower():
            provider = 'ga'
        elif 'csiro' in campaign_id.lower():
            provider = 'csiro'
        
        # Extract region and determine if metro
        geographic_region = 'unknown'
        if 'qld' in campaign_id.lower():
            geographic_region = 'qld'
            # Check if Brisbane metro area
            if (bounds['min_lat'] is not None and bounds['max_lat'] is not None and
                bounds['min_lon'] is not None and bounds['max_lon'] is not None):
                if (-28.0 <= bounds['min_lat'] <= -26.5 and 152.0 <= bounds['min_lon'] <= 154.0):
                    geographic_region = 'brisbane_metro'
        elif 'nsw' in campaign_id.lower():
            geographic_region = 'nsw'
            # Check if Sydney metro area
            if (bounds['min_lat'] is not None and bounds['max_lat'] is not None and
                bounds['min_lon'] is not None and bounds['max_lon'] is not None):
                if (-34.0 <= bounds['min_lat'] <= -33.0 and 150.0 <= bounds['min_lon'] <= 152.0):
                    geographic_region = 'sydney_metro'
        
        # Estimate resolution
        resolution_m = 5.0  # Default
        if '1m' in sample_path.lower() or 'lidar' in sample_path.lower():
            resolution_m = 1.0
        elif '0.5m' in sample_path.lower() or '50cm' in sample_path.lower():
            resolution_m = 0.5
        elif '5m' in sample_path.lower():
            resolution_m = 5.0
        elif '30m' in sample_path.lower():
            resolution_m = 30.0
        
        # Determine priority
        priority = 99
        if resolution_m <= 1.0:
            priority = 1 if geographic_region in ['brisbane_metro', 'sydney_metro'] else 2
        elif resolution_m <= 5.0:
            priority = 2 if geographic_region in ['brisbane_metro', 'sydney_metro'] else 3
        else:
            priority = 5
        
        return {
            'campaign_id': campaign_id,
            'name': f"Campaign {campaign_id.split('_')[-1]} ({campaign_year})",
            'file_count': len(campaign_files),
            'campaign_year': campaign_year,
            'provider': provider,
            'geographic_region': geographic_region,
            'resolution_m': resolution_m,
            'priority': priority,
            'bounds': bounds,
            'bounds_coverage': f"{valid_bounds_count}/{len(campaign_files)} files with bounds",
            'manual_update': True,
            'created_timestamp': datetime.now().isoformat(),
            'files': campaign_files
        }
    
    def update_campaign_index(self, new_campaigns: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the campaign index with new campaigns found.
        Maintains existing performance while adding new data.
        """
        if not new_campaigns:
            logger.info("No new campaigns to add")
            return {'campaigns_added': 0, 'campaigns_updated': 0}
        
        logger.info(f"Updating campaign index with {len(new_campaigns)} new campaigns...")
        
        # Load existing index or create new one
        if self.campaign_index_file.exists():
            with open(self.campaign_index_file, 'r') as f:
                campaign_index = json.load(f)
        else:
            campaign_index = {
                'generation_timestamp': datetime.now().isoformat(),
                'total_campaigns': 0,
                'total_files': 0,
                'datasets': {}
            }
        
        datasets = campaign_index.get('datasets', {})
        campaigns_added = 0
        campaigns_updated = 0
        total_files_added = 0
        
        # Create backup
        backup_file = self.campaign_index_file.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        if self.campaign_index_file.exists():
            import shutil
            shutil.copy2(self.campaign_index_file, backup_file)
            logger.info(f"Backup created: {backup_file}")
        
        # Add new campaigns
        for campaign_id, campaign_data in new_campaigns.items():
            if campaign_id in datasets:
                # Update existing campaign
                existing_count = datasets[campaign_id].get('file_count', 0)
                new_count = campaign_data.get('file_count', 0)
                if new_count > existing_count:
                    # Extract full metadata
                    updated_metadata = self.extract_campaign_metadata(
                        campaign_data.get('files', []), 
                        campaign_id
                    )
                    datasets[campaign_id].update(updated_metadata)
                    campaigns_updated += 1
                    total_files_added += (new_count - existing_count)
                    logger.info(f"Updated campaign: {campaign_id} (+{new_count - existing_count} files)")
            else:
                # Add new campaign
                campaign_metadata = self.extract_campaign_metadata(
                    campaign_data.get('files', []), 
                    campaign_id
                )
                datasets[campaign_id] = campaign_metadata
                campaigns_added += 1
                total_files_added += campaign_data.get('file_count', 0)
                logger.info(f"Added new campaign: {campaign_id} ({campaign_data.get('file_count', 0)} files)")
        
        # Update index metadata
        campaign_index['datasets'] = datasets
        campaign_index['total_campaigns'] = len(datasets)
        campaign_index['total_files'] = sum(d.get('file_count', 0) for d in datasets.values())
        campaign_index['last_manual_update'] = datetime.now().isoformat()
        
        # Save updated index
        with open(self.campaign_index_file, 'w') as f:
            json.dump(campaign_index, f, indent=2)
        
        update_results = {
            'campaigns_added': campaigns_added,
            'campaigns_updated': campaigns_updated,
            'total_files_added': total_files_added,
            'total_campaigns': len(datasets),
            'backup_file': str(backup_file),
            'index_file': str(self.campaign_index_file)
        }
        
        logger.info(f"Index update complete: {campaigns_added} added, {campaigns_updated} updated, {total_files_added} total files added")
        return update_results
    
    def validate_campaign_index(self) -> Dict[str, Any]:
        """Validate the current campaign index structure and performance"""
        logger.info("Validating campaign index...")
        
        if not self.campaign_index_file.exists():
            return {'valid': False, 'error': 'Campaign index file not found'}
        
        try:
            with open(self.campaign_index_file, 'r') as f:
                campaign_index = json.load(f)
            
            datasets = campaign_index.get('datasets', {})
            
            # Performance analysis
            brisbane_campaigns = [d for d in datasets.values() if d.get('geographic_region') == 'brisbane_metro']
            sydney_campaigns = [d for d in datasets.values() if d.get('geographic_region') == 'sydney_metro']
            manual_campaigns = [d for d in datasets.values() if d.get('manual_update', False)]
            
            # Check for campaigns that might benefit from tiling
            large_campaigns = [(k, v) for k, v in datasets.items() if v.get('file_count', 0) > 500]
            
            validation = {
                'valid': True,
                'total_campaigns': len(datasets),
                'total_files': campaign_index.get('total_files', 0),
                'brisbane_metro_campaigns': len(brisbane_campaigns),
                'sydney_metro_campaigns': len(sydney_campaigns),
                'manual_update_campaigns': len(manual_campaigns),
                'large_campaigns_needing_tiling': len(large_campaigns),
                'large_campaigns': [{'id': k, 'files': v.get('file_count', 0)} for k, v in large_campaigns[:5]],
                'performance_estimate': self._estimate_performance_impact(datasets),
                'recommendations': []
            }
            
            # Generate recommendations
            if len(large_campaigns) > 0:
                validation['recommendations'].append(f"Consider tiling {len(large_campaigns)} large campaigns for better performance")
            
            if len(brisbane_campaigns) > 5:
                validation['recommendations'].append("Brisbane metro has many campaigns - tiled index is recommended")
            
            if validation['total_campaigns'] > 1000:
                validation['recommendations'].append("Large number of campaigns - consider memory optimization")
            
            logger.info(f"Validation complete: {validation['total_campaigns']} campaigns, {validation['total_files']} files")
            return validation
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}
    
    def _estimate_performance_impact(self, datasets: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate performance impact of current campaign structure"""
        
        # Calculate average files per campaign by region
        brisbane_files = [d.get('file_count', 0) for d in datasets.values() if d.get('geographic_region') == 'brisbane_metro']
        sydney_files = [d.get('file_count', 0) for d in datasets.values() if d.get('geographic_region') == 'sydney_metro']
        other_files = [d.get('file_count', 0) for d in datasets.values() if d.get('geographic_region') not in ['brisbane_metro', 'sydney_metro']]
        
        return {
            'brisbane_avg_files_per_campaign': sum(brisbane_files) / len(brisbane_files) if brisbane_files else 0,
            'sydney_avg_files_per_campaign': sum(sydney_files) / len(sydney_files) if sydney_files else 0,
            'other_avg_files_per_campaign': sum(other_files) / len(other_files) if other_files else 0,
            'total_campaigns': len(datasets),
            'estimated_query_time_impact': 'minimal - uses campaign selection',
            'tiled_optimization_benefit': 'high' if sum(brisbane_files) > 10000 else 'medium'
        }
    
    def run_manual_update(self, validate_only: bool = False) -> Dict[str, Any]:
        """
        Run the complete manual update process.
        Call this after you've updated S3 data.
        """
        logger.info("Starting manual campaign update process...")
        start_time = time.time()
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'process_time_seconds': 0,
            'steps_completed': [],
            'analysis_results': {},
            'update_results': {},
            'validation_results': {},
            'success': False
        }
        
        try:
            # Step 1: Analyze for new campaigns
            logger.info("Step 1: Analyzing for new campaigns...")
            analysis = self.analyze_new_campaigns_from_grouped_index()
            results['analysis_results'] = analysis
            results['steps_completed'].append('analysis')
            
            if validate_only:
                # Step 2: Just validate current state
                logger.info("Step 2: Validating current campaign index...")
                validation = self.validate_campaign_index()
                results['validation_results'] = validation
                results['steps_completed'].append('validation')
                results['success'] = validation.get('valid', False)
            else:
                # Step 2: Update campaign index if new campaigns found
                if analysis.get('action_required', False):
                    logger.info("Step 2: Updating campaign index...")
                    update_results = self.update_campaign_index(analysis.get('new_campaigns', {}))
                    results['update_results'] = update_results
                    results['steps_completed'].append('update')
                else:
                    logger.info("Step 2: No updates needed - no new campaigns found")
                    results['update_results'] = {'campaigns_added': 0, 'campaigns_updated': 0}
                    results['steps_completed'].append('update_skipped')
                
                # Step 3: Validate updated index
                logger.info("Step 3: Validating updated campaign index...")
                validation = self.validate_campaign_index()
                results['validation_results'] = validation
                results['steps_completed'].append('validation')
                results['success'] = validation.get('valid', False)
        
        except Exception as e:
            logger.error(f"Manual update process failed: {e}")
            results['error'] = str(e)
            results['success'] = False
        
        results['process_time_seconds'] = time.time() - start_time
        
        # Save results
        results_file = self.config_dir / f"manual_update_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Manual update process complete in {results['process_time_seconds']:.1f}s")
        logger.info(f"Results saved: {results_file}")
        
        return results

def main():
    """Main execution for manual campaign updates"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Manual Campaign Update System')
    parser.add_argument('--analyze', action='store_true', help='Only analyze for new campaigns')
    parser.add_argument('--update', action='store_true', help='Analyze and update campaign index')
    parser.add_argument('--validate', action='store_true', help='Only validate current campaign index')
    
    args = parser.parse_args()
    
    updater = ManualCampaignUpdater()
    
    if args.analyze:
        logger.info("Running analysis only...")
        analysis = updater.analyze_new_campaigns_from_grouped_index()
        print(f"\nAnalysis Results:")
        print(f"New campaigns found: {analysis.get('new_campaigns_found', 0)}")
        print(f"Total new files: {analysis.get('total_new_files', 0)}")
        print(f"Action required: {analysis.get('action_required', False)}")
        
        if analysis.get('new_campaigns_found', 0) > 0:
            print(f"\nNew campaigns:")
            for campaign_id, info in analysis.get('new_campaigns', {}).items():
                print(f"  {campaign_id}: {info.get('file_count', 0)} files")
    
    elif args.validate:
        logger.info("Running validation only...")
        validation = updater.validate_campaign_index()
        print(f"\nValidation Results:")
        print(f"Valid: {validation.get('valid', False)}")
        print(f"Total campaigns: {validation.get('total_campaigns', 0)}")
        print(f"Total files: {validation.get('total_files', 0)}")
        print(f"Manual update campaigns: {validation.get('manual_update_campaigns', 0)}")
        
        for rec in validation.get('recommendations', []):
            print(f"Recommendation: {rec}")
    
    elif args.update:
        logger.info("Running full update process...")
        results = updater.run_manual_update()
        print(f"\nUpdate Results:")
        print(f"Process time: {results.get('process_time_seconds', 0):.1f}s")
        print(f"Success: {results.get('success', False)}")
        print(f"Steps completed: {', '.join(results.get('steps_completed', []))}")
        
        if 'update_results' in results:
            update = results['update_results']
            print(f"Campaigns added: {update.get('campaigns_added', 0)}")
            print(f"Campaigns updated: {update.get('campaigns_updated', 0)}")
            print(f"Total files added: {update.get('total_files_added', 0)}")
    
    else:
        print("Choose one option:")
        print("  --analyze: Check for new campaigns without updating")
        print("  --validate: Validate current campaign index")
        print("  --update: Run full analysis and update process")
        print("\nRecommended workflow after updating S3:")
        print("  1. python manual_campaign_update.py --analyze")
        print("  2. python manual_campaign_update.py --update")
        print("  3. python manual_campaign_update.py --validate")

if __name__ == "__main__":
    main()