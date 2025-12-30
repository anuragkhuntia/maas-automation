# Bond and VLAN Configuration Guide

This guide explains how to create bonds and add VLANs using the new separate actions.

## Overview

The MAAS Automation SDK provides two approaches for bond and VLAN configuration:

### New Approach (Recommended): Separate Actions
- **`create_bond`**: Create a bond from specified interfaces
- **`add_vlan_to_bond`**: Add VLAN interface(s) to an existing bond
- **`update_interface`**: Configure subnet and IP for VLAN interfaces

### Legacy Approach: Combined Action
- **`set_network_bond`**: Automatically finds interfaces by VLAN and creates bond

## When to Use Each Approach

### Use Separate Actions When:
- You want explicit control over which interfaces are bonded
- You need to create the bond first, then add VLANs later
- You want to reuse a bond for multiple VLANs
- You need maximum flexibility and clarity

### Use Legacy Action When:
- You want automatic interface discovery by VLAN ID
- You need backward compatibility with existing configurations
- You prefer a single-step operation

## Separate Actions Workflow

### Step 1: Create Bond (`create_bond`)

Creates a bond interface from specified physical interfaces.

**Configuration:**
```json
{
  "actions": ["create_bond"],
  "machines": [{
    "hostname": "server01.example.com",
    "bonds": [{
      "name": "bond0",
      "interfaces": ["eth0", "eth1"],
      "mode": "802.3ad",
      "mtu": 9000,
      "lacp_rate": "fast",
      "xmit_hash_policy": "layer3+4"
    }]
  }]
}
```

**Parameters:**
- `name`: Bond interface name (e.g., "bond0", "bond1")
- `interfaces`: List of interface names to bond (e.g., ["eth0", "eth1"])
- `mode`: Bond mode (default: "802.3ad")
  - `802.3ad`: LACP (requires switch support)
  - `active-backup`: Active-backup for fault tolerance
  - `balance-rr`: Round-robin load balancing
  - `balance-xor`: XOR hash-based selection
- `mtu`: MTU size (default: 1500, recommend 9000 for jumbo frames)
- `lacp_rate`: LACP rate for 802.3ad mode (default: "fast")
  - `fast`: Request partner to transmit LACPDUs every second
  - `slow`: Request partner to transmit LACPDUs every 30 seconds
- `xmit_hash_policy`: Hash policy for 802.3ad (default: "layer3+4")
  - `layer2`: MAC addresses
  - `layer2+3`: MAC + IP addresses
  - `layer3+4`: IP addresses + ports (recommended)

### Step 2: Add VLANs to Bond (`add_vlan_to_bond`)

Adds one or more VLAN interfaces to an existing bond.

**Single VLAN:**
```json
{
  "actions": ["add_vlan_to_bond"],
  "machines": [{
    "hostname": "server01.example.com",
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": 100
    }]
  }]
}
```

**Multiple VLANs:**
```json
{
  "actions": ["add_vlan_to_bond"],
  "machines": [{
    "hostname": "server01.example.com",
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [100, 200, 300]
    }]
  }]
}
```

**Parameters:**
- `bond_name`: Name of existing bond (e.g., "bond0")
- `vlan_ids`: Single VLAN ID (int) or list of VLAN IDs

**Important Notes:**
- The bond must already exist (use `create_bond` first)
- VLANs must exist in MAAS (create via web UI if needed)
- VLAN interface names will be `<bond_name>.<vlan_id>` (e.g., "bond0.100")

### Step 3: Configure VLAN Interfaces (`update_interface`)

Configure subnet, IP address, and other properties for VLAN interfaces.

```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01.example.com",
    "update_interfaces": [
      {
        "name": "bond0.100",
        "vlan": 100,
        "subnet": "Production_Network",
        "ip_mode": "static",
        "ip_address": "10.0.100.10",
        "mtu": 9000
      },
      {
        "name": "bond0.200",
        "vlan": 200,
        "subnet": "Storage_Network",
        "ip_mode": "static",
        "ip_address": "10.0.200.10",
        "mtu": 9000
      }
    ]
  }]
}
```

**Parameters:**
- `name`: VLAN interface name (e.g., "bond0.100")
- `vlan`: VLAN ID to connect to
- `subnet`: Subnet name or CIDR
- `ip_mode`: IP assignment mode
  - `static`: Static IP (requires `ip_address`)
  - `dhcp`: DHCP assignment
  - `automatic`: MAAS auto-assignment
- `ip_address`: Static IP address (required for static mode)
- `mtu`: MTU size (optional)

## Complete Example

This example shows the full workflow using separate actions:

