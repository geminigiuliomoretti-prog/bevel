package com.beveltry.ble

class PuffinFrameException(message: String, val code: ErrorCode) : Exception(message) {
    enum class ErrorCode {
        INVALID_SOF, INVALID_VERSION, INVALID_PAYLOAD_LENGTH,
        FRAME_TOO_SHORT, HEADER_CRC_INVALID, PAYLOAD_CRC_INVALID,
    }
}

object PuffinFrameCodec {
    private const val HEADER_SIZE = 8

    @Throws(PuffinFrameException::class)
    fun encode(field: Int, payload: ByteArray): ByteArray {
        if (field !in 0..0xFFFF) invalidLength("field fuori intervallo u16")
        val paddedLength = (payload.size + 3) and 3.inv()
        val payloadLength = paddedLength + 4 // payload paddato più CRC32
        if (payloadLength > 0xFFFF) invalidLength("payload troppo grande")
        if (HEADER_SIZE + payloadLength <= 15) tooShort()

        val rawPayload = payload.copyOf(paddedLength)
        val frame = ByteArray(HEADER_SIZE + payloadLength)
        frame[0] = 0xAA.toByte()
        frame[1] = 0x01
        putU16(frame, 2, payloadLength)
        putU16(frame, 4, field)
        putU16(frame, 6, CRC.crc16Modbus(frame.copyOfRange(0, 6)))
        rawPayload.copyInto(frame, HEADER_SIZE)
        putU32(frame, HEADER_SIZE + paddedLength, CRC.crc32IEEE(rawPayload))
        return frame
    }

    @Throws(PuffinFrameException::class)
    fun decode(frame: ByteArray): PuffinFrame {
        if (frame.size < 2) tooShort()
        if ((frame[0].toInt() and 0xFF) != 0xAA) {
            throw PuffinFrameException("SOF non valido", PuffinFrameException.ErrorCode.INVALID_SOF)
        }
        if ((frame[1].toInt() and 0xFF) != 0x01) {
            throw PuffinFrameException("Versione non valida", PuffinFrameException.ErrorCode.INVALID_VERSION)
        }
        if (frame.size < HEADER_SIZE) tooShort()

        val payloadLength = readU16(frame, 2)
        if (payloadLength < 4 || payloadLength % 4 != 0) invalidLength("payloadLen non valido")
        if (HEADER_SIZE + payloadLength <= 15 || frame.size != HEADER_SIZE + payloadLength) tooShort()

        val expectedHeader = CRC.crc16Modbus(frame.copyOfRange(0, 6))
        val actualHeader = readU16(frame, 6)
        if (expectedHeader != actualHeader) {
            throw PuffinFrameException("CRC16 header non valido", PuffinFrameException.ErrorCode.HEADER_CRC_INVALID)
        }

        val paddedLength = payloadLength - 4
        val rawPayload = frame.copyOfRange(HEADER_SIZE, HEADER_SIZE + paddedLength)
        val expectedPayload = CRC.crc32IEEE(rawPayload)
        val actualPayload = readU32(frame, HEADER_SIZE + paddedLength)
        if (expectedPayload != actualPayload) {
            throw PuffinFrameException("CRC32 payload non valido", PuffinFrameException.ErrorCode.PAYLOAD_CRC_INVALID)
        }

        var logicalLength = rawPayload.size
        while (logicalLength > 0 && rawPayload[logicalLength - 1] == 0.toByte()) logicalLength--
        return PuffinFrame(
            field = readU16(frame, 4), payload = rawPayload.copyOf(logicalLength),
            rawPayload = rawPayload, headerCRC = actualHeader, payloadCRC = actualPayload,
        )
    }

    internal fun readU16(bytes: ByteArray, offset: Int): Int =
        (bytes[offset].toInt() and 0xFF) or ((bytes[offset + 1].toInt() and 0xFF) shl 8)

    private fun readU32(bytes: ByteArray, offset: Int): Long =
        (bytes[offset].toLong() and 0xFF) or
            ((bytes[offset + 1].toLong() and 0xFF) shl 8) or
            ((bytes[offset + 2].toLong() and 0xFF) shl 16) or
            ((bytes[offset + 3].toLong() and 0xFF) shl 24)

    private fun putU16(bytes: ByteArray, offset: Int, value: Int) {
        bytes[offset] = value.toByte()
        bytes[offset + 1] = (value ushr 8).toByte()
    }

    private fun putU32(bytes: ByteArray, offset: Int, value: Long) {
        repeat(4) { bytes[offset + it] = (value ushr (8 * it)).toByte() }
    }

    private fun invalidLength(message: String): Nothing = throw PuffinFrameException(
        message, PuffinFrameException.ErrorCode.INVALID_PAYLOAD_LENGTH,
    )

    private fun tooShort(): Nothing = throw PuffinFrameException(
        "Frame troppo corto o lunghezza totale incoerente", PuffinFrameException.ErrorCode.FRAME_TOO_SHORT,
    )
}

class PuffinFrameReassembler {
    private var buffer = ByteArray(0)

    fun reset() { buffer = ByteArray(0) }

    fun feed(chunk: ByteArray): List<PuffinFrame> {
        buffer += chunk
        val frames = mutableListOf<PuffinFrame>()
        while (true) {
            val start = findSof(buffer)
            if (start < 0) {
                buffer = if (buffer.lastOrNull()?.toInt()?.and(0xFF) == 0xAA) byteArrayOf(0xAA.toByte()) else ByteArray(0)
                break
            }
            if (start > 0) buffer = buffer.copyOfRange(start, buffer.size)
            if (buffer.size < 2) break
            if ((buffer[1].toInt() and 0xFF) != 0x01) { discardSof(); continue }
            if (buffer.size < 8) break

            val payloadLength = PuffinFrameCodec.readU16(buffer, 2)
            if (payloadLength < 4 || payloadLength % 4 != 0) { discardSof(); continue }
            val headerCRC = CRC.crc16Modbus(buffer.copyOfRange(0, 6))
            if (headerCRC != PuffinFrameCodec.readU16(buffer, 6)) { discardSof(); continue }
            val totalLength = 8 + payloadLength
            if (totalLength <= 15) { discardSof(); continue }
            if (buffer.size < totalLength) break

            val candidate = buffer.copyOfRange(0, totalLength)
            try {
                frames += PuffinFrameCodec.decode(candidate)
                buffer = buffer.copyOfRange(totalLength, buffer.size)
            } catch (_: PuffinFrameException) {
                // CRC32 errato: riparte dal byte successivo al SOF per cercare un frame valido.
                discardSof()
            }
        }
        return frames
    }

    private fun discardSof() { buffer = buffer.copyOfRange(1, buffer.size) }

    private fun findSof(bytes: ByteArray): Int {
        for (index in 0 until bytes.size - 1) {
            if ((bytes[index].toInt() and 0xFF) == 0xAA && (bytes[index + 1].toInt() and 0xFF) == 0x01) return index
        }
        return -1
    }
}
