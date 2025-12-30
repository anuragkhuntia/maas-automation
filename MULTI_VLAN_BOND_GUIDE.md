# Multi-VLAN Bond Configuration Guide

## Overview

The MAAS automation toolkit now supports creating bonds with multiple VLAN tags. This allows you to:
- Create a single bond from physical interfaces
- Tag the bond with multiple VLANs
- Configure each VLAN interface with different subnets and IP settings

## Configuration Format

### Single VLAN (Original)
```json
{
  "name": "bond0",
  "vlan_id": 1234,
  "mode": "802.3ad"
}
```
**Result:** Creates `bond0` and VLAN interface `bond0_1234`

### Multiple VLANs (New)
```json
{
  "name": "prov_bond",
  "vlan_id": [1234, 1235, 1236],
  "mode": "active-backup"
}
```
**Result:** Creates `prov_bond` and VLAN interfaces:
- `prov_bond_1234`
- `prov_bond_1235`
- `prov_bond_1236`

## Complete Example

```json
{
  "actions": ["set_network_bond", "update_interface"],
  "machines": [{
    "hostname": "storage",
    
    "bonds": [
      {
        "name": "prov_bond",
        "vlan_id": [1234, 1235],
        "mode": "active-backup",
        "mtu": 9000
      }
    ],
    
    "update_interfaces": [
      {
        "name": "prov_bond_1234",
        "vlan": 1234,
        "subnet": "prov",
        "ip_mode": "dhcp"
      },
      {
        "name": "prov_bond_1235",
        "vlan": 1235,
        "subnet": "backup",
        "ip_mode": "dhcp"
      }
    ]
  }]
}
```

## How It Works

### Step 1: Bond Creation
```json
"bonds": [{
  "name": "prov_bond",
  "vlan_id": [1234, 1235]
}]
```

1. Finds physical interfaces with primary VLAN (1234)
2. Creates bond `prov_bond` from those interfaces
3. Creates VLAN interface `prov_bond_1234` (VLAN 1234)
4. Creates VLAN interface `prov_bond_1235` (VLAN 1235)

### Step 2: VLAN Interface Configuration
```json
"update_interfaces": [
  {
    "name": "prov_bond_1234",
    "subnet": "prov",
    "ip_mode": "dhcp"
  },
  {
    "name": "prov_bond_1235",
    "subnet": "backup",
    "ip_mode": "static",
    "ip_address": "10.0.0.100"
  }
]
```

Each VLAN interface can have:
- Different subnets
- Different IP modes (static, dhcp, automatic)
- Different static IPs
- Different MTU settings

## Use Cases

### 1. Provisioning + Backup Networks
```json
{
  "name": "prov_bond",
  "vlan_id": [1234, 1235],
  "mode": "active-backup"
}
```
- VLAN 1234: Provisioning network
- VLAN 1235: Backup network

### 2. Multiple Data Networks
```json
{
  "name": "data_bond",
  "vlan_id": [2000, 2001, 2002],
  "mode": "802.3ad"
}
```
- VLAN 2000: Primary data
- VLAN 2001: Replication
- VLAN 2002: Management

### 3. Storage Multi-Pathing
```json
{
  "name": "storage_bond",
  "vlan_id": [3000, 3001],
  "mode": "balance-rr"
}
```
- VLAN 3000: iSCSI path A
- VLAN 3001: iSCSI path B

## Interface Naming Convention

MAAS automatically names VLAN interfaces:

**Pattern:** `<bond_name>_<vlan_id>`

**Examples:**
- Bond: `prov_bond`, VLAN: 1234 → `prov_bond_1234`
- Bond: `data_bond`, VLAN: 2345 → `data_bond_2345`
- Bond: `mgmt`, VLAN: 100 → `mgmt_100`

