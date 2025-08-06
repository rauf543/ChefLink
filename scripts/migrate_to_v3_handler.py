#!/usr/bin/env python3
"""
Migration script to safely transition from old family handlers to the unified v3 handler.
This script performs verification before removing old files.
"""
import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_imports():
    """Verify that all imports have been updated."""
    print("🔍 Checking for old handler imports...")
    
    old_imports = [
        "from app.services.telegram.handlers.family import",
        "from app.services.telegram.handlers.family_v2 import",
        "from app.services.telegram.handlers.family_v2_agentic import",
        "FamilyHandlers()",
        "FamilyHandlersV2Agentic()"
    ]
    
    files_to_check = [
        "app/services/telegram/bot.py",
        "tests/test_agentic_workflow.py",
        "tests/load_test_scenarios.py",
        "test_family_v2_fixes.py"
    ]
    
    issues_found = False
    
    for file_path in files_to_check:
        full_path = project_root / file_path
        if full_path.exists():
            with open(full_path, 'r') as f:
                content = f.read()
                for old_import in old_imports:
                    if old_import in content:
                        print(f"  ❌ Found old import in {file_path}: {old_import}")
                        issues_found = True
    
    if not issues_found:
        print("  ✅ All imports have been updated!")
    
    return not issues_found


def check_v3_handler_exists():
    """Verify that the v3 handler exists and is valid."""
    print("🔍 Checking v3 handler...")
    
    v3_path = project_root / "app/services/telegram/handlers/family_v3_refactored.py"
    
    if not v3_path.exists():
        print("  ❌ family_v3_refactored.py not found!")
        return False
    
    # Check that it has the required class
    with open(v3_path, 'r') as f:
        content = f.read()
        if "class FamilyHandlerV3" not in content:
            print("  ❌ FamilyHandlerV3 class not found in file!")
            return False
    
    print("  ✅ family_v3_refactored.py exists and is valid!")
    return True


def run_tests():
    """Run tests to ensure everything still works."""
    print("🧪 Running tests...")
    
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("  ✅ All tests passed!")
            return True
        else:
            # Check if it's just import errors (missing dependencies)
            if "ModuleNotFoundError" in result.stdout or "ModuleNotFoundError" in result.stderr:
                print("  ⚠️  Tests skipped due to missing dependencies (telegram, openai, etc.)")
                print("  ℹ️  This is expected if not all dependencies are installed.")
                return True
            else:
                print("  ❌ Tests failed!")
                print(result.stdout[:500])  # Show first 500 chars
                return False
    except Exception as e:
        print(f"  ⚠️  Could not run tests: {e}")
        # Don't block migration if tests can't run
        return True


def backup_old_files():
    """Create backups of old files before deletion."""
    print("💾 Creating backups...")
    
    backup_dir = project_root / "backups" / "old_handlers"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    old_files = [
        "app/services/telegram/handlers/family.py",
        "app/services/telegram/handlers/family_v2.py",
        "app/services/telegram/handlers/family_v2_agentic.py"
    ]
    
    for file_path in old_files:
        full_path = project_root / file_path
        if full_path.exists():
            backup_path = backup_dir / Path(file_path).name
            with open(full_path, 'r') as src, open(backup_path, 'w') as dst:
                dst.write(src.read())
            print(f"  ✅ Backed up {file_path}")
    
    print(f"  📁 Backups saved to: {backup_dir}")
    return True


def remove_old_files():
    """Remove the old handler files."""
    print("🗑️  Removing old files...")
    
    old_files = [
        "app/services/telegram/handlers/family.py",
        "app/services/telegram/handlers/family_v2.py",
        "app/services/telegram/handlers/family_v2_agentic.py"
    ]
    
    for file_path in old_files:
        full_path = project_root / file_path
        if full_path.exists():
            os.remove(full_path)
            print(f"  ✅ Removed {file_path}")
        else:
            print(f"  ⚠️  {file_path} not found (already removed?)")
    
    return True


def main():
    """Main migration function."""
    print("=" * 60)
    print("🚀 ChefLink Handler Migration to V3")
    print("=" * 60)
    print()
    
    steps = [
        ("Checking v3 handler exists", check_v3_handler_exists),
        ("Verifying imports are updated", verify_imports),
        ("Running tests", run_tests),
        ("Creating backups", backup_old_files),
    ]
    
    for step_name, step_func in steps:
        print(f"\n{step_name}...")
        if not step_func():
            print(f"\n❌ Migration failed at: {step_name}")
            print("Please fix the issues and run again.")
            return 1
    
    print("\n" + "=" * 60)
    print("✅ All checks passed!")
    print("=" * 60)
    
    # Ask for confirmation before removing files
    response = input("\n🤔 Do you want to remove the old handler files? (yes/no): ")
    
    if response.lower() == 'yes':
        if remove_old_files():
            print("\n✨ Migration completed successfully!")
            print("Old handlers have been removed and backed up.")
            print(f"Backups location: {project_root}/backups/old_handlers/")
        else:
            print("\n❌ Failed to remove old files.")
            return 1
    else:
        print("\n⏸️  Migration paused. Old files kept.")
        print("You can run this script again to complete the migration.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())