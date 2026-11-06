package com.beveltry.ble

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import java.time.Instant
import java.security.SecureRandom

sealed interface HandshakeState {
    data object Idle : HandshakeState
    data object Connecting : HandshakeState
    data object Bonding : HandshakeState
    data object Subscribing : HandshakeState
    data object SendingHello : HandshakeState
    data object ReadingClock : HandshakeState
    data object SettingClock : HandshakeState
    data object VerifyingClock : HandshakeState
    data object KeyExchange : HandshakeState
    data class SettingFlags(val current: Int, val total: Int) : HandshakeState
    data object QueryingRange : HandshakeState
    data object StartingHistorical : HandshakeState
    data object Ready : HandshakeState
    data object OffloadStarted : HandshakeState
    data class Failed(val error: PuffinHandshakeError) : HandshakeState
}

sealed class PuffinHandshakeError(message: String) : Exception(message) {
    data class AckTimeout(val opcode: Int) : PuffinHandshakeError("Timeout ACK opcode 0x${opcode.toString(16)}")
    data class AckStatusFailure(val opcode: Int, val status: Int) :
        PuffinHandshakeError("ACK opcode 0x${opcode.toString(16)} con status 0x${status.toString(16)}")
    data object ClockNotLatched : PuffinHandshakeError("Il clock del cinturino non è stato aggiornato")
    data class UnexpectedResponse(val opcode: Int) :
        PuffinHandshakeError("Risposta inattesa opcode 0x${opcode.toString(16)}")
    data object Cancelled : PuffinHandshakeError("Handshake annullato")
    data class TransportFailure(val reason: String) : PuffinHandshakeError(reason)
}

interface PuffinHandshakeDelegate {
    fun didChangeState(handshake: PuffinHandshake, state: HandshakeState)
    fun didReceiveRawFrame(handshake: PuffinHandshake, frame: PuffinFrame)
    fun didFail(handshake: PuffinHandshake, error: PuffinHandshakeError)
}

