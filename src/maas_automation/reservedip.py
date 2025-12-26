"""Reserved IP management operations"""
import logging
from typing import Dict, List, Optional
from .client import MaasClient
from .utils import retry

log = logging.getLogger("maas_automation.reservedip")


class ReservedIPManager:
    """Manages Reserved IP operations"""

    def __init__(self, client: MaasClient, max_retries: int = 5):
        self.client = client
        self.max_retries = max_retries

    def list(self) -> List[Dict]:
        """Get all reserved IPs"""
        try:
            reserved_ips = retry(
                lambda: self.client.get_reserved_ips(),
                retries=self.max_retries,
                delay=2.0
            )
            if not reserved_ips:
                reserved_ips = []
            
            log.debug(f"Found {len(reserved_ips)} reserved IPs")
            return reserved_ips
        except Exception as e:
            log.error(f"Failed to get reserved IPs: {e}")
            raise

    def get(self, reserved_ip_id: int) -> Optional[Dict]:
        """Get a specific reserved IP by ID"""
        try:
            reserved_ip = retry(
                lambda: self.client.get_reserved_ip(reserved_ip_id),
                retries=self.max_retries,
                delay=2.0
            )
            log.debug(f"Retrieved reserved IP {reserved_ip_id}")
            return reserved_ip
        except Exception as e:
            log.error(f"Failed to get reserved IP {reserved_ip_id}: {e}")
            raise

    def create(self, config: Dict) -> Dict:
        """
        Create a new reserved IP.
        
        Args:
            config: Reserved IP configuration with keys:
                - ip: IP address to reserve (required)
                - mac: MAC address (required)
                - subnet: Subnet ID (numeric) or subnet name (string) (optional)
                - comment: Comment describing the reservation (optional)
        
        Returns:
            Created reserved IP details
        """
        ip_address = config.get("ip")
        if not ip_address:
            raise ValueError("Reserved IP config must have 'ip' address")
        
        mac_address = config.get("mac")
        if not mac_address:
            raise ValueError("Reserved IP config must have 'mac' address - MAC address is required by MAAS")
        
        log.info(f"Creating reserved IP: {ip_address}")
        
        payload = {"ip": ip_address, "mac": mac_address}
        
        # Handle subnet - accept either ID (int) or name (string)
        if "subnet" in config:
            subnet_value = config["subnet"]
            if isinstance(subnet_value, str):
                # Look up subnet by name
                log.debug(f"Looking up subnet by name: {subnet_value}")
                subnets = self.client.list_subnets()
                subnet_id = None
                for subnet in subnets:
                    if subnet.get('name') == subnet_value:
                        subnet_id = subnet.get('id')
                        log.debug(f"Found subnet '{subnet_value}' with ID {subnet_id}")
                        break
                
                if subnet_id is None:
                    raise ValueError(f"Subnet '{subnet_value}' not found in MAAS")
                
                payload["subnet"] = subnet_id
            else:
                # Assume it's an ID
                payload["subnet"] = subnet_value
        
        # Only add comment if it's provided and not empty
        if config.get("comment"):
            payload["comment"] = config["comment"]
        
        log.debug(f"Reserved IP payload: {payload}")
        
        try:
            reserved_ip = retry(
                lambda: self.client.create_reserved_ip(payload),
                retries=self.max_retries,
                delay=2.0
            )
            log.info(f"✓ Created reserved IP: {ip_address} (ID: {reserved_ip.get('id')})")
            return reserved_ip
        except Exception as e:
            log.error(f"Failed to create reserved IP '{ip_address}': {e}")
            raise

    def update(self, reserved_ip_id: int, config: Dict) -> Dict:
        """
        Update an existing reserved IP.
        
        Args:
            reserved_ip_id: ID of the reserved IP to update
            config: Updated configuration with keys:
                - ip: New IP address (optional)
                - mac: New MAC address (optional)
                - comment: New comment (optional)
        
        Returns:
            Updated reserved IP details
        """
        log.info(f"Updating reserved IP ID: {reserved_ip_id}")
        
        payload = {}
        
        if "ip" in config:
            payload["ip"] = config["ip"]
        if "mac" in config:
            payload["mac"] = config["mac"]
        if "comment" in config:
            payload["comment"] = config["comment"]
        
        if not payload:
            log.warning("No update fields provided")
            return self.get(reserved_ip_id)
        
        log.debug(f"Update payload: {payload}")
        
        try:
            reserved_ip = retry(
                lambda: self.client.update_reserved_ip(reserved_ip_id, payload),
                retries=self.max_retries,
                delay=2.0
            )
            log.info(f"✓ Updated reserved IP ID: {reserved_ip_id}")
            return reserved_ip
        except Exception as e:
            log.error(f"Failed to update reserved IP {reserved_ip_id}: {e}")
            raise

    def delete(self, reserved_ip_id: int) -> bool:
        """
        Delete a reserved IP.
        
        Args:
            reserved_ip_id: ID of the reserved IP to delete
        
        Returns:
            True if successful
        """
        log.info(f"Deleting reserved IP ID: {reserved_ip_id}")
        
        try:
            retry(
                lambda: self.client.delete_reserved_ip(reserved_ip_id),
                retries=self.max_retries,
                delay=2.0
            )
            log.info(f"✓ Deleted reserved IP ID: {reserved_ip_id}")
            return True
        except Exception as e:
            log.error(f"Failed to delete reserved IP {reserved_ip_id}: {e}")
            raise

    def find_by_ip(self, ip_address: str) -> Optional[Dict]:
        """Find a reserved IP by its IP address"""
        try:
            reserved_ips = self.list()
            for reserved_ip in reserved_ips:
                if reserved_ip.get("ip") == ip_address:
                    log.debug(f"Found reserved IP with address {ip_address} (ID: {reserved_ip.get('id')})")
                    return reserved_ip
            log.warning(f"Reserved IP with address '{ip_address}' not found")
            return None
        except Exception as e:
            log.error(f"Failed to search for reserved IP '{ip_address}': {e}")
            return None

    def find_by_mac(self, mac_address: str) -> Optional[Dict]:
        """Find a reserved IP by its MAC address"""
        try:
            reserved_ips = self.list()
            for reserved_ip in reserved_ips:
                if reserved_ip.get("mac") == mac_address:
                    log.debug(f"Found reserved IP with MAC {mac_address} (ID: {reserved_ip.get('id')})")
                    return reserved_ip
            log.warning(f"Reserved IP with MAC '{mac_address}' not found")
            return None
        except Exception as e:
            log.error(f"Failed to search for reserved IP by MAC '{mac_address}': {e}")
            return None
