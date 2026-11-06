package com.beveltry.ble

import org.junit.Assert.assertEquals
import org.junit.Test

class CRCTest {
    @Test fun knownCrcValues() {
        val input = "123456789".toByteArray(Charsets.US_ASCII)
        assertEquals(0x4B37, CRC.crc16Modbus(input))
        assertEquals(0xCBF43926L, CRC.crc32IEEE(input))
    }

    @Test fun clientHelloHeaderCRC() {
        val header = byteArrayOf(0xAA.toByte(), 1, 8, 0, 0, 1)
        assertEquals(0x71E6, CRC.crc16Modbus(header))
    }
}
