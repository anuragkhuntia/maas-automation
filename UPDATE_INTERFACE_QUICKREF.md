# Update Interface Quick Reference

## Quick Start

Update an interface (e.g., configure VLAN after bond creation):

```bash
python3 maas_automation.py -i example_update_interface.json
```

## Minimal Configuration

```json
{
  "maas_api_url": "http://your-maas:5240/MAAS",
  "maas_api_key": "consumer:token:secret",
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server01",
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

## Common Use Cases

### Configure VLAN on Bond
```json
{
  "name": "bond0_1551",
  "vlan": 1551,
  "subnet": "UPI_App_Prov",
  "ip_mode": "static",
  "ip_address": "10.83.96.25"
}
```

### Update MTU
```json
{
  "name": "eth0",
  "mtu": 9000
}
```

### Link to DHCP Subnet
```json
{
  "name": "eth1",
  "subnet": "192.168.1.0/24",
  "ip_mode": "dhcp"
}
```

### Update Bond Mode
```json
{
  "name": "bond0",
  "bond_mode": "active-backup",
  "bond_miimon": 100
}
```

## Key Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `name` | Interface name (required) | `"bond0"`, `"eth0"` |
| `vlan` | VLAN ID | `1551` |
| `subnet` | Subnet name or CIDR | `"UPI_App_Prov"` |
| `ip_mode` | IP assignment mode | `"static"`, `"dhcp"`, `"automatic"` |
| `ip_address` | Static IP (with static mode) | `"10.83.96.25"` |
| `mtu` | Maximum transmission unit | `9000` |

## Bond + VLAN Workflow

1. Create bond with VLAN:
```json
{
  "actions": ["set_network_bond"],
  "machines": [{
    "bonds": [{
      "name": "bond0",
      "vlan_id": 1551,
      "mode": "802.3ad"
    }]
  }]
}
```

2. Update VLAN interface (automatically named `bond0_1551`):
```json
{
  "actions": ["update_interface"],
  "machines": [{
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

## Combined Workflow

```json
{
  "actions": ["set_network_bond", "update_interface"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "prov_bond",
      "vlan_id": 1551,
      "mode": "802.3ad"
    }],
    "update_interfaces": [{
      "name": "prov_bond_1551",
      "vlan": 1551,
      "subnet": "UPI_App_Prov",
      "ip_mode": "static",
      "ip_address": "10.83.96.25"
    }]
  }]
}
```

## Tips

- VLAN interface name format: `<bond_name>_<vlan_id>`
- Use same VLAN ID in both bond creation and update
- Subnet can be name or CIDR notation
- Machine must be in Ready/Broken state for full updates
- Deployed machines: only `name` and `mac_address` can be updated

## See Full Documentation

[UPDATE_INTERFACE_GUIDE.md](UPDATE_INTERFACE_GUIDE.md) - Complete guide with all parameters and examples
