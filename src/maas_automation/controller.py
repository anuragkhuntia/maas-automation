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
from .reservedip import ReservedIPManager

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
        self.reservedip = ReservedIPManager(self.client, max_retries=max_retries)
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

        # Step 2: Set hostname
        if 'set_hostname' in actions:
            log.info("=" * 60)
            log.info("STEP: Set Hostname")
            log.info("=" * 60)
            hostname = machine_cfg.get('hostname')
            if not hostname:
                log.warning("No hostname provided in machine config")
            else:
                machine_obj = self.machine.get_by_id(system_id)
                current_hostname = machine_obj.get('hostname', 'unknown')
                if current_hostname != hostname:
                    log.info(f"Updating hostname from '{current_hostname}' to '{hostname}'")
                    self.machine.update_hostname(system_id, hostname)
                else:
                    log.info(f"Hostname already set to: {hostname}")
            log.info("")

        # Step 3: Update power configuration
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

        # Step 8: Configure network bonds - after commission, before deploy
        if 'set_network_bond' in actions:
            log.info("=" * 60)
            log.info("STEP: Set Network Bond(s)")
            log.info("=" * 60)
            bonds_cfg = machine_cfg.get('bonds', [])
            log.debug(f"Bonds config from machine_cfg: {bonds_cfg}")
            if not bonds_cfg or len(bonds_cfg) == 0:
                log.warning("No bonds configuration provided in machine config")
            else:
                log.info(f"Found {len(bonds_cfg)} bond(s) to configure")
                bond_errors = []
                for bond_cfg in bonds_cfg:
                    try:
                        self.network.configure_bond_by_vlan(system_id, bond_cfg)
                    except Exception as e:
                        error_msg = f"Failed to configure bond {bond_cfg.get('name')}: {e}"
                        log.error(error_msg)
                        bond_errors.append(error_msg)
                
                # If any bonds failed, raise an error
                if bond_errors:
                    raise Exception(f"Bond configuration failed for {len(bond_errors)} bond(s): " + "; ".join(bond_errors))
            log.info("")

        # Step 9: Deploy machine
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

        # Step 10: Release machine
        if 'release' in actions:
            log.info("=" * 60)
            log.info("STEP: Release Machine")
            log.info("=" * 60)
            erase = release_cfg.get('wipe_disks', True)
            wait = release_cfg.get('wait_release', True)
            timeout = release_cfg.get('release_timeout', 1800)
            self.machine.release(system_id, erase=erase, wait=wait, timeout=timeout)
            log.info("")

        # Step 11: Delete machine
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
                print(f"\n{'ID':<8} {'INTERFACE':<15} {'TYPE':<10} {'MAC ADDRESS':<20} {'VLAN':<10} {'IP ADDRESS':<20} {'SUBNET':<20} {'MODE':<10}")
                print("-" * 138)
                
                for iface in interfaces:
                    iface_id = iface.get('id', '-')
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
                            print(f"{str(iface_id):<8} {status_icon} {iface_name:<13} {iface_type:<10} {mac:<20} {str(vlan_id):<10} {ip_addr:<20} {subnet_cidr:<20} {mode:<10}")
                    else:
                        status_icon = '✓' if enabled else '✗'
                        print(f"{str(iface_id):<8} {status_icon} {iface_name:<13} {iface_type:<10} {mac:<20} {str(vlan_id):<10} {'-':<20} {'-':<20} {'-':<10}")
                
            except Exception as e:
                print(f"\n❌ Error getting network info for {hostname}: {e}")
                continue
        
        print("\n" + "=" * 130 + "\n")
    
    def list_dhcp_snippets(self):
        """List all DHCP snippets with count, name, and last updated"""
        snippets = self.client.list_dhcp_snippets()
        
        print("\n" + "=" * 100)
        print(f"{'ID':<8} {'NAME':<40} {'ENABLED':<10} {'LAST UPDATED':<30}")
        print("=" * 100)
        
        for snippet in snippets:
            snippet_id = snippet.get('id', '-')
            name = snippet.get('name', '-')
            enabled = '✓ Yes' if snippet.get('enabled', False) else '✗ No'
            updated = snippet.get('updated', '-')
            
            print(f"{str(snippet_id):<8} {name:<40} {enabled:<10} {updated:<30}")
        
        print("=" * 100)
        print(f"Total: {len(snippets)} DHCP snippets\n")
    
    def list_subnets(self):
        """List all subnets in MAAS"""
        try:
            subnets = self.client.list_subnets()
            
            if not subnets:
                print("\nNo subnets found in MAAS\n")
                return
            
            print("\n" + "=" * 130)
            print(f"{'ID':<6} {'NAME':<25} {'CIDR':<20} {'VLAN':<15} {'GATEWAY':<20} {'DNS':<20} {'MANAGED':<10}")
            print("=" * 130)
            
            for subnet in subnets:
                subnet_id = str(subnet.get('id', '-'))
                name = subnet.get('name') or '-'
                cidr = subnet.get('cidr') or '-'
                vlan = subnet.get('vlan', {})
                vlan_name = vlan.get('name', '-') if isinstance(vlan, dict) else (str(vlan) if vlan else '-')
                gateway_ip = subnet.get('gateway_ip') or '-'
                dns_servers = ', '.join(subnet.get('dns_servers', [])) if subnet.get('dns_servers') else '-'
                managed = 'Yes' if subnet.get('managed', False) else 'No'
                
                print(f"{subnet_id:<6} {name:<25} {cidr:<20} {vlan_name:<15} {gateway_ip:<20} {dns_servers:<20} {managed:<10}")
            
            print("=" * 130)
            print(f"Total: {len(subnets)} subnets\n")
        except Exception as e:
            log.error(f"Failed to list subnets: {e}")
            print(f"\n❌ Failed to list subnets: {e}\n")
    
    def list_reserved_ips(self):
        """List all reserved IP addresses using the new reservedips endpoint"""
        try:
            reserved_ips = self.reservedip.list()
            
            if not reserved_ips:
                print("\nNo reserved IP addresses found\n")
                return
            
            print("\n" + "=" * 120)
            print(f"{'ID':<8} {'IP ADDRESS':<20} {'MAC ADDRESS':<20} {'SUBNET':<25} {'COMMENT':<40}")
            print("=" * 120)
            
            for ip_data in reserved_ips:
                ip_id = str(ip_data.get('id', '-'))
                ip_addr = ip_data.get('ip', '-')
                mac = ip_data.get('mac_address', '-')
                subnet = ip_data.get('subnet', {})
                subnet_cidr = subnet.get('cidr', '-') if isinstance(subnet, dict) else str(subnet)
                comment = ip_data.get('comment', '-')
                
                print(f"{ip_id:<8} {ip_addr:<20} {mac:<20} {subnet_cidr:<25} {comment:<40}")
            
            print("=" * 120)
            print(f"Total: {len(reserved_ips)} reserved IP addresses\n")
        except Exception as e:
            log.error(f"Failed to list reserved IPs: {e}")
            print(f"\n❌ Failed to list reserved IPs: {e}\n")
    
    def list_static_leases(self):
        """List all static DHCP leases by iterating over all subnets"""
        # Get all subnets first
        subnets = self.client.list_subnets()
        
        if not subnets:
            print("\nNo subnets found in MAAS\n")
            return
        
        print(f"\nFound {len(subnets)} subnet(s), collecting reserved IPs...")
        
        all_leases = []
        
        # Iterate over each subnet and get reserved IPs
        for subnet in subnets:
            subnet_id = subnet.get('id')
            subnet_cidr = subnet.get('cidr', 'unknown')
            
            try:
                reserved = self.client.get_subnet_reserved_ips(subnet_id)
                if reserved:
                    for ip in reserved:
                        ip['subnet_cidr'] = subnet_cidr  # Add subnet info
                        all_leases.append(ip)
                    log.debug(f"Subnet {subnet_cidr}: {len(reserved)} reserved IPs")
            except Exception as e:
                log.debug(f"Error getting reserved IPs for subnet {subnet_cidr}: {e}")
                continue
        
        if not all_leases:
            print("\nNo static DHCP leases found\n")
            return
        
        print("\n" + "=" * 140)
        print(f"{'IP ADDRESS':<20} {'MAC ADDRESS':<20} {'HOSTNAME':<25} {'SUBNET':<25} {'OWNER':<20} {'COMMENT':<25}")
        print("=" * 140)
        
        for lease in all_leases:
            ip_addr = lease.get('ip', '-')
            mac = lease.get('mac', '-')
            hostname = lease.get('hostname', '-')
            subnet_cidr = lease.get('subnet_cidr', '-')
            owner = lease.get('user', '-')
            comment = lease.get('comment', '-')
            
            print(f"{ip_addr:<20} {mac:<20} {hostname:<25} {subnet_cidr:<25} {owner:<20} {comment:<25}")
        
        print("=" * 140)
        print(f"Total: {len(all_leases)} static DHCP leases across {len(subnets)} subnet(s)\n")
    
    def get_reserved_ip_details(self, reserved_ip_id: int):
        """Get and display details of a specific reserved IP"""
        try:
            reserved_ip = self.reservedip.get(reserved_ip_id)
            
            if not reserved_ip:
                print(f"\n❌ Reserved IP with ID {reserved_ip_id} not found\n")
                return
            
            print("\n" + "=" * 80)
            print(f"RESERVED IP DETAILS (ID: {reserved_ip_id})")
            print("=" * 80)
            print(f"IP Address:    {reserved_ip.get('ip', '-')}")
            print(f"MAC Address:   {reserved_ip.get('mac_address', '-')}")
            
            subnet = reserved_ip.get('subnet', {})
            if isinstance(subnet, dict):
                print(f"Subnet:        {subnet.get('cidr', '-')} (ID: {subnet.get('id', '-')})")
            else:
                print(f"Subnet:        {subnet}")
            
            print(f"Comment:       {reserved_ip.get('comment', '-')}")
            print("=" * 80 + "\n")
        except Exception as e:
            log.error(f"Failed to get reserved IP {reserved_ip_id}: {e}")
            print(f"\n❌ Failed to get reserved IP {reserved_ip_id}: {e}\n")
    
    def create_reserved_ip_from_config(self, config: Dict):
        """Create reserved IP(s) from configuration - supports both single object and array"""
        # Support both single object and array
        reserved_ips_config = config
        if not isinstance(config, list):
            reserved_ips_config = [config]
        
        created_ids = []
        
        for idx, ip_config in enumerate(reserved_ips_config, 1):
            try:
                log.info(f"Creating reserved IP {idx}/{len(reserved_ips_config)}")
                reserved_ip = self.reservedip.create(ip_config)
                
                print("\n" + "=" * 80)
                print(f"✓ RESERVED IP CREATED ({idx}/{len(reserved_ips_config)})")
                print("=" * 80)
                print(f"ID:            {reserved_ip.get('id')}")
                print(f"IP Address:    {reserved_ip.get('ip')}")
                print(f"MAC Address:   {reserved_ip.get('mac_address', '-')}")
                
                subnet = reserved_ip.get('subnet', {})
                if isinstance(subnet, dict):
                    print(f"Subnet:        {subnet.get('cidr', '-')}")
                else:
                    print(f"Subnet:        {subnet}")
                
                print(f"Comment:       {reserved_ip.get('comment', '-')}")
                print("=" * 80 + "\n")
                
                created_ids.append(reserved_ip.get('id'))
            except Exception as e:
                log.error(f"Failed to create reserved IP {idx}: {e}")
                print(f"\n❌ Failed to create reserved IP {idx}: {e}\n")
                # Continue with next IP instead of raising
                continue
        
        if created_ids:
            print(f"\n✓ Successfully created {len(created_ids)}/{len(reserved_ips_config)} reserved IP(s)\n")
        
        return created_ids
    
    def update_reserved_ip_from_config(self, reserved_ip_id: int, config: Dict):
        """Update a reserved IP from configuration"""
        try:
            reserved_ip = self.reservedip.update(reserved_ip_id, config)
            
            print("\n" + "=" * 80)
            print(f"✓ RESERVED IP UPDATED (ID: {reserved_ip_id})")
            print("=" * 80)
            print(f"IP Address:    {reserved_ip.get('ip')}")
            print(f"MAC Address:   {reserved_ip.get('mac_address', '-')}")
            
            subnet = reserved_ip.get('subnet', {})
            if isinstance(subnet, dict):
                print(f"Subnet:        {subnet.get('cidr', '-')}")
            else:
                print(f"Subnet:        {subnet}")
            
            print(f"Comment:       {reserved_ip.get('comment', '-')}")
            print("=" * 80 + "\n")
        except Exception as e:
            log.error(f"Failed to update reserved IP {reserved_ip_id}: {e}")
            print(f"\n❌ Failed to update reserved IP {reserved_ip_id}: {e}\n")
            raise
    
    def delete_reserved_ip_by_id(self, reserved_ip_id: int):
        """Delete a reserved IP by ID"""
        try:
            self.reservedip.delete(reserved_ip_id)
            
            print("\n" + "=" * 80)
            print(f"✓ RESERVED IP DELETED (ID: {reserved_ip_id})")
            print("=" * 80 + "\n")
        except Exception as e:
            log.error(f"Failed to delete reserved IP {reserved_ip_id}: {e}")
            print(f"\n❌ Failed to delete reserved IP {reserved_ip_id}: {e}\n")
            raise
