"""
BLE Notification Handler.
Subscribes to notifications/indications, manages callbacks, logs raw packets, and handles errors cleanly.
"""

from typing import Callable, Dict, Optional
from bleak import BleakClient
from whoop_ble.constants import UUID_HR_MEASUREMENT, normalize_uuid, lookup_characteristic_name
from whoop_ble.hr_decoder import decode_heart_rate_measurement
from whoop_ble.logger import DiagnosticLogger


class NotificationHandler:
    def __init__(self, client: BleakClient, logger: DiagnosticLogger):
        self.client = client
        self.logger = logger
        self.active_subscriptions: Dict[str, Callable] = {}

    async def start_heart_rate_stream(
        self,
        callback: Optional[Callable[[Dict], None]] = None,
    ) -> bool:
        """Subscribe to standard Heart Rate Measurement notifications (0x2A37)."""
        uuid = UUID_HR_MEASUREMENT

        char = self.client.services.get_characteristic(uuid)
        if not char:
            self.logger.log_gatt_error("start_hr_stream", "HR Measurement characteristic (0x2A37) not found")
            return False

        if "notify" not in char.properties and "indicate" not in char.properties:
            self.logger.log_gatt_error("start_hr_stream", f"Characteristic {uuid} does not support notify/indicate: {char.properties}")
            return False

        def _hr_notification_callback(sender, data: bytearray):
            raw_bytes = bytes(data)
            decoded = decode_heart_rate_measurement(raw_bytes)

            self.logger.log_packet(
                device_address=self.client.address,
                characteristic_uuid=uuid,
                characteristic_name="Heart Rate Measurement",
                raw_bytes=raw_bytes,
                decoded_data=decoded,
            )

            if callback:
                try:
                    callback(decoded)
                except Exception as cb_err:
                    self.logger.logger.error(f"Callback error in HR handler: {cb_err}")

        try:
            await self.client.start_notify(uuid, _hr_notification_callback)
            self.active_subscriptions[uuid] = _hr_notification_callback
            self.logger.log_event("HR_STREAM_STARTED", {"uuid": uuid})
            return True
        except Exception as e:
            self.logger.log_gatt_error("start_hr_stream", str(e), uuid)
            return False

    async def stop_heart_rate_stream(self) -> bool:
        """Stop standard Heart Rate Measurement notifications."""
        uuid = UUID_HR_MEASUREMENT
        if uuid in self.active_subscriptions:
            try:
                await self.client.stop_notify(uuid)
                del self.active_subscriptions[uuid]
                self.logger.log_event("HR_STREAM_STOPPED", {"uuid": uuid})
                return True
            except Exception as e:
                self.logger.log_gatt_error("stop_hr_stream", str(e), uuid)
                return False
        return True

    async def stop_all_notifications(self):
        """Unsubscribe from all active notifications safely."""
        for uuid in list(self.active_subscriptions.keys()):
            try:
                await self.client.stop_notify(uuid)
                self.logger.log_event("NOTIFICATION_STOPPED", {"uuid": uuid})
            except Exception as e:
                self.logger.log_gatt_error("stop_all_notifications", str(e), uuid)
        self.active_subscriptions.clear()
