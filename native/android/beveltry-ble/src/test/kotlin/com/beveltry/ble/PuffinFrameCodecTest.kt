package com.beveltry.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class PuffinFrameCodecTest {
    private val hello = byteArrayOf(
        0xAA.toByte(), 1, 8, 0, 0, 1, 0xE6.toByte(), 0x71,
        0x23, 1, 0x91.toByte(), 1, 0x36, 0x3E, 0x5C, 0x8D.toByte(),
    )

    @Test fun knownHelloEncodeAndDecode() {
        assertArrayEquals(hello, PuffinFrameCodec.encode(1, byteArrayOf(0x23, 1, 0x91.toByte(), 1)))
        val frame = PuffinFrameCodec.decode(hello)
        assertEquals(1, frame.field)
        assertArrayEquals(byteArrayOf(0x23, 1, 0x91.toByte(), 1), frame.payload)
        assertArrayEquals(frame.payload, frame.rawPayload)
    }

    @Test fun oneBytePayloadPaddingAndMinimumFrame() {
        val encoded = PuffinFrameCodec.encode(1, byteArrayOf(0x23))
        assertEquals(16, encoded.size)
        assertEquals(8, PuffinFrameCodec.readU16(encoded, 2))
        assertArrayEquals(byteArrayOf(0x23, 0, 0, 0), encoded.copyOfRange(8, 12))
        assertArrayEquals(byteArrayOf(0x23), PuffinFrameCodec.decode(encoded).payload)
    }

    @Test fun emptyPayloadWouldMakeFrameTooShort() {
        val error = assertThrows(PuffinFrameException::class.java) { PuffinFrameCodec.encode(1, byteArrayOf()) }
        assertEquals(PuffinFrameException.ErrorCode.FRAME_TOO_SHORT, error.code)
    }

    @Test fun roundTrip() {
        val payload = byteArrayOf(0x10, 0x22, 0x33, 0x44, 0x55)
        val result = PuffinFrameCodec.decode(PuffinFrameCodec.encode(0x1234, payload))
        assertEquals(0x1234, result.field)
        assertArrayEquals(payload, result.payload)
    }

    @Test fun invalidSofAndVersion() {
        val badSof = hello.copyOf().also { it[0] = 0 }
        assertEquals(PuffinFrameException.ErrorCode.INVALID_SOF,
            assertThrows(PuffinFrameException::class.java) { PuffinFrameCodec.decode(badSof) }.code)
        val badVersion = hello.copyOf().also { it[1] = 2 }
        assertEquals(PuffinFrameException.ErrorCode.INVALID_VERSION,
            assertThrows(PuffinFrameException::class.java) { PuffinFrameCodec.decode(badVersion) }.code)
    }

    @Test fun invalidLengthAndChecksums() {
        val badLength = hello.copyOf().also { it[2] = 7 }
        assertEquals(PuffinFrameException.ErrorCode.INVALID_PAYLOAD_LENGTH,
            assertThrows(PuffinFrameException::class.java) { PuffinFrameCodec.decode(badLength) }.code)
        val badHeader = hello.copyOf().also { it[6] = (it[6].toInt() xor 1).toByte() }
        assertEquals(PuffinFrameException.ErrorCode.HEADER_CRC_INVALID,
            assertThrows(PuffinFrameException::class.java) { PuffinFrameCodec.decode(badHeader) }.code)
        val badPayload = hello.copyOf().also { it[8] = (it[8].toInt() xor 1).toByte() }
        assertEquals(PuffinFrameException.ErrorCode.PAYLOAD_CRC_INVALID,
            assertThrows(PuffinFrameException::class.java) { PuffinFrameCodec.decode(badPayload) }.code)
    }

    @Test fun reassemblesWholeFragmentedBackToBackAndAfterNoise() {
        val codec = PuffinFrameReassembler()
        assertEquals(1, codec.feed(hello).size)
        codec.reset()
        assertEquals(0, codec.feed(hello.copyOfRange(0, 4)).size)
        assertEquals(0, codec.feed(hello.copyOfRange(4, 11)).size)
        assertEquals(1, codec.feed(hello.copyOfRange(11, hello.size)).size)
        assertEquals(2, codec.feed(hello + hello).size)
        assertEquals(1, codec.feed(byteArrayOf(0, 0xFF.toByte(), 0xAA.toByte(), 0xAA.toByte()) + hello).size)
    }

    @Test fun waitsForCompleteHeaderBeforeCheckingHeaderCrc() {
        val codec = PuffinFrameReassembler()
        assertEquals(0, codec.feed(hello.copyOfRange(0, 6)).size)
        assertEquals(0, codec.feed(hello.copyOfRange(6, 8)).size)
        assertEquals(1, codec.feed(hello.copyOfRange(8, hello.size)).size)
    }

    @Test fun embeddedSofDoesNotCreateFalseFrameAndResetClearsState() {
        val codec = PuffinFrameReassembler()
        val embeddedPayload = byteArrayOf(0xAA.toByte(), 1, 0xAA.toByte(), 1)
        val encoded = PuffinFrameCodec.encode(1, embeddedPayload)
        assertEquals(1, codec.feed(encoded).size)
        codec.reset()
        assertEquals(0, codec.feed(hello.copyOfRange(0, 9)).size)
        codec.reset()
        assertEquals(0, codec.feed(hello.copyOfRange(9, hello.size)).size)
        assertEquals(1, codec.feed(hello).size)
    }
}
