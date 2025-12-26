# Reserved IP Quick Reference

## Quick Commands

### List all reserved IPs
```bash
maas-automation -i config.json -a list_reserved_ips
```

### Create a reserved IP
```bash
# Edit config.json to include:
{
  "actions": ["create_reserved_ip"],
  "reserved_ip": {
    "ip": "192.168.1.100",
    "mac": "00:11:22:33:44:55",
    "subnet": 1,
    "comment": "My reserved IP"
  }
}

maas-automation -i config.json
```

### Get reserved IP details
```bash
# Edit config.json to include:
{
  "actions": ["get_reserved_ip"],
  "reserved_ip_id": 1
}

maas-automation -i config.json
```

### Update a reserved IP
```bash
# Edit config.json to include:
{
  "actions": ["update_reserved_ip"],
  "reserved_ip_id": 1,
  "reserved_ip": {
    "comment": "Updated comment",
    "mac": "00:11:22:33:44:66"
  }
}

maas-automation -i config.json
```

### Delete a reserved IP
```bash
# Edit config.json to include:
{
  "actions": ["delete_reserved_ip"],
  "reserved_ip_id": 1
}

maas-automation -i config.json
```

## Configuration Template

```json
{
  "maas_api_url": "http://your-maas-server:5240/MAAS",
  "maas_api_key": "consumer_key:token_key:secret",
  "actions": ["ACTION_HERE"],
  "reserved_ip_id": 1,
  "reserved_ip": {
    "ip": "192.168.1.100",
    "mac": "00:11:22:33:44:55",
    "subnet": 1,
    "comment": "Description here"
  }
}
```

## Reserved IP Fields

| Field | Required | Description |
|-------|----------|-------------|
| `ip` | Yes (create) | IP address to reserve |
| `mac` | No | MAC address associated with the IP |
| `subnet` | No | Subnet ID (numeric) |
| `comment` | No | Description or notes |

## Action Reference

| Action | Requires | Description |
|--------|----------|-------------|
| `list_reserved_ips` | None | List all reserved IPs |
| `get_reserved_ip` | `reserved_ip_id` | Get details of one reserved IP |
| `create_reserved_ip` | `reserved_ip` | Create a new reserved IP |
| `update_reserved_ip` | `reserved_ip_id`, `reserved_ip` | Update reserved IP fields |
| `delete_reserved_ip` | `reserved_ip_id` | Delete a reserved IP |
