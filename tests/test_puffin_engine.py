"""
Unit tests for PuffinEngine safety constraints and parameter encoding.
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from whoop_ble.puffin_engine import PuffinEngine, PuffinSafetyViolation
from whoop_ble.constants import (
    CMD_ERASE_DEVICE,
    CMD_REBOOT_DEVICE,
    CMD_GET_HELLO,
    PUFFIN_16_FEATURE_FLAGS,
)


def test_safety_blocked_opcodes():
    # Verify that dangerous opcodes 0x19 and 0x1D raise PuffinSafetyViolation immediately
    engine = PuffinEngine(client=None, logger=None)

    for blocked_cmd in [CMD_ERASE_DEVICE, CMD_REBOOT_DEVICE, 0x19, 0x1D]:
        try:
            # We run synchronously or catch directly
            asyncio.run(engine.send_command(cmd=blocked_cmd))
            assert False, f"Expected PuffinSafetyViolation for opcode 0x{blocked_cmd:02X}"
        except PuffinSafetyViolation as e:
            assert f"0x{blocked_cmd:02X}" in str(e)
            assert "permanently blocked" in str(e)


def test_feature_flags_definition():
    assert len(PUFFIN_16_FEATURE_FLAGS) == 16
    flag_dict = dict(PUFFIN_16_FEATURE_FLAGS)
    assert flag_dict["enable_r22_packets"] == 2
    assert flag_dict["enable_r22_v4_packets"] == 1
    assert flag_dict["wear_detect_bias"] == 2
    assert flag_dict["make_hrfm_visible"] == 2
    assert flag_dict["enable_sig12"] == 2


if __name__ == "__main__":
    test_safety_blocked_opcodes()
    test_feature_flags_definition()
    print("ALL PUFFIN ENGINE SAFETY TESTS PASSED!")
