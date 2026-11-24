import socket
import json
import time
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any, Tuple

class WizBulbController:
    DEFAULT_PORT = 38899

    def __init__(self, ip: str = "192.168.0.101", signing_key: Optional[str] = None):
        self.ip = ip
        self.signing_key = signing_key.strip() if signing_key and signing_key.strip() else None
        self.last_state: Dict[str, Any] = {}

    def _to_wiz_json(self, dump_obj: Any) -> str:
        return json.dumps(dump_obj, separators=(',', ':'))

    def _sign_request(self, msg: Dict[str, Any], signing_key_hex: str) -> Dict[str, Any]:
        key_bytes = bytes.fromhex(signing_key_hex)
        params = dict(msg.get("params", {}))
        params["sigTs"] = int(time.time())
        compact_json = self._to_wiz_json(params)
        digest = hmac.new(key_bytes, compact_json.encode("utf-8"), hashlib.sha256).digest()
        return {
            "method": msg["method"],
            "env": "pro",
            "params": params,
            "hmac": base64.b64encode(digest).decode("ascii")
        }

    def _send_udp(self, payload: Dict[str, Any], timeout: float = 1.8) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if sys.platform == "win32":
            try:
                sock.ioctl(0x9800000C, False)  # SIO_UDP_CONNRESET
            except Exception:
                pass
        sock.settimeout(timeout)
        try:
            data = json.dumps(payload).encode("utf-8")
            sock.sendto(data, (self.ip, self.DEFAULT_PORT))
            resp, _ = sock.recvfrom(2048)
            result = json.loads(resp.decode("utf-8"))
            return True, result, ""
        except socket.timeout:
            return False, None, "Bulb did not respond (device offline or mains power out)"
        except Exception as e:
            return False, None, str(e)
        finally:
            sock.close()

    @classmethod
    def discover_bulb(cls, timeout: float = 1.2, target_mac: Optional[str] = None) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Broadcasts UDP discovery across the local subnet to locate WiZ bulbs."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if sys.platform == "win32":
            try:
                sock.ioctl(0x9800000C, False)  # SIO_UDP_CONNRESET
            except Exception:
                pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        payload = json.dumps({"method": "getPilot", "params": {}}).encode("utf-8")
        for bcast_addr in ["255.255.255.255", "192.168.0.255"]:
            try:
                sock.sendto(payload, (bcast_addr, cls.DEFAULT_PORT))
            except Exception:
                pass
        discovered = []
        try:
            while True:
                data, (resp_ip, _) = sock.recvfrom(2048)
                resp = json.loads(data.decode("utf-8"))
                result = resp.get("result", {})
                mac = result.get("mac", "")
                if target_mac and mac.lower().replace(":", "") != target_mac.lower().replace(":", ""):
                    continue
                discovered.append((resp_ip, result))
                break
        except Exception:
            pass
        finally:
            sock.close()
        return discovered[0] if discovered else None

    def get_state(self) -> Dict[str, Any]:
        """Fetch current live state from the bulb, with auto-discovery fallback."""
        success, resp, err = self._send_udp({"method": "getPilot", "params": {}})
        discovered_ip = None
        if not success or not resp:
            # Automatic discovery fallback if DHCP changed the bulb's IP address
            disc = self.discover_bulb(timeout=1.0)
            if disc:
                self.ip = disc[0]
                discovered_ip = disc[0]
                success, resp, err = self._send_udp({"method": "getPilot", "params": {}})

        if not success or not resp:
            return {
                "online": False,
                "error": err or "Connection timed out"
            }
        
        result = resp.get("result", {})
        state_data = {
            "online": True,
            "state": result.get("state", False),
            "dimming": result.get("dimming", 100),
            "temp": result.get("temp", 6500),
            "rssi": result.get("rssi", 0),
            "mac": result.get("mac", ""),
            "sceneId": result.get("sceneId", 0)
        }
        if discovered_ip:
            state_data["discovered_ip"] = discovered_ip
        self.last_state = state_data
        return state_data

    def set_pilot(self, **kwargs) -> Tuple[bool, str]:
        """
        Send control command to the bulb.
        kwargs can include: state (bool), dimming (10-100), temp (3000-6500), sceneId (int).
        """
        params = {}
        if "state" in kwargs:
            params["state"] = bool(kwargs["state"])
        if "dimming" in kwargs:
            params["dimming"] = max(10, min(100, int(kwargs["dimming"])))
        if "temp" in kwargs:
            params["temp"] = max(3000, min(6500, int(kwargs["temp"])))
        if "sceneId" in kwargs:
            params["sceneId"] = int(kwargs["sceneId"])

        if not params:
            return True, "No changes requested"

        payload = {"method": "setPilot", "params": params}

        if self.signing_key:
            try:
                payload = self._sign_request(payload, self.signing_key)
            except Exception as e:
                return False, f"Signing error (check hex key): {e}"

        success, resp, err = self._send_udp(payload)
        if not success or not resp:
            # Auto-discovery fallback if IP shifted
            disc = self.discover_bulb(timeout=1.0)
            if disc:
                self.ip = disc[0]
                success, resp, err = self._send_udp(payload)

        if not success or not resp:
            return False, err or "Bulb did not respond"

        if "error" in resp:
            code = resp["error"].get("code", 0)
            msg = resp["error"].get("message", "Unknown error")
            if code == -32602:
                return False, "KEY_REQUIRED"
            elif code == -32605:
                return False, "INVALID_KEY"
            return False, f"Bulb error ({code}): {msg}"

        if resp.get("result", {}).get("success", False) or "result" in resp:
            return True, "Success"

        return False, "Unexpected response from bulb"
