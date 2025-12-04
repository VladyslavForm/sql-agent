#!/usr/bin/env python3
"""Development environment setup script for SQL Agent.

This script helps set up the development environment by:
- Validating Python version
- Installing dependencies
- Setting up pre-commit hooks
- Validating configuration
"""

import os
import subprocess
import sys
from pathlib import Path


def check_python_version() -> bool:
    """Check if Python version is compatible."""
    required_version = (3, 13)
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        print(f"❌ Python {required_version[0]}.{required_version[1]}+ required")
        print(f"   Current version: {current_version[0]}.{current_version[1]}")
        return False
    
    print(f"✅ Python version check passed: {current_version[0]}.{current_version[1]}")
    return True


def check_uv_installed() -> bool:
    """Check if UV package manager is installed."""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ UV package manager found: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ UV package manager not found")
    print("   Install from: https://docs.astral.sh/uv/getting-started/installation/")
    return False


def install_dependencies() -> bool:
    """Install project dependencies."""
    print("📦 Installing dependencies...")
    
    try:
        # Install main dependencies
        result = subprocess.run(["uv", "sync"], check=True, capture_output=True, text=True)
        print("✅ Main dependencies installed")
        
        # Install development dependencies
        result = subprocess.run(["uv", "sync", "--group", "dev"], check=True, capture_output=True, text=True)
        print("✅ Development dependencies installed")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print(f"   Output: {e.stdout}")
        print(f"   Error: {e.stderr}")
        return False


def create_env_file() -> bool:
    """Create .env file from template if it doesn't exist."""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    if not env_example.exists():
        print("❌ .env.example template not found")
        return False
    
    try:
        env_file.write_text(env_example.read_text())
        print("✅ Created .env file from template")
        print("   ⚠️  Please edit .env with your actual credentials")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False


def validate_project_structure() -> bool:
    """Validate that project structure is correct."""
    required_dirs = [
        "src",
        "src/config",
        "src/database",
        "src/llm",
        "src/vacation",
        "src/agents",
        "src/utils",
        "tests",
        "tests/unit",
        "tests/integration",
    ]
    
    missing_dirs = []
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing_dirs.append(dir_path)
    
    if missing_dirs:
        print(f"❌ Missing directories: {', '.join(missing_dirs)}")
        return False
    
    print("✅ Project structure validation passed")
    return True


def setup_git_hooks() -> bool:
    """Setup git hooks for development."""
    if not Path(".git").exists():
        print("⚠️  Git repository not initialized, skipping git hooks")
        return True
    
    try:
        # Install pre-commit if available
        subprocess.run(["pre-commit", "install"], check=True, capture_output=True)
        print("✅ Pre-commit hooks installed")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("⚠️  Pre-commit not available, skipping git hooks")
        return True


def run_initial_tests() -> bool:
    """Run initial tests to verify setup."""
    print("🧪 Running initial tests...")
    
    try:
        # Test import of main modules
        subprocess.run([
            "python", "-c", 
            "from src.config import get_settings; print('✅ Configuration module works')"
        ], check=True, capture_output=True)
        
        subprocess.run([
            "python", "-c",
            "from src.utils.logging import setup_logging; print('✅ Logging module works')"
        ], check=True, capture_output=True)
        
        print("✅ Initial tests passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Initial tests failed: {e}")
        return False


def main() -> None:
    """Main setup function."""
    print("🚀 Setting up SQL Agent development environment...\n")
    
    checks = [
        ("Python version", check_python_version),
        ("UV package manager", check_uv_installed),
        ("Project structure", validate_project_structure),
        ("Environment file", create_env_file),
        ("Dependencies", install_dependencies),
        ("Git hooks", setup_git_hooks),
        ("Initial tests", run_initial_tests),
    ]
    
    failed_checks = []
    
    for check_name, check_func in checks:
        print(f"\n🔍 {check_name}:")
        if not check_func():
            failed_checks.append(check_name)
    
    print("\n" + "="*50)
    
    if failed_checks:
        print(f"❌ Setup incomplete. Failed checks: {', '.join(failed_checks)}")
        print("\nPlease resolve the issues above and run the setup again.")
        sys.exit(1)
    else:
        print("🎉 Development environment setup completed successfully!")
        print("\nNext steps:")
        print("1. Edit .env with your actual credentials")
        print("2. Run: python -m src.main setup")
        print("3. Start developing!")


if __name__ == "__main__":
    main()