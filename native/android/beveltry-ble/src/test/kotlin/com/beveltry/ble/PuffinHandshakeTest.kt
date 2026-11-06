package com.beveltry.ble

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private class MockPuffinTransport : PuffinTransport {
    private val incoming = Channel<Pair<PuffinFrame, PuffinCharacteristic>>(Channel.UNLIMITED)
    val writes = mutableListOf<Pair<ByteArray, PuffinCharacteristic>>()
    val subscriptions = mutableListOf<PuffinCharacteristic>()
    val flagFrames = mutableListOf<PuffinFrame>()
    val clockSetFrames = mutableListOf<PuffinFrame>()
    val ackFrames = mutableListOf<PuffinFrame>()
    var initialClock = 0u
    var clockWillLatch = true
    var failClockSet = false
    var failFlagName: String? = null
    var withholdHelloAck = false
    private var clockReads = 0
    private var latchedClock: UInt? = null

    override fun incomingFrames() = incoming.receiveAsFlow()

    override suspend fun subscribe(characteristic: PuffinCharacteristic) {
        subscriptions += characteristic
    }

    override suspend fun write(frame: ByteArray, characteristic: PuffinCharacteristic) {
        writes += frame to characteristic
        val decoded = PuffinFrameCodec.decode(frame)
        val raw = decoded.rawPayload
        if (raw.size < 3) return
        val seq = raw[1].toInt() and 0xFF
        val opcode = raw[2].toInt() and 0xFF
        when (opcode) {
            0x91 -> if (!withholdHelloAck) emitAck(seq, opcode, 1)
            0x0B -> {
                clockReads++
                val timestamp = when {
                    clockReads == 1 -> initialClock
                    clockWillLatch -> latchedClock ?: 0u
                    else -> 0u
                }
                val response = byteArrayOf(0x24, seq.toByte(), opcode.toByte(), 1) + timestamp.toLittleEndian() + byteArrayOf(0)
                emit(response, PuffinCharacteristic.CMD_FROM_STRAP)
            }
            0x0A -> {
                clockSetFrames += decoded
                latchedClock = readU32(raw, 4)
                emitAck(seq, opcode, if (failClockSet) 2 else 1)
            }
            0x73 -> emitAck(seq, opcode, 1)
            0x78 -> {
                flagFrames += decoded
                val nameBytes = raw.copyOfRange(4, 36).takeWhile { it != 0.toByte() }.toByteArray()
                val name = nameBytes.toString(Charsets.US_ASCII)
                emitAck(seq, opcode, if (name == failFlagName) 2 else 1)
            }
            0x22 -> emit(byteArrayOf(0x24, seq.toByte(), opcode.toByte(), 1, 0xAA.toByte()), PuffinCharacteristic.CMD_FROM_STRAP)
            0x16 -> {
                val metadata = ByteArray(24) { it.toByte() }
                metadata[0] = 0x31
                val cursor = byteArrayOf(0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87.toByte())
                cursor.copyInto(metadata, 13)
                emit(metadata, PuffinCharacteristic.DATA_FROM_STRAP)
            }
            0x17 -> ackFrames += decoded
        }
    }

    private suspend fun emitAck(seq: Int, opcode: Int, status: Int) {
        emit(byteArrayOf(0x24, seq.toByte(), opcode.toByte(), status.toByte()), PuffinCharacteristic.CMD_FROM_STRAP)
    }

    private suspend fun emit(payload: ByteArray, characteristic: PuffinCharacteristic) {
        val frame = PuffinFrameCodec.decode(PuffinFrameCodec.encode(1, payload))
        incoming.send(frame to characteristic)
    }

    private fun readU32(bytes: ByteArray, offset: Int): UInt =
        (bytes[offset].toUInt() and 0xFFu) or
            ((bytes[offset + 1].toUInt() and 0xFFu) shl 8) or
            ((bytes[offset + 2].toUInt() and 0xFFu) shl 16) or
            ((bytes[offset + 3].toUInt() and 0xFFu) shl 24)

    private fun UInt.toLittleEndian() = byteArrayOf(
        (this and 0xFFu).toByte(), (this shr 8 and 0xFFu).toByte(),
        (this shr 16 and 0xFFu).toByte(), (this shr 24 and 0xFFu).toByte(),
    )
}

private class MockHandshakeDelegate : PuffinHandshakeDelegate {
    val states = mutableListOf<HandshakeState>()
    val frames = mutableListOf<PuffinFrame>()
    val failures = mutableListOf<PuffinHandshakeError>()

