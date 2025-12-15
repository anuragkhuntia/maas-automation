# Quick Start Guide

## Multiple Ways to Run

### 1. Using the installed command (recommended)
```bash
maas-automation -i config.json
maas-automation -i config.json -v  # verbose
```

### 2. Using Python module
```bash
python3 -m maas_automation.cli -i config.json
```

### 3. Using standalone script
```bash
python3 maas_automation.py -i config.json
```

### 4. Direct execution (after chmod +x)
```bash
./maas_automation.py -i config.json
```

## Target Specific Hosts

### Run action on specific host(s)
```bash
# Commission only TESTPOD1
python3 maas_automation.py -i config.json -a commission --hosts TESTPOD1

# Deploy two specific hosts
python3 maas_automation.py -i config.json -a deploy --hosts TESTPOD1,WZP293393H8

# Release single host
python3 maas_automation.py -i config.json -a release --hosts WZP293393H8
```

### Run on all hosts in config
```bash
python3 maas_automation.py -i config.json -a commission --hosts all
# or just omit --hosts to use all machines in config
python3 maas_automation.py -i config.json -a commission
```

## Config Format (Multiple Machines)

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
    },
    {
      "hostname": "node02",
      "pxe_mac": "11:22:33:44:55:66",
      "power_type": "ipmi",
      "power_parameters": {
        "power_address": "10.0.0.101",
        "power_user": "root",
        "power_pass": "password"
      },
      "distro_series": "jammy"
    }
  ]
}
```

## Common Actions

### List all machines
```json
{"actions": ["list"]}
```

### Commission multiple machines
```json
{
  "actions": ["commission"],
  "machines": [{"hostname": "node01"}, {"hostname": "node02"}]
}
```

### Deploy multiple machines
```json
{
  "actions": ["deploy"],
  "machines": [
    {"hostname": "node01", "distro_series": "jammy"},
    {"hostname": "node02", "distro_series": "focal"}
  ]
}
```

### Release multiple machines
```json
{
  "actions": ["release"],
  "machines": [{"hostname": "node01"}, {"hostname": "node02"}],
  "release": {"wipe_disks": true}
}
```

### Full workflow (create → commission → deploy)
```json
{
  "actions": ["create_machine", "set_power", "configure_storage", "commission", "deploy"],
  "machines": [...],
  "storage": {...}
}
```

## Real-World Examples

### Example 1: List all machines in MAAS
```bash
python3 maas_automation.py -i config.json -a list
```

### Example 2: Commission just TESTPOD1
```bash
python3 maas_automation.py -i config.json -a commission --hosts TESTPOD1
```

### Example 3: Deploy specific machine with verbose logging
```bash
python3 maas_automation.py -i config.json -a deploy --hosts WZP293393H8 -v
```

### Example 4: Release and wipe both machines
```bash
python3 maas_automation.py -i config.json -a release --hosts TESTPOD1,WZP293393H8
```

### Example 5: Full workflow for one machine
```bash
# Edit config.json to set actions: ["create_machine", "commission", "deploy"]
python3 maas_automation.py -i config.json --hosts TESTPOD1
```

### Example 6: Override action but use config settings
```bash
# Config has storage/power settings, but override to just commission
python3 maas_automation.py -i config.json -a commission --hosts all
```

## Notes

- The SDK processes machines sequentially (one at a time)
- Each machine waits for operations to complete before moving to next
- Errors on one machine don't stop processing of remaining machines
- Progress is logged in real-time for each machine
- Use `-a/--action` to override config actions at runtime
- Use `--hosts` to target specific machines by hostname
