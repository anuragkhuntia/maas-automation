# Update Interface Guide

## Overview

The `update_interface` action allows you to update network interface properties in MAAS using the PUT API endpoint. This is particularly useful for:

1. Configuring VLANs on bond interfaces after creation
2. Linking interfaces to subnets with static or DHCP IP assignment
3. Updating bond parameters
4. Modifying bridge settings
5. Changing interface properties like MTU, MAC address, etc.

## API Reference

**Endpoint:** `PUT /MAAS/api/2.0/nodes/{system_id}/interfaces/{id}/`

**Operation ID:** `InterfaceHandler_update`

## Use Cases

### 1. Configure VLAN After Creating Bond

This is the most common workflow - create a bond from physical interfaces, then configure a VLAN on top of it.

```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": ["set_network_bond", "update_interface"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "vlan_id": 1551,
      "mode": "802.3ad",
      "mtu": 1500
    }],
    "update_interfaces": [{
      "name": "bond0_1551",
      "vlan": 1551,
      "subnet": "UPI_App_Prov",
      "ip_mode": "static",
      "ip_address": "10.83.96.25"
    }]
  }]
}
```

**Note:** When you create a bond with VLAN tagging, MAAS creates a VLAN interface named `<bond_name>_<vlan_id>`. This is the interface you update.

### 2. Update Existing Interface Properties

Update properties of an existing interface without changing its VLAN or subnet.

```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01",
    "update_interfaces": [{
      "name": "eth0",
      "mtu": 9000,
      "tags": "production,high-priority",
      "link_connected": true,
      "interface_speed": 10000
    }]
  }]
}
```

### 3. Link Interface to Subnet with DHCP

```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01",
    "update_interfaces": [{
      "name": "eth1",
      "subnet": "192.168.1.0/24",
      "ip_mode": "dhcp"
    }]
  }]
}
```

### 4. Update Bond Parameters

```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01",
    "update_interfaces": [{
      "name": "bond0",
      "bond_mode": "active-backup",
      "bond_miimon": 100,
      "bond_downdelay": 200,
      "bond_updelay": 200
    }]
  }]
}
```

### 5. Update Bridge Interface

```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01",
    "update_interfaces": [{
      "name": "br0",
      "bridge_type": "standard",
      "bridge_stp": true,
      "bridge_fd": 15,
      "mtu": 1500
    }]
  }]
}
```

### 6. Update MAC Address (Deployed Machines)

For deployed machines with broken interfaces, you can update the MAC address:

```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01",
    "update_interfaces": [{
      "name": "eth0",
      "mac_address": "00:11:22:33:44:55"
    }]
  }]
}
```

## Configuration Parameters

### Required Parameters

- **`name`**: Interface name to update (e.g., "bond0", "eth0", "prov_bond_1551")
  - OR **`interface_id`**: Interface ID (if you know it)

### Basic Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name_update` | string | New name for the interface |
| `mac_address` | string | MAC address (updatable for deployed machines) |
| `mtu` | integer | Maximum transmission unit |
| `tags` | string | Comma-separated tags |

### VLAN & Subnet Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `vlan` | integer | VLAN ID to connect interface to |
| `subnet` | string | Subnet name or CIDR to link to |
| `ip_mode` | string | IP assignment: "static", "dhcp", or "automatic" |
| `ip_address` | string | Static IP (required when ip_mode="static") |

### Physical Interface Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `accept_ra` | boolean | Accept router advertisements (IPv6 only) |
| `link_connected` | boolean | Whether physically connected to uplink |
| `interface_speed` | integer | Interface speed in Mbit/s (default: 0) |
| `link_speed` | integer | Link speed in Mbit/s (default: 0) |

### Bond Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `bond_mode` | string | Operating mode: "802.3ad", "active-backup", "balance-rr", etc. |
| `bond_miimon` | integer | Link monitoring frequency in ms (default: 100) |
| `bond_downdelay` | integer | Time to wait before disabling slave (ms) |
| `bond_updelay` | integer | Time to wait before enabling slave (ms) |
| `bond_lacp_rate` | string | "fast" or "slow" (default: "slow") |
| `bond_xmit_hash_policy` | string | Hash policy: "layer2", "layer2+3", "layer3+4", etc. |

### Bridge Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `bridge_type` | string | Type: "standard" or "ovs" |
| `bridge_stp` | boolean | Spanning tree protocol on/off (default: false) |
| `bridge_fd` | integer | Bridge forward delay in seconds (default: 15) |

## Bond Modes

