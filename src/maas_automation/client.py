"""MAAS API client with OAuth PLAINTEXT signature"""
import time
import random
import string
import logging
import requests
from typing import Optional, Dict, Any

log = logging.getLogger("maas_automation.client")


def parse_api_key(key: str) -> tuple[str, str, str]:
    """Parse MAAS API key into consumer:token:secret"""
    parts = key.split(":")
    if len(parts) != 3:
        raise ValueError("API key must be: consumer:token:secret")
    return parts[0], parts[1], parts[2]


def build_oauth_header(api_key: str) -> str:
    """Build OAuth PLAINTEXT authorization header for MAAS 3.x"""
    consumer, token, secret = parse_api_key(api_key)

    oauth = {
        "oauth_consumer_key": consumer,
        "oauth_token": token,
        "oauth_signature_method": "PLAINTEXT",
        "oauth_signature": f"&{secret}",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
        "oauth_version": "1.0"
    }

    header = "OAuth " + ", ".join(f'{k}="{v}"' for k, v in oauth.items())
    return header


class MaasClient:
    """MAAS API client with automatic OAuth signing"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.verify = True  # Set to False for self-signed certs

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": build_oauth_header(self.api_key),
            "Accept": "application/json",
        }

    def request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                json_data: Optional[Dict] = None) -> Any:
        """Make authenticated request to MAAS API"""
        endpoint = endpoint.strip("/")
        url = f"{self.api_url}/api/2.0/{endpoint}/"

        headers = self._headers()
        
        log.debug(f"{method} {url}")
        
        try:
            if method == "GET":
                resp = self.session.get(url, headers=headers, timeout=30)
            elif method == "POST":
                resp = self.session.post(url, headers=headers, data=data, json=json_data, timeout=30)
            elif method == "PUT":
                resp = self.session.put(url, headers=headers, data=data, json=json_data, timeout=30)
            elif method == "DELETE":
                resp = self.session.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if resp.status_code >= 400:
                log.error(f"HTTP {resp.status_code}: {resp.text}")
                resp.raise_for_status()

            try:
                return resp.json()
            except:
                return resp.text

        except requests.exceptions.RequestException as e:
            log.error(f"Request failed: {e}")
            raise

    # High-level API wrappers
    def list_machines(self):
        return self.request("GET", "machines")

    def get_machine(self, system_id: str):
        return self.request("GET", f"machines/{system_id}")

    def create_machine(self, data: Dict):
        return self.request("POST", "machines", data=data)

    def update_machine(self, system_id: str, data: Dict):
        return self.request("PUT", f"machines/{system_id}", data=data)

    def delete_machine(self, system_id: str):
        return self.request("POST", f"machines/{system_id}", data={"op": "delete"})

    def commission(self, system_id: str, data: Optional[Dict] = None):
        payload = data or {}
        payload["op"] = "commission"
        return self.request("POST", f"machines/{system_id}", data=payload)

    def deploy(self, system_id: str, data: Optional[Dict] = None):
        payload = data or {}
        payload["op"] = "deploy"
        return self.request("POST", f"machines/{system_id}", data=payload)

    def release(self, system_id: str, erase: bool = True):
        return self.request("POST", f"machines/{system_id}", data={"op": "release", "erase": str(erase).lower()})

    def abort_operation(self, system_id: str):
        return self.request("POST", f"machines/{system_id}", data={"op": "abort"})

    def list_block_devices(self, system_id: str):
        return self.request("GET", f"machines/{system_id}/block-devices")

    def set_storage_layout(self, system_id: str, layout_type: str):
        return self.request("POST", f"machines/{system_id}", 
                          data={"op": "set_storage_layout", "storage_layout": layout_type})