    override fun didChangeState(handshake: PuffinHandshake, state: HandshakeState) { states += state }
    override fun didReceiveRawFrame(handshake: PuffinHandshake, frame: PuffinFrame) { frames += frame }
    override fun didFail(handshake: PuffinHandshake, error: PuffinHandshakeError) { failures += error }
}

class PuffinHandshakeTest {
    @Test fun happyPathRunsThroughFirstHistoricalCursorAck() = runBlocking {
        val transport = MockPuffinTransport()
        val handshake = PuffinHandshake(transport, timeoutMillis = 500)
        handshake.start()
        println("state = ${handshake.state}")
        println("frames sent = ${transport.writes.joinToString(" | ") { it.first.joinToString(" ") { byte -> "%02X".format(byte) } }}")
        assertEquals(HandshakeState.OffloadStarted, handshake.state)
        assertEquals(
            listOf(PuffinCharacteristic.CMD_FROM_STRAP, PuffinCharacteristic.EVENTS_FROM_STRAP, PuffinCharacteristic.DATA_FROM_STRAP),
            transport.subscriptions,
        )
        assertEquals(32, transport.flagFrames.size)
        assertEquals(1, transport.ackFrames.size)
        assertEquals(listOf(0xAA, 1, 8, 0, 0, 1, 0xE6, 0x71, 0x23, 1, 0x91, 1, 0x36, 0x3E, 0x5C, 0x8D),
            transport.writes.first().first.map { it.toInt() and 0xFF })
        assertEquals(byteArrayOf(0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87.toByte()).toList(),
            transport.ackFrames.single().rawPayload.copyOfRange(4, 12).toList())
        val expectedFlags = listOf(
            "enable_r22_packets" to 2, "enable_r22_v2_packets" to 2,
            "enable_r22_v3_packets" to 2, "enable_r22_v4_packets" to 1,
            "enable_r22_v5_packets" to 2, "enable_r22_v6_packets" to 2,
            "enable_r22_v8_packets" to 2, "make_hrfm_visible" to 2,
            "disable_pip_r26_packets" to 2, "wear_detect_bias" to 2,
            "hr_ch_switching" to 2, "ir_hw_switching" to 2,
            "enable_passive_strap_fit_gen5" to 1, "enable_sig11_during_sleep" to 2,
            "dorset_inhibit_wpt" to 2, "enable_sig12" to 2,
        )
        expectedFlags.forEachIndexed { index, (name, value) ->
            repeat(2) { duplicate ->
                val raw = transport.flagFrames[index * 2 + duplicate].rawPayload
                assertEquals(name, raw.copyOfRange(4, 36).takeWhile { it != 0.toByte() }.toByteArray().toString(Charsets.US_ASCII))
                assertEquals(value, raw[36].toInt() and 0xFF)
            }
        }
        val keyFrame = transport.writes.mapNotNull { runCatching { PuffinFrameCodec.decode(it.first) }.getOrNull() }
            .first { it.rawPayload.size == 40 && (it.rawPayload[2].toInt() and 0xFF) == 0x73 }
        assertEquals(0x01, keyFrame.rawPayload[4].toInt() and 0xFF)
        assertEquals(32, keyFrame.rawPayload.copyOfRange(5, 37).size)
        assertEquals(listOf(0, 0, 0), keyFrame.rawPayload.copyOfRange(37, 40).map { it.toInt() and 0xFF })
    }

    @Test fun validClockIsStillSetAndSetClockPayloadIsCorrect() = runBlocking {
        val transport = MockPuffinTransport().apply { initialClock = java.time.Instant.now().epochSecond.toUInt() }
        val handshake = PuffinHandshake(transport, timeoutMillis = 500)
        handshake.start()
        assertEquals(1, transport.clockSetFrames.size)
        val raw = transport.clockSetFrames.single().rawPayload
        assertEquals(listOf(0x23, raw[1].toInt() and 0xFF, 0x0A, 0x01), raw.copyOfRange(0, 4).map { it.toInt() and 0xFF })
        assertEquals(8, raw.size)
        val timestamp = raw.copyOfRange(4, 8).foldIndexed(0L) { index, value, byte ->
            value or ((byte.toLong() and 0xFF) shl (8 * index))
        }
        assertTrue(kotlin.math.abs(timestamp - java.time.Instant.now().epochSecond) <= 2)
        val expected = PuffinFrameCodec.encode(1, byteArrayOf(0x23, raw[1], 0x0A, 0x01) + raw.copyOfRange(4, 8))
        val wireFrame = transport.writes.map { it.first }.first { bytes ->
            PuffinFrameCodec.decode(bytes).rawPayload.let { it.size >= 3 && (it[2].toInt() and 0xFF) == 0x0A }
        }
        assertEquals(expected.toList(), wireFrame.toList())
    }

