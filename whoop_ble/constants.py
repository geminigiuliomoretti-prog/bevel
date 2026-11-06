"""
Bluetooth SIG Standard UUIDs and Known WHOOP UUID Definitions.
"""

from typing import Dict, Optional

# Standard Bluetooth SIG 16-bit Service UUIDs (converted to 128-bit lowercase strings)
SIG_SERVICES: Dict[str, str] = {
    "00001800-0000-1000-8000-00805f9b34fb": "Generic Access",
    "00001801-0000-1000-8000-00805f9b34fb": "Generic Attribute",
    "0000180a-0000-1000-8000-00805f9b34fb": "Device Information",
    "0000180f-0000-1000-8000-00805f9b34fb": "Battery Service",
    "0000180d-0000-1000-8000-00805f9b34fb": "Heart Rate Service",
    "00001805-0000-1000-8000-00805f9b34fb": "Current Time Service",
    "00001812-0000-1000-8000-00805f9b34fb": "Human Interface Device",
    "0000fe59-0000-1000-8000-00805f9b34fb": "Nordic DFU Service (Legacy)",
    "8ec90001-f315-4f60-9fb8-838830daea50": "Nordic Secure DFU Service",
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART Service (NUS)",
    # WHOOP Gen 5 Puffin Service
    "fd4b0001-cce1-4033-93ce-002d5875f58a": "WHOOP Gen 5 Command/Data Service (Puffin)",
}

# Standard Bluetooth SIG 16-bit Characteristic UUIDs
SIG_CHARACTERISTICS: Dict[str, str] = {
    "fd4b0002-cce1-4033-93ce-002d5875f58a": "Puffin Command Tx (Write)",
    "fd4b0003-cce1-4033-93ce-002d5875f58a": "Puffin Command Rx (Notify)",
    "fd4b0004-cce1-4033-93ce-002d5875f58a": "Puffin Events (Notify)",
    "fd4b0005-cce1-4033-93ce-002d5875f58a": "Puffin Data Stream (Notify)",
    "fd4b0007-cce1-4033-93ce-002d5875f58a": "Puffin Extra Notify (Notify)",
    "00002a00-0000-1000-8000-00805f9b34fb": "Device Name",
    "00002a01-0000-1000-8000-00805f9b34fb": "Appearance",
    "00002aa6-0000-1000-8000-00805f9b34fb": "Central Address Resolution",
    "00002a04-0000-1000-8000-00805f9b34fb": "Peripheral Preferred Connection Parameters",
    "00002a05-0000-1000-8000-00805f9b34fb": "Service Changed",
    "00002a19-0000-1000-8000-00805f9b34fb": "Battery Level",
    "00002a23-0000-1000-8000-00805f9b34fb": "System ID",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model Number String",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial Number String",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware Revision String",
    "00002a27-0000-1000-8000-00805f9b34fb": "Hardware Revision String",
    "00002a28-0000-1000-8000-00805f9b34fb": "Software Revision String",
    "00002a29-0000-1000-8000-00805f9b34fb": "Manufacturer Name String",
    "00002a37-0000-1000-8000-00805f9b34fb": "Heart Rate Measurement",
    "00002a38-0000-1000-8000-00805f9b34fb": "Body Sensor Location",
    "00002a39-0000-1000-8000-00805f9b34fb": "Heart Rate Control Point",
    "00002a50-0000-1000-8000-00805f9b34fb": "PnP ID",
    # Nordic UART
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART RX (Write)",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART TX (Notify)",
}

# Standard Descriptors
SIG_DESCRIPTORS: Dict[str, str] = {
    "00002901-0000-1000-8000-00805f9b34fb": "Characteristic User Description",
    "00002902-0000-1000-8000-00805f9b34fb": "Client Characteristic Configuration (CCCD)",
    "00002904-0000-1000-8000-00805f9b34fb": "Characteristic Presentation Format",
}

# Known WHOOP Company ID (assigned number in BLE manufacturer data if used, or Nordic 0x0059)
WHOOP_COMPANY_IDENTIFIERS = [
    0x02DC,  # Whoop, Inc. / CBAS (or related registered company identifiers)
    0x0059,  # Nordic Semiconductor ASA (often in Dev/SDK beacons)
]