| Mode | Description |
|------|-------------|
| `balance-rr` | Round-robin load balancing and fault tolerance |
| `active-backup` | One active slave, failover to backup |
| `balance-xor` | XOR hash-based load balancing |
| `broadcast` | Transmit on all slaves |
| `802.3ad` | IEEE 802.3ad dynamic link aggregation (LACP) |
| `balance-tlb` | Adaptive transmit load balancing |
| `balance-alb` | Adaptive load balancing (transmit + receive) |

## Machine Status Requirements

- **Ready or Broken**: Full access to all update options
- **Deployed**: Can only update `name` and `mac_address`

This restriction allows replacing faulty hardware on deployed machines without requiring redeployment.

## Complete Workflow Example

Here's a complete example showing bond creation and VLAN configuration:

```json
{
  "maas_api_url": "http://10.0.0.1:5240/MAAS",
  "maas_api_key": "consumer:token:secret",
  "actions": [
    "find_machine",
    "set_network_bond",
    "update_interface"
  ],
  "machines": [
    {
      "hostname": "HYNRBBMPRUFIWAF05.npotech.io",
      "serial": "HYNRBBMPOD2MAAS",
      
      "bonds": [
        {
          "name": "prov_bond",
          "vlan_id": 1551,
          "mode": "802.3ad",
          "mtu": 1500,
          "lacp_rate": "fast",
          "xmit_hash_policy": "layer3+4"
        }
      ],
      
      "update_interfaces": [
        {
          "name": "prov_bond_1551",
          "vlan": 1551,
          "subnet": "UPI_App_Prov",
          "ip_mode": "static",
          "ip_address": "10.83.96.25",
          "mtu": 9000
        }
      ]
    }
  ]
}
```

### Workflow Steps

1. **find_machine**: Locate the machine by hostname or serial number
2. **set_network_bond**: 
   - Finds physical interfaces with VLAN ID 1551
   - Creates bond "prov_bond" with 802.3ad mode
   - MAAS automatically creates VLAN interface "prov_bond_1551"
3. **update_interface**:
   - Updates the VLAN interface "prov_bond_1551"
   - Sets VLAN to 1551
   - Links to subnet "UPI_App_Prov"
   - Assigns static IP 10.83.96.25
   - Sets MTU to 9000

## Command Line Usage

```bash
# Update interface using configuration file
python3 maas_automation.py -i example_update_interface.json

# With verbose logging
python3 maas_automation.py -i example_update_interface.json -v

# Update specific machine
python3 maas_automation.py -i config.json -a update_interface --hosts server01
```

## Troubleshooting

### Interface Not Found

**Error:** `Interface 'bond0_1551' not found on machine`

**Solution:** 
- Verify the interface name by listing machine interfaces first
- Check if VLAN interface was created during bond setup
- Use correct naming pattern: `<bond_name>_<vlan_id>`

### VLAN Not Found

**Error:** `VLAN with VID 1551 not found in MAAS`

**Solution:**
- Create VLAN in MAAS first via web UI or API
- Verify VLAN ID is correct
- Check that VLAN exists in the correct fabric

### Subnet Not Found

**Error:** `Subnet 'UPI_App_Prov' not found`

**Solution:**
- Verify subnet name matches MAAS configuration
- Try using CIDR notation instead (e.g., "10.83.96.0/23")
- List available subnets: use `list_subnets` action

### Cannot Update Deployed Machine

**Error:** `Cannot update interface properties on deployed machine`

**Solution:**
- Only `name` and `mac_address` can be updated on deployed machines
- Release the machine first if you need to make other changes
- Or redeploy after making changes

## Best Practices

1. **Create Bonds Before Updating**: Always create bonds first, then update their VLAN interfaces
2. **Use Consistent Naming**: Follow naming conventions like `<purpose>_bond` for clarity
3. **Verify VLAN Exists**: Ensure VLANs are configured in MAAS before referencing them
4. **Check Machine Status**: Verify machine is in Ready or Broken state for full updates
5. **Use Static IPs for Servers**: Production servers should use static IP assignment
6. **Set Appropriate MTU**: Use jumbo frames (MTU 9000) for storage/backup networks
7. **Test Configuration**: Test on a single machine before applying to multiple machines

## See Also

- [set_network_bond](RESERVED_IP_GUIDE.md) - Create network bonds
- [list_machine_network](QUICKSTART.md) - View machine network configuration
- [list_subnets](QUICKSTART.md) - List available subnets
- [MAAS API Documentation](https://maas.io/docs/api)
