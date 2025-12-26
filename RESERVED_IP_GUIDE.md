# MAAS Reserved IP Management

This guide covers how to use the Reserved IP management features in the MAAS Automation SDK.

## Overview

The MAAS Automation SDK now supports full CRUD operations for Reserved IPs using the MAAS API 2.0 `/reservedips/` endpoint:

- **List** all reserved IPs
- **Get** details of a specific reserved IP
- **Create** a new reserved IP
- **Update** an existing reserved IP
- **Delete** a reserved IP

## API Endpoints Used

- `GET /MAAS/api/2.0/reservedips/` - List all reserved IPs
- `POST /MAAS/api/2.0/reservedips/` - Create a reserved IP
- `GET /MAAS/api/2.0/reservedips/{id}/` - Read a reserved IP
- `PUT /MAAS/api/2.0/reservedips/{id}/` - Update a reserved IP
- `DELETE /MAAS/api/2.0/reservedips/{id}/` - Delete a reserved IP

## Available Actions

### 1. List Reserved IPs

List all reserved IP addresses in MAAS.

**Configuration:**
```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": [
    "list_reserved_ips"
  ]
}
```

**Usage:**
```bash
maas-automation -i example_list_reserved_ips.json
```

**Output:**
```
========================================================================================================================
ID       IP ADDRESS           MAC ADDRESS          SUBNET                    COMMENT                                 
========================================================================================================================
1        192.168.1.100        00:11:22:33:44:55    192.168.1.0/24            Reserved for production server          
2        192.168.1.101        -                    192.168.1.0/24            Test environment                        
========================================================================================================================
Total: 2 reserved IP addresses
```

### 2. Get Reserved IP Details

Get detailed information about a specific reserved IP.

**Configuration:**
```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": [
    "get_reserved_ip"
  ],
  "reserved_ip_id": 1
}
```

**Usage:**
```bash
maas-automation -i example_get_reserved_ip.json
```

**Output:**
```
================================================================================
RESERVED IP DETAILS (ID: 1)
================================================================================
IP Address:    192.168.1.100
MAC Address:   00:11:22:33:44:55
Subnet:        192.168.1.0/24 (ID: 5)
Comment:       Reserved for production server
================================================================================
```

### 3. Create Reserved IP

Create a new reserved IP address.

**Configuration:**
```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": [
    "create_reserved_ip"
  ],
  "reserved_ip": {
    "ip": "192.168.1.100",
    "mac": "00:11:22:33:44:55",
    "subnet": 1,
    "comment": "Reserved for production server"
  }
}
```

**Parameters:**
- `ip` (required): IP address to reserve
- `mac` (optional): MAC address to associate with the reserved IP
- `subnet` (optional): Subnet ID for the IP address
- `comment` (optional): Description or comment for the reservation

**Usage:**
```bash
maas-automation -i example_create_reserved_ip.json
```

**Output:**
```
================================================================================
✓ RESERVED IP CREATED
================================================================================
ID:            1
IP Address:    192.168.1.100
MAC Address:   00:11:22:33:44:55
Subnet:        192.168.1.0/24
Comment:       Reserved for production server
================================================================================
```

### 4. Update Reserved IP

Update an existing reserved IP's properties.

**Configuration:**
```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": [
    "update_reserved_ip"
  ],
  "reserved_ip_id": 1,
  "reserved_ip": {
    "comment": "Updated comment for reserved IP",
    "mac": "00:11:22:33:44:66"
  }
}
```

**Parameters:**
- `reserved_ip_id` (required): ID of the reserved IP to update
- `reserved_ip` (required): Object containing fields to update:
  - `ip` (optional): New IP address
  - `mac` (optional): New MAC address
  - `comment` (optional): New comment

**Usage:**
```bash
maas-automation -i example_update_reserved_ip.json
```

**Output:**
```
================================================================================
✓ RESERVED IP UPDATED (ID: 1)
================================================================================
IP Address:    192.168.1.100
MAC Address:   00:11:22:33:44:66
Subnet:        192.168.1.0/24
Comment:       Updated comment for reserved IP
================================================================================
```

### 5. Delete Reserved IP

Delete a reserved IP from MAAS.

**Configuration:**
```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": [
    "delete_reserved_ip"
  ],
  "reserved_ip_id": 1
}
```

**Parameters:**
- `reserved_ip_id` (required): ID of the reserved IP to delete

**Usage:**
```bash
maas-automation -i example_delete_reserved_ip.json
```

**Output:**
```
================================================================================
✓ RESERVED IP DELETED (ID: 1)
================================================================================
```

## Command Line Usage

You can also override actions via command line:

```bash
# List all reserved IPs
maas-automation -i config.json -a list_reserved_ips

# Create a reserved IP (config must include reserved_ip section)
maas-automation -i config_with_reserved_ip.json -a create_reserved_ip

# Delete a reserved IP (config must include reserved_ip_id)
maas-automation -i config_with_id.json -a delete_reserved_ip
```

## Error Handling

The SDK includes comprehensive error handling:

- Validates required fields before API calls
- Retries failed operations (configurable with `--max-retries`)
- Provides clear error messages

Example error output:
```
❌ Failed to create reserved IP: IP address already reserved
❌ Missing 'reserved_ip_id' in configuration for get_reserved_ip action
```

## Integration with Other Features

Reserved IPs can be used in conjunction with other MAAS automation features:

1. **Network Configuration**: Reserve IPs before configuring network bonds
2. **Machine Deployment**: Pre-reserve IPs for machines before deployment
3. **Subnet Management**: Organize reserved IPs by subnet

## Module Structure

The Reserved IP functionality is organized into:

- **`client.py`**: Low-level API methods (`get_reserved_ips()`, `create_reserved_ip()`, etc.)
- **`reservedip.py`**: `ReservedIPManager` class with business logic
- **`controller.py`**: High-level orchestration methods
- **`cli.py`**: Command-line interface integration

## Examples Directory

Example configurations are provided:
- `example_list_reserved_ips.json`
- `example_create_reserved_ip.json`
- `example_get_reserved_ip.json`
- `example_update_reserved_ip.json`
- `example_delete_reserved_ip.json`

## Notes

- The Reserved IP ID is returned when creating a new reserved IP
- Use `list_reserved_ips` to find the ID of an existing reserved IP
- Deleting a reserved IP is permanent and cannot be undone
- MAC addresses are optional but recommended for better tracking
- Comments help document the purpose of each reserved IP

## Troubleshooting

**Reserved IP not found:**
- Verify the IP exists using `list_reserved_ips`
- Check the reserved IP ID is correct

**Cannot create reserved IP:**
- Ensure IP address is valid and within a managed subnet
- Check that the IP is not already assigned or reserved
- Verify subnet ID exists in MAAS

**Permission denied:**
- Ensure your API key has sufficient permissions
- Check MAAS user roles and access rights