## Bond Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `active-backup` | One active, one standby | Simple failover |
| `802.3ad` | LACP aggregation | Load balancing + failover (requires switch config) |
| `balance-rr` | Round-robin | Load balancing |
| `balance-xor` | XOR hash-based | Load balancing |
| `balance-alb` | Adaptive load balancing | Load balancing without switch config |

## IP Assignment Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| `static` | Fixed IP address | Servers, infrastructure |
| `dhcp` | DHCP from subnet | Dynamic workloads |
| `automatic` | MAAS assigns from subnet pool | Auto-provisioning |

## Configuration Tips

### 1. Primary VLAN Selection
When using multiple VLANs, the **first VLAN** in the array is used to find physical interfaces:

```json
"vlan_id": [1234, 1235, 1236]
           ^^^^^ Primary - used to find interfaces
```

Ensure this VLAN is visible on the physical interfaces you want to bond.

### 2. Subnet Configuration
Link each VLAN interface to appropriate subnet:

```json
"update_interfaces": [
  {"name": "prov_bond_1234", "subnet": "provisioning"},
  {"name": "prov_bond_1235", "subnet": "backup"}
]
```

### 3. MTU Settings
Set consistent MTU across bond and VLAN interfaces:

```json
"bonds": [{
  "name": "prov_bond",
  "vlan_id": [1234, 1235],
  "mtu": 9000
}],
"update_interfaces": [
  {"name": "prov_bond_1234", "mtu": 9000},
  {"name": "prov_bond_1235", "mtu": 9000}
]
```

### 4. Mixed IP Modes
Different VLANs can use different IP assignment:

```json
"update_interfaces": [
  {
    "name": "prov_bond_1234",
    "ip_mode": "static",
    "ip_address": "10.0.0.100"
  },
  {
    "name": "prov_bond_1235",
    "ip_mode": "dhcp"
  }
]
```

## Troubleshooting

### Interface Not Found
**Error:** `Interface 'prov_bond_1234' not found`

**Solution:** 
- Verify bond was created successfully
- Check VLAN interface was created
- Use correct naming: `<bond_name>_<vlan_id>`

### VLAN Not Found
**Error:** `VLAN with VID 1234 not found in MAAS`

**Solution:**
- Create VLANs in MAAS first
- Check VLAN IDs are correct
- Verify VLANs exist in correct fabric

### Insufficient Interfaces
**Error:** `Found only 1 interface(s) with VLAN 1234`

**Solution:**
- Ensure at least 2 physical interfaces have the primary VLAN
- Check VLAN is configured on network switch
- Verify interfaces are connected

### Partial VLAN Creation
**Scenario:** First VLAN succeeds, subsequent VLANs fail

**Behavior:** 
- First VLAN creation is critical - will fail entire operation
- Subsequent VLAN failures are logged but don't stop workflow
- Bond remains usable with successfully created VLANs

## Command Line Usage

```bash
# Create multi-VLAN bonds
python3 maas_automation.py -i example_multi_vlan_bond.json

# With verbose logging
python3 maas_automation.py -i example_multi_vlan_bond.json -v

# Target specific machine
python3 maas_automation.py -i config.json --hosts storage
```

## Full Example Configuration

See [example_multi_vlan_bond.json](example_multi_vlan_bond.json) for complete configuration with:
- Multiple bonds
- Multiple VLANs per bond
- Different bond modes
- Mixed IP assignment modes
- Comprehensive documentation

## Backward Compatibility

✅ **Fully backward compatible**

Old configurations with single VLAN still work:
```json
{"vlan_id": 1234}  // Works
{"vlan_id": [1234]}  // Also works
```

New configurations with multiple VLANs:
```json
{"vlan_id": [1234, 1235, 1236]}  // New feature
```

## See Also

- [UPDATE_INTERFACE_GUIDE.md](UPDATE_INTERFACE_GUIDE.md) - Interface update reference
- [example_multi_vlan_bond.json](example_multi_vlan_bond.json) - Complete example
- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
