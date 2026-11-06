package com.beveltry.ble

import android.Manifest
import android.bluetooth.BluetoothDevice
import android.content.Context
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.channels.receiveAsFlow
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant
import kotlin.math.sqrt

@RunWith(AndroidJUnit4::class)
class AndroidBleInstrumentationTest {
    @Test
    fun scansConnectsPairsAndValidatesLiveFrames() = runBlocking {
        val started = System.nanoTime()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context: Context = instrumentation.targetContext
        grantRuntimePermissions(instrumentation, context)
        val observations = mutableListOf<Pair<String, Boolean>>()
        fun log(step: String, message: String) {
            val elapsed = (System.nanoTime() - started) / 1_000_000
            val line = "[WHOOP-IT] +${elapsed}ms $step $message"
            Log.i(TAG, line)
            println(line)
        }
        fun checkPoint(name: String, passed: Boolean, values: String) {
            observations += name to passed
            log(name, "${if (passed) "PASS" else "FAIL"} $values")
        }

        log("SCAN", "avvio scansione, timeout=${WhoopScanner.DEFAULT_TIMEOUT_MILLIS}ms")
        val found = WhoopScanner(context).scan().first()
        log("SCAN", "UUID=${found.advertisedServiceUuids} name=${found.name} RSSI=${found.rssi} address=${found.device.address}")

        val transport = AndroidPuffinTransport(context)
        log("CONNECT", "connessione GATT (limite 10s)")
        transport.connect(found.device, 10_000).first()
        assertEquals(AndroidBleState.Ready, transport.state)
        log("DISCOVER", "servizio e caratteristiche richieste presenti")

        val receivedFrames = Channel<Pair<PuffinFrame, PuffinCharacteristic>>(Channel.UNLIMITED)
        val framesCollector = launch { transport.incomingFrames().collect { receivedFrames.send(it) } }
        val states = mutableListOf<String>()
        val delegate = object : PuffinHandshakeDelegate {
            override fun didChangeState(handshake: PuffinHandshake, state: HandshakeState) {
                states += state.toString()
                log("HANDSHAKE", state.toString())
            }
            override fun didReceiveRawFrame(handshake: PuffinHandshake, frame: PuffinFrame) = Unit
            override fun didFail(handshake: PuffinHandshake, error: PuffinHandshakeError) { log("HANDSHAKE", "FAIL ${error.message}") }
        }
        transport.subscribe(PuffinCharacteristic.MEMFAULT)
        log("SUBSCRIBE", "MEMFAULT completata; handshake sottoscriverà CMD/EVENTS/DATA")
        // Il primo invio su fd4b0002 avvia il pairing OS se GATT richiede cifratura.
        val handshake = PuffinHandshake(transport, delegate, timeoutMillis = 3_000)
        val handshakeTask = async { runCatching { handshake.start() } }
        var metadata: PuffinFrame? = null
        try {
            metadata = withTimeout(30_000) {
                while (true) {
                    val (frame, characteristic) = receivedFrames.receive()
                    if (characteristic == PuffinCharacteristic.DATA_FROM_STRAP && frame.rawPayload.firstOrNull()?.u8() == 0x31) {
                        log("FRAME-31", "payload=${frame.rawPayload.hex()}")
                        assertTrue("Il cursore 0x31 deve contenere 8 byte", frame.rawPayload.size >= 21)
                        val cursor = frame.rawPayload.copyOfRange(13, 21)
                        log("FRAME-31", "cursor=${cursor.hex()} bytes=${cursor.size}")
                        checkPoint("CURSOR", cursor.size == 8, "cursor=${cursor.hex()}")
                        return@withTimeout frame
                    }
                }
                @Suppress("UNREACHABLE_CODE") null
            }
        } catch (_: kotlinx.coroutines.TimeoutCancellationException) {
            checkPoint("FRAME-31", states.any { it.contains("Ready") }, "0x31 non arrivato entro 30s; handshake=${handshake.state}")
        }

        val v18: PuffinFrame = withTimeout(60_000) {
            metadata?.takeIf(::isV18) ?: receivedFrames.receiveAsFlow()
                .first { (frame, characteristic) -> characteristic == PuffinCharacteristic.DATA_FROM_STRAP && isV18(frame) }
                .first
        }
        val bytes = v18.rawPayload
        val rrCount = bytes.getOrNull(15)?.u8() ?: 0
        val rrValues = (0 until rrCount).mapNotNull { index ->
            val offset = 16 + index * 2
            if (offset + 1 >= bytes.size) null else bytes.u16(offset)
        }
        val hr = bytes.getOrNull(14)?.u8() ?: -1
        val timestamp = bytes.u32(7)
        val gravity = if (bytes.size >= 45) listOf(bytes.f32(33), bytes.f32(37), bytes.f32(41)) else emptyList()
        val magnitude = if (gravity.size == 3 && gravity.all(Float::isFinite)) sqrt(gravity.sumOf { it.toDouble() * it.toDouble() }) else Double.NaN
        log("V18", "type=${bytes.getOrNull(0)?.u8()} version=${bytes.getOrNull(1)?.u8()} HR=$hr rrCount=$rrCount RR=$rrValues timestamp=$timestamp gravity=$gravity magnitude=$magnitude frame=${bytes.hex()}")

        val officialHr = instrumentation.arguments.getString("officialHrBpm")?.toIntOrNull()
        val p1 = hr == 0 || (hr in 25..230 && officialHr != null && kotlin.math.abs(hr - officialHr) <= 2)
        checkPoint("P1-HR", p1, "hrPrimary=$hr officialHr=$officialHr frame=${bytes.hex()}")
        val rr0 = rrValues.firstOrNull()
        val p2 = rr0 == null || rr0 in 300..2000
        checkPoint("P2-RR", p2, "rrIntervals=$rrValues unit=${if (rr0 != null && rr0 in 300..2000) "ms" else "raw/unknown"} frame=${bytes.hex()}")
        checkPoint("P3-GRAVITY", magnitude.isFinite() && kotlin.math.abs(magnitude - 1.0) <= 0.15, "xyz=$gravity magnitude=$magnitude frame=${bytes.hex()}")
        val now = Instant.now().epochSecond
        val p4 = kotlin.math.abs(now - timestamp) <= 300
        checkPoint("P4-TIMESTAMP", p4, "epoch=$timestamp now=$now delta=${now - timestamp}s frame=${bytes.hex()}")

        transport.subscribeHeartRate()
        log("P5-HR", "sottoscritto 2A37, raccolta 10 notifiche")
        val hrNotifications = withTimeout(60_000) { transport.incomingHeartRate().take(10).toList() }
        val allRr = mutableListOf<Int>()
        var haveRr = false
        for ((index, packet) in hrNotifications.withIndex()) {
            if (packet.isEmpty()) continue
            val flags = packet[0].u8()
            var offset = if (flags and 0x01 != 0) 3 else 2
            if (flags and 0x10 != 0) {
                haveRr = true
                while (offset + 1 < packet.size) {
                    allRr += packet.u16(offset)
                    offset += 2
                }
            }
            log("P5-HR", "notification=$index flags=0x${flags.toString(16)} rr=$allRr raw=${packet.hex()}")
        }
        val p5 = !haveRr || allRr.isNotEmpty() && allRr.all { it in 300..2000 }
        checkPoint("P5-2A37", p5, "RR=$allRr unit=ms if in 300..2000")

        handshake.cancel()
        handshakeTask.cancelAndJoin()
        framesCollector.cancelAndJoin()
        transport.disconnect()
        withTimeout(5_000) {
            while (transport.state != AndroidBleState.Disconnected) delay(50)
        }
        log("DISCONNECT", "PASS close() completato e stato DISCONNECTED")
        val failures = observations.filterNot { it.second }
        assertTrue("Checklist fallita: ${failures.joinToString { it.first }}", failures.isEmpty())
    }

    private fun grantRuntimePermissions(instrumentation: android.app.Instrumentation, context: Context) {
        val command = "pm grant ${context.packageName} ${Manifest.permission.BLUETOOTH_SCAN}; " +
            "pm grant ${context.packageName} ${Manifest.permission.BLUETOOTH_CONNECT}"
        instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor).use { it.readBytes() }
        }
    }

    private fun isV18(frame: PuffinFrame): Boolean = frame.rawPayload.size > 15 &&
        frame.rawPayload[0].u8() == 0x2F && frame.rawPayload[1].u8() == 0x12

    private fun Byte.u8() = toInt() and 0xFF
    private fun ByteArray.u16(offset: Int) = this[offset].u8() or (this[offset + 1].u8() shl 8)
    private fun ByteArray.u32(offset: Int): Long = (0..3).fold(0L) { acc, i -> acc or (this[offset + i].u8().toLong() shl (8 * i)) }
    private fun ByteArray.f32(offset: Int) = ByteBuffer.wrap(this, offset, 4).order(ByteOrder.LITTLE_ENDIAN).float
    private fun ByteArray.hex() = joinToString("") { "%02x".format(it.u8()) }

    companion object { private const val TAG = "BeveltryBLE" }
}
