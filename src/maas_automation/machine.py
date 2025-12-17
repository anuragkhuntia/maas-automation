"""Machine lifecycle operations with state polling"""
from typing import Optional, Dict, List
import logging
import time
from .client import MaasClient
from .utils import wait_for_state

log = logging.getLogger("maas_automation.machine")


class MachineManager:
    """Manages machine lifecycle operations"""

    def __init__(self, client: MaasClient, max_retries: int = 5):
        self.client = client
        self.max_retries = max_retries

    def find_by_hostname(self, hostname: str) -> Optional[Dict]:
        """Find machine by hostname (case-insensitive)"""
        hostname = hostname.lower()
        
        # Retry list_machines on timeout
        from .utils import retry
        try:
            machines = retry(lambda: self.client.list_machines(), retries=self.max_retries, delay=2.0)
        except Exception as e:
            log.error(f"Failed to list machines after retries: {e}")
            raise
        
        for m in machines:
            if m.get("hostname", "").lower() == hostname:
                return m
        return None

    def find_by_mac(self, mac: str) -> Optional[Dict]:
        """Find machine by MAC address"""
        mac = mac.lower().replace(":", "").replace("-", "")
        
        # Retry list_machines on timeout
        from .utils import retry
        try:
            machines = retry(lambda: self.client.list_machines(), retries=self.max_retries, delay=2.0)
        except Exception as e:
            log.error(f"Failed to list machines after retries: {e}")
            raise
        
        for m in machines:
            for iface in m.get("interfaces", []):
                iface_mac = iface.get("mac_address", "").lower().replace(":", "").replace("-", "")
                if iface_mac == mac:
                    return m
        return None

    def find_by_serial(self, serial: str) -> Optional[Dict]:
        """Find machine by system serial number"""
        from .utils import retry
        try:
            machines = retry(lambda: self.client.list_machines(), retries=self.max_retries, delay=2.0)
        except Exception as e:
            log.error(f"Failed to list machines after retries: {e}")
            raise
        
        serial_lower = serial.lower().strip()
        for m in machines:
            # Check hardware_info for serial number
            hw_info = m.get("hardware_info", {})
            if isinstance(hw_info, dict):
                system_serial = hw_info.get("system_serial", "").lower().strip()
                if system_serial and system_serial == serial_lower:
                    return m
            
            # Also check tag_names for serial number tags
            tag_names = m.get("tag_names", [])
            for tag in tag_names:
                if serial_lower in tag.lower():
                    return m
        
        return None

    def update_hostname(self, system_id: str, new_hostname: str) -> Dict:
        """Update machine hostname"""
        log.info(f"Updating hostname to: {new_hostname}")
        try:
            machine = self.client.request(
                "PUT",
                f"machines/{system_id}/",
                data={"hostname": new_hostname}
            )
            log.info(f"✓ Hostname updated to: {new_hostname}")
            return machine
        except Exception as e:
            log.error(f"Failed to update hostname: {e}")
            raise

    def create_or_find(self, cfg: Dict) -> Dict:
        """Find machine by serial number only and update hostname if needed"""
        hostname = cfg.get("hostname")
        serial = cfg.get("serial_number")

        if not serial:
            raise ValueError("Machine config must have 'serial_number' to match discovered machines")

        # Search ONLY by serial number
        log.info(f"Searching for machine by serial number: {serial}")
        machine = self.find_by_serial(serial)
        
        if not machine:
            log.error(f"Machine with serial '{serial}' not found in MAAS")
            log.info("Ensure the machine has PXE booted and been discovered by MAAS")
            return None
        
        current_hostname = machine.get('hostname', 'unknown')
        system_id = machine['system_id']
        status = machine.get('status_name', 'unknown')
        
        log.info(f"✓ Found machine by serial: {current_hostname} ({system_id}) - Status: {status}")
        
        # Always update hostname to match what's in the JSON config
        if hostname and current_hostname != hostname:
            log.info(f"Updating hostname from '{current_hostname}' to '{hostname}'")
            try:
                machine = self.update_hostname(system_id, hostname)
                log.info(f"✓ Hostname updated successfully")
            except Exception as e:
                log.error(f"Failed to update hostname: {e}")
                raise
        elif hostname:
            log.info(f"Hostname already matches: {hostname}")
        
        return machine

        # Machine not found - create new one
        # Note: In MAAS, machines that PXE boot are auto-discovered. 
        # Manual creation is only needed for machines that haven't PXE booted yet.
        log.info(f"Machine not found in MAAS. Creating new machine entry...")
        
        payload = {
            "hostname": hostname or f"node-{pxe_mac.replace(':', '')}",
            "architecture": cfg.get("architecture", "amd64/generic"),  # Required field
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
        log.info("Creating machine in MAAS (this adds it without commissioning)...")
        
        from .utils import retry
        try:
            # Retry machine creation on timeout
            machine = retry(
                lambda: self.client.create_machine(payload),
                retries=self.max_retries,
                delay=3.0,
                backoff=2.0
            )
            
            if not machine or not machine.get('system_id'):
                raise ValueError(f"Machine creation returned invalid response: {machine}")
            
            log.info(f"✓ Machine added to MAAS: {machine['system_id']} (Status: {machine.get('status_name', 'New')})")
            log.info(f"Note: Machine is added but NOT commissioned. Use 'commission' action to commission it.")
            return machine
        except Exception as e:
            log.error(f"Failed to create machine after retries: {e}")
            log.error(f"Tip: If machine already PXE booted, it may be auto-discovered. Check MAAS UI for 'New' machines.")
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
            try:
                final_state = wait_for_state(
                    lambda: self.get_state(system_id),
                    target_states=["READY", "DEPLOYED"],
                    timeout=timeout,
                    poll_interval=10,
                    error_states=["FAILED_COMMISSIONING", "FAILED"]
                )
                log.info(f"✓ Commissioning complete: {final_state}")
                return final_state
            except Exception as e:
                log.error(f"Commissioning wait failed: {e}")
                raise

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
            try:
                final_state = wait_for_state(
                    lambda: self.get_state(system_id),
                    target_states=["DEPLOYED"],
                    timeout=timeout,
                    poll_interval=15,
                    error_states=["FAILED_DEPLOYMENT", "FAILED"]
                )
                log.info(f"✓ Deployment complete: {final_state}")
                return final_state
            except Exception as e:
                log.error(f"Deployment wait failed: {e}")
                raise

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
