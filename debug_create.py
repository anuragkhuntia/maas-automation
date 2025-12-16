#!/usr/bin/env python3
"""
Debug script to test machine creation

Usage:
    python3 debug_create.py -i config.json
"""
import sys
import os
import json
import logging

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from maas_automation.client import MaasClient
from maas_automation.machine import MachineManager

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

if len(sys.argv) < 3 or sys.argv[1] != '-i':
    print("Usage: python3 debug_create.py -i config.json")
    sys.exit(1)

# Load config
with open(sys.argv[2]) as f:
    cfg = json.load(f)

api_url = cfg['maas_api_url']
api_key = cfg['maas_api_key']
machines = cfg.get('machines', [])

if not machines:
    print("No machines in config")
    sys.exit(1)

machine_cfg = machines[0]
print(f"\n=== Testing with machine: {machine_cfg.get('hostname')} ===\n")

# Create client
client = MaasClient(api_url, api_key)
manager = MachineManager(client)

# Try to create/find
try:
    print("Calling create_or_find...")
    machine = manager.create_or_find(machine_cfg)
    print(f"\n✓ Success!")
    print(f"System ID: {machine.get('system_id')}")
    print(f"Hostname: {machine.get('hostname')}")
    print(f"Status: {machine.get('status_name')}")
except Exception as e:
    print(f"\n✗ Failed: {e}")
    import traceback
    traceback.print_exc()
