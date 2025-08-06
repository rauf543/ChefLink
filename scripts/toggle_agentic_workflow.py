#!/usr/bin/env python3
"""Script to toggle the agentic workflow feature flag."""

import os
import json
import sys


def update_feature_flags(enable_agentic: bool, user_ids: list = None, percentage: int = 0):
    """Update feature flags environment variable."""
    
    flags = {
        "agentic_workflow": {
            "enabled": enable_agentic,
            "rollout_percentage": percentage,
            "user_allowlist": user_ids or [],
            "user_blocklist": []
        },
        "increased_context_window": {
            "enabled": enable_agentic,  # Enable with agentic workflow
            "max_tokens": 8000 if enable_agentic else 4000
        },
        "debug_mode": {
            "enabled": True,
            "log_traces": True,
            "log_costs": True
        }
    }
    
    # Create export command for shell
    export_cmd = f'export CHEFLINK_FEATURE_FLAGS=\'{json.dumps(flags)}\''
    
    print("Feature flags configuration:")
    print(json.dumps(flags, indent=2))
    print("\nTo apply these flags, run:")
    print(export_cmd)
    print("\nOr add to your .env file:")
    print(f'CHEFLINK_FEATURE_FLAGS={json.dumps(flags)}')
    
    # Also write to a file for docker-compose
    with open('.env.feature_flags', 'w') as f:
        f.write(f'CHEFLINK_FEATURE_FLAGS={json.dumps(flags)}\n')
    
    print("\nWritten to .env.feature_flags - you can source this file or add to docker-compose.yml")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Toggle agentic workflow feature flag")
    parser.add_argument("--enable", action="store_true", help="Enable agentic workflow")
    parser.add_argument("--disable", action="store_true", help="Disable agentic workflow")
    parser.add_argument("--users", nargs="+", help="Specific user IDs to enable for")
    parser.add_argument("--percentage", type=int, default=0, help="Rollout percentage (0-100)")
    
    args = parser.parse_args()
    
    if args.enable and args.disable:
        print("Error: Cannot both enable and disable")
        sys.exit(1)
    
    if not args.enable and not args.disable:
        print("Error: Must specify --enable or --disable")
        sys.exit(1)
    
    update_feature_flags(
        enable_agentic=args.enable,
        user_ids=args.users,
        percentage=args.percentage
    )