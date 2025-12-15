"""Boot device configuration"""
from .client import MaasClient
import logging
from typing import List, Union

log = logging.getLogger("maas_automation.boot")


class BootManager:
    """Manages boot device configuration"""

    def __init__(self, client: MaasClient):
        self.client = client

    def set_boot_device(self, system_id: str, device: Union[str, List[str]], persistent: bool = True):
        """
        Set boot device order for machine.
        
        Note: MAAS API support for boot device is limited.
        This is best-effort and may require vendor-specific tools.
        """
        log.info(f"Setting boot device for {system_id}")
        
        if isinstance(device, list):
            device_str = ",".join(device)
        else:
            device_str = device

        payload = {
            "boot_device": device_str,
            "persistent": str(bool(persistent)).lower()
        }

        try:
            # Try various endpoints
            endpoints = [
                f"machines/{system_id}/set_boot_device",
                f"machines/{system_id}",  # with op=set_boot_device in data
            ]
            
            last_error = None
            for endpoint in endpoints:
                try:
                    if "set_boot_device" in endpoint:
                        result = self.client.request("POST", endpoint, data=payload)
                    else:
                        payload["op"] = "set_boot_device"
                        result = self.client.request("POST", endpoint, data=payload)
                    
                    log.info(f"✓ Boot device set: {device_str}")
                    return result
                except Exception as e:
                    last_error = e
                    continue

            if last_error:
                raise last_error

        except Exception as e:
            log.warning(f"Failed to set boot device (may not be supported): {e}")
            return None
