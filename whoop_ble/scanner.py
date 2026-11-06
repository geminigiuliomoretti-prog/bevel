"""
BLE Scanner Module (FASE A).
Scans for BLE devices, captures advertisement data, computes multi-factor identification scores
for WHOOP without relying solely on advertised local name, and supports repeated scans.
"""

import asyncio
from typing import Dict, List, Optional, Tuple, Callable
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from whoop_ble.constants import (
    WHOOP_COMPANY_IDENTIFIERS,
    normalize_uuid,
    lookup_service_name,
)
from whoop_ble.logger import DiagnosticLogger


class DiscoveredBLEDevice:
    def __init__(self, device: BLEDevice, adv_data: Optional[AdvertisementData] = None):
        self.device = device
        self.adv_data = adv_data
        self.address = device.address
        local_name = adv_data.local_name if adv_data else None
        self.name = local_name or device.name or "Unknown / Unnamed"
        self.rssi = adv_data.rssi if (adv_data and adv_data.rssi is not None) else getattr(device, "rssi", None)
        self.service_uuids = [normalize_uuid(u) for u in ((adv_data.service_uuids if adv_data else None) or [])]
        self.manufacturer_data = (adv_data.manufacturer_data if adv_data else {}) or {}
        self.service_data = (adv_data.service_data if adv_data else {}) or {}
        self.whoop_heuristic_score, self.whoop_heuristic_reasons = self._evaluate_whoop_affinity()

    def _evaluate_whoop_affinity(self) -> Tuple[int, List[str]]:
        """
        Multi-factor heuristic identification of WHOOP devices.
        Does NOT rely solely on device name.
        Returns a score (0 to 100) and rationale.
        """
        score = 0
        reasons = []

        # 1. Local Name check
        name_lower = self.name.lower()
        if "whoop" in name_lower:
            score += 50
            reasons.append(f"Name contains 'whoop' ('{self.name}')")

        # 2. Manufacturer Data check
        for comp_id in self.manufacturer_data.keys():
            if comp_id in WHOOP_COMPANY_IDENTIFIERS:
                score += 30
                reasons.append(f"Manufacturer ID matched WHOOP/Nordic ecosystem (0x{comp_id:04X})")
            else:
                reasons.append(f"Manufacturer ID: 0x{comp_id:04X}")

        # 3. Advertised Services check
        for uuid in self.service_uuids:
            # Standard Heart Rate Service
            if "180d" in uuid:
                score += 20
                reasons.append("Advertises Standard Heart Rate Service (0x180D)")
            # Standard Battery Service
            elif "180f" in uuid:
                score += 10
                reasons.append("Advertises Standard Battery Service (0x180F)")
            # Nordic UART or proprietary vendor bases
            elif "6e400001" in uuid or "8ec90001" in uuid:
                score += 20
                reasons.append(f"Advertises Nordic/Custom Service ({uuid[:8]}...)")
            else:
                reasons.append(f"Advertises Service: {lookup_service_name(uuid)} ({uuid[:8]}...)")

        return score, reasons

    def to_dict(self) -> Dict:
        # Convert manufacturer data keys to hex strings for serialization
        mfg_dict = {f"0x{k:04X}": v.hex().upper() for k, v in self.manufacturer_data.items()}
        svc_dict = {k: v.hex().upper() for k, v in self.service_data.items()}

        return {
            "address": self.address,
            "name": self.name,
            "rssi": self.rssi,
            "advertised_services": self.service_uuids,
            "manufacturer_data": mfg_dict,
            "service_data": svc_dict,
            "whoop_score": self.whoop_heuristic_score,
            "whoop_reasons": self.whoop_heuristic_reasons,
        }


class BLEDeviceScanner:
    def __init__(self, logger: DiagnosticLogger):
        self.logger = logger
        self.discovered_devices: Dict[str, DiscoveredBLEDevice] = {}

    async def scan(
        self,
        duration_seconds: float = 5.0,
        detection_callback: Optional[Callable[[DiscoveredBLEDevice], None]] = None,
    ) -> List[DiscoveredBLEDevice]:
        """
        Run a BLE scan for duration_seconds.
        Collects all advertisement packets without making any connection.
        """
        self.discovered_devices.clear()
        self.logger.log_event("BLE_SCAN_STARTED", {"duration_seconds": duration_seconds})

        def _detection_handler(device: BLEDevice, adv_data: AdvertisementData):
            dev_obj = DiscoveredBLEDevice(device, adv_data)
            self.discovered_devices[device.address] = dev_obj
            if detection_callback:
                detection_callback(dev_obj)

        scanner = BleakScanner(detection_callback=_detection_handler)
        await scanner.start()
        await asyncio.sleep(duration_seconds)
        await scanner.stop()

        results = list(self.discovered_devices.values())
        # Sort by whoop score desc, then rssi desc
        results.sort(key=lambda d: (d.whoop_heuristic_score, d.rssi if d.rssi is not None else -999), reverse=True)

        self.logger.log_event("BLE_SCAN_COMPLETED", {
            "total_devices_found": len(results),
            "devices": [d.to_dict() for d in results],
        })

        return results
