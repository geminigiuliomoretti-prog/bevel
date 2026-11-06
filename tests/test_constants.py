"""
Unit tests for constants and UUID utilities.
"""

from whoop_ble.constants import (
    normalize_uuid,
    is_standard_uuid,
    lookup_service_name,
    lookup_characteristic_name,
)


def test_normalize_uuid():
    assert normalize_uuid("180D") == "0000180d-0000-1000-8000-00805f9b34fb"
    assert normalize_uuid("0000180A-0000-1000-8000-00805F9B34FB") == "0000180a-0000-1000-8000-00805f9b34fb"
    assert normalize_uuid("FD4B0001-CCE1-4033-93CE-002D5875F58A") == "fd4b0001-cce1-4033-93ce-002d5875f58a"


def test_is_standard_uuid():
    assert is_standard_uuid("0000180d-0000-1000-8000-00805f9b34fb") is True
    assert is_standard_uuid("0000180a-0000-1000-8000-00805f9b34fb") is True
    assert is_standard_uuid("fd4b0001-cce1-4033-93ce-002d5875f58a") is False


def test_lookup_names():
    assert lookup_service_name("180D") == "Heart Rate Service"
    assert lookup_service_name("180A") == "Device Information"
    assert lookup_characteristic_name("2A37") == "Heart Rate Measurement"
    assert lookup_characteristic_name("2A19") == "Battery Level"


if __name__ == "__main__":
    test_normalize_uuid()
    test_is_standard_uuid()
    test_lookup_names()
    print("ALL CONSTANTS TESTS PASSED!")
