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

    def find_by_bmc_ip(self, bmc_ip: str) -> Optional[Dict]:
        """Find machine by BMC/IPMI IP address in power parameters"""
        from .utils import retry
        try:
            machines = retry(lambda: self.client.list_machines(), retries=self.max_retries, delay=2.0)
        except Exception as e:
            log.error(f"Failed to list machines after retries: {e}")
            raise
        
        for m in machines:
            power_params = m.get("power_parameters", {})
            # Check various power_address fields
            machine_bmc = power_params.get("power_address", "")
            if machine_bmc == bmc_ip:
                return m
        return None

    def create_or_find(self, cfg: Dict) -> Dict:
        """Create machine or return existing one (including discovered machines)"""
        hostname = cfg.get("hostname")
        pxe_mac = cfg.get("pxe_mac")
        bmc_ip = None
        
        # Extract BMC IP from power_parameters if present
        if cfg.get("power_parameters"):
            bmc_ip = cfg["power_parameters"].get("power_address")

        if not hostname and not pxe_mac and not bmc_ip:
            raise ValueError("Machine config must have either 'hostname', 'pxe_mac', or 'power_address' (BMC IP)")

        # Try to find existing machine (including discovered/new machines)
        # Search by MAC first as it's most reliable for discovered machines
        if pxe_mac:
            log.info(f"Searching for machine by MAC: {pxe_mac}")
            machine = self.find_by_mac(pxe_mac)
            if machine:
                log.info(f"✓ Found existing machine by MAC: {machine.get('hostname', 'unknown')} ({machine['system_id']}) - Status: {machine.get('status_name', 'unknown')}")
                return machine

        # Search by BMC IP (useful when MAC might change but BMC IP is static)
        if bmc_ip:
            log.info(f"Searching for machine by BMC IP: {bmc_ip}")
            machine = self.find_by_bmc_ip(bmc_ip)
            if machine:
                log.info(f"✓ Found existing machine by BMC IP: {machine.get('hostname', 'unknown')} ({machine['system_id']}) - Status: {machine.get('status_name', 'unknown')}")
                return machine

        if hostname:
            log.info(f"Searching for machine by hostname: {hostname}")
            machine = self.find_by_hostname(hostname)
            if machine:
                log.info(f"✓ Found existing machine by hostname: {hostname} ({machine['system_id']}) - Status: {machine.get('status_name', 'unknown')}")
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
