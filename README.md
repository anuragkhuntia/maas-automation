# MAAS Automation SDK

Production-ready, modular Python SDK for MAAS automation with state polling and complete lifecycle management.

## Features

- **Machine lifecycle**: create, commission, deploy, release, delete
- **Storage configuration**: Curtin-based storage layout with LVM (EFI + XFS + LVM)
- **State polling**: Automatically waits for operations to complete with configurable timeouts
- **JSON-driven**: Configure entire workflows via JSON
- **Modular**: Clean separation of concerns across managers
- **OAuth PLAINTEXT**: Working authentication for MAAS 3.x

## Installation

```bash
pip install -e .
```

## Quick Start

1. **Edit `example_input.json`** with your MAAS credentials:
```json
{
  "maas_api_url": "http://10.81.31.31:5240/MAAS",
  "maas_api_key": "consumer:token:secret",
  "actions": ["create_machine", "commission", "deploy"],
  "machines": [
    {
      "hostname": "node01",
      "pxe_mac": "aa:bb:cc:dd:ee:ff",
      "power_type": "ipmi",
      "power_parameters": {
        "power_address": "10.0.0.100",
        "power_user": "root",
        "power_pass": "password"
      },
      "distro_series": "jammy"
    }
  ]
}
```

2. **Run the automation** (multiple ways):
```bash
# Using installed command
maas-automation -i example_input.json

# Using Python module
python3 -m maas_automation.cli -i example_input.json

# Using standalone script
python3 maas_automation.py -i example_input.json

# With infinite retries (never give up on failures)
maas-automation -i example_input.json --max-retries 0

# Target specific machines
maas-automation -i example_input.json --hosts node01,node02

# Override action from CLI
maas-automation -i example_input.json -a commission --hosts node01
```

## Use Cases

### 1. Full Provisioning (Create → Commission → Deploy)
```json
{
  "actions": ["create_machine", "set_power", "configure_storage", "commission", "deploy"]
}
```
- Creates/finds machine in MAAS
- Configures IPMI power control
- Applies custom storage layout (EFI + LVM with XFS)
- Commissions machine (waits for completion)
- Deploys OS (waits for completion)

### 2. Re-provision Existing Machine
```json
{
  "actions": ["release", "configure_storage", "commission", "deploy"]
}
```
- Releases machine and wipes disks
- Reconfigures storage
- Commissions and deploys fresh

### 3. Cleanup (Release → Delete)
```json
{
  "actions": ["release", "delete"]
}
```
- Releases machine with disk wipe
- Removes machine from MAAS

### 4. Commission Only (for testing)
```json
{
  "actions": ["commission"],
  "machines": [{"hostname": "existing-node"}]
}
```
- Just runs commissioning on existing machine
- Waits for completion and reports status

### 5. Process Multiple Machines
```json
{
  "actions": ["commission", "deploy"],
  "machines": [
    {"hostname": "node01", "distro_series": "jammy"},
    {"hostname": "node02", "distro_series": "focal"}
  ]
}
```
- Processes machines sequentially
- Each machine completes before moving to next
- Errors on one machine don't stop others

## Available Actions

Actions run in the order specified:

- `list`: List all machines in MAAS (ignores machines array)
- `create_machine` / `find_machine`: Find by hostname/MAC/BMC-IP or create new
- `set_power`: Configure IPMI/power parameters
- `set_bios`: Store BIOS settings (metadata only)
- `set_boot_order`: Configure boot device order
- `configure_storage`: Apply Curtin storage layout (before commissioning)
- `commission`: Commission machine with optional scripts
- `create_bond`: Create bond from specified interfaces (after commission, before deploy)
- `add_vlan_to_bond`: Add VLAN interface(s) to existing bond (after commission, before deploy)
- `set_network_bond`: Create bonds from VLAN interfaces (legacy, after commission, before deploy)
- `update_interface`: Update interface properties, VLAN, subnet (after commission, before deploy)
- `deploy`: Deploy operating system
- `release`: Release machine and wipe disks
- `delete`: Remove machine from MAAS

### Network Actions

**`create_bond`**: Creates a bond from physical interfaces - supports explicit and auto-discovery modes
- **Explicit mode**: Specify exact interface names (e.g., ["eth0", "eth1"])
- **Auto-discovery mode**: Provide VLAN ID to auto-find interfaces with that VLAN
- **✨ Auto-configures subnet** when using VLAN ID mode
- Configure bond mode (802.3ad, active-backup, etc.)
- Set MTU, LACP rate, and hash policy
- See example: `example_create_bond.json`
- See comparison: `BOND_ACTIONS_COMPARISON.md`

**`add_vlan_to_bond`**: Adds VLAN interface(s) to an existing bond
- Specify bond name and VLAN ID(s) to add
- **✨ Auto-configures subnet** for each VLAN interface
- Supports single VLAN or multiple VLANs
- Bond must already exist (use `create_bond` first)
- See example: `example_add_vlan_to_bond.json`

