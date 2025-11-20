#!/bin/bash
set -e

# Pandora Patiobar Development Deployment Script
# Copies custom component files to Home Assistant using rsync

# Configuration
HA_HOST="homeassistant.local"
HA_USER="$USER"
HA_CONFIG_DIR="/config"
COMPONENT_NAME="pandora_patiobar"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Pandora Patiobar Development Deployment${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Check for SSH key authentication
echo -e "${YELLOW}Checking SSH connection...${NC}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 ${HA_USER}@${HA_HOST} exit 2>/dev/null; then
    echo -e "${YELLOW}⚠ SSH key authentication not set up${NC}"
    echo ""
    echo "To avoid password prompts on every deployment, set up SSH keys:"
    echo -e "  ${GREEN}ssh-copy-id ${HA_USER}@${HA_HOST}${NC}"
    echo ""
    echo "You will be prompted for your password 2-3 times during this deployment."
    echo ""
    read -p "Press Enter to continue or Ctrl+C to cancel..."
fi

# Check if custom_components directory exists locally
if [ ! -d "custom_components/$COMPONENT_NAME" ]; then
    echo -e "${RED}Error: custom_components/$COMPONENT_NAME directory not found${NC}"
    echo "Please run this script from the repository root"
    exit 1
fi

# Sync custom component Python files
echo -e "${YELLOW}Syncing custom component files...${NC}"
rsync -avz --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.DS_Store' \
    --exclude='*.swp' \
    --exclude='*~' \
    --exclude='.git*' \
    --exclude='*.log' \
    --exclude='.pytest_cache' \
    --exclude='*.egg-info' \
    custom_components/$COMPONENT_NAME/ \
    ${HA_USER}@${HA_HOST}:${HA_CONFIG_DIR}/custom_components/${COMPONENT_NAME}/

echo -e "${GREEN}✓ Custom component files synced${NC}"

# Summary
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart Home Assistant to load changes"
echo "  2. Check that Pandora Patiobar integration loads successfully"
echo ""
echo "Quick commands:"
echo -e "  ${YELLOW}Restart HA:${NC} ssh ${HA_USER}@${HA_HOST} 'ha core restart'"
echo -e "  ${YELLOW}Check logs:${NC} ssh ${HA_USER}@${HA_HOST} 'tail -f /config/home-assistant.log | grep pandora_patiobar'"
echo -e "  ${YELLOW}Check integration:${NC} Look for 'Pandora' in Settings > Devices & Services"
echo ""

