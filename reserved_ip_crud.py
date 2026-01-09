#!/usr/bin/env python3
"""
Standalone script for CRUD operations on MAAS Reserved IPs

Usage (with config file):
    # List all reserved IPs
    python3 reserved_ip_crud.py -i config.json list
    
    # List reserved IPs in a specific subnet
    python3 reserved_ip_crud.py -i config.json list --subnet 1
    python3 reserved_ip_crud.py -i config.json list --subnet-name "10.0.1.0/24"
    
    # Create a reserved IP
    python3 reserved_ip_crud.py -i config.json create \
        --ip 10.0.1.100 --mac 00:11:22:33:44:55 --subnet 1 --comment "My reservation"
    
    # Get reserved IP details
    python3 reserved_ip_crud.py -i config.json get --id 1
    
    # Update a reserved IP
    python3 reserved_ip_crud.py -i config.json update \
        --id 1 --comment "Updated comment" --mac 00:11:22:33:44:66
    
    # Delete a reserved IP
    python3 reserved_ip_crud.py -i config.json delete --id 1

Usage (with CLI args):
    python3 reserved_ip_crud.py --url http://maas:5240/MAAS --key KEY list
"""

import argparse
import json
import sys
import time
import random
import string
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional


class MAASClient:
    """Simple MAAS API client for reserved IP operations"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        
        # Parse API key
        parts = api_key.split(':')
        if len(parts) != 3:
            raise ValueError("API key must be in format: consumer:token:secret")
        self.consumer, self.token, self.secret = parts
    
    def _build_oauth_header(self) -> str:
        """Build OAuth PLAINTEXT authorization header for MAAS"""
        oauth = {
            "oauth_consumer_key": self.consumer,
            "oauth_token": self.token,
            "oauth_signature_method": "PLAINTEXT",
            "oauth_signature": f"&{self.secret}",
            "oauth_timestamp": str(int(time.time())),
            "oauth_nonce": ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            "oauth_version": "1.0"
        }
        
        return "OAuth " + ", ".join(f'{k}="{v}"' for k, v in oauth.items())
        
    def _make_request(self, endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> any:
        """Make authenticated request to MAAS API"""
        url = f"{self.api_url}/api/2.0/{endpoint}"
        
        # Prepare request
        headers = {
            'Authorization': self._build_oauth_header(),
            'Accept': 'application/json'
        }
        
        # Encode data for POST/PUT/DELETE
        encoded_data = None
        if data:
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
        
        # Create request
        req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req) as response:
                content = response.read().decode('utf-8')
                if content:
                    return json.loads(content)
                return None
        except urllib.error.HTTPError as e:
            error_content = e.read().decode('utf-8')
            raise Exception(f"HTTP {e.code}: {error_content}")
        except urllib.error.URLError as e:
            raise Exception(f"URL Error: {e.reason}")
    
    def list_reserved_ips(self) -> List[Dict]:
        """List all reserved IPs"""
        return self._make_request('reservedips/')
    
    def list_subnets(self) -> List[Dict]:
        """List all subnets"""
        return self._make_request('subnets/')
    
    def get_reserved_ip(self, ip_id: int) -> Dict:
        """Get a specific reserved IP"""
        return self._make_request(f'reservedips/{ip_id}/')
    
    def create_reserved_ip(self, ip: str, mac: str, subnet: Optional[int] = None, 
                          comment: Optional[str] = None) -> Dict:
        """Create a new reserved IP"""
        data = {
            'ip': ip,
            'mac_address': mac
        }
        if subnet:
            data['subnet'] = subnet
        if comment:
            data['comment'] = comment
        
        return self._make_request('reservedips/', method='POST', data=data)
    
    def update_reserved_ip(self, ip_id: int, mac: Optional[str] = None, 
                          comment: Optional[str] = None) -> Dict:
        """Update an existing reserved IP"""
        data = {}
        if mac:
            data['mac_address'] = mac
        if comment is not None:  # Allow empty string to clear comment
            data['comment'] = comment
        
        if not data:
            raise ValueError("Must provide at least one field to update (mac or comment)")
        
        return self._make_request(f'reservedips/{ip_id}/', method='PUT', data=data)
    
    def delete_reserved_ip(self, ip_id: int) -> None:
        """Delete a reserved IP"""
        self._make_request(f'reservedips/{ip_id}/', method='DELETE')


def print_reserved_ips(reserved_ips: List[Dict], subnet_filter: Optional[str] = None):
    """Pretty print reserved IPs"""
    if not reserved_ips:
        print("\n✗ No reserved IPs found")
        return
    
    print("\n" + "=" * 130)
    print(f"{'ID':<8} {'IP ADDRESS':<20} {'MAC ADDRESS':<20} {'SUBNET':<30} {'COMMENT':<45}")
    print("=" * 130)
    
    for ip_data in reserved_ips:
        ip_id = ip_data.get('id', '-')
        ip_addr = ip_data.get('ip', '-')
        mac = ip_data.get('mac_address', '-')
        subnet = ip_data.get('subnet', {})
        
        if isinstance(subnet, dict):
            subnet_cidr = subnet.get('cidr', '-')
            subnet_name = subnet.get('name', '-')
            subnet_display = f"{subnet_name} ({subnet_cidr})"
        else:
            subnet_display = str(subnet) if subnet else '-'
        
        comment = ip_data.get('comment', '-') or '-'
        
        print(f"{ip_id:<8} {ip_addr:<20} {mac:<20} {subnet_display:<30} {comment:<45}")
    
    print("=" * 130)
    print(f"Total: {len(reserved_ips)} reserved IP(s)")
    if subnet_filter:
        print(f"Filtered by subnet: {subnet_filter}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='MAAS Reserved IP CRUD Operations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Global arguments
    parser.add_argument('-i', '--input', help='Path to JSON configuration file (containing maas_api_url and maas_api_key)')
    parser.add_argument('--url', help='MAAS API URL (e.g., http://maas:5240/MAAS) - overrides config file')
    parser.add_argument('--key', help='MAAS API key (consumer:token:secret) - overrides config file')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True
    
    # LIST command
    list_parser = subparsers.add_parser('list', help='List reserved IPs')
    list_parser.add_argument('--subnet', type=int, help='Filter by subnet ID')
    list_parser.add_argument('--subnet-name', help='Filter by subnet name/CIDR')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # GET command
    get_parser = subparsers.add_parser('get', help='Get reserved IP details')
    get_parser.add_argument('--id', type=int, required=True, help='Reserved IP ID')
    get_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # CREATE command
    create_parser = subparsers.add_parser('create', help='Create a reserved IP')
    create_parser.add_argument('--ip', required=True, help='IP address to reserve')
    create_parser.add_argument('--mac', required=True, help='MAC address')
    create_parser.add_argument('--subnet', type=int, help='Subnet ID')
    create_parser.add_argument('--subnet-name', help='Subnet name/CIDR (instead of ID)')
    create_parser.add_argument('--comment', help='Comment/description')
    create_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # UPDATE command
    update_parser = subparsers.add_parser('update', help='Update a reserved IP')
    update_parser.add_argument('--id', type=int, required=True, help='Reserved IP ID')
    update_parser.add_argument('--mac', help='New MAC address')
    update_parser.add_argument('--comment', help='New comment (use "" to clear)')
    update_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # DELETE command
    delete_parser = subparsers.add_parser('delete', help='Delete reserved IP(s)')
    delete_parser.add_argument('--id', type=int, help='Reserved IP ID to delete')
    delete_parser.add_argument('--subnet', type=int, help='Delete all reserved IPs in this subnet ID')
    delete_parser.add_argument('--subnet-name', help='Delete all reserved IPs in this subnet name/CIDR')
    delete_parser.add_argument('--confirm', action='store_true', help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    # Load configuration
    api_url = args.url
    api_key = args.key
    
    # Load from config file if provided
    if args.input:
        try:
            with open(args.input, 'r') as f:
                config = json.load(f)
            
            # Use config file values if not overridden by CLI
            if not api_url:
                api_url = config.get('maas_api_url')
            if not api_key:
                api_key = config.get('maas_api_key')
        except FileNotFoundError:
            print(f"\n✗ Configuration file not found: {args.input}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"\n✗ Invalid JSON in configuration file: {e}")
            sys.exit(1)
    
    # Validate required credentials
    if not api_url:
        print("\n✗ MAAS API URL is required (use -i config.json or --url)")
        sys.exit(1)
    if not api_key:
        print("\n✗ MAAS API key is required (use -i config.json or --key)")
        sys.exit(1)
    
    # Initialize client
    try:
        client = MAASClient(api_url, api_key)
    except Exception as e:
        print(f"\n✗ Failed to initialize MAAS client: {e}")
        sys.exit(1)
    
    try:
        # Execute command
        if args.command == 'list':
            reserved_ips = client.list_reserved_ips()
            
            # Filter by subnet if requested
            subnet_filter_name = None
            if args.subnet or args.subnet_name:
                if args.subnet_name:
                    # Look up subnet by name
                    subnets = client.list_subnets()
                    subnet_id = None
                    for subnet in subnets:
                        if subnet.get('name') == args.subnet_name or subnet.get('cidr') == args.subnet_name:
                            subnet_id = subnet.get('id')
                            subnet_filter_name = f"{subnet.get('name')} ({subnet.get('cidr')})"
                            break
                    
                    if subnet_id is None:
                        print(f"\n✗ Subnet '{args.subnet_name}' not found")
                        sys.exit(1)
                else:
                    subnet_id = args.subnet
                    subnet_filter_name = f"ID {subnet_id}"
                
                # Filter reserved IPs by subnet
                filtered = []
                for ip_data in reserved_ips:
                    subnet = ip_data.get('subnet', {})
                    if isinstance(subnet, dict):
                        if subnet.get('id') == subnet_id:
                            filtered.append(ip_data)
                    elif subnet == subnet_id:
                        filtered.append(ip_data)
                
                reserved_ips = filtered
            
            if args.json:
                print(json.dumps(reserved_ips, indent=2))
            else:
                print_reserved_ips(reserved_ips, subnet_filter_name)
        
        elif args.command == 'get':
            reserved_ip = client.get_reserved_ip(args.id)
            
            if args.json:
                print(json.dumps(reserved_ip, indent=2))
            else:
                print(f"\n{'=' * 80}")
                print(f"Reserved IP Details (ID: {args.id})")
                print(f"{'=' * 80}")
                print(f"IP Address:  {reserved_ip.get('ip', '-')}")
                print(f"MAC Address: {reserved_ip.get('mac_address', '-')}")
                
                subnet = reserved_ip.get('subnet', {})
                if isinstance(subnet, dict):
                    print(f"Subnet:      {subnet.get('name', '-')} ({subnet.get('cidr', '-')})")
                else:
                    print(f"Subnet ID:   {subnet}")
                
                print(f"Comment:     {reserved_ip.get('comment', '-') or '-'}")
                print(f"{'=' * 80}\n")
        
        elif args.command == 'create':
            # Resolve subnet name to ID if provided
            subnet_id = args.subnet
            if args.subnet_name:
                subnets = client.list_subnets()
                for subnet in subnets:
                    if subnet.get('name') == args.subnet_name or subnet.get('cidr') == args.subnet_name:
                        subnet_id = subnet.get('id')
                        break
                
                if subnet_id is None:
                    print(f"\n✗ Subnet '{args.subnet_name}' not found")
                    sys.exit(1)
            
            reserved_ip = client.create_reserved_ip(
                ip=args.ip,
                mac=args.mac,
                subnet=subnet_id,
                comment=args.comment
            )
            
            if args.json:
                print(json.dumps(reserved_ip, indent=2))
            else:
                print(f"\n✓ Reserved IP created successfully!")
                print(f"  ID:      {reserved_ip.get('id')}")
                print(f"  IP:      {reserved_ip.get('ip')}")
                print(f"  MAC:     {reserved_ip.get('mac_address')}")
                if reserved_ip.get('subnet'):
                    subnet = reserved_ip.get('subnet', {})
                    if isinstance(subnet, dict):
                        print(f"  Subnet:  {subnet.get('name')} ({subnet.get('cidr')})")
                print()
        
        elif args.command == 'update':
            if not args.mac and args.comment is None:
                print("\n✗ Must provide at least one field to update (--mac or --comment)")
                sys.exit(1)
            
            reserved_ip = client.update_reserved_ip(
                ip_id=args.id,
                mac=args.mac,
                comment=args.comment
            )
            
            if args.json:
                print(json.dumps(reserved_ip, indent=2))
            else:
                print(f"\n✓ Reserved IP {args.id} updated successfully!")
                print(f"  IP:      {reserved_ip.get('ip')}")
                print(f"  MAC:     {reserved_ip.get('mac_address')}")
                print(f"  Comment: {reserved_ip.get('comment', '-') or '-'}")
                print()
        
        elif args.command == 'delete':
            # Validate that either --id or --subnet/--subnet-name is provided
            if not args.id and not args.subnet and not args.subnet_name:
                print("\n✗ Must provide either --id or --subnet/--subnet-name")
                sys.exit(1)
            
            if args.id:
                # Delete single reserved IP by ID
                if not args.confirm:
                    response = input(f"\nAre you sure you want to delete reserved IP {args.id}? (yes/no): ")
                    if response.lower() not in ['yes', 'y']:
                        print("Cancelled.")
                        sys.exit(0)
                
                client.delete_reserved_ip(args.id)
                print(f"\n✓ Reserved IP {args.id} deleted successfully!\n")
            
            else:
                # Delete all reserved IPs in a subnet
                reserved_ips = client.list_reserved_ips()
                
                # Determine subnet ID
                subnet_id = args.subnet
                subnet_name = None
                if args.subnet_name:
                    subnets = client.list_subnets()
                    for subnet in subnets:
                        if subnet.get('name') == args.subnet_name or subnet.get('cidr') == args.subnet_name:
                            subnet_id = subnet.get('id')
                            subnet_name = f"{subnet.get('name')} ({subnet.get('cidr')})"
                            break
                    
                    if subnet_id is None:
                        print(f"\n✗ Subnet '{args.subnet_name}' not found")
                        sys.exit(1)
                else:
                    subnet_name = f"ID {subnet_id}"
                
                # Filter reserved IPs by subnet
                ips_to_delete = []
                for ip_data in reserved_ips:
                    subnet = ip_data.get('subnet', {})
                    if isinstance(subnet, dict):
                        if subnet.get('id') == subnet_id:
                            ips_to_delete.append(ip_data)
                    elif subnet == subnet_id:
                        ips_to_delete.append(ip_data)
                
                if not ips_to_delete:
                    print(f"\n✗ No reserved IPs found in subnet {subnet_name}\n")
                    sys.exit(0)
                
                # Show what will be deleted
                print(f"\n{'=' * 80}")
                print(f"Found {len(ips_to_delete)} reserved IP(s) to delete in subnet {subnet_name}:")
                print(f"{'=' * 80}")
                for ip_data in ips_to_delete:
                    print(f"  ID {ip_data.get('id')}: {ip_data.get('ip')} (MAC: {ip_data.get('mac_address')})")
                print(f"{'=' * 80}")
                
                if not args.confirm:
                    response = input(f"\nAre you sure you want to delete ALL {len(ips_to_delete)} reserved IP(s)? (yes/no): ")
                    if response.lower() not in ['yes', 'y']:
                        print("Cancelled.")
                        sys.exit(0)
                
                # Delete all
                success_count = 0
                failed_count = 0
                for ip_data in ips_to_delete:
                    ip_id = ip_data.get('id')
                    try:
                        client.delete_reserved_ip(ip_id)
                        print(f"✓ Deleted reserved IP {ip_id} ({ip_data.get('ip')})")
                        success_count += 1
                    except Exception as e:
                        print(f"✗ Failed to delete reserved IP {ip_id}: {e}")
                        failed_count += 1
                
                print(f"\n{'=' * 80}")
                print(f"Summary: {success_count} deleted, {failed_count} failed")
                print(f"{'=' * 80}\n")
    
    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