**Complete workflow**: See `example_bond_vlan_with_subnet.json` for bond + multi-VLAN + auto-subnet

**`set_network_bond`**: Creates network bonds from interfaces with matching VLAN IDs (LEGACY)
- Automatically finds physical interfaces with specified VLAN
- Creates bond with specified mode (802.3ad, active-backup, etc.)
- Supports multiple VLANs per bond - `vlan_id: [1234, 1235]`
- Automatically creates VLAN interface for each VLAN tag
- ⚠️ **Legacy action** - Use `create_bond` + `add_vlan_to_bond` for new workflows
- See examples: `example_bond_vlan_workflow.json`, `example_multi_vlan_bond.json`
- See guide: [MULTI_VLAN_BOND_GUIDE.md](MULTI_VLAN_BOND_GUIDE.md)

**`update_interface`**: Updates interface properties using MAAS PUT API
- Configure VLAN on bond or physical interfaces
- Link interfaces to subnets with static/DHCP IP assignment
- Update bond parameters (mode, LACP rate, hash policy)
- Modify bridge settings (STP, forward delay)
- Change physical properties (MTU, MAC address, link speed)
- **Key use case**: Configure VLAN on bond after creation
- See guide: [UPDATE_INTERFACE_GUIDE.md](UPDATE_INTERFACE_GUIDE.md)

## Storage Layout

The SDK creates a production-ready storage layout:

- **Disk 1 Partition 1**: 512MB FAT32 (EFI) → `/boot/efi`
- **Disk 1 Partition 2**: 2GB XFS → `/boot`
- **Disk 1 Partition 3**: Remaining space → LVM PV
  - **vg-main/root**: 50GB XFS → `/`
  - **vg-main/home**: 10GB XFS → `/home`
  - **vg-main/var**: 10GB XFS → `/var`
  - **vg-main/var-log**: 10GB XFS → `/var/log`
  - **vg-main/tmp**: 10GB XFS → `/tmp`

All sizes are configurable via `storage.params` in the JSON config.

## State Polling

The SDK automatically waits for long-running operations:

- **Commission**: Waits up to 20 minutes (configurable)
- **Deploy**: Waits up to 30 minutes (configurable)
- **Release**: Waits up to 30 minutes (configurable)

## Retry Logic

The SDK includes robust retry logic for transient failures:

- **Default**: 5 retries with exponential backoff (1s, 2s, 4s, 8s, 16s...)
- **Infinite mode**: `--max-retries 0` retries forever until success
- **Max delay**: Caps at 60 seconds between retries
- **Timeout**: HTTP requests timeout after 120 seconds

Example with infinite retries (recommended for unreliable networks):
```bash
maas-automation -i config.json --max-retries 0
```

This ensures the workflow never breaks on transient API timeouts or network issues.

Progress is logged in real-time. Operations fail fast on error states.

## Network Configuration

The SDK can configure network bonds and interfaces after commissioning (when machine is in READY state):

### Bond Configuration

Create network bonds from multiple interfaces:

```json
{
  "network": {
    "bonds": [
      {
        "name": "bond0",
        "interfaces": ["eth0", "eth1"],
        "mode": "802.3ad",
        "mtu": 9000,
        "lacp_rate": "fast",
        "xmit_hash_policy": "layer3+4"
      }
    ]
  }
}
```

**Supported bond modes:**
- `802.3ad` - LACP (IEEE 802.3ad) - requires switch support
- `active-backup` - Active-backup policy (fault tolerance)
- `balance-rr` - Round-robin policy (load balancing)
- `balance-xor` - XOR policy
- `broadcast` - Broadcast policy
- `balance-tlb` - Adaptive transmit load balancing
- `balance-alb` - Adaptive load balancing

### Interface Configuration

Configure IP addresses, VLANs, and MTU:

```json
{
  "network": {
    "interfaces": [
      {
        "name": "bond0",
        "subnet": "10.0.0.0/24",
        "ip_mode": "static",
        "ip_address": "10.0.0.10",
        "mtu": 9000
      },
      {
        "name": "eth2",
        "subnet": "192.168.1.0/24",
        "ip_mode": "dhcp"
      }
    ]
  }
}
```

**IP modes:**
- `static` - Static IP (requires `ip_address`)
- `dhcp` - DHCP assignment
- `auto` - MAAS auto-assignment from subnet

### Complete Workflow Example

```json
{
  "actions": ["create_machine", "commission", "configure_network", "deploy"],
  "machines": [
    {
      "hostname": "node01",
      "network": {
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
            "ip_address": "10.0.0.10"
          }
        ]
      }
    }
  ]
}
```

**Network configuration must run:**
- ✓ After `commission` (when machine is READY)
- ✓ Before `deploy`

## Configuration Reference

