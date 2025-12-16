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
