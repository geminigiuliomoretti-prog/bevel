"""
GATT Services & Characteristics Explorer (FASE B).
Discovers and categorizes all GATT services, characteristics, and descriptors.
Classifies between Bluetooth SIG standard and proprietary UUIDs.
Exports complete structure to JSON.
"""

from typing import Any, Dict, List
from bleak import BleakClient
from whoop_ble.constants import (
    normalize_uuid,
    lookup_service_name,
    lookup_characteristic_name,
    lookup_descriptor_name,
    is_standard_uuid,
)
from whoop_ble.logger import DiagnosticLogger


class GATTExplorer:
    def __init__(self, client: BleakClient, logger: DiagnosticLogger):
        self.client = client
        self.logger = logger
        self.discovered_tree: Dict[str, Any] = {}

    async def explore(self) -> Dict[str, Any]:
        """
        Traverse the entire GATT table and build a structured representation.
        """
        self.logger.log_event("GATT_DISCOVERY_STARTED", {"address": self.client.address})

        services_list: List[Dict[str, Any]] = []
        standard_services_count = 0
        proprietary_services_count = 0
        total_characteristics = 0

        for service in self.client.services:
            svc_uuid = normalize_uuid(service.uuid)
            is_std_svc = is_standard_uuid(svc_uuid)
            svc_name = lookup_service_name(svc_uuid)

            if is_std_svc:
                standard_services_count += 1
            else:
                proprietary_services_count += 1

            characteristics_list: List[Dict[str, Any]] = []

            for char in service.characteristics:
                total_characteristics += 1
                char_uuid = normalize_uuid(char.uuid)
                is_std_char = is_standard_uuid(char_uuid)
                char_name = lookup_characteristic_name(char_uuid)

                # Descriptors
                descriptors_list: List[Dict[str, Any]] = []
                for desc in char.descriptors:
                    desc_uuid = normalize_uuid(desc.uuid)
                    descriptors_list.append({
                        "uuid": desc_uuid,
                        "handle": desc.handle,
                        "name": lookup_descriptor_name(desc_uuid),
                        "is_standard": is_standard_uuid(desc_uuid),
                    })

                char_info = {
                    "uuid": char_uuid,
                    "handle": char.handle,
                    "name": char_name,
                    "is_standard": is_std_char,
                    "properties": sorted(list(char.properties)),
                    "descriptors": descriptors_list,
                }
                characteristics_list.append(char_info)

            service_info = {
                "uuid": svc_uuid,
                "handle": service.handle,
                "name": svc_name,
                "is_standard": is_std_svc,
                "characteristics_count": len(characteristics_list),
                "characteristics": characteristics_list,
            }
            services_list.append(service_info)

        summary = {
            "device_address": self.client.address,
            "total_services": len(services_list),
            "standard_services_count": standard_services_count,
            "proprietary_services_count": proprietary_services_count,
            "total_characteristics": total_characteristics,
            "has_heart_rate_service": any("180d" in s["uuid"] for s in services_list),
            "has_battery_service": any("180f" in s["uuid"] for s in services_list),
            "has_device_info_service": any("180a" in s["uuid"] for s in services_list),
            "services": services_list,
        }

        self.discovered_tree = summary

        self.logger.log_event("GATT_DISCOVERY_COMPLETED", {
            "total_services": len(services_list),
            "total_characteristics": total_characteristics,
            "standard_services": standard_services_count,
            "proprietary_services": proprietary_services_count,
        })

        return summary
