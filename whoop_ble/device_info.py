"""
Device Information (0x180A) and Battery (0x180F) GATT Readers.
Distinguishes clearly between:
- RECEIVED
- DECODED
- NOT_AVAILABLE
- UNINTERPRETED / GATT_ERROR
"""

from typing import Any, Dict, Optional
from bleak import BleakClient
from whoop_ble.constants import (
    UUID_DEVICE_INFO_SERVICE,
    UUID_BATTERY_SERVICE,
    UUID_BATTERY_LEVEL,
    UUID_BODY_SENSOR_LOCATION,
    SIG_CHARACTERISTICS,
)
from whoop_ble.logger import DiagnosticLogger, mask_identifier


BODY_LOCATIONS = {
    0: "Other",
    1: "Chest",
    2: "Wrist",
    3: "Finger",
    4: "Hand",
    5: "Ear Lobe",
    6: "Foot",
}


class StandardDataReader:
    def __init__(self, client: BleakClient, logger: DiagnosticLogger):
        self.client = client
        self.logger = logger
        self.device_address = client.address

    async def read_battery_level(self) -> Dict[str, Any]:
        """Read Battery Level (0x2A19)."""
        uuid = UUID_BATTERY_LEVEL
        try:
            # Check if characteristic exists in client services
            char = self.client.services.get_characteristic(uuid)
            if not char or "read" not in char.properties:
                self.logger.log_event("BATTERY_READ_SKIPPED", {"reason": "Characteristic not found or not readable"})
                return {
                    "status": "NOT_AVAILABLE",
                    "uuid": uuid,
                    "name": "Battery Level",
                    "raw_hex": None,
                    "value": None,
                }

            raw_bytes = await self.client.read_gatt_char(uuid)
            raw_hex = raw_bytes.hex().upper()
            level = int(raw_bytes[0]) if len(raw_bytes) > 0 else None

            decoded = {
                "status": "DECODED",
                "uuid": uuid,
                "name": "Battery Level",
                "raw_hex": raw_hex,
                "battery_level_percent": level,
            }

            self.logger.log_packet(
                device_address=self.device_address,
                characteristic_uuid=uuid,
                characteristic_name="Battery Level",
                raw_bytes=raw_bytes,
                decoded_data=decoded,
            )
            return decoded
        except Exception as e:
            self.logger.log_gatt_error("read_battery_level", str(e), uuid)
            return {
                "status": "GATT_ERROR",
                "uuid": uuid,
                "error": str(e),
                "raw_hex": None,
                "value": None,
            }

    async def read_device_information(self) -> Dict[str, Any]:
        """Read standard Device Information Service (0x180A) characteristics."""
        results: Dict[str, Any] = {}

        char_mapping = {
            "00002a00-0000-1000-8000-00805f9b34fb": ("device_name", "string"),
            "00002a01-0000-1000-8000-00805f9b34fb": ("appearance", "hex"),
            "00002aa6-0000-1000-8000-00805f9b34fb": ("central_address_resolution", "hex"),
            "00002a29-0000-1000-8000-00805f9b34fb": ("manufacturer_name", "string"),
            "00002a24-0000-1000-8000-00805f9b34fb": ("model_number", "string"),
            "00002a25-0000-1000-8000-00805f9b34fb": ("serial_number", "string_masked"),
            "00002a27-0000-1000-8000-00805f9b34fb": ("hardware_revision", "string"),
            "00002a26-0000-1000-8000-00805f9b34fb": ("firmware_revision", "string"),
            "00002a28-0000-1000-8000-00805f9b34fb": ("software_revision", "string"),
            "00002a23-0000-1000-8000-00805f9b34fb": ("system_id", "hex"),
            "00002a50-0000-1000-8000-00805f9b34fb": ("pnp_id", "hex"),
        }

        for uuid, (field_name, field_type) in char_mapping.items():
            char = self.client.services.get_characteristic(uuid)
            char_friendly_name = SIG_CHARACTERISTICS.get(uuid, field_name)

            if not char:
                results[field_name] = {
                    "status": "NOT_AVAILABLE",
                    "uuid": uuid,
                    "field_name": field_name,
                    "name": char_friendly_name,
                    "raw_hex": None,
                    "value": None,
                }
                continue

            if "read" not in char.properties:
                results[field_name] = {
                    "status": "READ_NOT_PERMITTED",
                    "uuid": uuid,
                    "field_name": field_name,
                    "name": char_friendly_name,
                    "properties": char.properties,
                    "raw_hex": None,
                    "value": None,
                }
                continue

            try:
                raw_bytes = await self.client.read_gatt_char(uuid)
                raw_hex = raw_bytes.hex().upper()

                if field_type == "string":
                    decoded_val = raw_bytes.decode("utf-8", errors="replace").strip("\x00").strip()
                elif field_type == "string_masked":
                    full_val = raw_bytes.decode("utf-8", errors="replace").strip("\x00").strip()
                    decoded_val = mask_identifier(full_val)
                elif field_type == "hex":
                    decoded_val = raw_hex
                else:
                    decoded_val = raw_hex

                field_data = {
                    "status": "DECODED",
                    "uuid": uuid,
                    "field_name": field_name,
                    "name": char_friendly_name,
                    "raw_hex": raw_hex,
                    "value": decoded_val,
                }
                results[field_name] = field_data

                self.logger.log_packet(
                    device_address=self.device_address,
                    characteristic_uuid=uuid,
                    characteristic_name=char_friendly_name,
                    raw_bytes=raw_bytes,
                    decoded_data=field_data,
                )
            except Exception as e:
                self.logger.log_gatt_error(f"read_{field_name}", str(e), uuid)
                results[field_name] = {
                    "status": "GATT_ERROR",
                    "uuid": uuid,
                    "field_name": field_name,
                    "error": str(e),
                    "raw_hex": None,
                    "value": None,
                }

        return results

    async def read_body_sensor_location(self) -> Dict[str, Any]:
        """Read Body Sensor Location (0x2A38) if present in Heart Rate Service."""
        uuid = UUID_BODY_SENSOR_LOCATION
        char = self.client.services.get_characteristic(uuid)
        if not char or "read" not in char.properties:
            return {
                "status": "NOT_AVAILABLE",
                "uuid": uuid,
                "name": "Body Sensor Location",
                "raw_hex": None,
                "value": None,
            }

        try:
            raw_bytes = await self.client.read_gatt_char(uuid)
            raw_hex = raw_bytes.hex().upper()
            loc_code = int(raw_bytes[0]) if raw_bytes else None
            loc_name = BODY_LOCATIONS.get(loc_code, f"Unknown ({loc_code})")

            decoded = {
                "status": "DECODED",
                "uuid": uuid,
                "name": "Body Sensor Location",
                "raw_hex": raw_hex,
                "location_code": loc_code,
                "location_name": loc_name,
            }

            self.logger.log_packet(
                device_address=self.device_address,
                characteristic_uuid=uuid,
                characteristic_name="Body Sensor Location",
                raw_bytes=raw_bytes,
                decoded_data=decoded,
            )
            return decoded
        except Exception as e:
            self.logger.log_gatt_error("read_body_sensor_location", str(e), uuid)
            return {
                "status": "GATT_ERROR",
                "uuid": uuid,
                "error": str(e),
                "raw_hex": None,
                "value": None,
            }
