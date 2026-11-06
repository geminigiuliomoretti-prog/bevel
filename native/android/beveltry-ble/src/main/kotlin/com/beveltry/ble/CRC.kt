package com.beveltry.ble

import java.util.zip.CRC32

object CRC {
    /** CRC-16/MODBUS (polinomio riflesso A001, init FFFF). */
    fun crc16Modbus(bytes: ByteArray): Int {
        var crc = 0xFFFF
        for (byte in bytes) {
            crc = crc xor (byte.toInt() and 0xFF)
            repeat(8) { crc = if ((crc and 1) != 0) (crc ushr 1) xor 0xA001 else crc ushr 1 }
        }
        return crc and 0xFFFF
    }

    /** CRC-32 IEEE/zlib usato nel trailer. */
    fun crc32IEEE(bytes: ByteArray): Long = CRC32().run { update(bytes); value }
}
