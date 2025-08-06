#!/usr/bin/env python3
"""
Cleanup script to remove redundant files and optimize the codebase after refactoring.
Run this to clean up obsolete files, cache, and unnecessary development artifacts.
"""
import os
import sys
import shutil
from pathlib import Path
from typing import List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


def get_file_size(file_path: Path) -> int:
    """Get file size in bytes."""
    try:
        return file_path.stat().st_size if file_path.exists() else 0
    except:
        return 0


def calculate_directory_size(dir_path: Path) -> int:
    """Calculate total size of a directory."""
    total_size = 0
    if dir_path.exists() and dir_path.is_dir():
        for file_path in dir_path.rglob('*'):
            if file_path.is_file():
                total_size += get_file_size(file_path)
    return total_size


class CodebaseCleaner:
    """Clean up redundant and unnecessary files from the codebase."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.project_root = project_root
        self.total_saved = 0
        self.files_removed = []
        self.dirs_removed = []
    
    def clean_obsolete_test_files(self) -> int:
        """Remove obsolete test files from root directory."""
        print("\n🧹 Cleaning obsolete test files...")
        
        obsolete_files = [
            "test_family_v2_fixes.py",
            "test_family_v3_migration.py"
        ]
        
        space_saved = 0
        for file_name in obsolete_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                size = get_file_size(file_path)
                space_saved += size
                
                if not self.dry_run:
                    os.remove(file_path)
                    self.files_removed.append(file_name)
                
                print(f"  {'Would remove' if self.dry_run else '✅ Removed'} {file_name} ({format_size(size)})")
            else:
                print(f"  ⚠️  {file_name} not found (already removed?)")
        
        return space_saved
    
    def clean_python_cache(self) -> int:
        """Remove Python cache files and directories."""
        print("\n🧹 Cleaning Python cache...")
        
        space_saved = 0
        cache_count = 0
        
        # Remove __pycache__ directories
        for cache_dir in self.project_root.rglob('__pycache__'):
            size = calculate_directory_size(cache_dir)
            space_saved += size
            cache_count += 1
            
            if not self.dry_run:
                shutil.rmtree(cache_dir)
                self.dirs_removed.append(str(cache_dir.relative_to(self.project_root)))
        
        # Remove .pyc files
        for pyc_file in self.project_root.rglob('*.pyc'):
            size = get_file_size(pyc_file)
            space_saved += size
            cache_count += 1
            
            if not self.dry_run:
                os.remove(pyc_file)
                self.files_removed.append(str(pyc_file.relative_to(self.project_root)))
        
        # Remove .pyo files
        for pyo_file in self.project_root.rglob('*.pyo'):
            size = get_file_size(pyo_file)
            space_saved += size
            cache_count += 1
            
            if not self.dry_run:
                os.remove(pyo_file)
                self.files_removed.append(str(pyo_file.relative_to(self.project_root)))
        
        print(f"  {'Would remove' if self.dry_run else '✅ Removed'} {cache_count} cache files/dirs ({format_size(space_saved)})")
        
        return space_saved
    
    def clean_backup_files(self) -> int:
        """Remove backup files from old migration."""
        print("\n🧹 Cleaning backup files...")
        
        backup_dir = self.project_root / "backups" / "old_handlers"
        
        if backup_dir.exists():
            size = calculate_directory_size(backup_dir)
            
            # List what's in the backup
            backup_files = list(backup_dir.glob('*.py'))
            for file in backup_files:
                file_size = get_file_size(file)
                print(f"  📁 {file.name} ({format_size(file_size)})")
            
            if not self.dry_run:
                shutil.rmtree(backup_dir)
                # Remove backups dir if empty
                backups_root = self.project_root / "backups"
                if backups_root.exists() and not list(backups_root.iterdir()):
                    backups_root.rmdir()
                self.dirs_removed.append("backups/old_handlers")
            
            print(f"  {'Would remove' if self.dry_run else '✅ Removed'} backup directory ({format_size(size)})")
            return size
        else:
            print("  ⚠️  No backup files found")
            return 0
    
    def clean_migration_scripts(self) -> int:
        """Remove completed migration scripts."""
        print("\n🧹 Cleaning migration scripts...")
        
        migration_files = [
            "scripts/migrate_to_v3_handler.py",
            "enable_agentic.sh"  # This could be integrated into CLI
        ]
        
        space_saved = 0
        for file_path in migration_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                size = get_file_size(full_path)
                space_saved += size
                
                if not self.dry_run:
                    os.remove(full_path)
                    self.files_removed.append(file_path)
                
                print(f"  {'Would remove' if self.dry_run else '✅ Removed'} {file_path} ({format_size(size)})")
        
        return space_saved
    
    def review_test_pdfs(self) -> int:
        """Review and optionally clean test PDF files."""
        print("\n📊 Analyzing test PDF files...")
        
        test_recipes_dir = self.project_root / "test-recipes"
        
        if test_recipes_dir.exists():
            pdf_files = list(test_recipes_dir.glob('*.pdf'))
            total_size = sum(get_file_size(f) for f in pdf_files)
            
            print(f"  Found {len(pdf_files)} PDF files totaling {format_size(total_size)}")
            
            # Group by size to identify potential duplicates
            size_groups = {}
            for pdf in pdf_files:
                size = get_file_size(pdf)
                if size not in size_groups:
                    size_groups[size] = []
                size_groups[size].append(pdf.name)
            
            # Report potential duplicates
            duplicates_found = False
            for size, files in size_groups.items():
                if len(files) > 1:
                    duplicates_found = True
                    print(f"  ⚠️  Potential duplicates ({format_size(size)} each): {', '.join(files)}")
            
            if not duplicates_found:
                print("  ✅ No obvious duplicates found")
            
            print(f"  ℹ️  Consider reviewing if all {len(pdf_files)} PDFs are needed for testing")
            
            return 0  # Don't auto-delete PDFs, just report
        else:
            print("  ⚠️  test-recipes directory not found")
            return 0
    
    def fix_remaining_imports(self) -> None:
        """Fix any remaining incorrect imports."""
        print("\n🔧 Checking for remaining import issues...")
        
        # Check load_test_scenarios.py for old type hints
        load_test_file = self.project_root / "tests" / "load_test_scenarios.py"
        
        if load_test_file.exists():
            content = load_test_file.read_text()
            
            # Check for old handler references
            if "FamilyHandlersV2Agentic" in content:
                print(f"  ⚠️  Found old references in {load_test_file.name}")
                print("     Lines with issues: type hints on lines 83, 148")
                print("     These should be updated to use FamilyHandlerV3")
            else:
                print(f"  ✅ {load_test_file.name} is clean")
    
    def add_to_gitignore(self) -> None:
        """Ensure cache and backup files are in .gitignore."""
        print("\n📝 Updating .gitignore...")
        
        gitignore_path = self.project_root / ".gitignore"
        
        patterns_to_add = [
            "\n# Python cache",
            "__pycache__/",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".Python",
            "\n# Backups",
            "backups/",
            "\n# Test outputs",
            "test_*.py",  # Be careful with this one
        ]
        
        if gitignore_path.exists():
            current_content = gitignore_path.read_text()
            
            patterns_added = []
            for pattern in patterns_to_add:
                if pattern.startswith("\n"):
                    continue  # Skip comment lines for checking
                if pattern not in current_content and not pattern.startswith("test_"):
                    patterns_added.append(pattern)
            
            if patterns_added:
                print(f"  ℹ️  Consider adding these patterns to .gitignore:")
                for pattern in patterns_added:
                    print(f"     {pattern}")
            else:
                print("  ✅ .gitignore already has necessary patterns")
    
    def run(self) -> None:
        """Run all cleanup tasks."""
        print("=" * 60)
        print("🚀 ChefLink Codebase Cleanup")
        print("=" * 60)
        
        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - No files will be deleted")
        
        # Run cleanup tasks
        self.total_saved += self.clean_obsolete_test_files()
        self.total_saved += self.clean_python_cache()
        self.total_saved += self.clean_backup_files()
        self.total_saved += self.clean_migration_scripts()
        
        # Review tasks (no automatic deletion)
        self.review_test_pdfs()
        self.fix_remaining_imports()
        self.add_to_gitignore()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Cleanup Summary")
        print("=" * 60)
        
        if self.dry_run:
            print(f"Would save: {format_size(self.total_saved)}")
            print(f"Would remove: {len(self.files_removed) + len(self.dirs_removed)} items")
        else:
            print(f"✅ Space saved: {format_size(self.total_saved)}")
            print(f"✅ Files removed: {len(self.files_removed)}")
            print(f"✅ Directories removed: {len(self.dirs_removed)}")
            
            if self.files_removed or self.dirs_removed:
                print("\nRemoved items:")
                for item in self.files_removed[:10]:  # Show first 10
                    print(f"  - {item}")
                if len(self.files_removed) > 10:
                    print(f"  ... and {len(self.files_removed) - 10} more files")
                
                for item in self.dirs_removed[:5]:  # Show first 5
                    print(f"  - {item}/")
                if len(self.dirs_removed) > 5:
                    print(f"  ... and {len(self.dirs_removed) - 5} more directories")
        
        print("\n✨ Cleanup complete!")
        
        # Provide next steps
        print("\n📋 Recommended next steps:")
        print("1. Review test PDFs in test-recipes/ for potential cleanup")
        print("2. Fix type hints in tests/load_test_scenarios.py")
        print("3. Consider documenting the difference between meal_planning_agent.py and meal_planning_service.py")
        print("4. Run 'git add -A && git commit' to commit cleanup changes")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up ChefLink codebase')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompts')
    
    args = parser.parse_args()
    
    if not args.yes and not args.dry_run:
        response = input("⚠️  This will delete files. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            return 1
    
    cleaner = CodebaseCleaner(dry_run=args.dry_run)
    cleaner.run()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())