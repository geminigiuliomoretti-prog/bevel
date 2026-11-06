"""
WHOOP Proprietary Service Inspection Module (FASE D).
Inspects proprietary non-standard GATT services and characteristics.
Safely checks:
- Read capability on readable proprietary characteristics (records any unauthenticated data or security errors)
- Notification / Indication capability
- ZERO writes performed (respecting absolute constraint: no unverified writes)
- Full documentation of exposed endpoints and GATT response codes / errors.
"""

from typing import Any, Dict, List
from bleak import BleakClient
from whoop_ble.constants import normalize_uuid, is_standard_uuid
from whoop_ble.logger import DiagnosticLogger


class ProprietaryServiceInspector:
    def __init__(self, client: BleakClient, logger: DiagnosticLogger):
        self.client = client
        self.logger = logger

    async def inspect(self) -> List[Dict[str, Any]]:
        """
        Scans all non-standard services in the client's GATT table.
        Attempts safe, non-destructive reads only on characteristics with 'read' property.
        Logs any GATT errors (e.g. Insufficient Authentication / Authorization / Read Not Permitted).
        """
        self.logger.log_event("PROPRIETARY_INSPECTION_STARTED", {"address": self.client.address})

        proprietary_services_report: List[Dict[str, Any]] = []

        for service in self.client.services:
            svc_uuid = normalize_uuid(service.uuid)
            if is_standard_uuid(svc_uuid):
                continue  # Skip standard Bluetooth SIG services

            service_data: Dict[str, Any] = {
                "service_uuid": svc_uuid,
                "handle": service.handle,
                "characteristics": [],
            }

            for char in service.characteristics:
                char_uuid = normalize_uuid(char.uuid)
                props = sorted(list(char.properties))

                char_entry: Dict[str, Any] = {
                    "uuid": char_uuid,
                    "handle": char.handle,
                    "properties": props,
                    "supports_read": "read" in props,
                    "supports_write": "write" in props,
                    "supports_write_without_response": "write-without-response" in props,
                    "supports_notify": "notify" in props,
                    "supports_indicate": "indicate" in props,
                    "read_result": None,
                    "descriptors": [
                        {
                            "uuid": normalize_uuid(d.uuid),
                            "handle": d.handle,
                        }
                        for d in char.descriptors
                    ],
                }

                # If readable, attempt a safe read to see if authentication is required
                if "read" in props:
                    try:
                        raw_bytes = await self.client.read_gatt_char(char.uuid)
                        raw_hex = raw_bytes.hex().upper()
                        char_entry["read_result"] = {
                            "status": "READ_SUCCESS_UNAUTHENTICATED",
                            "raw_hex": raw_hex,
                            "byte_length": len(raw_bytes),
                            "ascii_representation": raw_bytes.decode("ascii", errors="replace"),
                        }
                        self.logger.log_packet(
                            device_address=self.client.address,
                            characteristic_uuid=char_uuid,
                            characteristic_name="Proprietary Characteristic",
                            raw_bytes=raw_bytes,
                            decoded_data={"note": "Unauthenticated read permitted"},
                        )
                    except Exception as e:
                        err_str = str(e)
                        char_entry["read_result"] = {
                            "status": "READ_DENIED_OR_FAILED",
                            "error": err_str,
                        }
                        self.logger.log_gatt_error(
                            "read_proprietary_characteristic",
                            err_str,
                            char_uuid,
                        )
                else:
                    char_entry["read_result"] = {
                        "status": "NOT_READABLE",
                        "note": "Characteristic does not have READ property (Write or Notify only)",
                    }

                service_data["characteristics"].append(char_entry)

            proprietary_services_report.append(service_data)

        self.logger.log_event("PROPRIETARY_INSPECTION_COMPLETED", {
            "total_proprietary_services": len(proprietary_services_report),
            "services": proprietary_services_report,
        })

        return proprietary_services_report