# Standard Service Short IDs for easy reference
UUID_DEVICE_INFO_SERVICE = "0000180a-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
UUID_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
UUID_HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
UUID_HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
UUID_BODY_SENSOR_LOCATION = "00002a38-0000-1000-8000-00805f9b34fb"

# WHOOP Gen 5 ("Puffin") Proprietary Service & Characteristic UUIDs
PUFFIN_SERVICE_UUID = "fd4b0001-cce1-4033-93ce-002d5875f58a"
PUFFIN_CHAR_COMMAND_TX = "fd4b0002-cce1-4033-93ce-002d5875f58a"  # Write with response
PUFFIN_CHAR_COMMAND_RX = "fd4b0003-cce1-4033-93ce-002d5875f58a"  # Notify (cmd response)
PUFFIN_CHAR_EVENTS = "fd4b0004-cce1-4033-93ce-002d5875f58a"      # Notify (hardware events 0x30)
PUFFIN_CHAR_DATA_STREAM = "fd4b0005-cce1-4033-93ce-002d5875f58a" # Notify (live/historical data 0x28, 0x2F, 0x31)
PUFFIN_CHAR_EXTRA_NOTIFY = "fd4b0007-cce1-4033-93ce-002d5875f58a" # Notify

# Puffin Protocol Opcodes
CMD_GET_CLOCK = 0x0B
CMD_SEND_HISTORICAL = 0x16
CMD_HISTORICAL_DATA_RESULT = 0x17
CMD_GET_BATTERY = 0x1A
CMD_GET_DATA_RANGE = 0x22
CMD_ALARM_CONTROL = 0x42
CMD_KEY_EXCHANGE = 0x73
CMD_SET_FF_VALUE = 0x78
CMD_GET_ADVERTISING_NAME = 0x8D
CMD_GET_HELLO = 0x91

# Safety blocked opcodes (destructive commands prohibited by safety allowlist)
CMD_ERASE_DEVICE = 0x19
CMD_REBOOT_DEVICE = 0x1D
BLOCKED_OPCODES = {CMD_ERASE_DEVICE, CMD_REBOOT_DEVICE}

# 16 Gen 5 Feature Flags
PUFFIN_16_FEATURE_FLAGS = [
    ("enable_r22_packets", 2),
    ("enable_r22_v2_packets", 2),
    ("enable_r22_v3_packets", 2),
    ("enable_r22_v4_packets", 1),
    ("enable_r22_v5_packets", 2),
    ("enable_r22_v6_packets", 2),
    ("enable_r22_v8_packets", 2),
    ("make_hrfm_visible", 2),
    ("disable_pip_r26_packets", 2),
    ("wear_detect_bias", 2),
    ("hr_ch_switching", 2),
    ("ir_hw_switching", 2),
    ("enable_passive_strap_fit_gen5", 1),
    ("enable_sig11_during_sleep", 2),
    ("dorset_inhibit_wpt", 2),
    ("enable_sig12", 2),
]


def normalize_uuid(uuid_str: str) -> str:
    """Normalize UUID to standard 128-bit lowercase string format."""
    clean = uuid_str.lower().strip()
    if len(clean) == 4:  # 16-bit short form
        return f"0000{clean}-0000-1000-8000-00805f9b34fb"
    if len(clean) == 8:  # 32-bit short form
        return f"{clean}-0000-1000-8000-00805f9b34fb"
    return clean


def lookup_service_name(uuid_str: str) -> str:
    norm = normalize_uuid(uuid_str)
    return SIG_SERVICES.get(norm, "Proprietary / Unknown Service")


def lookup_characteristic_name(uuid_str: str) -> str:
    norm = normalize_uuid(uuid_str)
    return SIG_CHARACTERISTICS.get(norm, "Proprietary / Custom Characteristic")


def lookup_descriptor_name(uuid_str: str) -> str:
    norm = normalize_uuid(uuid_str)
    return SIG_DESCRIPTORS.get(norm, "Custom / Unknown Descriptor")


def is_standard_uuid(uuid_str: str) -> bool:
    norm = normalize_uuid(uuid_str)
    # Standard SIG UUIDs end with -0000-1000-8000-00805f9b34fb and have 0000xxxx prefix
    return norm.endswith("-0000-1000-8000-00805f9b34fb") and norm.startswith("0000")
