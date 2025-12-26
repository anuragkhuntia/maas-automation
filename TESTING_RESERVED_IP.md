# Testing Reserved IP Functionality

## Prerequisites
- MAAS server running and accessible
- Valid API credentials
- At least one subnet configured in MAAS

## Test Scenarios

### 1. List Reserved IPs (READ ALL)
```bash
maas-automation -i example_list_reserved_ips.json
```

**Expected Output:**
- Table showing all reserved IPs
- Columns: ID, IP ADDRESS, MAC ADDRESS, SUBNET, COMMENT
- Total count at the bottom

### 2. Create Reserved IP (CREATE)
```bash
# Edit example_create_reserved_ip.json with your subnet ID
maas-automation -i example_create_reserved_ip.json
```

**Expected Output:**
- Success message with created reserved IP details
- ID assigned by MAAS
- All fields displayed

**Verify:**
```bash
maas-automation -i example_list_reserved_ips.json
```
Should show the newly created reserved IP.

### 3. Get Reserved IP Details (READ ONE)
```bash
# Update reserved_ip_id in example_get_reserved_ip.json
# Use the ID from the create step
maas-automation -i example_get_reserved_ip.json
```

**Expected Output:**
- Detailed information about the reserved IP
- All fields displayed in formatted output

### 4. Update Reserved IP (UPDATE)
```bash
# Update reserved_ip_id in example_update_reserved_ip.json
# Use the ID from the create step
maas-automation -i example_update_reserved_ip.json
```

**Expected Output:**
- Success message with updated fields
- Updated values displayed

**Verify:**
```bash
maas-automation -i example_get_reserved_ip.json
```
Should show the updated comment and MAC address.

### 5. Delete Reserved IP (DELETE)
```bash
# Update reserved_ip_id in example_delete_reserved_ip.json
# Use the ID from the create step
maas-automation -i example_delete_reserved_ip.json
```

**Expected Output:**
- Success message confirming deletion
- Reserved IP ID displayed

**Verify:**
```bash
maas-automation -i example_list_reserved_ips.json
```
The deleted reserved IP should no longer appear in the list.

## Test with Command-Line Override

```bash
# Create config.json with credentials and reserved_ip section
maas-automation -i config.json -a create_reserved_ip

# List using action override
maas-automation -i config.json -a list_reserved_ips

# Delete using action override (config must have reserved_ip_id)
maas-automation -i config.json -a delete_reserved_ip
```

## Error Testing

### Test 1: Missing IP Address
Edit `example_create_reserved_ip.json` and remove the `ip` field.

```bash
maas-automation -i example_create_reserved_ip.json
```

**Expected:** Error message about missing required field.

### Test 2: Invalid Reserved IP ID
Edit `example_get_reserved_ip.json` and set `reserved_ip_id` to 99999.

```bash
maas-automation -i example_get_reserved_ip.json
```

**Expected:** Error message about reserved IP not found.

### Test 3: Duplicate IP Address
Try to create two reserved IPs with the same IP address.

**Expected:** Error message from MAAS API about duplicate IP.

### Test 4: Missing Configuration
Edit config and remove `reserved_ip_id` field, then try:

```bash
maas-automation -i config.json -a get_reserved_ip
```

**Expected:** Error message about missing `reserved_ip_id`.

## Integration Testing

### Test with Retry Logic
```bash
# Test with custom retry settings
maas-automation -i example_create_reserved_ip.json --max-retries 3
```

### Test with Verbose Logging
```bash
# Enable debug logging
maas-automation -i example_list_reserved_ips.json -v
```

**Expected:** Detailed debug logs showing API calls and responses.

## Performance Testing

### Test List Operation with Many Reserved IPs
If your MAAS has many reserved IPs:

```bash
time maas-automation -i example_list_reserved_ips.json
```

Should complete in reasonable time (< 5 seconds for hundreds of IPs).

## Manual API Verification (Optional)

You can verify the implementation matches MAAS API behavior using `curl`:

```bash
# List reserved IPs
curl -H "Authorization: OAuth ..." \
  http://your-maas:5240/MAAS/api/2.0/reservedips/

# Create reserved IP
curl -X POST -H "Authorization: OAuth ..." \
  -d "ip=192.168.1.100" \
  -d "comment=Test" \
  http://your-maas:5240/MAAS/api/2.0/reservedips/

# Get reserved IP
curl -H "Authorization: OAuth ..." \
  http://your-maas:5240/MAAS/api/2.0/reservedips/1/

# Update reserved IP
curl -X PUT -H "Authorization: OAuth ..." \
  -d "comment=Updated" \
  http://your-maas:5240/MAAS/api/2.0/reservedips/1/

# Delete reserved IP
curl -X DELETE -H "Authorization: OAuth ..." \
  http://your-maas:5240/MAAS/api/2.0/reservedips/1/
```

## Test Checklist

- [ ] List empty reserved IPs
- [ ] Create first reserved IP
- [ ] List shows created IP
- [ ] Get details of created IP
- [ ] Update reserved IP comment
- [ ] Update reserved IP MAC address
- [ ] List shows updated values
- [ ] Create second reserved IP with minimal fields (only IP)
- [ ] Delete first reserved IP
- [ ] Verify deletion (list or get)
- [ ] Test error: missing IP on create
- [ ] Test error: invalid ID on get
- [ ] Test error: missing reserved_ip_id
- [ ] Test with command-line override
- [ ] Test with verbose logging
- [ ] Test with custom retry count

## Success Criteria

✅ All CRUD operations work correctly
✅ Error handling provides clear messages
✅ Output is formatted and readable
✅ Configuration validation works
✅ Command-line overrides work
✅ Retry logic functions properly
✅ Integration with existing SDK is seamless
