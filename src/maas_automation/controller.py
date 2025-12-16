"""Main orchestration controller"""
import logging
from typing import Dict, Optional
from .client import MaasClient
from .machine import MachineManager
from .storage import StorageManager
from .bios import BIOSManager
from .boot import BootManager
from .network import NetworkManager

log = logging.getLogger("maas_automation.controller")


class Controller:
    """Orchestrates MAAS automation workflows"""

    def __init__(self, api_url: str, api_key: str, max_retries: int = 5):
        self.client = MaasClient(api_url, api_key)
        self.machine = MachineManager(self.client, max_retries=max_retries)
        self.storage = StorageManager(self.client)
        self.bios = BIOSManager(self.client)
        self.boot = BootManager(self.client)
        self.network = NetworkManager(self.client, max_retries=max_retries)
        self.max_retries = max_retries
        
        if max_retries == 0:
            log.info("⚠️  Infinite retry mode enabled - operations will retry forever on failure")

    def execute_workflow(self, cfg: Dict) -> list:
        """
        Execute complete machine workflow based on configuration.
        
        Returns list of system_ids processed.
        """
        actions = cfg.get('actions', [])
        machines_cfg = cfg.get('machines', [])
        
        # Support legacy single machine config
        if not machines_cfg and cfg.get('machine'):
            machines_cfg = [cfg.get('machine')]
        
        if not machines_cfg:
            log.error("No machines defined in configuration")
            return []
        
        storage_cfg = cfg.get('storage', {})
        bios_cfg = cfg.get('bios', {})
        boot_order = cfg.get('boot_order', [])
        release_cfg = cfg.get('release', {})
        
        system_ids = []
        
        # Process each machine
        for idx, machine_cfg in enumerate(machines_cfg, 1):
            log.info("\n" + "=" * 60)
            log.info(f"PROCESSING MACHINE {idx}/{len(machines_cfg)}: {machine_cfg.get('hostname', 'unknown')}")
            log.info("=" * 60)
            
            try:
                system_id = self._execute_single_machine(machine_cfg, actions, storage_cfg, 
                                                          bios_cfg, boot_order, release_cfg)
                if system_id:
                    system_ids.append(system_id)
                    log.info(f"✓ Successfully processed machine: {system_id}")
                else:
                    log.warning(f"Machine {machine_cfg.get('hostname')} was not processed (no system_id)")
            except Exception as e:
                log.error(f"Failed to process machine {machine_cfg.get('hostname')}: {e}")
                log.info("Continuing with next machine...")
                continue
        
        return system_ids

    def _execute_single_machine(self, machine_cfg: Dict, actions: list, storage_cfg: Dict,
                                bios_cfg: Dict, boot_order: list, release_cfg: Dict) -> Optional[str]:
        """
        Execute workflow for a single machine.
        
        Returns system_id of the machine.
        """
        system_id = None
        machine = None

        # Step 1: Create or find machine
        if 'create_machine' in actions or 'find_machine' in actions:
            log.info("=" * 60)
            log.info("STEP: Create/Find Machine")
            log.info("=" * 60)
            try:
                machine = self.machine.create_or_find(machine_cfg)
                
                if not machine:
                    log.error("create_or_find returned None")
                    return None
                    
                system_id = machine.get('system_id')
                
                if not system_id:
                    log.error(f"Machine object has no system_id. Machine data: {machine}")
                    return None
                    
                log.info(f"Machine system_id: {system_id}\n")
            except Exception as e:
                log.error(f"Failed to create/find machine: {e}")
                return None
        else:
            # If no create/find action, must have hostname to lookup existing machine
            hostname = machine_cfg.get('hostname')
            if not hostname:
                log.error("No 'create_machine' action specified and no hostname provided")
                return None
            
            log.info(f"Looking up existing machine: {hostname}")
            machine = self.machine.find_by_hostname(hostname)
            
            if not machine:
                log.error(f"Machine '{hostname}' not found. Add 'create_machine' to actions to create it.")
                return None
            
            system_id = machine.get('system_id')
            log.info(f"Found machine system_id: {system_id}\n")

        if not system_id:
            log.error("No machine system_id available")
            return None

        # Step 2: Update power configuration
        if 'set_power' in actions:
            log.info("=" * 60)
            log.info("STEP: Configure Power")
            log.info("=" * 60)
            self.machine.update_power(system_id, machine_cfg)
            log.info("")

        # Step 3: Apply BIOS settings
        if 'set_bios' in actions and bios_cfg:
            log.info("=" * 60)
            log.info("STEP: Configure BIOS")
            log.info("=" * 60)
            self.bios.apply_settings(system_id, bios_cfg)
            log.info("")

        # Step 4: Set boot order
        if 'set_boot_order' in actions and boot_order:
            log.info("=" * 60)
            log.info("STEP: Configure Boot Order")
            log.info("=" * 60)
            self.boot.set_boot_device(system_id, boot_order)
            log.info("")

        # Step 5: Configure storage layout (before commissioning)
        if 'configure_storage' in actions:
            log.info("=" * 60)
            log.info("STEP: Configure Storage Layout")
            log.info("=" * 60)
            device = storage_cfg.get('device')
            params = storage_cfg.get('params', {})
            self.storage.apply_layout(system_id, device=device, params=params)
            log.info("")

        # Step 6: Commission machine
        if 'commission' in actions:
            log.info("=" * 60)
            log.info("STEP: Commission Machine")
            log.info("=" * 60)
            scripts = machine_cfg.get('commissioning_scripts')
            wait = machine_cfg.get('wait_commissioning', True)
            timeout = machine_cfg.get('commission_timeout', 1200)
            self.machine.commission(system_id, scripts=scripts, wait=wait, timeout=timeout)
            log.info("")

        # Step 7: Configure network (bonds/interfaces) - after commission, before deploy
        if 'configure_network' in actions:
            log.info("=" * 60)
            log.info("STEP: Configure Network")
            log.info("=" * 60)
            network_cfg = machine_cfg.get('network', {})
            if not network_cfg:
                log.warning("No network configuration provided in machine config")
            else:
                self.network.apply_network_config(system_id, network_cfg)
            log.info("")

        # Step 8: Deploy machine
        if 'deploy' in actions:
            log.info("=" * 60)
            log.info("STEP: Deploy Machine")
            log.info("=" * 60)
            distro = machine_cfg.get('distro_series')
            user_data = machine_cfg.get('cloud_init')
            wait = machine_cfg.get('wait_deployment', True)
            timeout = machine_cfg.get('deploy_timeout', 1800)
            self.machine.deploy(system_id, distro_series=distro, user_data=user_data, 
                              wait=wait, timeout=timeout)
            log.info("")

        # Step 9: Release machine
        if 'release' in actions:
            log.info("=" * 60)
            log.info("STEP: Release Machine")
            log.info("=" * 60)
            erase = release_cfg.get('wipe_disks', True)
            wait = release_cfg.get('wait_release', True)
            timeout = release_cfg.get('release_timeout', 1800)
            self.machine.release(system_id, erase=erase, wait=wait, timeout=timeout)
            log.info("")

        # Step 10: Delete machine
        if 'delete' in actions:
            log.info("=" * 60)
            log.info("STEP: Delete Machine")
            log.info("=" * 60)
            self.machine.delete(system_id)
            log.info("")
            return None  # Machine no longer exists

        return system_id

    def list_machines(self):
        """List all machines in MAAS"""
        machines = self.client.list_machines()
        
        print("\n" + "=" * 120)
        print(f"{'SYSTEM_ID':<15} {'HOSTNAME':<20} {'STATUS':<15} {'MAC ADDRESS':<20} {'BMC IP':<20}")
        print("=" * 120)
        
        for m in machines:
            system_id = m['system_id']
            hostname = m.get('hostname', '-')
            status = m.get('status_name', '-')
            
            # Get first MAC address from interfaces
            mac_addr = '-'
            interfaces = m.get('interface_set', m.get('interfaces', []))
            if interfaces and len(interfaces) > 0:
                mac_addr = interfaces[0].get('mac_address', '-')
            
            # Get BMC IP from power parameters
            bmc_ip = '-'
            power_params = m.get('power_parameters', {})
            if isinstance(power_params, dict):
                bmc_ip = power_params.get('power_address', '-')
            
            print(f"{system_id:<15} {hostname:<20} {status:<15} {mac_addr:<20} {bmc_ip:<20}")
        
        print("=" * 120)
        print(f"Total: {len(machines)} machines\n")
