#!/bin/bash
# Simple script to enable/disable agentic workflow

if [ "$1" = "on" ]; then
    echo "Enabling agentic workflow..."
    export USE_AGENTIC_WORKFLOW=true
    echo "USE_AGENTIC_WORKFLOW=true" >> .env
    echo "✅ Agentic workflow enabled!"
    echo "Restart the bot to apply changes: docker-compose restart bot"
elif [ "$1" = "off" ]; then
    echo "Disabling agentic workflow..."
    export USE_AGENTIC_WORKFLOW=false
    # Remove from .env
    grep -v "USE_AGENTIC_WORKFLOW" .env > .env.tmp && mv .env.tmp .env
    echo "❌ Agentic workflow disabled!"
    echo "Restart the bot to apply changes: docker-compose restart bot"
else
    echo "Usage: ./enable_agentic.sh [on|off]"
    echo "Current status:"
    if grep -q "USE_AGENTIC_WORKFLOW=true" .env 2>/dev/null; then
        echo "✅ Agentic workflow is ENABLED"
    else
        echo "❌ Agentic workflow is DISABLED"
    fi
fi