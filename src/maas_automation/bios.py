"""BIOS configuration helpers"""
import logging
from .client import MaasClient
from typing import Dict

log = logging.getLogger("maas_automation.bios")


class BIOSManager:
    """Manages BIOS settings (vendor-agnostic)"""

    def __init__(self, client: MaasClient):
        self.client = client

    def apply_settings(self, system_id: str, settings: Dict):
        """
        Apply BIOS settings to machine.
        
        Note: MAAS doesn't expose direct BIOS control via API.
        This stores settings as machine tags/notes for reference.
        For actual BIOS changes, use vendor-specific tools (Redfish, iDRAC, iLO).
        """
        log.info(f"Storing BIOS settings for {system_id}")
        
        payload = {}
        if settings.get('tags'):
            payload['tag_names'] = settings['tags']
        
        if settings.get('notes'):
            payload['description'] = settings['notes']

        if payload:
            result = self.client.update_machine(system_id, payload)
            log.info("✓ BIOS settings stored")
            return result
        
        log.warning("No BIOS settings to apply")
        return None
