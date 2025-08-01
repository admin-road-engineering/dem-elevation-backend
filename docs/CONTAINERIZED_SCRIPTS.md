# Containerized Scripts Guide

This guide covers running operational scripts in containerized environments for consistent execution across different systems.

## 🚀 Quick Start

### Prerequisites
- Docker Desktop installed and running
- Git repository cloned locally

### Run Common Operations
```bash
# Update campaign index
docker-scripts campaign-update --analyze
docker-scripts campaign-update --update

# Generate spatial indexes
docker-scripts spatial-index generate
docker-scripts nz-spatial-index generate

# Run validation
docker-scripts validate

# Run integration tests
docker-scripts test-integration
```

## 🏗️ Architecture

Containerized scripts provide:

- **Consistent Environment** - Same Python version, dependencies, and GDAL libraries
- **Isolated Execution** - Scripts run in dedicated container with controlled resources
- **State Management** - Redis service for scripts that need shared state
- **Volume Mounting** - Access to config files and log outputs
- **Security** - Non-root user execution for security

## 📋 Available Commands

### Campaign Management
```bash
# Analyze S3 bucket for new campaigns
docker-scripts campaign-update --analyze

# Update campaign index with new campaigns
docker-scripts campaign-update --update

# Validate campaign index integrity
docker-scripts campaign-update --validate
```

### Spatial Index Generation
```bash
# Generate Australian spatial index
docker-scripts spatial-index generate

# Generate New Zealand spatial index
docker-scripts nz-spatial-index generate

# Validate spatial indexes
docker-scripts validate
```

### Testing & Validation
```bash
# Run integration tests
docker-scripts test-integration

# Run custom validation script
docker-scripts custom scripts/my_validation.py
```

### Development & Debugging
```bash
# Open interactive shell
docker-scripts shell

# Run custom Python script
docker-scripts custom path/to/script.py arg1 arg2

# Build/rebuild containers
docker-scripts build

# Clean up containers and volumes
docker-scripts clean
```

## 🔧 Container Configuration

### Environment
Scripts run with:
- **APP_ENV**: `development` (allows Redis fallback)
- **PYTHONPATH**: `/app` for proper imports
- **GDAL**: Full geospatial library support
- **Redis**: Dedicated Redis instance on port 6380

### Volume Mounts
- **Config**: `./config` → `/app/config` (read-write for index updates)
- **Logs**: `./logs` → `/app/logs` (write access for log files)
- **Environment**: `.env.development` → `/app/.env` (configuration)

### Network
- **Isolated Network**: `dem-backend-scripts-network`
- **Redis Port**: 6380 (avoids conflicts with main development stack)

## 📊 Script Examples

### Campaign Index Update Workflow
```bash
# 1. Analyze what's changed (safe, read-only)
docker-scripts campaign-update --analyze

# 2. Update index with new campaigns
docker-scripts campaign-update --update

# 3. Validate the updated index
docker-scripts campaign-update --validate

# 4. Deploy updated config to production
git add config/ && git commit -m "Update campaign index" && git push
```

### Spatial Index Regeneration
```bash
# Full regeneration workflow
docker-scripts spatial-index generate
docker-scripts nz-spatial-index generate
docker-scripts validate

# Check results
docker-scripts shell
# Inside container:
ls -la config/
python -c "import json; print(len(json.load(open('config/phase3_campaign_populated_index.json'))['campaigns']))"
```

### Custom Script Development
```bash
# Create new script
echo 'print("Hello from container!")' > scripts/test_container.py

# Run in container
docker-scripts custom scripts/test_container.py

# Interactive development
docker-scripts shell
# Inside container:
python scripts/test_container.py
```

## 🔍 Debugging

### Check Container Status
```bash
# List running containers
docker ps

# Check script container logs
docker logs dem-backend-scripts

# Check Redis logs
docker logs dem-backend-scripts-redis
```

### Troubleshooting Common Issues

#### Script Fails to Start
```bash
# Rebuild container
docker-scripts build

# Check Docker resources
docker system df

# Clean and retry
docker-scripts clean
docker-scripts campaign-update --analyze
```

#### Permission Issues
```bash
# Check file permissions
docker-scripts shell
ls -la config/
ls -la logs/

# Scripts run as non-root user (UID 1000)
```

#### GDAL/Geospatial Issues
```bash
# Check GDAL installation
docker-scripts shell
gdalinfo --version
python -c "from osgeo import gdal; print(gdal.__version__)"
```

#### Redis Connection Issues
```bash
# Check Redis status
docker-compose -f scripts/docker/docker-compose.scripts.yml ps

# Test Redis connection
docker-scripts shell
python -c "import redis; r=redis.from_url('redis://redis-scripts:6379'); print(r.ping())"
```

## 🚨 Security Considerations

### User Permissions
- Scripts run as non-root user (`scriptuser`, UID 1000)
- Limited file system access via volume mounts
- Isolated network namespace

### Credential Management
- Environment file (`.env.development`) mounted read-only
- AWS credentials handled via environment variables
- No hardcoded secrets in containers

### Resource Limits
- Container memory/CPU limits can be configured in docker-compose file
- Automatic cleanup after script completion
- Isolated Redis instance with data persistence

## 🎯 Best Practices

### Script Development
1. **Test locally first** - Use `docker-scripts shell` for development
2. **Use relative paths** - Scripts work from `/app` working directory
3. **Handle errors gracefully** - Scripts should exit with proper error codes
4. **Log appropriately** - Use Python logging, output goes to `logs/` directory

### Operational Use
1. **Backup before updates** - Backup `config/` directory before major changes
2. **Validate results** - Always run validation after index updates
3. **Monitor resources** - Check Docker resource usage for long-running scripts
4. **Clean regularly** - Use `docker-scripts clean` to manage disk space

### Integration with CI/CD
```yaml
# Example GitHub Actions workflow
- name: Update Campaign Index
  run: |
    docker-scripts campaign-update --analyze
    docker-scripts campaign-update --update
    docker-scripts campaign-update --validate
```

## 📈 Performance

### Benchmark Results
- **Campaign Analysis**: ~30 seconds for 1,000+ campaigns
- **Spatial Index Generation**: ~45 seconds for Australian index
- **Memory Usage**: Peak ~500MB for large index operations
- **Disk Usage**: ~2GB for complete containerized environment

### Optimization Tips
- Use `--profile scripts` to only start needed services
- Clean up regularly with `docker-scripts clean`
- Monitor `docker stats` during long operations
- Use specific script commands instead of `custom` when possible

This containerized approach ensures consistent, secure, and isolated execution of operational scripts across different development and deployment environments.