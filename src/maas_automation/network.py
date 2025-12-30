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
            # Get machine details which includes interfaces
            machine = retry(
                lambda: self.client.request("GET", f"nodes/{system_id}"),
                retries=self.max_retries,
                delay=2.0
            )
            if not machine:
                raise ValueError(f"Failed to get machine details for {system_id}")
            
            interfaces = machine.get("interface_set", [])
            if interfaces is None:
                interfaces = []
            
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

    def find_subnet_by_name(self, subnet_name: str) -> Optional[Dict]:
        """Find a subnet by its name"""
        try:
            subnets = self.client.request("GET", "subnets/")
            for subnet in subnets:
                if subnet.get("name") == subnet_name:
                    log.debug(f"Found subnet '{subnet_name}' with ID {subnet['id']} (CIDR: {subnet.get('cidr')})")
                    return subnet
            log.warning(f"Subnet '{subnet_name}' not found in MAAS")
            return None
        except Exception as e:
            log.error(f"Failed to search for subnet '{subnet_name}': {e}")
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
                - ip_mode: "static", "dynamic", or "automatic" (optional, default: "automatic")
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
        
        # Create bond - parents must be sent as separate parameters
        payload = [
            ("name", bond_name),
            ("bond_mode", bond_mode),
            ("mtu", str(mtu))
        ]
        
        # Add each parent interface ID separately
        for iface_id in interface_ids:
            payload.append(("parents", str(iface_id)))
        
        # Add bond parameters based on mode
        if bond_mode == "802.3ad":
            payload.append(("bond_lacp_rate", bond_config.get("lacp_rate", "fast")))
            payload.append(("bond_xmit_hash_policy", bond_config.get("xmit_hash_policy", "layer3+4")))
        
        log.debug(f"Bond payload: {payload}")
        
        try:
            bond = self.client.request(
                "POST",
                f"nodes/{system_id}/interfaces",
                op="create_bond",
                data=payload
            )
            log.info(f"✓ Created bond: {bond_name} (ID: {bond['id']})")
            return bond
        except Exception as e:
            error_msg = str(e)
            # Check if bond already exists
            if "already" in error_msg.lower() or "exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                log.warning(f"Bond '{bond_name}' already exists on machine {system_id}")
                raise ValueError(f"Bond '{bond_name}' already exists")
            else:
                log.error(f"Failed to create bond '{bond_name}': {e}")
                raise

    def create_vlan_interface(self, system_id: str, parent_id: int, vlan_id: int, parent_name: str) -> Dict:
        """
        Create a VLAN interface on top of a parent interface (bond, physical interface, etc.).
        
        Args:
            system_id: Machine system ID
            parent_id: ID of the parent interface (e.g., bond ID)
            vlan_id: VLAN ID to tag with
            parent_name: Name of the parent interface (for logging)
        
        Returns:
            Created VLAN interface details
        """
        log.info(f"Creating VLAN interface with tag {vlan_id} on parent {parent_name} (ID: {parent_id})")
        
        try:
            # First, get the VLAN object from MAAS for this VLAN ID
            vlans = self.client.request("GET", "vlans/")
            target_vlan = None
            for vlan in vlans:
                if vlan.get("vid") == vlan_id:
                    target_vlan = vlan
                    log.debug(f"Found VLAN object: ID={vlan['id']}, VID={vlan_id}, Fabric={vlan.get('fabric')}")
                    break
            
            if not target_vlan:
                log.warning(f"VLAN with VID {vlan_id} not found in MAAS. Attempting to use default fabric...")
                # Get default fabric and try to find/create VLAN there
                fabrics = self.client.request("GET", "fabrics/")
                if fabrics and len(fabrics) > 0:
                    default_fabric = fabrics[0]
                    log.info(f"Using fabric: {default_fabric.get('name')} (ID: {default_fabric['id']})")
                    
                    # Check if VLAN exists on this fabric
                    fabric_vlans = self.client.request("GET", f"fabrics/{default_fabric['id']}/vlans/")
                    for vlan in fabric_vlans:
                        if vlan.get("vid") == vlan_id:
                            target_vlan = vlan
                            break
            
            if not target_vlan:
                raise ValueError(f"VLAN with VID {vlan_id} not found in MAAS. Please create it first.")
            
            # Create VLAN interface using the parent and VLAN
            payload = {
                "vlan": target_vlan["id"],
                "parents": [parent_id]
            }
            
            log.debug(f"VLAN interface payload: {payload}")
            
            vlan_iface = retry(
                lambda: self.client.request(
                    "POST",
                    f"nodes/{system_id}/interfaces",
                    op="create_vlan",
                    data=payload
                ),
                retries=self.max_retries,
                delay=2.0
            )
            
            log.info(f"✓ Created VLAN interface: {vlan_iface.get('name')} (ID: {vlan_iface['id']})")
            return vlan_iface
            
        except Exception as e:
            log.error(f"Failed to create VLAN interface: {e}")
            raise

    def configure_interface(self, system_id: str, interface_config: Dict) -> Dict:
        """
        Configure a network interface (IP, VLAN, etc.).
        
        Args:
            system_id: Machine system ID
            interface_config: Interface configuration with keys:
                - name: Interface name (e.g., "eth0", "bond0")
                - subnet: Subnet CIDR for IP assignment (e.g., "10.0.0.0/24")
                - ip_mode: "static", "dynamic", or "automatic" (default: "automatic")
                - ip_address: Static IP if ip_mode is "static"
                - vlan: VLAN ID (optional)
                - mtu: MTU size (optional)
        
        Returns:
            Updated interface details
        """
        interface_name = interface_config.get("name")
        subnet_cidr = interface_config.get("subnet")
        ip_mode = interface_config.get("ip_mode", "automatic")
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
                            f"nodes/{system_id}/interfaces/{interface_id}",
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
        Configure a network bond by finding interfaces with a specific VLAN ID or multiple VLANs.
        
        This method:
        1. Takes VLAN ID(s) from the bond configuration (single int or list)
        2. Finds all interfaces where the VLAN(s) is/are visible
        3. Creates a bond between those interfaces
        4. If multiple VLANs specified, creates VLAN interfaces for each VLAN
        5. Optionally links to subnet if provided
        
        Args:
            system_id: Machine system ID
            bond_config: Bond configuration with keys:
                - name: Bond name (e.g., "bond0")
                - vlan_id: VLAN ID (int) or list of VLAN IDs [int, int, ...]
                - mode: Bond mode (e.g., "802.3ad", "active-backup", "balance-rr")
                - mtu: MTU size (optional, default: 1500)
                - subnet: Subnet name to link both interfaces to (optional)
                - ip_mode: "static", "dynamic", or "automatic" (optional, default: "automatic")
                - ip_address: Static IP if ip_mode is "static" (optional)
        
        Example config (single VLAN):
        {
            "name": "bond0",
            "vlan_id": 100,
            "mode": "802.3ad"
        }
        
        Example config (multiple VLANs):
        {
            "name": "prov_bond",
            "vlan_id": [1234, 1235],
            "mode": "active-backup"
        }
        
        Returns:
            Created bond interface details (or last VLAN interface if multiple VLANs)
        """
        bond_name = bond_config.get("name")
        vlan_id_config = bond_config.get("vlan_id")
        
        if not bond_name:
            raise ValueError("Bond config must have 'name'")
        if vlan_id_config is None:
            raise ValueError("Bond config must have 'vlan_id'")
        
        # Support both single VLAN and multiple VLANs
        if isinstance(vlan_id_config, list):
            vlan_ids = vlan_id_config
            primary_vlan_id = vlan_ids[0]
            log.info(f"Multiple VLANs requested: {vlan_ids}, using {primary_vlan_id} to find interfaces")
        else:
            vlan_ids = [vlan_id_config]
            primary_vlan_id = vlan_id_config
            log.info(f"Single VLAN requested: {primary_vlan_id}")
        
        vlan_id = primary_vlan_id
        
        log.info(f"Looking for interfaces with VLAN ID {vlan_id} on {system_id}")
        
        # Get all interfaces for the machine
        interfaces = self.get_interfaces(system_id)
        log.info(f"Total interfaces found: {len(interfaces)}")
        
        # Debug: Show all interfaces and their VLANs
        log.info("Scanning all interfaces on machine:")
        for iface in interfaces:
            if not iface or not isinstance(iface, dict):
                log.warning(f"Skipping invalid interface entry: {iface}")
                continue
            iface_name = iface.get("name", "UNKNOWN")
            iface_type = iface.get("type", "UNKNOWN")
            iface_vlan = iface.get("vlan")
            if iface_vlan and isinstance(iface_vlan, dict):
                vlan_vid = iface_vlan.get("vid", "None")
            else:
                vlan_vid = "None"
            log.info(f"  - {iface_name} (type: {iface_type}, VLAN: {vlan_vid})")
        
        # Find interfaces that have access to the specified VLAN
        log.info(f"\nSearching for interfaces with VLAN ID {vlan_id}...")
        matching_interfaces = []
        for iface in interfaces:
            if not iface or not isinstance(iface, dict):
                continue
                
            iface_name = iface.get("name")
            iface_type = iface.get("type")
            
            if not iface_name:
                log.warning(f"Skipping interface with no name")
                continue
            
            # Skip bond and bridge interfaces - we only want physical or VLAN interfaces
            if iface_type in ["bond", "bridge"]:
                log.debug(f"Skipping {iface_name} (type: {iface_type})")
                continue
            
            # Check the interface's VLAN directly (most reliable)
            iface_vlan = iface.get("vlan")
            if iface_vlan and isinstance(iface_vlan, dict):
                if iface_vlan.get("vid") == vlan_id:
                    if iface_name not in matching_interfaces:
                        matching_interfaces.append(iface_name)
                        log.info(f"  ✓ IDENTIFIED: {iface_name} (has VLAN {vlan_id})")
                    continue
            
            # Check if interface has links to the VLAN (fallback)
            links = iface.get("links", [])
            if links and isinstance(links, list):
                for link in links:
                    if not link or not isinstance(link, dict):
                        continue
                    subnet = link.get("subnet")
                    if subnet and isinstance(subnet, dict):
                        vlan = subnet.get("vlan")
                        if vlan and isinstance(vlan, dict) and vlan.get("vid") == vlan_id:
                            if iface_name not in matching_interfaces:
                                matching_interfaces.append(iface_name)
                                log.info(f"  ✓ IDENTIFIED: {iface_name} (VLAN {vlan_id} via subnet link)")
                            break
        
        log.info(f"\n{'='*60}")
        log.info(f"INTERFACE IDENTIFICATION SUMMARY")
        log.info(f"{'='*60}")
        log.info(f"Interfaces identified for bond '{bond_name}': {len(matching_interfaces)}")
        if matching_interfaces:
            for idx, iface_name in enumerate(matching_interfaces, 1):
                log.info(f"  {idx}. {iface_name}")
        else:
            log.info("  NONE FOUND")
        log.info(f"{'='*60}")
        
        if len(matching_interfaces) < 2:
            log.error(f"\n{'='*60}")
            log.error("ERROR: Not enough interfaces with matching VLAN")
            log.error(f"{'='*60}")
            log.error(f"Required: 2+ interfaces")
            log.error(f"Found: {len(matching_interfaces)} interface(s)")
            if matching_interfaces:
                log.error(f"Identified interfaces: {', '.join(matching_interfaces)}")
            log.error(f"\nAll available interfaces:")
            for iface in interfaces:
                if not iface or not isinstance(iface, dict):
                    continue
                vlan_info = iface.get("vlan")
                if vlan_info and isinstance(vlan_info, dict):
                    vlan_vid = vlan_info.get("vid", "None")
                else:
                    vlan_vid = "None"
                log.error(f"  - {iface.get('name', 'UNKNOWN')} (type: {iface.get('type', 'UNKNOWN')}, VLAN: {vlan_vid})")
            log.error(f"{'='*60}")
            raise ValueError(
                f"Found only {len(matching_interfaces)} interface(s) with VLAN {vlan_id}. "
                f"Need at least 2 interfaces to create a bond. Identified: {matching_interfaces if matching_interfaces else 'none'}"
            )
        
        log.info(f"Found {len(matching_interfaces)} interfaces with VLAN {vlan_id}: {', '.join(matching_interfaces)}")
        
        # Get interface IDs for the matching interfaces
        log.info("=" * 60)
        log.info(f"BOND PARENT INTERFACES for '{bond_name}':")
        log.info("=" * 60)
        interface_ids = []
        for iface_name in matching_interfaces:
            for iface in interfaces:
                if iface.get("name") == iface_name:
                    interface_ids.append(iface["id"])
                    iface_mac = iface.get("mac_address", "N/A")
                    iface_type = iface.get("type", "N/A")
                    log.info(f"  ✓ Parent Interface: {iface_name}")
                    log.info(f"    - ID: {iface['id']}")
                    log.info(f"    - MAC: {iface_mac}")
                    log.info(f"    - Type: {iface_type}")
                    log.info(f"    - VLAN: {vlan_id}")
                    break
        log.info("=" * 60)
        
        if len(interface_ids) != len(matching_interfaces):
            raise ValueError(f"Failed to get IDs for all interfaces. Expected {len(matching_interfaces)}, got {len(interface_ids)}")
        
        # Create bond directly
        bond_mode = bond_config.get("mode", "802.3ad")
        mtu = bond_config.get("mtu", 1500)
        
        # Create payload as a list of tuples for proper multipart encoding
        payload = [
            ("name", bond_name),
            ("bond_mode", bond_mode),
            ("mtu", str(mtu))
        ]
        
        # Add each parent interface ID separately
        log.info(f"Adding parent interface IDs to bond payload:")
        for iface_id in interface_ids:
            payload.append(("parents", str(iface_id)))
            log.info(f"  - Adding parent ID: {iface_id}")
        
        # Add bond parameters based on mode
        if bond_mode == "802.3ad":
            payload.append(("bond_lacp_rate", bond_config.get("lacp_rate", "fast")))
            payload.append(("bond_xmit_hash_policy", bond_config.get("xmit_hash_policy", "layer3+4")))
        
        log.info(f"Creating bond '{bond_name}' with mode '{bond_mode}' and MTU {mtu}")
        log.info(f"\nCalling MAAS API to create bond...")
        log.info(f"Endpoint: POST /api/2.0/nodes/{system_id}/interfaces/?op=create_bond")
        log.debug(f"Bond payload: {payload}")
        
        try:
            bond = retry(
                lambda: self.client.request(
                    "POST",
                    f"nodes/{system_id}/interfaces",
                    op="create_bond",
                    data=payload
                ),
                retries=self.max_retries,
                delay=2.0
            )
            log.info("=" * 60)
            log.info(f"✓ Successfully created bond: {bond_name}")
            log.info(f"  - Bond ID: {bond.get('id')}")
            log.info(f"  - Bond Mode: {bond_mode}")
            log.info(f"  - Parent Interfaces: {', '.join(matching_interfaces)}")
            log.info(f"  - Parent IDs: {', '.join(map(str, interface_ids))}")
            log.info("=" * 60)
            
            # Get subnet configuration if specified
            subnet_name = bond_config.get("subnet")
            ip_mode = bond_config.get("ip_mode")
            ip_address = bond_config.get("ip_address")
            target_subnet = None
            
            if subnet_name and ip_mode:
                log.info(f"\nLooking up subnet '{subnet_name}' for bond configuration...")
                try:
                    # Find subnet by name
                    target_subnet = self.find_subnet_by_name(subnet_name)
                    
                    if not target_subnet:
                        log.error(f"✗ Subnet '{subnet_name}' not found in MAAS")
                        log.warning(f"Bond '{bond_name}' created but subnet will not be configured")
                    else:
                        log.info(f"✓ Found subnet '{subnet_name}' (CIDR: {target_subnet.get('cidr')})")
                        
                        # Link the bond to subnet BEFORE creating VLAN interfaces
                        log.info(f"\nLinking bond '{bond_name}' to subnet '{subnet_name}'...")
                        try:
                            link_payload = {
                                "mode": ip_mode.upper(),
                                "subnet": target_subnet["id"]
                            }
                            
                            if ip_mode == "static" and ip_address:
                                link_payload["ip_address"] = ip_address
                            
                            retry(
                                lambda: self.client.request(
                                    "POST",
                                    f"nodes/{system_id}/interfaces/{bond['id']}",
                                    op="link_subnet",
                                    data=link_payload
                                ),
                                retries=self.max_retries,
                                delay=2.0
                            )
                            log.info(f"✓ Linked bond to subnet '{subnet_name}'")
                            log.info(f"  - Subnet CIDR: {target_subnet.get('cidr')}")
                            log.info(f"  - IP Mode: {ip_mode}")
                            if ip_mode == "static" and ip_address:
                                log.info(f"  - Static IP: {ip_address}")
                            
                        except Exception as subnet_error:
                            log.error(f"✗ Failed to link bond to subnet: {subnet_error}")
                            log.warning(f"Bond created but subnet linking failed")
                        
                except Exception as subnet_error:
                    log.error(f"✗ Failed to lookup subnet '{subnet_name}': {subnet_error}")
                    log.warning(f"Bond '{bond_name}' created but subnet lookup failed")
            elif subnet_name and not ip_mode:
                log.info(f"⚠ Subnet '{subnet_name}' specified but no ip_mode provided - skipping subnet configuration")
                log.info(f"  To configure subnet, add 'ip_mode' field with value: 'static', 'dynamic', or 'automatic'")
            
            # Tag the bond with VLAN ID(s)
            # If multiple VLANs, create VLAN interface for each
            created_vlan_interfaces = []
            last_vlan_interface = None
            
            for vlan_idx, vlan_tag in enumerate(vlan_ids, 1):
                log.info(f"\nCreating VLAN interface for VLAN {vlan_tag} on bond '{bond_name}' ({vlan_idx}/{len(vlan_ids)})...")
                try:
                    # Use the create_vlan operation which just needs parent and VLAN ID
                    vlan_payload = [
                        ("parents", str(bond['id'])),
                        ("vlan", str(vlan_tag))
                    ]
                    
                    log.debug(f"Creating VLAN interface with payload: {vlan_payload}")
                    
                    vlan_iface = retry(
                        lambda: self.client.request(
                            "POST",
                            f"nodes/{system_id}/interfaces",
                            op="create_vlan",
                            data=vlan_payload
                        ),
                        retries=self.max_retries,
                        delay=2.0
                    )
                    
                    log.info(f"✓ Successfully created VLAN interface for VLAN {vlan_tag}")
                    log.info(f"  - VLAN Interface ID: {vlan_iface.get('id')}")
                    log.info(f"  - VLAN Interface Name: {vlan_iface.get('name')}")
                    
                    created_vlan_interfaces.append(vlan_iface)
                    last_vlan_interface = vlan_iface
                    
                except Exception as vlan_error:
                    log.error(f"✗ Failed to create VLAN interface for VLAN {vlan_tag}: {vlan_error}")
                    if vlan_idx == 1:
                        # If first VLAN fails, this is critical
                        log.error(f"First VLAN creation failed - this is critical")
                        raise
                    else:
                        # For subsequent VLANs, log but continue
                        log.warning(f"Continuing with remaining VLANs...")
            
            # Summary
            if len(created_vlan_interfaces) > 0:
                log.info(f"\n✓ Created {len(created_vlan_interfaces)} VLAN interface(s) on bond '{bond_name}':")
                for vlan_iface in created_vlan_interfaces:
                    vlan_vid = vlan_iface.get('vlan', {}).get('vid', 'N/A') if isinstance(vlan_iface.get('vlan'), dict) else 'N/A'
                    log.info(f"  - {vlan_iface.get('name')} (VLAN {vlan_vid})")
                log.info(f"\n💡 Next step: Use 'update_interface' action to configure subnet/IP for each VLAN interface")
                return last_vlan_interface
            else:
                # No VLAN interfaces created, return the bond
                log.info(f"\n✓ Bond '{bond_name}' created (no VLAN interfaces)")
                return bond
            
        except Exception as e:
            log.error("=" * 60)
            log.error(f"✗ Failed to create bond '{bond_name}'")
            log.error(f"  Error: {e}")
            log.error(f"  System ID: {system_id}")
            log.error(f"  Parent Interfaces: {', '.join(matching_interfaces)}")
            log.error(f"  Parent IDs: {', '.join(map(str, interface_ids))}")
            log.error(f"  Bond Mode: {bond_mode}")
            log.error(f"  Payload: {payload}")
            log.error("=" * 60)
            raise

    def update_interface(self, system_id: str, interface_config: Dict) -> Dict:
        """
        Update an interface using the MAAS PUT API.
        
        This method supports updating interface properties including VLAN configuration,
        bonding parameters, bridge settings, and physical interface attributes.
        
        Args:
            system_id: Machine system ID
            interface_config: Interface configuration with keys:
                - name: Interface name to update (e.g., "bond0", "eth0") - required
                - interface_id: Interface ID (if name not provided) - optional
                - vlan: VLAN ID to connect interface to - optional
                - subnet: Subnet name or CIDR to link to - optional
                - ip_mode: "static", "dhcp", or "automatic" - optional (required with subnet)
                - ip_address: Static IP address - optional (for static mode)
                - mac_address: MAC address (can be updated for deployed machines) - optional
                - name_update: New name for the interface - optional
                - mtu: Maximum transmission unit - optional
                - tags: Comma-separated tags - optional
                - accept_ra: Accept router advertisements (IPv6 only) - optional
                - link_connected: Whether interface is physically connected - optional
                - interface_speed: Speed of interface in Mbit/s - optional
                - link_speed: Speed of link in Mbit/s - optional
                
                Bond-specific parameters:
                - bond_mode: Bond mode (e.g., "802.3ad", "active-backup") - optional
                - bond_miimon: Link monitoring frequency in ms - optional
                - bond_downdelay: Time to wait before disabling slave (ms) - optional
                - bond_updelay: Time to wait before enabling slave (ms) - optional
                - bond_lacp_rate: "fast" or "slow" - optional
                - bond_xmit_hash_policy: Hash policy for slave selection - optional
                
                Bridge-specific parameters:
                - bridge_type: "standard" or "ovs" - optional
                - bridge_stp: Enable/disable spanning tree protocol - optional
                - bridge_fd: Bridge forward delay in seconds - optional
        
        Returns:
            Updated interface details
        
        Example config for VLAN configuration after bond creation:
        {
            "name": "bond0",
            "vlan": 1551,
            "subnet": "UPI_App_Prov",
            "ip_mode": "static",
            "ip_address": "10.83.96.25"
        }
        """
        interface_name = interface_config.get("name")
        interface_id = interface_config.get("interface_id")
        
        if not interface_name and not interface_id:
            raise ValueError("Interface config must have 'name' or 'interface_id'")
        
        # Find interface by name if ID not provided
        if not interface_id:
            iface = self.find_interface_by_name(system_id, interface_name)
            if not iface:
                raise ValueError(f"Interface '{interface_name}' not found on machine {system_id}")
            interface_id = iface["id"]
            log.info(f"Found interface '{interface_name}' with ID {interface_id}")
        else:
            log.info(f"Using provided interface ID {interface_id}")
        
        log.info(f"Updating interface ID {interface_id} on system {system_id}")
        
        # Build update payload
        update_data = []
        
        # Basic interface parameters
        if "name_update" in interface_config:
            update_data.append(("name", interface_config["name_update"]))
            log.debug(f"  - Updating name to: {interface_config['name_update']}")
        
        if "mac_address" in interface_config:
            update_data.append(("mac_address", interface_config["mac_address"]))
            log.debug(f"  - Updating MAC address to: {interface_config['mac_address']}")
        
        if "mtu" in interface_config:
            update_data.append(("mtu", str(interface_config["mtu"])))
            log.debug(f"  - Setting MTU to: {interface_config['mtu']}")
        
        if "tags" in interface_config:
            update_data.append(("tags", interface_config["tags"]))
            log.debug(f"  - Setting tags to: {interface_config['tags']}")
        
        # VLAN configuration
        if "vlan" in interface_config:
            vlan_id = interface_config["vlan"]
            log.info(f"  - Configuring VLAN ID: {vlan_id}")
            
            # Find VLAN object in MAAS
            try:
                vlans = self.client.request("GET", "vlans/")
                target_vlan = None
                for vlan in vlans:
                    if vlan.get("vid") == vlan_id:
                        target_vlan = vlan
                        log.debug(f"    Found VLAN: ID={vlan['id']}, VID={vlan_id}, Fabric={vlan.get('fabric')}")
                        break
                
                if target_vlan:
                    update_data.append(("vlan", str(target_vlan["id"])))
                else:
                    log.warning(f"    VLAN with VID {vlan_id} not found in MAAS")
            except Exception as e:
                log.error(f"    Failed to lookup VLAN {vlan_id}: {e}")
        
        # Physical interface parameters
        if "accept_ra" in interface_config:
            update_data.append(("accept_ra", str(interface_config["accept_ra"]).lower()))
            log.debug(f"  - Accept RA: {interface_config['accept_ra']}")
        
        if "link_connected" in interface_config:
            update_data.append(("link_connected", str(interface_config["link_connected"]).lower()))
            log.debug(f"  - Link connected: {interface_config['link_connected']}")
        
        if "interface_speed" in interface_config:
            update_data.append(("interface_speed", str(interface_config["interface_speed"])))
            log.debug(f"  - Interface speed: {interface_config['interface_speed']} Mbit/s")
        
        if "link_speed" in interface_config:
            update_data.append(("link_speed", str(interface_config["link_speed"])))
            log.debug(f"  - Link speed: {interface_config['link_speed']} Mbit/s")
        
        # Bond parameters
        if "bond_mode" in interface_config:
            update_data.append(("bond_mode", interface_config["bond_mode"]))
            log.debug(f"  - Bond mode: {interface_config['bond_mode']}")
        
        if "bond_miimon" in interface_config:
            update_data.append(("bond_miimon", str(interface_config["bond_miimon"])))
            log.debug(f"  - Bond miimon: {interface_config['bond_miimon']}")
        
        if "bond_downdelay" in interface_config:
            update_data.append(("bond_downdelay", str(interface_config["bond_downdelay"])))
            log.debug(f"  - Bond downdelay: {interface_config['bond_downdelay']}")
        
        if "bond_updelay" in interface_config:
            update_data.append(("bond_updelay", str(interface_config["bond_updelay"])))
            log.debug(f"  - Bond updelay: {interface_config['bond_updelay']}")
        
        if "bond_lacp_rate" in interface_config:
            update_data.append(("bond_lacp_rate", interface_config["bond_lacp_rate"]))
            log.debug(f"  - Bond LACP rate: {interface_config['bond_lacp_rate']}")
        
        if "bond_xmit_hash_policy" in interface_config:
            update_data.append(("bond_xmit_hash_policy", interface_config["bond_xmit_hash_policy"]))
            log.debug(f"  - Bond xmit hash policy: {interface_config['bond_xmit_hash_policy']}")
        
        # Bridge parameters
        if "bridge_type" in interface_config:
            update_data.append(("bridge_type", interface_config["bridge_type"]))
            log.debug(f"  - Bridge type: {interface_config['bridge_type']}")
        
        if "bridge_stp" in interface_config:
            update_data.append(("bridge_stp", str(interface_config["bridge_stp"]).lower()))
            log.debug(f"  - Bridge STP: {interface_config['bridge_stp']}")
        
        if "bridge_fd" in interface_config:
            update_data.append(("bridge_fd", str(interface_config["bridge_fd"])))
            log.debug(f"  - Bridge forward delay: {interface_config['bridge_fd']}")
        
        # Update the interface if there are changes
        if update_data:
            try:
                log.debug(f"Calling MAAS API: PUT /api/2.0/nodes/{system_id}/interfaces/{interface_id}/")
                updated_iface = retry(
                    lambda: self.client.request(
                        "PUT",
                        f"nodes/{system_id}/interfaces/{interface_id}/",
                        data=update_data
                    ),
                    retries=self.max_retries,
                    delay=2.0
                )
                log.info(f"✓ Interface updated successfully")
            except Exception as e:
                log.error(f"Failed to update interface: {e}")
                raise
        else:
            log.info("No interface properties to update")
            updated_iface = self.find_interface_by_name(system_id, interface_name)
        
        # Link to subnet if specified
        subnet_name = interface_config.get("subnet")
        ip_mode = interface_config.get("ip_mode")
        ip_address = interface_config.get("ip_address")
        
        if subnet_name and ip_mode:
            log.info(f"  - Linking to subnet: {subnet_name} (mode: {ip_mode})")
            
            try:
                # Find subnet by name or CIDR
                target_subnet = self.find_subnet_by_name(subnet_name)
                
                if not target_subnet:
                    # Try to find by CIDR
                    subnets = self.client.request("GET", "subnets/")
                    for subnet in subnets:
                        if subnet.get("cidr") == subnet_name:
                            target_subnet = subnet
                            log.debug(f"    Found subnet by CIDR: {subnet_name}")
                            break
                
                if not target_subnet:
                    log.error(f"    Subnet '{subnet_name}' not found in MAAS")
                    raise ValueError(f"Subnet '{subnet_name}' not found")
                
                # Link interface to subnet
                link_payload = {
                    "mode": ip_mode.upper(),
                    "subnet": target_subnet["id"]
                }
                
                if ip_mode.lower() == "static" and ip_address:
                    link_payload["ip_address"] = ip_address
                    log.debug(f"    Static IP: {ip_address}")
                
                retry(
                    lambda: self.client.request(
                        "POST",
                        f"nodes/{system_id}/interfaces/{interface_id}",
                        op="link_subnet",
                        data=link_payload
                    ),
                    retries=self.max_retries,
                    delay=2.0
                )
                log.info(f"✓ Linked interface to subnet '{subnet_name}' (CIDR: {target_subnet.get('cidr')})")
                if ip_mode.lower() == "static" and ip_address:
                    log.info(f"  - Assigned static IP: {ip_address}")
                
            except Exception as e:
                log.error(f"Failed to link interface to subnet: {e}")
                raise
        elif subnet_name and not ip_mode:
            log.warning(f"Subnet '{subnet_name}' specified but no ip_mode provided - skipping subnet linking")
            log.info("  To link subnet, add 'ip_mode' field with value: 'static', 'dhcp', or 'automatic'")
        
        # Get final interface state
        try:
            final_iface = retry(
                lambda: self.client.request("GET", f"nodes/{system_id}/interfaces/{interface_id}/"),
                retries=self.max_retries,
                delay=1.0
            )
            log.debug(f"Final interface state: {final_iface.get('name')} - VLAN: {final_iface.get('vlan', {}).get('vid', 'N/A')}")
            return final_iface
        except Exception:
            return updated_iface

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