class PuffinHandshake(
    private val transport: PuffinTransport,
    private val delegate: PuffinHandshakeDelegate? = null,
    private val timeoutMillis: Long = 3_000,
) {
    @Volatile var state: HandshakeState = HandshakeState.Idle
        private set

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val random = SecureRandom()
    private var sequence = 1
    private var operation: Deferred<Unit>? = null
    private var didReportFailure = false

    private val flags = listOf(
        "enable_r22_packets" to 2,
        "enable_r22_v2_packets" to 2,
        "enable_r22_v3_packets" to 2,
        "enable_r22_v4_packets" to 1,
        "enable_r22_v5_packets" to 2,
        "enable_r22_v6_packets" to 2,
        "enable_r22_v8_packets" to 2,
        "make_hrfm_visible" to 2,
        "disable_pip_r26_packets" to 2,
        "wear_detect_bias" to 2,
        "hr_ch_switching" to 2,
        "ir_hw_switching" to 2,
        "enable_passive_strap_fit_gen5" to 1,
        "enable_sig11_during_sleep" to 2,
        "dorset_inhibit_wpt" to 2,
        "enable_sig12" to 2,
    )

    /** Il trasporto deve essere già connesso e bonded prima di chiamare start(). */
    suspend fun start() {
        check(state == HandshakeState.Idle) { "Handshake già avviato" }
        val task = scope.async { run() }
        operation = task
        try {
            task.await()
        } catch (error: PuffinHandshakeError) {
            fail(error)
            throw error
        } catch (_: CancellationException) {
            fail(PuffinHandshakeError.Cancelled)
            throw PuffinHandshakeError.Cancelled
        } catch (error: Throwable) {
            val failure = PuffinHandshakeError.TransportFailure(error.message ?: error.toString())
            fail(failure)
            throw failure
        } finally {
            operation = null
            scope.cancel()
        }
    }

    fun cancel() {
        operation?.cancel(CancellationException("Richiesta di annullamento"))
    }

    private suspend fun run() {
        val inbox = Channel<Pair<PuffinFrame, PuffinCharacteristic>>(Channel.UNLIMITED)
        val collector = scope.launch {
            transport.incomingFrames().collect { inbox.send(it) }
        }
        try {
            transition(HandshakeState.Subscribing)
            transport.subscribe(PuffinCharacteristic.CMD_FROM_STRAP)
            transport.subscribe(PuffinCharacteristic.EVENTS_FROM_STRAP)
            transport.subscribe(PuffinCharacteristic.DATA_FROM_STRAP)

            transition(HandshakeState.SendingHello)
            val helloSequence = nextSequence()
            sendAndAcknowledge(byteArrayOf(0x23, helloSequence.toByte(), 0x91.toByte(), 0x01), 0x91, helloSequence, inbox)

            transition(HandshakeState.ReadingClock)
            readClock(inbox)

            transition(HandshakeState.SettingClock)
            val setTimestamp = Instant.now().epochSecond.toUInt()
            val clockSequence = nextSequence()
            val clockPayload = byteArrayOf(0x23, clockSequence.toByte(), 0x0A, 0x01) + setTimestamp.toLittleEndian()
            sendAndAcknowledge(clockPayload, 0x0A, clockSequence, inbox)

            transition(HandshakeState.VerifyingClock)
            val verifiedClock = readClock(inbox)
            if (verifiedClock != setTimestamp && verifiedClock != setTimestamp + 1u) {
                throw PuffinHandshakeError.ClockNotLatched
            }

            transition(HandshakeState.KeyExchange)
            val keySequence = nextSequence()
            val keyPayload = byteArrayOf(0x23, keySequence.toByte(), 0x73, 0x01, 0x01) + ByteArray(32).also(random::nextBytes)
            sendAndAcknowledge(keyPayload, 0x73, keySequence, inbox)

            flags.forEachIndexed { index, (name, value) ->
                transition(HandshakeState.SettingFlags(index + 1, flags.size))
                repeat(2) {
                    val flagSequence = nextSequence()
                    val nameBytes = name.encodeToByteArray().take(32).toByteArray()
                    val payload = byteArrayOf(0x23, flagSequence.toByte(), 0x78, 0x01) +
                        nameBytes + ByteArray(32 - nameBytes.size) + byteArrayOf(value.toByte())
                    sendAndAcknowledge(payload, 0x78, flagSequence, inbox, retryOnce = true)
                }
            }

            transition(HandshakeState.QueryingRange)
            val rangeSequence = nextSequence()
            transport.write(encode(byteArrayOf(0x23, rangeSequence.toByte(), 0x22, 0x00)), PuffinCharacteristic.CMD_TO_STRAP)
            waitForResponse(0x22, rangeSequence, inbox)

            transition(HandshakeState.Ready)
            transition(HandshakeState.StartingHistorical)
            val historicalSequence = nextSequence()
            transport.write(encode(byteArrayOf(0x23, historicalSequence.toByte(), 0x16, 0x00)), PuffinCharacteristic.CMD_TO_STRAP)
            val metadata = waitForFirstMetadata(inbox)
            if (metadata.rawPayload.size < 21) throw PuffinHandshakeError.UnexpectedResponse(0x31)

            val ackSequence = nextSequence()
            val cursor = metadata.rawPayload.copyOfRange(13, 21)
            val ackPayload = byteArrayOf(0x23, ackSequence.toByte(), 0x17, 0x01) + cursor
            transport.write(encode(ackPayload), PuffinCharacteristic.CMD_TO_STRAP)
            transition(HandshakeState.OffloadStarted)
        } catch (error: PuffinHandshakeError) {
            fail(error)
            throw error
        } catch (_: CancellationException) {
            fail(PuffinHandshakeError.Cancelled)
            throw PuffinHandshakeError.Cancelled
        } catch (error: Throwable) {
            val failure = PuffinHandshakeError.TransportFailure(error.message ?: error.toString())
            fail(failure)
            throw failure
        } finally {
            collector.cancel()
            inbox.close()
        }
    }

    private suspend fun readClock(inbox: Channel<Pair<PuffinFrame, PuffinCharacteristic>>): UInt {
        val seq = nextSequence()
        val response = sendAndAcknowledge(
            byteArrayOf(0x23, seq.toByte(), 0x0B, 0x00), 0x0B, seq, inbox, returnFrame = true,
        ) ?: throw PuffinHandshakeError.UnexpectedResponse(0x0B)
        val bytes = response.rawPayload
        if (bytes.size < 8) throw PuffinHandshakeError.UnexpectedResponse(0x0B)
        if ((bytes[3].toInt() and 0xFF) != 0x01) {
            throw PuffinHandshakeError.AckStatusFailure(0x0B, bytes[3].toInt() and 0xFF)
        }
        return (bytes[4].toUInt() and 0xFFu) or
            ((bytes[5].toUInt() and 0xFFu) shl 8) or
            ((bytes[6].toUInt() and 0xFFu) shl 16) or
            ((bytes[7].toUInt() and 0xFFu) shl 24)
    }

    private suspend fun sendAndAcknowledge(
        payload: ByteArray,
        opcode: Int,
        seq: Int,
        inbox: Channel<Pair<PuffinFrame, PuffinCharacteristic>>,
        retryOnce: Boolean = false,
        returnFrame: Boolean = false,
    ): PuffinFrame? {
        val frame = encode(payload)
        var lastError: PuffinHandshakeError = PuffinHandshakeError.AckTimeout(opcode)
        repeat(if (retryOnce) 2 else 1) { attempt ->
            if (attempt > 0) kotlinx.coroutines.currentCoroutineContext().ensureActive()
            transport.write(frame, PuffinCharacteristic.CMD_TO_STRAP)
            try {
                val response = waitForResponse(opcode, seq, inbox)
                val status = response.rawPayload.getOrNull(3)?.toInt()?.and(0xFF) ?: 0
                if (status != 0x01) {
                    lastError = PuffinHandshakeError.AckStatusFailure(opcode, status)
                    if (retryOnce && attempt == 0) return@repeat
                    throw lastError
                }
                return if (returnFrame) response else null
            } catch (error: PuffinHandshakeError) {
                lastError = error
                if (!retryOnce || attempt > 0) throw error
            }
        }
        throw lastError
    }

    private suspend fun waitForResponse(
        opcode: Int,
        seq: Int,
        inbox: Channel<Pair<PuffinFrame, PuffinCharacteristic>>,
    ): PuffinFrame {
        while (true) {
            val (frame, characteristic) = nextIncoming(opcode, inbox)
            delegate?.didReceiveRawFrame(this, frame)
            val bytes = frame.rawPayload
            if (characteristic != PuffinCharacteristic.CMD_FROM_STRAP || bytes.size < 3 ||
                (bytes[0].toInt() and 0xFF) != 0x24 || (bytes[1].toInt() and 0xFF) != seq
            ) continue
            val responseOpcode = bytes[2].toInt() and 0xFF
            if (responseOpcode != opcode) throw PuffinHandshakeError.UnexpectedResponse(responseOpcode)
            return frame
        }
    }

    private suspend fun waitForFirstMetadata(
        inbox: Channel<Pair<PuffinFrame, PuffinCharacteristic>>,
    ): PuffinFrame {
        while (true) {
            val (frame, characteristic) = nextIncoming(0x31, inbox)
            delegate?.didReceiveRawFrame(this, frame)
            if (characteristic == PuffinCharacteristic.DATA_FROM_STRAP && frame.rawPayload.firstOrNull()?.toInt()?.and(0xFF) == 0x31) {
                return frame
            }
        }
    }

    private suspend fun nextIncoming(
        opcode: Int,
        inbox: Channel<Pair<PuffinFrame, PuffinCharacteristic>>,
    ): Pair<PuffinFrame, PuffinCharacteristic> = try {
        withTimeout(timeoutMillis.coerceAtLeast(1)) { inbox.receive() }
    } catch (_: kotlinx.coroutines.TimeoutCancellationException) {
        throw PuffinHandshakeError.AckTimeout(opcode)
    }

    private fun encode(payload: ByteArray): ByteArray = PuffinFrameCodec.encode(1, payload)

    private fun nextSequence(): Int {
        val current = sequence
        sequence = if (sequence == 0xFF) 1 else sequence + 1
        return current
    }

    private fun transition(newState: HandshakeState) {
        state = newState
        delegate?.didChangeState(this, newState)
    }

    private fun fail(error: PuffinHandshakeError) {
        if (didReportFailure) return
        didReportFailure = true
        transition(HandshakeState.Failed(error))
        delegate?.didFail(this, error)
    }

    private fun UInt.toLittleEndian(): ByteArray = byteArrayOf(
        (this and 0xFFu).toByte(), (this shr 8 and 0xFFu).toByte(),
        (this shr 16 and 0xFFu).toByte(), (this shr 24 and 0xFFu).toByte(),
    )
}
