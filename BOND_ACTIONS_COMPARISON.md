# Bond Actions Comparison

## Overview of Bond-Related Actions

There are three actions for creating and managing bonds in MAAS:

### 1. `create_bond` ⭐ **RECOMMENDED**
**Purpose:** Create a bond with full control - either explicit or auto-discovery

**Key Features:**
- ✅ Supports **explicit interface names** (`interfaces` list)
- ✅ Supports **auto-discovery by VLAN** (`vlan_id`)
- ✅ Only creates the bond (no VLAN interfaces on top)
- ✅ Full control over bond parameters
- ✅ Clean separation of concerns

**When to use:**
- When you want to create just the bond
- When you need explicit control over which interfaces to bond
- When you want to auto-discover interfaces by VLAN
- When you'll add VLAN interfaces separately using `add_vlan_to_bond`

**Example (Explicit mode):**
```json
{
  "actions": ["create_bond"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "interfaces": ["eth0", "eth1"],
      "mode": "802.3ad"
    }]
  }]
}
```

**Example (Auto-discovery mode):**
```json
{
  "actions": ["create_bond"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "vlan_id": 100,
      "mode": "802.3ad"
    }]
  }]
}
```

---

### 2. `add_vlan_to_bond`
**Purpose:** Add VLAN tagged interfaces to an existing bond

**Key Features:**
- ✅ Bond must already exist
- ✅ Creates VLAN interfaces (e.g., bond0.100, bond0.200)
- ✅ Supports single or multiple VLANs
- ✅ Clean, explicit approach

**When to use:**
- After creating a bond with `create_bond`
- When you want to add VLAN tagging to an existing bond

**Example:**
```json
{
  "actions": ["add_vlan_to_bond"],
  "machines": [{
    "hostname": "server01",
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [100, 200, 300]
    }]
  }]
}
```

---

### 3. `set_network_bond` ⚠️ **LEGACY**
**Purpose:** Auto-discover interfaces by VLAN and create bond + VLAN interfaces in one step

**Key Features:**
- ⚠️ Marked as legacy
- Auto-discovers interfaces by VLAN ID
- Creates bond AND VLAN interfaces in single action
- Less predictable when VLAN topology is complex

**When to use:**
- Legacy workflows that already use it
- When migrating from older automation

**Example:**
```json
{
  "actions": ["set_network_bond"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "vlan_id": [100, 200],
      "mode": "802.3ad"
    }]
  }]
}
```

---

## Recommended Workflow

### Modern Approach (Recommended)

```json
{
  "actions": ["create_bond", "add_vlan_to_bond"],
  "machines": [{
    "hostname": "server01",
    "bonds": [{
      "name": "bond0",
      "vlan_id": 100,           // Auto-discover interfaces with VLAN 100
      "mode": "802.3ad"
    }],
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [100, 200, 300]  // Add VLAN interfaces
    }]
  }]
}
```

**Benefits:**
1. Clear separation: bond creation vs VLAN configuration
2. Easier troubleshooting
3. More flexible
4. Better logging at each step

---

## Quick Reference

| Action | Creates Bond | Creates VLANs | Auto-Discovery | Explicit Interfaces | Status |
|--------|--------------|---------------|----------------|---------------------|--------|
| `create_bond` | ✅ | ❌ | ✅ | ✅ | **Recommended** |
| `add_vlan_to_bond` | ❌ | ✅ | ❌ | N/A | **Recommended** |
| `set_network_bond` | ✅ | ✅ | ✅ | ❌ | Legacy |

---

## Migration Guide

### From `set_network_bond` to modern approach:

**Old (Legacy):**
```json
{
  "actions": ["set_network_bond"],
  "machines": [{
    "bonds": [{
      "name": "bond0",
      "vlan_id": [100, 200],
      "mode": "802.3ad"
    }]
  }]
}
```

**New (Recommended):**
```json
{
  "actions": ["create_bond", "add_vlan_to_bond"],
  "machines": [{
    "bonds": [{
      "name": "bond0",
      "vlan_id": 100,
      "mode": "802.3ad"
    }],
    "vlan_configs": [{
      "bond_name": "bond0",
      "vlan_ids": [100, 200]
    }]
  }]
}
```