```json
{
  "maas_api_url": "https://maas-server:5240/MAAS",
  "maas_api_key": "consumer:token:secret",
  "actions": ["create_machine", "commission", "deploy"],
  
  "machine": {
    "hostname": "node01",
    "pxe_mac": "aa:bb:cc:dd:ee:ff",
    "power_type": "ipmi",
    "power_parameters": {
      "power_address": "10.0.0.100",
      "power_user": "admin",
      "power_pass": "password"
    },
    "distro_series": "jammy",
    "commissioning_scripts": ["update_firmware"],
    "wait_commissioning": true,
    "commission_timeout": 1200,
    "wait_deployment": true,
    "deploy_timeout": 1800
  },
  
  "storage": {
    "device": "/dev/sda",
    "params": {
      "efi_mb": 512,
      "boot_size_g": 2,
      "root_size_g": 50,
      "home_size_g": 10,
      "var_size_g": 10,
      "var_log_size_g": 10,
      "tmp_size_g": 10
    }
  },
  
  "release": {
    "wipe_disks": true,
    "wait_release": true
  }
}
```

## Module Architecture

```
src/maas_automation/
├── __init__.py          # Package initialization
├── client.py            # MAAS API client with OAuth PLAINTEXT
├── utils.py             # Retry logic and state polling
├── machine.py           # Machine lifecycle (create/commission/deploy/release/delete)
├── storage.py           # Curtin storage layout rendering
├── bios.py              # BIOS settings (metadata)
├── boot.py              # Boot device configuration
├── controller.py        # Orchestration layer
└── cli.py               # Command-line interface
```

## CLI Options

```bash
# Run with config file actions
maas-automation -i config.json

# Override action for specific hosts
maas-automation -i config.json -a commission --hosts node01,node02

# Target single host
maas-automation -i config.json -a deploy --hosts TESTPOD1

# List all machines
maas-automation -i config.json -a list

# Verbose logging
maas-automation -i config.json -v

# Show help
maas-automation --help
```

### Command-Line Arguments

- `-i, --input FILE` - Path to JSON configuration file (required)
- `-a, --action ACTION` - Override action from config (list, commission, deploy, release, delete)
- `--hosts HOSTS` - Target specific machines by hostname (comma-separated or "all")
- `-v, --verbose` - Enable verbose/debug logging
- `--help` - Show help message

## Example Output

```
============================================================
MAAS AUTOMATION SDK
============================================================
API URL: https://<MAAS_URI>:5240/MAAS
Actions: create_machine, commission, deploy

============================================================
STEP: Create/Find Machine
============================================================
2025-12-15 10:30:15 [INFO] Found existing machine: testnode01 (abc123)
Machine system_id: abc123

============================================================
STEP: Commission Machine
============================================================
2025-12-15 10:30:20 [INFO] Starting commissioning for abc123
2025-12-15 10:30:22 [INFO] ✓ Commissioning started
2025-12-15 10:30:22 [INFO] Waiting for commissioning to complete...
2025-12-15 10:30:32 [INFO] State: COMMISSIONING
2025-12-15 10:35:42 [INFO] State: READY
2025-12-15 10:35:42 [INFO] ✓ Commissioning complete: READY

============================================================
STEP: Deploy Machine
============================================================
2025-12-15 10:35:45 [INFO] Starting deployment for abc123
2025-12-15 10:35:47 [INFO] ✓ Deployment started
2025-12-15 10:35:47 [INFO] Waiting for deployment to complete...
2025-12-15 10:35:57 [INFO] State: DEPLOYING
2025-12-15 10:50:12 [INFO] State: DEPLOYED
2025-12-15 10:50:12 [INFO] ✓ Deployment complete: DEPLOYED

============================================================
✓ Workflow complete. Machine system_id: abc123
============================================================
```

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Quick start guide with examples
- [MULTI_VLAN_BOND_GUIDE.md](MULTI_VLAN_BOND_GUIDE.md) - **NEW:** Multi-VLAN bond configuration guide
- [UPDATE_INTERFACE_GUIDE.md](UPDATE_INTERFACE_GUIDE.md) - Complete guide for updating interfaces
- [UPDATE_INTERFACE_QUICKREF.md](UPDATE_INTERFACE_QUICKREF.md) - Quick reference for interface updates
- [RESERVED_IP_GUIDE.md](RESERVED_IP_GUIDE.md) - Reserved IP management guide
- [RESERVED_IP_QUICKREF.md](RESERVED_IP_QUICKREF.md) - Reserved IP quick reference
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Implementation details
- [example_multi_vlan_bond.json](example_multi_vlan_bond.json) - **NEW:** Multi-VLAN bond example
- [example_bond_vlan_workflow.json](example_bond_vlan_workflow.json) - Bond + VLAN configuration example
- [example_update_interface.json](example_update_interface.json) - Interface update example

## Contributing

Contributions welcome! Please ensure:
- Code follows existing style and patterns
- All functions include docstrings
- Error handling is robust
- State polling waits for completion

## License

MIT License
