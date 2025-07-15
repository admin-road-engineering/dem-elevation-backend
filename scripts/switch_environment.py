import shutil
import sys
import logging
from pathlib import Path
from typing import Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_environment_file(env_path: Path) -> bool:
    """Validate that environment file contains required settings"""
    try:
        with open(env_path, 'r') as f:
            content = f.read()
            
        # Check for required DEM_SOURCES line
        if 'DEM_SOURCES=' not in content:
            logger.error(f"Environment file {env_path} missing DEM_SOURCES configuration")
            return False
            
        # Check for basic structure
        if len(content.strip()) < 10:
            logger.error(f"Environment file {env_path} appears to be empty or corrupted")
            return False
            
        logger.debug(f"Environment file {env_path} validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate environment file {env_path}: {e}")
        return False

def get_environment_info(mode: str) -> Dict[str, str]:
    """Get descriptive information about each environment mode"""
    return {
        'local': {
            'description': 'Local DTM only',
            'cost': 'Zero cost',
            'dependencies': 'None (local files only)',
            'suitable_for': 'Development and basic testing'
        },
        'api-test': {
            'description': 'GPXZ API + NZ Open Data + Local fallback',
            'cost': 'Free tier limits (100 GPXZ requests/day)',
            'dependencies': 'Internet access, optional GPXZ API key',
            'suitable_for': 'Integration testing without major costs'
        },
        'production': {
            'description': 'Full S3 + APIs + Local fallback',
            'cost': 'S3 storage + transfer costs, GPXZ paid tier',
            'dependencies': 'AWS credentials, GPXZ API key, internet access',
            'suitable_for': 'Production deployment with full capabilities'
        }
    }.get(mode, {
        'description': 'Unknown mode',
        'cost': 'Unknown',
        'dependencies': 'Unknown',
        'suitable_for': 'Unknown use case'
    })

def switch_env(mode: str) -> bool:
    """
    Switch between environment configurations
    
    Args:
        mode: Environment mode ('local', 'api-test', 'production')
        
    Returns:
        bool: True if switch successful, False otherwise
    """
    try:
        root = Path(__file__).parent.parent
        
        env_files = {
            'local': root / '.env.local',
            'api-test': root / '.env.api-test',
            'production': root / '.env.production'
        }
        
        if mode not in env_files:
            logger.error(f"Invalid mode '{mode}'. Choose from: {', '.join(env_files.keys())}")
            return False
        
        source = env_files[mode]
        target = root / '.env'
        
        # Validate source file exists and is readable
        if not source.exists():
            logger.error(f"Environment file {source} does not exist!")
            logger.info(f"Expected location: {source.absolute()}")
            return False
            
        if not source.is_file():
            logger.error(f"Path {source} is not a file")
            return False
            
        # Validate file content
        if not validate_environment_file(source):
            logger.error(f"Environment file {source} failed validation")
            return False
            
        # Backup existing .env if it exists
        if target.exists():
            backup_path = root / '.env.backup'
            try:
                shutil.copy2(target, backup_path)
                logger.debug(f"Backed up existing .env to {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to backup existing .env: {e}")
        
        # Perform the switch
        try:
            shutil.copy2(source, target)
            logger.info(f"Successfully switched to {mode} environment")
        except PermissionError as e:
            logger.error(f"Permission denied when copying environment file: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to copy environment file: {e}")
            return False
        
        # Display environment information
        env_info = get_environment_info(mode)
        print(f"Environment: {mode}")
        print(f"Description: {env_info['description']}")
        print(f"Cost: {env_info['cost']}")
        print(f"Dependencies: {env_info['dependencies']}")
        print(f"Suitable for: {env_info['suitable_for']}")
        
        # Log successful switch
        logger.info(f"Environment successfully switched to {mode}")
        logger.info(f"Active configuration: {target.absolute()}")
        
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error during environment switch: {e}")
        return False

def main():
    """Main entry point for environment switching"""
    # Default to local mode if no argument provided
    mode = sys.argv[1] if len(sys.argv) > 1 else 'local'
    
    # Show help if requested
    if mode in ['-h', '--help', 'help']:
        print("DEM Backend Environment Switcher")
        print("Usage: python switch_environment.py [mode]")
        print("\nAvailable modes:")
        for env_mode in ['local', 'api-test', 'production']:
            info = get_environment_info(env_mode)
            print(f"  {env_mode:12} - {info['description']}")
        print(f"\nDefault mode: local")
        sys.exit(0)
    
    # Perform the switch
    success = switch_env(mode)
    
    # Exit with appropriate code
    if success:
        print(f"\n✅ Successfully switched to {mode} environment")
        sys.exit(0)
    else:
        print(f"\n❌ Failed to switch to {mode} environment")
        print("Check the logs above for details")
        sys.exit(1)

if __name__ == "__main__":
    main()