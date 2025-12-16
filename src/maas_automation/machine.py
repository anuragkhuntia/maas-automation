"""Machine lifecycle operations with state polling"""
from typing import Optional, Dict, List
import logging
import time
from .client import MaasClient
from .utils import wait_for_state

log = logging.getLogger("maas_automation.machine")


class MachineManager:
    """Manages machine lifecycle operations"""

    def __init__(self, client: MaasClient):
        self.client = client

    def find_by_hostname(self, hostname: str) -> Optional[Dict]:
        """Find machine by hostname (case-insensitive)"""
        hostname = hostname.lower()
        machines = self.client.list_machines()
        
        for m in machines:
            if m.get("hostname", "").lower() == hostname:
                return m
        return None

    def find_by_mac(self, mac: str) -> Optional[Dict]:
        """Find machine by MAC address"""
        mac = mac.lower().replace(":", "").replace("-", "")
        machines = self.client.list_machines()
        
        for m in machines:
            for iface in m.get("interfaces", []):
                iface_mac = iface.get("mac_address", "").lower().replace(":", "").replace("-", "")
                if iface_mac == mac:
                    return m
        return None

    def create_or_find(self, cfg: Dict) -> Dict:
        """Create machine or return existing one"""
        hostname = cfg.get("hostname")
        pxe_mac = cfg.get("pxe_mac")

        if not hostname and not pxe_mac:
            raise ValueError("Machine config must have either 'hostname' or 'pxe_mac'")

        # Try to find existing machine
        if hostname:
            log.debug(f"Searching for existing machine: {hostname}")
            machine = self.find_by_hostname(hostname)
            if machine:
                log.info(f"Found existing machine: {hostname} ({machine['system_id']})")
                return machine

        if pxe_mac:
            log.debug(f"Searching for existing machine by MAC: {pxe_mac}")
            machine = self.find_by_mac(pxe_mac)
            if machine:
                log.info(f"Found existing machine by MAC: {pxe_mac} ({machine['system_id']})")
                return machine

        # Create new machine
        log.info(f"Machine not found. Creating new machine: {hostname or pxe_mac}")
        payload = {
            "hostname": hostname or f"node-{pxe_mac.replace(':', '')}",
        }
        
        if pxe_mac:
            payload["mac_addresses"] = [pxe_mac]
        
        if cfg.get("power_type"):
            payload["power_type"] = cfg["power_type"]
        
        if cfg.get("power_parameters"):
            # Flatten power parameters for form data
            for k, v in cfg["power_parameters"].items():
                payload[f"power_parameters_{k}"] = str(v)

        log.debug(f"Create machine payload: {payload}")
        
        try:
            machine = self.client.create_machine(payload)
            
            if not machine or not machine.get('system_id'):
                raise ValueError(f"Machine creation returned invalid response: {machine}")
            
            log.info(f"✓ Created machine: {machine['system_id']}")
            return machine
        except Exception as e:
            log.error(f"Failed to create machine: {e}")
            raise

    def update_power(self, system_id: str, cfg: Dict):
        """Update power configuration"""
        log.info(f"Updating power configuration for {system_id}")
        
        payload = {}
        if cfg.get("power_type"):
            payload["power_type"] = cfg["power_type"]
        
        if cfg.get("power_parameters"):
            for k, v in cfg["power_parameters"].items():
                payload[f"power_parameters_{k}"] = str(v)

        return self.client.update_machine(system_id, payload)

    def get_state(self, system_id: str) -> str:
        """Get current machine state"""
        machine = self.client.get_machine(system_id)
        return machine.get("status_name", "UNKNOWN")

    def commission(self, system_id: str, scripts: Optional[List[str]] = None, 
                   enable_ssh: bool = True, wait: bool = True, timeout: int = 1200):
        """Commission machine and optionally wait for completion"""
        log.info(f"Starting commissioning for {system_id}")
        
        payload = {"enable_ssh": str(enable_ssh).lower()}
        if scripts:
            payload["commissioning_scripts"] = ",".join(scripts) if isinstance(scripts, list) else scripts

        self.client.commission(system_id, payload)
        log.info("✓ Commissioning started")

        if wait:
            log.info("Waiting for commissioning to complete...")
            final_state = wait_for_state(
                lambda: self.get_state(system_id),
                target_states=["READY", "DEPLOYED"],
                timeout=timeout,
                poll_interval=10,
                error_states=["FAILED_COMMISSIONING", "FAILED"]
            )
            log.info(f"✓ Commissioning complete: {final_state}")
            return final_state

    def deploy(self, system_id: str, distro_series: Optional[str] = None, 
               user_data: Optional[str] = None, wait: bool = True, timeout: int = 1800):
        """Deploy machine and optionally wait for completion"""
        log.info(f"Starting deployment for {system_id}")
        
        payload = {}
        if distro_series:
            payload["distro_series"] = distro_series
        if user_data:
            payload["user_data"] = user_data

        self.client.deploy(system_id, payload)
        log.info("✓ Deployment started")

        if wait:
            log.info("Waiting for deployment to complete...")
            final_state = wait_for_state(
                lambda: self.get_state(system_id),
                target_states=["DEPLOYED"],
                timeout=timeout,
                poll_interval=15,
                error_states=["FAILED_DEPLOYMENT", "FAILED"]
            )
            log.info(f"✓ Deployment complete: {final_state}")
            return final_state

    def release(self, system_id: str, erase: bool = True, wait: bool = True, timeout: int = 1800):
        """Release machine and optionally wait for completion"""
        log.info(f"Releasing machine {system_id} (erase={erase})")
        
        self.client.release(system_id, erase=erase)
        log.info("✓ Release started")

        if wait:
            log.info("Waiting for release to complete...")
            final_state = wait_for_state(
                lambda: self.get_state(system_id),
                target_states=["READY"],
                timeout=timeout,
                poll_interval=10,
                error_states=["FAILED_RELEASING", "FAILED_DISK_ERASING", "FAILED"]
            )
            log.info(f"✓ Release complete: {final_state}")
            return final_state

    def delete(self, system_id: str):
        """Delete machine from MAAS"""
        log.info(f"Deleting machine {system_id}")
        self.client.delete_machine(system_id)
        log.info("✓ Machine deleted")

    def get_status(self, system_id: str) -> Dict:
        """Get detailed machine status"""
        return self.client.get_machine(system_id)
