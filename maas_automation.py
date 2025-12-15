#!/usr/bin/env python3
"""
Standalone MAAS automation script - can be run directly with python3

Usage:
    python3 maas_automation.py -i config.json
    python3 maas_automation.py -i config.json -v
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the CLI
from maas_automation.cli import main

if __name__ == '__main__':
    main()
