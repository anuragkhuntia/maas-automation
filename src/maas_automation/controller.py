"""Main orchestration controller"""
import logging
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        parallel = cfg.get('parallel', True)  # Enable parallel processing by default
        
        system_ids = []
        
        if parallel and len(machines_cfg) > 1:
            log.info(f"\n⚡ Processing {len(machines_cfg)} machines in PARALLEL")
            log.info("=" * 60)
            
            # Process machines in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(machines_cfg)) as executor:
                # Submit all machines for processing
                future_to_machine = {
                    executor.submit(
                        self._execute_single_machine_safe,
                        machine_cfg, actions, storage_cfg, bios_cfg, boot_order, release_cfg
                    ): machine_cfg
                    for machine_cfg in machines_cfg
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_machine):
                    machine_cfg = future_to_machine[future]
                    hostname = machine_cfg.get('hostname', 'unknown')
                    try:
                        system_id = future.result(timeout=30)  # Add timeout to prevent hanging
                        if system_id:
                            system_ids.append(system_id)
                            log.info(f"✓ Completed: {hostname} ({system_id})")
                        else:
                            log.warning(f"✗ Failed: {hostname} (no system_id)")
                    except Exception as e:
                        log.error(f"✗ Failed: {hostname} - {e}")
            
            log.info("\n✓ All parallel tasks completed")
        else:
            # Sequential processing (original behavior)
            if not parallel:
                log.info(f"\n📋 Processing {len(machines_cfg)} machines SEQUENTIALLY")
            
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
                except KeyboardInterrupt:
                    log.warning("Interrupted by user")
                    raise
                except Exception as e:
                    log.error(f"Failed to process machine {machine_cfg.get('hostname')}: {e}", exc_info=True)
                    log.info("Continuing with next machine...")
                    continue
        
        log.info(f"\n✓ Completed processing {len(system_ids)}/{len(machines_cfg)} machine(s)")
        return system_ids
    
    def _execute_single_machine_safe(self, machine_cfg: Dict, actions: list, storage_cfg: Dict,
                                      bios_cfg: Dict, boot_order: list, release_cfg: Dict) -> Optional[str]:
        """
        Wrapper for _execute_single_machine that catches exceptions for parallel execution.
        """
        hostname = machine_cfg.get('hostname', 'unknown')
        log.info(f"\n🔄 Starting: {hostname}")
        
        try:
            system_id = self._execute_single_machine(machine_cfg, actions, storage_cfg, 
                                                      bios_cfg, boot_order, release_cfg)
            return system_id
        except Exception as e:
            log.error(f"Failed to process {hostname}: {e}")
            return None

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
            # If no create/find action, look up existing machine
            # Use create_or_find logic which searches by hostname then MAC
            log.info("=" * 60)
            log.info("STEP: Find Existing Machine")
            log.info("=" * 60)
            
            try:
                machine = self.machine.create_or_find(machine_cfg)
                
                if not machine:
                    log.error("Machine not found by hostname or MAC address")
                    hostname = machine_cfg.get('hostname', 'unknown')
                    pxe_mac = machine_cfg.get('pxe_mac', 'unknown')
                    log.error(f"Searched for: hostname='{hostname}', pxe_mac='{pxe_mac}'")
                    return None
                
                system_id = machine.get('system_id')
                log.info(f"Found machine system_id: {system_id}\n")
                
            except Exception as e:
                log.error(f"Failed to find machine: {e}")
                return None

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

        # Step 7: Configure network bond - after commission, before deploy
        if 'set_network_bond' in actions:
            log.info("=" * 60)
            log.info("STEP: Set Network Bond")
            log.info("=" * 60)
            bond_cfg = machine_cfg.get('bond', {})
            if not bond_cfg:
                log.warning("No bond configuration provided in machine config")
            else:
                self.network.configure_bond_by_vlan(system_id, bond_cfg)
            log.info("")

        # Step 8: Deploy machine
        if 'deploy' in actions:
            log.info("=" * 60)
            log.info("STEP: Deploy Machine")
            log.info("=" * 60)
            distro = machine_cfg.get('distro_series')
            
            # Support both inline cloud_init and external cloud_init_file
            user_data = machine_cfg.get('cloud_init')
            cloud_init_file = machine_cfg.get('cloud_init_file')
            
            if cloud_init_file and not user_data:
                try:
                    with open(cloud_init_file, 'r') as f:
                        user_data = f.read()
                    log.info(f"Loaded cloud-init from: {cloud_init_file}")
                except Exception as e:
                    log.error(f"Failed to load cloud-init file '{cloud_init_file}': {e}")
                    raise
            
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
        
        print("\n" + "=" * 105)
        print(f"{'SYSTEM_ID':<15} {'HOSTNAME':<25} {'STATUS':<15} {'SERIAL':<25} {'MAC ADDRESS':<20}")
        print("=" * 105)
        
        for m in machines:
            system_id = m['system_id']
            hostname = m.get('hostname', '-')
            status = m.get('status_name', '-')
            
            # Get serial number from hardware_info
            serial = '-'
            hw_info = m.get('hardware_info', {})
            if isinstance(hw_info, dict):
                serial = hw_info.get('system_serial', '-')
            
            # Get first MAC address from interfaces
            mac_addr = '-'
            interfaces = m.get('interface_set', m.get('interfaces', []))
            if interfaces and len(interfaces) > 0:
                mac_addr = interfaces[0].get('mac_address', '-')
            
            print(f"{system_id:<15} {hostname:<25} {status:<15} {serial:<25} {mac_addr:<20}")
        
        print("=" * 105)
        print(f"Total: {len(machines)} machines\n")
    
    def show_network_info(self, cfg: Dict):
        """Show detailed network information for machines"""
        machines_cfg = cfg.get('machines', [])
        
        if not machines_cfg:
            log.error("No machines defined in configuration")
            return
        
        print("\n" + "=" * 130)
        print("NETWORK CONFIGURATION DETAILS")
        print("=" * 130)
        
        for machine_cfg in machines_cfg:
            hostname = machine_cfg.get('hostname', 'unknown')
            serial = machine_cfg.get('serial_number')
            
            # Find machine
            try:
                if serial:
                    machine = self.machine.find_by_serial(serial)
                elif hostname:
                    machine = self.machine.find_by_hostname(hostname)
                else:
                    continue
                
                if not machine:
                    print(f"\n❌ Machine not found: {hostname}")
                    continue
                
                system_id = machine['system_id']
                status = machine.get('status_name', 'unknown')
                
                print(f"\n{'='*130}")
                print(f"Machine: {hostname} ({system_id}) - Status: {status}")
                print(f"{'='*130}")
                
                # Get detailed machine info with interfaces
                machine_detail = self.client.get_machine(system_id)
                interfaces = machine_detail.get('interface_set', [])
                
                if not interfaces:
                    print("  No network interfaces found")
                    continue
                
                # Display interface details
                print(f"\n{'INTERFACE':<15} {'TYPE':<10} {'MAC ADDRESS':<20} {'VLAN':<10} {'IP ADDRESS':<20} {'SUBNET':<20} {'MODE':<10}")
                print("-" * 130)
                
                for iface in interfaces:
                    iface_name = iface.get('name', '-')
                    iface_type = iface.get('type', '-')
                    mac = iface.get('mac_address', '-')
                    enabled = iface.get('enabled', False)
                    
                    # Get VLAN info
                    vlan = iface.get('vlan', {})
                    vlan_id = vlan.get('vid', '-') if vlan else '-'
                    
                    # Get IP addresses
                    links = iface.get('links', [])
                    if links:
                        for link in links:
                            ip_addr = link.get('ip_address', '-')
                            subnet = link.get('subnet', {})
                            subnet_cidr = subnet.get('cidr', '-') if subnet else '-'
                            mode = link.get('mode', '-')
                            
                            status_icon = '✓' if enabled else '✗'
                            print(f"{status_icon} {iface_name:<13} {iface_type:<10} {mac:<20} {str(vlan_id):<10} {ip_addr:<20} {subnet_cidr:<20} {mode:<10}")
                    else:
                        status_icon = '✓' if enabled else '✗'
                        print(f"{status_icon} {iface_name:<13} {iface_type:<10} {mac:<20} {str(vlan_id):<10} {'-':<20} {'-':<20} {'-':<10}")
                
            except Exception as e:
                print(f"\n❌ Error getting network info for {hostname}: {e}")
                continue
        
        print("\n" + "=" * 130 + "\n")
