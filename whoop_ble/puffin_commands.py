"""
WHOOP Gen 5 ("Puffin" fd4b) High-Level Commands and Bootstrap Hardware Unlock.
Implements:
1. 0x91 GET_HELLO (Opens authenticated session)
2. 0x8D GET_ADVERTISING_NAME (Reads strap internal name)
3. 0x0B GET_CLOCK (Reads RTC Unix timestamp, verifies Latched vs 1970)
4. 0x1A GET_BATTERY (Reads proprietary battery state)
5. 0x73 KEY_EXCHANGE & 0x78 SET_FF_VALUE (16 Gen 5 Feature Flags)
6. 0x22 GET_DATA_RANGE (NAND Flash 512MB historical data range)
7. 0x16 SEND_HISTORICAL & 0x17 HISTORICAL_DATA_RESULT (Auto-ACK cursor offload)
8. 0x42 ALARM_CONTROL (Optional vibration / alarm control)
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from whoop_ble.constants import (
    CMD_GET_CLOCK,
    CMD_SEND_HISTORICAL,
    CMD_HISTORICAL_DATA_RESULT,
    CMD_GET_BATTERY,
    CMD_GET_DATA_RANGE,
    CMD_ALARM_CONTROL,
    CMD_KEY_EXCHANGE,
    CMD_SET_FF_VALUE,
    CMD_GET_ADVERTISING_NAME,
    CMD_GET_HELLO,
    PUFFIN_16_FEATURE_FLAGS,
)
from whoop_ble.puffin_engine import PuffinEngine


class PuffinDeviceController:
    def __init__(self, engine: PuffinEngine):
        self.engine = engine

    async def get_hello(self, b3: int = 0x01) -> Dict[str, Any]:
        """
        0x91 GET_HELLO: Opens the authenticated session.
        """
        resp = await self.engine.send_command(cmd=CMD_GET_HELLO, b3=b3, timeout=3.0)
        return resp

    async def get_advertising_name(self, b3: int = 0x01) -> str:
        """
        0x8D GET_ADVERTISING_NAME: Reads the internal broadcast name.
        """
        resp = await self.engine.send_command(cmd=CMD_GET_ADVERTISING_NAME, b3=b3, timeout=3.0)
        return resp.get("parsed", {}).get("advertising_name", "")

    async def get_clock(self) -> Dict[str, Any]:
        """
        0x0B GET_CLOCK: Reads RTC Unix timestamp and checks if clock is Latched.
        Tries b3=0x01 first, fallback to b3=0x00 if needed.
        """
        try:
            resp = await self.engine.send_command(cmd=CMD_GET_CLOCK, b3=0x01, timeout=3.0)
            if resp.get("is_success"):
                return resp.get("parsed", {})
        except Exception:
            pass

        resp = await self.engine.send_command(cmd=CMD_GET_CLOCK, b3=0x00, timeout=3.0)
        return resp.get("parsed", {})

    async def get_battery(self) -> Dict[str, Any]:
        """
        0x1A GET_BATTERY: Reads battery details via proprietary channel.
        Tries b3=0x01 first, fallback to b3=0x00.
        """
        try:
            resp = await self.engine.send_command(cmd=CMD_GET_BATTERY, b3=0x01, timeout=3.0)
            if resp.get("is_success"):
                return resp.get("parsed", {})
        except Exception:
            pass

        resp = await self.engine.send_command(cmd=CMD_GET_BATTERY, b3=0x00, timeout=3.0)
        return resp.get("parsed", {})

    async def key_exchange(self, b3: int = 0x01) -> Dict[str, Any]:
        """
        0x73 KEY_EXCHANGE: Initiates / checks key exchange state.
        """
        try:
            resp = await self.engine.send_command(cmd=CMD_KEY_EXCHANGE, b3=b3, timeout=3.0)
            return resp
        except Exception as e:
            return {"status": "KEY_EXCHANGE_NOT_ACCEPTED_OR_NOT_REQUIRED", "error": str(e)}

    async def set_feature_flag(self, flag_name: str, value: int, b3: int = 0x01) -> Dict[str, Any]:
        """
        0x78 SET_FF_VALUE: Sets a feature flag on the strap.
        Payload format: 32 bytes ASCII name (0x00 padded) + 1 byte value (u8).
        """
        name_bytes = flag_name.encode("ascii").ljust(32, b"\x00")
        val_bytes = bytes([value & 0xFF])
        params = name_bytes + val_bytes

        resp = await self.engine.send_command(cmd=CMD_SET_FF_VALUE, b3=b3, params=params, timeout=3.0)
        return resp

    async def unlock_16_feature_flags(self) -> Dict[str, Any]:
        """
        Applies all 16 Gen 5 Feature Flags in sequence:
        enable_r22_packets=2, enable_r22_v2_packets=2, enable_r22_v3_packets=2,
        enable_r22_v4_packets=1, enable_r22_v5_packets=2, enable_r22_v6_packets=2,
        enable_r22_v8_packets=2, make_hrfm_visible=2, disable_pip_r26_packets=2,
        wear_detect_bias=2, hr_ch_switching=2, ir_hw_switching=2,
        enable_passive_strap_fit_gen5=1, enable_sig11_during_sleep=2,
        dorset_inhibit_wpt=2, enable_sig12=2.
        """
        results: Dict[str, Any] = {}
        successful_flags = 0

        for flag_name, flag_val in PUFFIN_16_FEATURE_FLAGS:
            try:
                resp = await self.set_feature_flag(flag_name, flag_val, b3=0x01)
                is_ok = resp.get("is_success", False)
                results[flag_name] = {
                    "value": flag_val,
                    "applied": is_ok,
                    "status_code": resp.get("status_code"),
                }
                if is_ok:
                    successful_flags += 1
            except Exception as e:
                results[flag_name] = {
                    "value": flag_val,
                    "applied": False,
                    "error": str(e),
                }

        return {
            "total_flags": len(PUFFIN_16_FEATURE_FLAGS),
            "successfully_applied": successful_flags,
            "flags": results,
        }

    async def get_data_range(self, b3: int = 0x00) -> Dict[str, Any]:
        """
        0x22 GET_DATA_RANGE: Queries start/end historical records stored in 512MB NAND flash.
        """
        resp = await self.engine.send_command(cmd=CMD_GET_DATA_RANGE, b3=b3, timeout=3.0)
        return resp.get("parsed", {})

    async def trigger_historical_offload(self, b3: int = 0x00, params: bytes = b"") -> Dict[str, Any]:
        """
        0x16 SEND_HISTORICAL: Initiates historical streaming from flash over fd4b0005.
        Auto-ACK is handled automatically in PuffinEngine when 0x31 arrives.
        """
        resp = await self.engine.send_command(cmd=CMD_SEND_HISTORICAL, b3=b3, params=params, timeout=3.0)
        return resp

    async def send_alarm_vibration(self, pattern: int = 1, duration_ms: int = 1000) -> Dict[str, Any]:
        """
        0x42 ALARM_CONTROL: Optional strap vibration test.
        """
        params = bytes([pattern & 0xFF]) + (duration_ms & 0xFFFF).to_bytes(2, "little")
        try:
            resp = await self.engine.send_command(cmd=CMD_ALARM_CONTROL, b3=0x01, params=params, timeout=3.0)
            return resp
        except Exception as e:
            return {"status": "ALARM_CMD_FAILED", "error": str(e)}

    async def run_full_bootstrap_unlock(self) -> Dict[str, Any]:
        """
        Executes the full Task 02 Hardware Unlock Sequence:
        1. Subscribes to all notification endpoints
        2. 0x91 GET_HELLO (Opens authenticated session)
        3. 0x8D GET_ADVERTISING_NAME (Reads strap name)
        4. 0x0B GET_CLOCK (Checks RTC Unix timestamp and Clock Latched state)
        5. 0x1A GET_BATTERY (Reads proprietary battery details)
        6. 0x78 SET_FF_VALUE (Activates all 16 Feature Flags)
        7. 0x22 GET_DATA_RANGE (Reads 512MB NAND Flash data range)
        """
        report: Dict[str, Any] = {
            "status": "STARTING_HARDWARE_UNLOCK",
            "session_opened": False,
            "advertising_name": None,
            "clock": {},
            "battery": {},
            "feature_flags": {},
            "data_range": {},
        }

        # Step 1: Subscriptions
        await self.engine.subscribe_all()

        # Step 2: 0x91 GET_HELLO
        try:
            hello_resp = await self.get_hello(b3=0x01)
            report["session_opened"] = hello_resp.get("is_success", False)
            report["hello_response"] = hello_resp
        except Exception as e:
            report["hello_error"] = str(e)

        # Step 3: 0x8D GET_ADVERTISING_NAME
        try:
            name = await self.get_advertising_name(b3=0x01)
            report["advertising_name"] = name
        except Exception as e:
            report["advertising_name_error"] = str(e)

        # Step 4: 0x0B GET_CLOCK
        try:
            clk = await self.get_clock()
            report["clock"] = clk
        except Exception as e:
            report["clock_error"] = str(e)

        # Step 5: 0x1A GET_BATTERY
        try:
            bat = await self.get_battery()
            report["battery"] = bat
        except Exception as e:
            report["battery_error"] = str(e)

        # Step 6: 16 Feature Flags
        try:
            ff_result = await self.unlock_16_feature_flags()
            report["feature_flags"] = ff_result
        except Exception as e:
            report["feature_flags_error"] = str(e)

        # Step 7: 0x22 GET_DATA_RANGE
        try:
            dr = await self.get_data_range(b3=0x00)
            report["data_range"] = dr
        except Exception as e:
            report["data_range_error"] = str(e)

        report["status"] = "HARDWARE_UNLOCK_COMPLETED"
        return report
