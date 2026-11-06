"""
Unit tests for BLE scanner heuristic scoring.
"""

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from whoop_ble.scanner import DiscoveredBLEDevice


def test_whoop_heuristics_name_and_services():
    mock_dev = BLEDevice("FD:49:44:66:1D:92", "WHOOP 5WP", details=None)
    mock_adv = AdvertisementData(
        local_name="WHOOP 5WP",
        manufacturer_data={},
        service_data={},
        service_uuids=["0000180d-0000-1000-8000-00805f9b34fb", "fd4b0001-cce1-4033-93ce-002d5875f58a"],
        tx_power=None,
        rssi=-65,
        platform_data=None,
    )
    dev = DiscoveredBLEDevice(mock_dev, mock_adv)
    assert dev.whoop_heuristic_score >= 70
    assert any("whoop" in r.lower() for r in dev.whoop_heuristic_reasons)
    assert any("Heart Rate Service" in r for r in dev.whoop_heuristic_reasons)


def test_non_whoop_device():
    mock_dev = BLEDevice("11:22:33:44:55:66", "Unknown / Unnamed", details=None)
    mock_adv = AdvertisementData(
        local_name=None,
        manufacturer_data={0x004C: b"\x01\x02"},  # Apple
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=-80,
        platform_data=None,
    )
    dev = DiscoveredBLEDevice(mock_dev, mock_adv)
    assert dev.whoop_heuristic_score == 0


if __name__ == "__main__":
    test_whoop_heuristics_name_and_services()
    test_non_whoop_device()
    print("ALL HEURISTIC TESTS PASSED!")
