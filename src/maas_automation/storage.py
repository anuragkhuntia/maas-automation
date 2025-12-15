"""Storage layout configuration with Curtin templates"""
from .client import MaasClient
import logging
from jinja2 import Template
from typing import Optional, Dict

log = logging.getLogger("maas_automation.storage")

CURTIN_TEMPLATE = """
storage:
  config:
    # EFI partition
    - id: disk-target
      type: disk
      path: {{ device }}
      ptable: gpt
      wipe: superblock
      preserve: false

    - id: part-efi
      type: partition
      device: disk-target
      size: {{ efi_mb }}MB
      flag: boot

    - id: format-efi
      type: format
      fstype: fat32
      volume: part-efi

    - id: mount-efi
      type: mount
      path: /boot/efi
      device: format-efi

    # Boot partition
    - id: part-boot
      type: partition
      device: disk-target
      size: {{ boot_size_g }}GB

    - id: format-boot
      type: format
      fstype: xfs
      volume: part-boot

    - id: mount-boot
      type: mount
      path: /boot
      device: format-boot

    # LVM partition
    - id: part-lvm
      type: partition
      device: disk-target
      size: -1

    - id: pv-lvm
      type: lvm_volgroup
      name: vg-main
      devices:
        - part-lvm

    # Logical volumes
{% for lv in lvs %}
    - id: lv-{{ lv.name }}
      type: lvm_partition
      name: {{ lv.name }}
      volgroup: pv-lvm
      size: {{ lv.size }}GB

    - id: format-{{ lv.name }}
      type: format
      fstype: {{ lv.fs }}
      volume: lv-{{ lv.name }}

    - id: mount-{{ lv.name }}
      type: mount
      path: {{ lv.mount }}
      device: format-{{ lv.name }}
{% endfor %}

grub:
  install_devices:
    - {{ device }}
  update_nvram: true
"""


class StorageManager:
    """Manages storage layout configuration"""

    def __init__(self, client: MaasClient):
        self.client = client

    def choose_device(self, system_id: str) -> Optional[str]:
        """Choose best device for OS installation"""
        try:
            devices = self.client.list_block_devices(system_id)
            if not devices:
                log.warning(f"No block devices found for {system_id}")
                return None

            # Prefer devices with 'boot' or 'ssd' tags
            for d in devices:
                tags = d.get('tags', [])
                if 'boot' in tags or 'os' in tags or 'ssd' in tags:
                    name = d.get('name') or d.get('id_path') or d.get('path')
                    path = name if name.startswith('/dev/') else f"/dev/{name}"
                    log.info(f"Selected boot device: {path}")
                    return path

            # Fallback to largest device
            largest = max(devices, key=lambda x: x.get('size', 0))
            name = largest.get('name') or largest.get('path')
            path = name if name.startswith('/dev/') else f"/dev/{name}"
            log.info(f"Selected largest device: {path} ({largest.get('size', 0)} bytes)")
            return path

        except Exception as e:
            log.error(f"Failed to choose device: {e}")
            return None

    def render_curtin(self, device: str, params: Dict) -> str:
        """Render Curtin storage configuration from template"""
        lvs = [
            {"name": "root", "size": params.get('root_size_g', 50), "fs": "xfs", "mount": "/"},
            {"name": "home", "size": params.get('home_size_g', 10), "fs": "xfs", "mount": "/home"},
            {"name": "var", "size": params.get('var_size_g', 10), "fs": "xfs", "mount": "/var"},
            {"name": "var-log", "size": params.get('var_log_size_g', 10), "fs": "xfs", "mount": "/var/log"},
            {"name": "tmp", "size": params.get('tmp_size_g', 10), "fs": "xfs", "mount": "/tmp"},
        ]

        tpl = Template(CURTIN_TEMPLATE)
        curtin_config = tpl.render(
            device=device,
            efi_mb=params.get('efi_mb', 512),
            boot_size_g=params.get('boot_size_g', 2),
            lvs=lvs
        )
        
        log.debug(f"Generated Curtin config:\n{curtin_config}")
        return curtin_config

    def apply_layout(self, system_id: str, device: Optional[str] = None, 
                     params: Optional[Dict] = None):
        """Apply storage layout to machine"""
        params = params or {}
        
        if not device:
            device = self.choose_device(system_id)
            if not device:
                raise ValueError(f"No suitable device found for {system_id}")

        log.info(f"Applying storage layout to {system_id} on {device}")
        curtin_config = self.render_curtin(device, params)

        # Upload Curtin configuration
        payload = {"curtin_userdata": curtin_config}
        result = self.client.update_machine(system_id, payload)
        
        log.info("✓ Storage layout configured")
        return result