    @Test fun epochClockIsSetAndThenLatched() = runBlocking {
        val transport = MockPuffinTransport().apply { initialClock = 0u }
        val handshake = PuffinHandshake(transport, timeoutMillis = 500)
        handshake.start()
        assertEquals(HandshakeState.OffloadStarted, handshake.state)
        assertEquals(1, transport.clockSetFrames.size)
    }

    @Test fun getHelloTimeoutFailsHandshake() = runBlocking {
        val transport = MockPuffinTransport().apply { withholdHelloAck = true }
        val delegate = MockHandshakeDelegate()
        val handshake = PuffinHandshake(transport, delegate, timeoutMillis = 20)
        val error = runCatching { handshake.start() }.exceptionOrNull()
        assertTrue(error is PuffinHandshakeError.AckTimeout && error.opcode == 0x91)
        assertEquals(HandshakeState.Failed(PuffinHandshakeError.AckTimeout(0x91)), handshake.state)
        assertEquals(listOf(PuffinHandshakeError.AckTimeout(0x91)), delegate.failures)
    }

    @Test fun setClockStatusFailureIsReported() = runBlocking {
        val transport = MockPuffinTransport().apply { failClockSet = true }
        val handshake = PuffinHandshake(transport, timeoutMillis = 500)
        val error = runCatching { handshake.start() }.exceptionOrNull()
        assertEquals(PuffinHandshakeError.AckStatusFailure(0x0A, 2), error)
    }

    @Test fun flagFailureRetriesOnceThenReportsStatus() = runBlocking {
        val transport = MockPuffinTransport().apply { failFlagName = "enable_r22_packets" }
        val handshake = PuffinHandshake(transport, timeoutMillis = 500)
        val error = runCatching { handshake.start() }.exceptionOrNull()
        assertEquals(PuffinHandshakeError.AckStatusFailure(0x78, 2), error)
        assertEquals(2, transport.flagFrames.size)
    }

    @Test fun clockThatRemainsAtEpochDoesNotLatch() = runBlocking {
        val transport = MockPuffinTransport().apply { clockWillLatch = false }
        val handshake = PuffinHandshake(transport, timeoutMillis = 500)
        val error = runCatching { handshake.start() }.exceptionOrNull()
        assertEquals(PuffinHandshakeError.ClockNotLatched, error)
    }

    @Test fun firstMetadataCursorIsAcknowledged() = runBlocking {
        val transport = MockPuffinTransport()
        PuffinHandshake(transport, timeoutMillis = 500).start()
        val raw = transport.ackFrames.single().rawPayload
        assertEquals(listOf(0x23, raw[1].toInt() and 0xFF, 0x17, 0x01), raw.copyOfRange(0, 4).map { it.toInt() and 0xFF })
        assertEquals(listOf(0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87),
            raw.copyOfRange(4, 12).map { it.toInt() and 0xFF })
        val ackWire = transport.writes.last().first
        assertEquals(24, ackWire.size)
        assertEquals(16, PuffinFrameCodec.readU16(ackWire, 2))
    }

    @Test fun flagFrameHasExpectedLengthAndPadding() = runBlocking {
        val transport = MockPuffinTransport()
        PuffinHandshake(transport, timeoutMillis = 500).start()
        val first = transport.flagFrames.first()
        val rawFrame = transport.writes.map { it.first }.first { bytes ->
            val payload = PuffinFrameCodec.decode(bytes).rawPayload
            payload.size == 40 && (payload[2].toInt() and 0xFF) == 0x78
        }
        assertEquals(52, rawFrame.size)
        assertEquals(44, PuffinFrameCodec.readU16(rawFrame, 2))
        assertEquals(40, first.rawPayload.size)
        assertEquals("enable_r22_packets", first.rawPayload.copyOfRange(4, 36).takeWhile { it != 0.toByte() }.toByteArray().toString(Charsets.US_ASCII))
    }
}
