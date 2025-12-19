"""Network configuration operations"""
import logging
from typing import Dict, List, Optional
from .client import MaasClient
from .utils import retry

log = logging.getLogger("maas_automation.network")


class NetworkManager:
    """Manages network interface and bond configuration"""

    def __init__(self, client: MaasClient, max_retries: int = 5):
        self.client = client
        self.max_retries = max_retries

    def get_interfaces(self, system_id: str) -> List[Dict]:
        """Get all network interfaces for a machine"""
        try:
            interfaces = retry(
                lambda: self.client.request("GET", f"machines/{system_id}/", op="interfaces"),
                retries=self.max_retries,
                delay=2.0
            )
            log.debug(f"Found {len(interfaces)} interfaces for {system_id}")
            return interfaces
        except Exception as e:
            log.error(f"Failed to get interfaces for {system_id}: {e}")
            raise

    def find_interface_by_name(self, system_id: str, interface_name: str) -> Optional[Dict]:
        """Find a specific interface by name"""
        interfaces = self.get_interfaces(system_id)
        for iface in interfaces:
            if iface.get("name") == interface_name:
                return iface
        return None

    def create_bond(self, system_id: str, bond_config: Dict) -> Dict:
        """
        Create a network bond from multiple interfaces.
        
        Args:
            system_id: Machine system ID
            bond_config: Bond configuration with keys:
                - name: Bond name (e.g., "bond0")
                - interfaces: List of interface names to bond (e.g., ["eth0", "eth1"])
                - mode: Bond mode (e.g., "802.3ad", "active-backup", "balance-rr")
                - mtu: MTU size (optional, default: 1500)
                - vlan: VLAN ID (optional)
                - subnet: Subnet CIDR for IP assignment (optional)
                - ip_mode: "static", "dhcp", or "auto" (optional, default: "auto")
                - ip_address: Static IP if ip_mode is "static" (optional)
        
        Returns:
            Created bond interface details
        """
        bond_name = bond_config.get("name")
        interface_names = bond_config.get("interfaces", [])
        bond_mode = bond_config.get("mode", "802.3ad")
        mtu = bond_config.get("mtu", 1500)
        
        if not bond_name:
            raise ValueError("Bond config must have 'name'")
        if not interface_names or len(interface_names) < 2:
            raise ValueError("Bond requires at least 2 interfaces")
        
        log.info(f"Creating bond '{bond_name}' with interfaces: {', '.join(interface_names)}")
        
        # Get interface IDs
        interfaces = self.get_interfaces(system_id)
        interface_ids = []
        
        for iface_name in interface_names:
            found = False
            for iface in interfaces:
                if iface.get("name") == iface_name:
                    interface_ids.append(iface["id"])
                    found = True
                    break
            if not found:
                raise ValueError(f"Interface '{iface_name}' not found on machine {system_id}")
        
        log.debug(f"Interface IDs for bond: {interface_ids}")
        
        # Create bond
        payload = {
            "name": bond_name,
            "parents": interface_ids,
            "bond_mode": bond_mode,
            "mtu": mtu
        }
        
        # Add bond parameters based on mode
        if bond_mode == "802.3ad":
            payload["bond_lacp_rate"] = bond_config.get("lacp_rate", "fast")
            payload["bond_xmit_hash_policy"] = bond_config.get("xmit_hash_policy", "layer3+4")
        
        log.debug(f"Bond payload: {payload}")
        
        try:
            bond = retry(
                lambda: self.client.request(
                    "POST",
                    f"machines/{system_id}/",
                    op="create_bond",
                    data=payload
                ),
                retries=self.max_retries,
                delay=2.0
            )
            log.info(f"✓ Created bond: {bond_name} (ID: {bond['id']})")
            return bond
        except Exception as e:
            log.error(f"Failed to create bond '{bond_name}': {e}")
            raise

    def configure_interface(self, system_id: str, interface_config: Dict) -> Dict:
        """
        Configure a network interface (IP, VLAN, etc.).
        
        Args:
            system_id: Machine system ID
            interface_config: Interface configuration with keys:
                - name: Interface name (e.g., "eth0", "bond0")
                - subnet: Subnet CIDR for IP assignment (e.g., "10.0.0.0/24")
                - ip_mode: "static", "dhcp", or "auto" (default: "auto")
                - ip_address: Static IP if ip_mode is "static"
                - vlan: VLAN ID (optional)
                - mtu: MTU size (optional)
        
        Returns:
            Updated interface details
        """
        interface_name = interface_config.get("name")
        subnet_cidr = interface_config.get("subnet")
        ip_mode = interface_config.get("ip_mode", "auto")
        ip_address = interface_config.get("ip_address")
        
        if not interface_name:
            raise ValueError("Interface config must have 'name'")
        
        log.info(f"Configuring interface '{interface_name}' on {system_id}")
        
        # Find the interface
        iface = self.find_interface_by_name(system_id, interface_name)
        if not iface:
            raise ValueError(f"Interface '{interface_name}' not found on machine {system_id}")
        
        interface_id = iface["id"]
        
        # Update interface properties if specified
        if "mtu" in interface_config:
            try:
                self.client.request(
                    "PUT",
                    f"machines/{system_id}/interfaces/{interface_id}/",
                    data={"mtu": interface_config["mtu"]}
                )
                log.debug(f"Updated MTU for {interface_name}")
            except Exception as e:
                log.warning(f"Failed to update MTU: {e}")
        
        # Link to subnet if specified
        if subnet_cidr:
            try:
                # Find subnet
                subnets = self.client.request("GET", "subnets/")
                target_subnet = None
                for subnet in subnets:
                    if subnet.get("cidr") == subnet_cidr:
                        target_subnet = subnet
                        break
                
                if not target_subnet:
                    log.warning(f"Subnet {subnet_cidr} not found in MAAS")
                else:
                    # Link interface to subnet
                    link_payload = {
                        "mode": ip_mode.upper(),
                        "subnet": target_subnet["id"]
                    }
                    
                    if ip_mode == "static" and ip_address:
                        link_payload["ip_address"] = ip_address
                    
                    result = retry(
                        lambda: self.client.request(
                            "POST",
                            f"machines/{system_id}/interfaces/{interface_id}/",
                            op="link_subnet",
                            data=link_payload
                        ),
                        retries=self.max_retries,
                        delay=2.0
                    )
                    log.info(f"✓ Linked {interface_name} to subnet {subnet_cidr} (mode: {ip_mode})")
                    
                    if ip_mode == "static" and ip_address:
                        log.info(f"  Static IP: {ip_address}")
                    
            except Exception as e:
                log.error(f"Failed to link interface to subnet: {e}")
                raise
        
        # Get updated interface details
        updated_iface = self.find_interface_by_name(system_id, interface_name)
        return updated_iface

    def configure_bond_by_vlan(self, system_id: str, bond_config: Dict) -> Dict:
        """
        Configure a network bond by finding interfaces with a specific VLAN ID.
        
        This method:
        1. Takes a VLAN ID from the bond configuration
        2. Finds all interfaces where this VLAN is visible
        3. Links both interfaces to the specified subnet (if provided)
        4. Creates a bond between those interfaces
        
        Args:
            system_id: Machine system ID
            bond_config: Bond configuration with keys:
                - name: Bond name (e.g., "bond0")
                - vlan_id: VLAN ID to search for in interfaces
                - mode: Bond mode (e.g., "802.3ad", "active-backup", "balance-rr")
                - mtu: MTU size (optional, default: 1500)
                - subnet: Subnet name to link both interfaces to (optional)
                - ip_mode: "static", "dhcp", or "auto" (optional)
                - ip_address: Static IP if ip_mode is "static" (optional)
        
        Example config:
        {
            "name": "bond0",
            "vlan_id": 100,
            "mode": "802.3ad",
            "mtu": 9000,
            "subnet": "my-subnet-name",
            "ip_mode": "static",
            "ip_address": "10.0.0.100"
        }
        
        Returns:
            Created bond interface details
        """
        bond_name = bond_config.get("name")
        vlan_id = bond_config.get("vlan_id")
        
        if not bond_name:
            raise ValueError("Bond config must have 'name'")
        if vlan_id is None:
            raise ValueError("Bond config must have 'vlan_id'")
        
        log.info(f"Looking for interfaces with VLAN ID {vlan_id} on {system_id}")
        
        # Get all interfaces for the machine
        interfaces = self.get_interfaces(system_id)
        log.info(f"Total interfaces found: {len(interfaces)}")
        
        # Debug: Show all interfaces and their VLANs
        for iface in interfaces:
            iface_name = iface.get("name")
            iface_type = iface.get("type")
            iface_vlan = iface.get("vlan", {})
            vlan_vid = iface_vlan.get("vid", "None")
            log.debug(f"  Interface: {iface_name} (type: {iface_type}, VLAN: {vlan_vid})")
        
        # Find interfaces that have access to the specified VLAN
        matching_interfaces = []
        for iface in interfaces:
            iface_name = iface.get("name")
            iface_type = iface.get("type")
            
            # Skip bond and bridge interfaces - we only want physical or VLAN interfaces
            if iface_type in ["bond", "bridge"]:
                log.debug(f"Skipping {iface_name} (type: {iface_type})")
                continue
            
            # Check if interface has links to the VLAN
            links = iface.get("links", [])
            for link in links:
                subnet = link.get("subnet", {})
                vlan = subnet.get("vlan", {})
                if vlan.get("vid") == vlan_id:
                    if iface_name not in matching_interfaces:
                        matching_interfaces.append(iface_name)
                        log.info(f"✓ Found interface {iface_name} with VLAN {vlan_id} (via link)")
                    break
            
            # Also check the interface's VLAN directly
            if iface.get("vlan", {}).get("vid") == vlan_id:
                if iface_name not in matching_interfaces:
                    matching_interfaces.append(iface_name)
                    log.info(f"✓ Found interface {iface_name} with VLAN {vlan_id} (direct)")
        
        if len(matching_interfaces) < 2:
            log.error(f"Not enough interfaces with VLAN {vlan_id}")
            log.error(f"Found {len(matching_interfaces)} interface(s): {matching_interfaces}")
            log.error("Available interfaces:")
            for iface in interfaces:
                vlan_info = iface.get("vlan", {})
                log.error(f"  - {iface.get('name')} (type: {iface.get('type')}, VLAN: {vlan_info.get('vid', 'None')})")
            raise ValueError(
                f"Found only {len(matching_interfaces)} interface(s) with VLAN {vlan_id}. "
                f"Need at least 2 interfaces to create a bond. Found: {matching_interfaces}"
            )
        
        log.info(f"Found {len(matching_interfaces)} interfaces with VLAN {vlan_id}: {', '.join(matching_interfaces)}")
        
        # Link both interfaces to subnet if specified (before creating bond)
        subnet_name = bond_config.get("subnet")
        if subnet_name:
            log.info(f"Looking up subnet by name: '{subnet_name}'")
            
            # Find subnet by name
            subnets = self.client.request("GET", "subnets/")
            target_subnet = None
            for subnet in subnets:
                if subnet.get("name") == subnet_name:
                    target_subnet = subnet
                    log.info(f"Found subnet '{subnet_name}' (CIDR: {subnet.get('cidr')}, ID: {subnet['id']})")
                    break
            
            if not target_subnet:
                raise ValueError(f"Subnet '{subnet_name}' not found in MAAS")
            
            # Get IP mode
            ip_mode = bond_config.get("ip_mode", "auto")
            ip_address = bond_config.get("ip_address")
            
            # Link each interface to the subnet (only if not already assigned through fabric)
            for iface_name in matching_interfaces:
                iface = self.find_interface_by_name(system_id, iface_name)
                if not iface:
                    log.warning(f"Interface {iface_name} not found, skipping subnet link")
                    continue
                
                interface_id = iface["id"]
                
                # Check if interface already has a subnet link through the fabric
                existing_links = iface.get("links", [])
                already_linked = False
                for link in existing_links:
                    link_subnet = link.get("subnet")
                    if link_subnet and link_subnet.get("id") == target_subnet["id"]:
                        already_linked = True
                        log.info(f"Interface {iface_name} already linked to subnet '{subnet_name}', skipping")
                        break
                    elif link_subnet:
                        # Check if any subnet is already assigned on the same fabric/VLAN
                        link_vlan = link_subnet.get("vlan", {})
                        target_vlan = target_subnet.get("vlan", {})
                        if link_vlan.get("id") == target_vlan.get("id"):
                            log.info(f"Interface {iface_name} already has subnet {link_subnet.get('name')} on the same VLAN, skipping")
                            already_linked = True
                            break
                
                if already_linked:
                    continue
                
                try:
                    link_payload = {
                        "mode": ip_mode.upper(),
                        "subnet": target_subnet["id"]
                    }
                    
                    # Only set static IP on one interface if specified
                    if ip_mode == "static" and ip_address and iface_name == matching_interfaces[0]:
                        link_payload["ip_address"] = ip_address
                    
                    retry(
                        lambda: self.client.request(
                            "POST",
                            f"machines/{system_id}/interfaces/{interface_id}/",
                            op="link_subnet",
                            data=link_payload
                        ),
                        retries=self.max_retries,
                        delay=2.0
                    )
                    log.info(f"✓ Linked {iface_name} to subnet '{subnet_name}' (mode: {ip_mode})")
                    
                except Exception as e:
                    log.error(f"Failed to link {iface_name} to subnet: {e}")
                    raise
        
        # Create the bond with the found interfaces
        bond_creation_config = {
            "name": bond_name,
            "interfaces": matching_interfaces,
            "mode": bond_config.get("mode", "802.3ad"),
            "mtu": bond_config.get("mtu", 1500)
        }
        
        # Add bond parameters
        if "lacp_rate" in bond_config:
            bond_creation_config["lacp_rate"] = bond_config["lacp_rate"]
        if "xmit_hash_policy" in bond_config:
            bond_creation_config["xmit_hash_policy"] = bond_config["xmit_hash_policy"]
        
        bond = self.create_bond(system_id, bond_creation_config)
        
        log.info(f"✓ Bond '{bond_name}' configured with VLAN {vlan_id} interfaces and subnet '{subnet_name}'")
        return bond

    def apply_network_config(self, system_id: str, network_config: Dict) -> None:
        """
        Apply complete network configuration to a machine.
        
        This should be called after commissioning when machine is in READY state.
        
        Args:
            system_id: Machine system ID
            network_config: Network configuration with keys:
                - bonds: List of bond configurations (optional)
                - interfaces: List of interface configurations (optional)
        
        Example config:
        {
            "bonds": [
                {
                    "name": "bond0",
                    "interfaces": ["eth0", "eth1"],
                    "mode": "802.3ad",
                    "mtu": 9000
                }
            ],
            "interfaces": [
                {
                    "name": "bond0",
                    "subnet": "10.0.0.0/24",
                    "ip_mode": "static",
                    "ip_address": "10.0.0.100"
                },
                {
                    "name": "eth2",
                    "subnet": "192.168.1.0/24",
                    "ip_mode": "dhcp"
                }
            ]
        }
        """
        if not network_config:
            log.debug("No network configuration provided")
            return
        
        log.info(f"Applying network configuration to {system_id}")
        
        # Create bonds first
        bonds = network_config.get("bonds", [])
        for bond_cfg in bonds:
            try:
                self.create_bond(system_id, bond_cfg)
            except Exception as e:
                log.error(f"Failed to create bond {bond_cfg.get('name')}: {e}")
                # Continue with other bonds
        
        # Configure interfaces
        interfaces = network_config.get("interfaces", [])
        for iface_cfg in interfaces:
            try:
                self.configure_interface(system_id, iface_cfg)
            except Exception as e:
                log.error(f"Failed to configure interface {iface_cfg.get('name')}: {e}")
                # Continue with other interfaces
        
        log.info(f"✓ Network configuration applied to {system_id}")
