import json
from pathlib import Path
import logging
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_json_file(file_path: Path):
    """Loads a JSON file, raising an error if it doesn't exist."""
    logging.info(f"Loading {file_path}...")
    if not file_path.exists():
        logging.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")
    with file_path.open('r', encoding='utf-8') as f:
        return json.load(f)

def group_files_by_dataset(sources_config: dict, spatial_index: dict) -> dict:
    """Groups files from a flat spatial index into datasets based on source paths."""
    
    # The target structure for the new grouped index
    grouped_index = {
        "index_timestamp": spatial_index.get("index_timestamp"),
        "extraction_method": spatial_index.get("extraction_method"),
        "total_file_count": spatial_index.get("file_count", 0),
        "datasets": {}
    }
    
    # A mapping from source ID to a list of its files
    dataset_files = defaultdict(list)
    
    # Get all files from the flat index structure
    all_files = spatial_index.get("utm_zones", {}).get("geographic", {}).get("files", [])
    if not all_files:
        logging.warning("No files found in spatial index under 'utm_zones.geographic.files'.")
        return grouped_index

    logging.info(f"Found {len(all_files)} total files to process.")

    # Sort sources by path length (descending) to handle nested paths correctly.
    # This ensures a file is matched to the most specific path first.
    sorted_sources = sorted(
        sources_config.items(), 
        key=lambda item: len(item[1].get('path', '')), 
        reverse=True
    )

    unassigned_files_count = 0
    unassigned_files = []

    for file_info in all_files:
        file_path = file_info.get("key")  # Using "key" field from spatial index
        if not file_path:
            continue

        assigned = False
        for source_id, source_details in sorted_sources:
            source_path = source_details.get("path", "")
            # Only match S3 sources for now (skip API and file sources)
            if source_details.get("source_type") == "s3" and file_path.startswith(source_path):
                dataset_files[source_id].append(file_info)
                assigned = True
                break  # Move to the next file once assigned
        
        if not assigned:
            unassigned_files_count += 1
            unassigned_files.append(file_path[:100] + "..." if len(file_path) > 100 else file_path)

    if unassigned_files_count > 0:
        logging.warning(f"{unassigned_files_count} files could not be assigned to any dataset.")
        logging.warning(f"Sample unassigned files: {unassigned_files[:5]}")

    # Populate the final grouped_index structure
    total_assigned_files = 0
    for source_id, source_details in sources_config.items():
        if source_id in dataset_files and len(dataset_files[source_id]) > 0:
            file_count = len(dataset_files[source_id])
            total_assigned_files += file_count
            
            grouped_index["datasets"][source_id] = {
                "name": source_details.get("name", source_id),
                "source_type": source_details.get("source_type"),
                "path": source_details.get("path"),
                "crs": source_details.get("crs"),
                "bounds": source_details.get("bounds", {}),
                "priority": source_details.get("priority", 99),
                "resolution_m": source_details.get("resolution_m"),
                "data_type": source_details.get("data_type"),
                "provider": source_details.get("provider"),
                "accuracy": source_details.get("accuracy"),
                "file_count": file_count,
                "metadata": source_details.get("metadata", {}),
                "files": dataset_files[source_id]
            }
            logging.info(f"Dataset '{source_id}': {file_count:,} files assigned")

    logging.info(f"Total files assigned: {total_assigned_files:,} / {len(all_files):,}")
    return grouped_index

def main():
    """Main script execution."""
    base_dir = Path(__file__).resolve().parent.parent
    
    sources_config_path = base_dir / "config" / "dem_sources.json"
    spatial_index_path = base_dir / "config" / "precise_spatial_index.json"
    output_path = base_dir / "config" / "grouped_spatial_index.json"
    
    sources_data = load_json_file(sources_config_path)
    # Convert sources list to dict for easier lookup
    sources_config = {src['id']: src for src in sources_data.get('elevation_sources', [])}
    
    spatial_index = load_json_file(spatial_index_path)
    
    grouped_index = group_files_by_dataset(sources_config, spatial_index)
    
    logging.info(f"Saving new grouped index to {output_path}")
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(grouped_index, f, indent=2)
    
    dataset_count = len(grouped_index['datasets'])
    total_grouped_files = sum(d.get('file_count', 0) for d in grouped_index['datasets'].values())
    
    logging.info("="*60)
    logging.info("✅ GROUPED SPATIAL INDEX GENERATION COMPLETE")
    logging.info("="*60)
    logging.info(f"📊 Total datasets created: {dataset_count}")
    logging.info(f"📁 Total files grouped: {total_grouped_files:,}")
    logging.info(f"💾 Output file: {output_path}")
    logging.info("="*60)
    
    # Show dataset summary
    for dataset_id, dataset_info in grouped_index['datasets'].items():
        logging.info(f"  {dataset_id}: {dataset_info['file_count']:,} files ({dataset_info['name']})")

if __name__ == "__main__":
    main()