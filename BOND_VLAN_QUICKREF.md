# Bond and VLAN Actions - Quick Reference

## Three Actions for Complete Control

### 1. `create_bond` - Create Bond Interface

**Purpose:** Create a bond from specified physical interfaces

**Configuration Structure:**
```json
{
  "actions": ["create_bond"],
  "machines": [{
    "hostname": "server.example.com",
    "bonds": [...]
  }]
}
```

**Bond Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | Yes | - | Bond name (e.g., "bond0") |
| `interfaces` | array | Yes | - | Interface names (e.g., ["eth0", "eth1"]) |
| `mode` | string | No | "802.3ad" | Bond mode |
| `mtu` | int | No | 1500 | MTU size |
| `lacp_rate` | string | No | "fast" | LACP rate ("fast"/"slow") |
| `xmit_hash_policy` | string | No | "layer3+4" | Hash policy |

**Example:**
```json
{
  "name": "bond0",
  "interfaces": ["eth0", "eth1"],
  "mode": "802.3ad",
  "mtu": 9000,
  "lacp_rate": "fast",
  "xmit_hash_policy": "layer3+4"
}
```

---

### 2. `add_vlan_to_bond` - Add VLAN Interfaces

**Purpose:** Add VLAN interface(s) to an existing bond

**Configuration Structure:**
```json
{
  "actions": ["add_vlan_to_bond"],
  "machines": [{
    "hostname": "server.example.com",
    "vlan_configs": [...]
  }]
}
```

**VLAN Config Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `bond_name` | string | Yes | Existing bond name (e.g., "bond0") |
| `vlan_ids` | int or array | Yes | VLAN ID(s) - single int or list |

**Examples:**

Single VLAN:
```json
{
  "bond_name": "bond0",
  "vlan_ids": 100
}
```

Multiple VLANs:
```json
{
  "bond_name": "bond0",
  "vlan_ids": [100, 200, 300]
}
```

**Output:** Creates interfaces named `<bond_name>.<vlan_id>` (e.g., "bond0.100")

---

### 3. `update_interface` - Configure VLAN Interfaces

**Purpose:** Configure subnet, IP, and properties for VLAN interfaces

**Configuration Structure:**
```json
{
  "actions": ["update_interface"],
  "machines": [{
    "hostname": "server.example.com",
    "update_interfaces": [...]
  }]
}
```

**Interface Update Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Interface name (e.g., "bond0.100") |
| `vlan` | int | No | VLAN ID to connect to |
| `subnet` | string | No | Subnet name or CIDR |
| `ip_mode` | string | No | "static", "dhcp", or "automatic" |
| `ip_address` | string | No | Static IP (required for "static" mode) |
| `mtu` | int | No | MTU size |

**Example:**
```json
{
  "name": "bond0.100",
  "vlan": 100,
  "subnet": "Production_Network",
  "ip_mode": "static",
  "ip_address": "10.0.100.10",
  "mtu": 9000
}
```

---

## Common Workflows

### Minimal: Bond + Single VLAN + IP

```json
{
  "actions": ["create_bond", "add_vlan_to_bond", "update_interface"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "interfaces": ["eth0", "eth1"],
      "mode": "802.3ad"
    }],
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": 100
    }],
    "update_interfaces": [{
      "name": "bond0.100",
      "subnet": "10.0.100.0/24",
      "ip_mode": "static",
      "ip_address": "10.0.100.10"
    }]
  }]
}
```

### Production: Bond + Multiple VLANs + IPs

```json
{
  "actions": ["create_bond", "add_vlan_to_bond", "update_interface"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "interfaces": ["eth0", "eth1"],
      "mode": "802.3ad",
      "mtu": 9000
    }],
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [100, 200, 300]
    }],
    "update_interfaces": [
      {
        "name": "bond0.100",
        "subnet": "Production_Network",
        "ip_mode": "static",
        "ip_address": "10.0.100.10"
      },
      {
        "name": "bond0.200",
        "subnet": "Storage_Network",
        "ip_mode": "static",
        "ip_address": "10.0.200.10"
      },
      {
        "name": "bond0.300",
        "subnet": "Management_Network",
        "ip_mode": "static",
        "ip_address": "10.0.300.10"
      }
    ]
  }]
}
```

### Incremental: Add VLANs to Existing Bond

```json
{
  "actions": ["add_vlan_to_bond", "update_interface"],
  "machines": [{
    "hostname": "server01",
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [400, 500]
    }],
    "update_interfaces": [
      {
        "name": "bond0.400",
        "subnet": "NewNetwork1",
        "ip_mode": "static",
        "ip_address": "10.0.400.10"
      },
      {
        "name": "bond0.500",
        "subnet": "NewNetwork2",
        "ip_mode": "static",
        "ip_address": "10.0.500.10"
      }
    ]
  }]
}
```

---

## Execution Order

**Correct sequence:**
1. `commission` - Machine must be in READY state
2. `create_bond` - Creates bond interface
3. `add_vlan_to_bond` - Adds VLAN interfaces to bond
4. `update_interface` - Configures IP addresses
5. `deploy` - Deploy OS

**Example command:**
```bash
maas-automation -i config.json
```

---

## Bond Modes Reference

| Mode | Description | Use Case |
|------|-------------|----------|
| `802.3ad` | LACP (IEEE 802.3ad) | Best performance, requires switch support |
| `active-backup` | Active-backup failover | High availability, no switch config needed |
| `balance-rr` | Round-robin | Load balancing, simple setup |
| `balance-xor` | XOR hash selection | Load balancing with consistency |
| `balance-tlb` | Adaptive TX load balancing | Outbound load balancing |
| `balance-alb` | Adaptive load balancing | Full load balancing |

**Recommended:** `802.3ad` with LACP for production environments

---

## Quick Comparison: New vs Legacy

### New Approach (Separate Actions)
✅ Explicit interface specification  
✅ Create bond and VLANs independently  
✅ Add VLANs to existing bonds  
✅ Clear, modular workflow  
✅ Better error handling  

```json
{
  "actions": ["create_bond", "add_vlan_to_bond"],
  "bonds": [{"name": "bond0", "interfaces": ["eth0", "eth1"]}],
  "vlan_configs": [{"bond_name": "bond0", "vlan_ids": [100, 200]}]
}
```

### Legacy Approach (Combined Action)
✅ Automatic interface discovery by VLAN  
✅ Single-step operation  
✅ Backward compatible  

```json
{
  "actions": ["set_network_bond"],
  "bonds": [{"name": "bond0", "vlan_id": [100, 200]}]
}
```

---

## Troubleshooting

### "Interface 'eth0' not found"
→ Check interface names: `maas-automation -i config.json -a list_machine_network`

### "Bond 'bond0' already exists"
→ Skip `create_bond` or use different name

### "VLAN with VID 100 not found in MAAS"
→ Create VLAN in MAAS web UI first

### "Interface 'bond0.100' not found"
→ Run `add_vlan_to_bond` before `update_interface`

---

## See Also

- [BOND_VLAN_SEPARATE_GUIDE.md](BOND_VLAN_SEPARATE_GUIDE.md) - Detailed guide
- [example_create_bond.json](example_create_bond.json)
- [example_add_vlan_to_bond.json](example_add_vlan_to_bond.json)
- [example_complete_bond_vlan_separate.json](example_complete_bond_vlan_separate.json)