**File: `complete_workflow.json`**
```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": [
    "commission",
    "create_bond",
    "add_vlan_to_bond",
    "update_interface",
    "deploy"
  ],
  "machines": [{
    "hostname": "server01.example.com",
    "bonds": [{
      "name": "bond0",
      "interfaces": ["eth0", "eth1"],
      "mode": "802.3ad",
      "mtu": 9000,
      "lacp_rate": "fast",
      "xmit_hash_policy": "layer3+4"
    }],
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [100, 200, 300]
    }],
    "update_interfaces": [
      {
        "name": "bond0.100",
        "vlan": 100,
        "subnet": "Production_Network",
        "ip_mode": "static",
        "ip_address": "10.0.100.10",
        "mtu": 9000
      },
      {
        "name": "bond0.200",
        "vlan": 200,
        "subnet": "Storage_Network",
        "ip_mode": "static",
        "ip_address": "10.0.200.10",
        "mtu": 9000
      },
      {
        "name": "bond0.300",
        "vlan": 300,
        "subnet": "Management_Network",
        "ip_mode": "static",
        "ip_address": "10.0.300.10",
        "mtu": 9000
      }
    ],
    "distro_series": "jammy"
  }]
}
```

**Run the workflow:**
```bash
maas-automation -i complete_workflow.json
```

## Example Scenarios

### Scenario 1: Simple Bond with One VLAN

Create a bond and add a single VLAN:

```bash
# Step 1: Create bond
maas-automation -i config.json -a create_bond

# Step 2: Add VLAN
maas-automation -i config.json -a add_vlan_to_bond

# Step 3: Configure IP
maas-automation -i config.json -a update_interface
```

### Scenario 2: High-Availability Setup

Create active-backup bond for redundancy:

```json
{
  "bonds": [{
    "name": "bond0",
    "interfaces": ["eth0", "eth1"],
    "mode": "active-backup",
    "mtu": 1500
  }],
  "vlan_configs": [{
    "bond_name": "bond0",
    "vlan_ids": 100
  }]
}
```

### Scenario 3: Multi-VLAN Production Server

Create bond with multiple VLANs for different networks:

```json
{
  "bonds": [{
    "name": "prov_bond",
    "interfaces": ["enp1s0f0", "enp1s0f1"],
    "mode": "802.3ad",
    "mtu": 9000
  }],
  "vlan_configs": [{
    "bond_name": "prov_bond",
    "vlan_ids": [1551, 1552, 1553]
  }]
}
```

### Scenario 4: Incremental VLAN Addition

Add VLANs to an existing bond without recreating it:

```json
{
  "actions": ["add_vlan_to_bond"],
  "machines": [{
    "hostname": "server01.example.com",
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [400, 500]
    }]
  }]
}
```

## Troubleshooting

### Bond Creation Fails

**Problem:** "Interface 'eth0' not found"
- **Solution:** Check interface names using `list_machine_network` action
- Interfaces must exist and be in correct state

**Problem:** "Bond 'bond0' already exists"
- **Solution:** Use different bond name or skip `create_bond` action

### VLAN Addition Fails

**Problem:** "VLAN with VID 100 not found in MAAS"
- **Solution:** Create VLAN in MAAS web UI first
- Go to: Subnets → VLANs → Add VLAN

**Problem:** "Bond 'bond0' not found"
- **Solution:** Create bond first using `create_bond` action

### Interface Update Fails

**Problem:** "Interface 'bond0.100' not found"
- **Solution:** Add VLAN to bond first using `add_vlan_to_bond`
- Check interface name format: `<bond_name>.<vlan_id>`

## Best Practices

1. **Always commission first**: Network configuration requires machine in READY state
2. **Create bonds before VLANs**: Use `create_bond` before `add_vlan_to_bond`
3. **Use jumbo frames**: Set `mtu: 9000` for better performance in data center networks
4. **Use 802.3ad with LACP fast**: Best performance and failover for supported switches
5. **Name bonds descriptively**: Use names like "prov_bond", "storage_bond"
6. **Document VLAN IDs**: Keep track of which VLAN serves which purpose
7. **Test incrementally**: Create bond, add one VLAN, test, then add more

## Migration from Legacy Action

If you're using the legacy `set_network_bond` action:

**Old configuration:**
```json
{
  "actions": ["set_network_bond"],
  "bonds": [{
    "name": "bond0",
    "vlan_id": [100, 200],
    "mode": "802.3ad"
  }]
}
```

**New configuration:**
```json
{
  "actions": ["create_bond", "add_vlan_to_bond"],
  "bonds": [{
    "name": "bond0",
    "interfaces": ["eth0", "eth1"],
    "mode": "802.3ad"
  }],
  "vlan_configs": [{
    "bond_name": "bond0",
    "vlan_ids": [100, 200]
  }]
}
```

## See Also

- [example_create_bond.json](example_create_bond.json) - Bond creation examples
- [example_add_vlan_to_bond.json](example_add_vlan_to_bond.json) - VLAN addition examples
- [example_complete_bond_vlan_separate.json](example_complete_bond_vlan_separate.json) - Complete workflow
- [UPDATE_INTERFACE_GUIDE.md](UPDATE_INTERFACE_GUIDE.md) - Interface configuration guide
- [MULTI_VLAN_BOND_GUIDE.md](MULTI_VLAN_BOND_GUIDE.md) - Legacy multi-VLAN guide
