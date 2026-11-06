import Foundation
import XCTest
@testable import BeveltryBLE

private final class MockPuffinTransport: PuffinTransport {
    let incomingFrames: AsyncStream<(PuffinFrame, PuffinCharacteristic)>
    private let continuation: AsyncStream<(PuffinFrame, PuffinCharacteristic)>.Continuation
    var writes: [(Data, PuffinCharacteristic)] = []
    var subscriptions: [PuffinCharacteristic] = []
    var initialClock: UInt32 = 0
    var clockWillLatch = true
    var failClockSet = false
    var failFlagName: String?
    var withholdHelloAck = false
    var flagWrites: [PuffinFrame] = []
    var clockSetFrames: [PuffinFrame] = []
    var ackFrames: [PuffinFrame] = []
    private var clockReads = 0
    private var latchedClock: UInt32?

    init() {
        let pair = AsyncStream<(PuffinFrame, PuffinCharacteristic)>.makeStream()
        incomingFrames = pair.stream
        continuation = pair.continuation
    }

    func subscribe(to characteristic: PuffinCharacteristic) async throws {
        subscriptions.append(characteristic)
    }

    func write(_ frameData: Data, to characteristic: PuffinCharacteristic) async throws {
        writes.append((frameData, characteristic))
        let frame = try PuffinFrameCodec.decode(frameData)
        let raw = Array(frame.rawPayload)
        guard raw.count >= 3 else { return }
        let seq = raw[1]
        let opcode = raw[2]
        switch opcode {
        case 0x91:
            if !withholdHelloAck { emitAck(sequence: seq, opcode: opcode, status: 1) }
        case 0x0B:
            clockReads += 1
            let timestamp: UInt32
            if clockReads == 1 {
                timestamp = initialClock
            } else if clockWillLatch, let latchedClock {
                timestamp = latchedClock
            } else {
                timestamp = 0
            }
            var response: [UInt8] = [0x24, seq, opcode, 1]
            appendLE(timestamp, to: &response)
            response.append(0) // flags opzionale
            emit(response, on: .cmdFromStrap)
        case 0x0A:
            clockSetFrames.append(frame)
            latchedClock = readU32(raw, 4)
            emitAck(sequence: seq, opcode: opcode, status: failClockSet ? 2 : 1)
        case 0x73:
            emitAck(sequence: seq, opcode: opcode, status: 1)
        case 0x78:
            flagWrites.append(frame)
            let nameBytes = raw[4..<36].prefix { $0 != 0 }
            let name = String(bytes: nameBytes, encoding: .ascii)
            let status: UInt8 = name == failFlagName ? 2 : 1
            emitAck(sequence: seq, opcode: opcode, status: status)
        case 0x22:
            emit([0x24, seq, opcode, 1, 0xAA], on: .cmdFromStrap)
        case 0x16:
            var metadata = (0..<24).map(UInt8.init)
            metadata[0] = 0x31
            let cursor: [UInt8] = [0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87]
            for index in 0..<8 { metadata[13 + index] = cursor[index] }
            emit(metadata, on: .dataFromStrap)
        case 0x17:
            ackFrames.append(frame)
        default:
            break
        }
    }

    private func emitAck(sequence: UInt8, opcode: UInt8, status: UInt8) {
        emit([0x24, sequence, opcode, status], on: .cmdFromStrap)
    }

    private func emit(_ payload: [UInt8], on characteristic: PuffinCharacteristic) {
        guard let encoded = try? PuffinFrameCodec.encode(field: 1, payload: Data(payload)),
              let frame = try? PuffinFrameCodec.decode(encoded) else { return }
        continuation.yield((frame, characteristic))
    }

    private func readU32(_ bytes: [UInt8], _ offset: Int) -> UInt32 {
        UInt32(bytes[offset]) | (UInt32(bytes[offset + 1]) << 8)
            | (UInt32(bytes[offset + 2]) << 16) | (UInt32(bytes[offset + 3]) << 24)
    }

    private func appendLE(_ value: UInt32, to bytes: inout [UInt8]) {
        bytes.append(UInt8(truncatingIfNeeded: value))
        bytes.append(UInt8(truncatingIfNeeded: value >> 8))
        bytes.append(UInt8(truncatingIfNeeded: value >> 16))
        bytes.append(UInt8(truncatingIfNeeded: value >> 24))
    }
}

private final class MockHandshakeDelegate: PuffinHandshakeDelegate {
    var states: [HandshakeState] = []
    var received: [PuffinFrame] = []
    var failures: [PuffinHandshakeError] = []

    func handshake(_ handshake: PuffinHandshake, didChangeState state: HandshakeState) { states.append(state) }
    func handshake(_ handshake: PuffinHandshake, didReceiveRawFrame frame: PuffinFrame) { received.append(frame) }
    func handshake(_ handshake: PuffinHandshake, didFailWith error: PuffinHandshakeError) { failures.append(error) }
}

final class PuffinHandshakeTests: XCTestCase {
    func testHappyPathRunsThroughFirstHistoricalCursorAck() async throws {
        let transport = MockPuffinTransport()
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        try await handshake.start()

        XCTAssertEqual(handshake.state, .offloadStarted)
        XCTAssertEqual(transport.subscriptions, [.cmdFromStrap, .eventsFromStrap, .dataFromStrap])
        XCTAssertEqual(transport.flagWrites.count, 32)
        XCTAssertEqual(transport.ackFrames.count, 1)
        XCTAssertEqual(transport.writes.first?.0,
                       Data([0xAA, 0x01, 0x08, 0x00, 0x00, 0x01, 0xE6, 0x71,
                             0x23, 0x01, 0x91, 0x01, 0x36, 0x3E, 0x5C, 0x8D]))
        XCTAssertEqual(Array(transport.ackFrames[0].rawPayload[4..<12]),
                       [0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87])
        let expectedFlags: [(String, UInt8)] = [
            ("enable_r22_packets", 2), ("enable_r22_v2_packets", 2),
            ("enable_r22_v3_packets", 2), ("enable_r22_v4_packets", 1),
            ("enable_r22_v5_packets", 2), ("enable_r22_v6_packets", 2),
            ("enable_r22_v8_packets", 2), ("make_hrfm_visible", 2),
            ("disable_pip_r26_packets", 2), ("wear_detect_bias", 2),
            ("hr_ch_switching", 2), ("ir_hw_switching", 2),
            ("enable_passive_strap_fit_gen5", 1), ("enable_sig11_during_sleep", 2),
            ("dorset_inhibit_wpt", 2), ("enable_sig12", 2)
        ]
        for (index, expected) in expectedFlags.enumerated() {
            for duplicate in 0..<2 {
                let raw = transport.flagWrites[index * 2 + duplicate].rawPayload
                XCTAssertEqual(String(bytes: raw[4..<36].prefix { $0 != 0 }, encoding: .ascii), expected.0)
                XCTAssertEqual(raw[36], expected.1)
            }
        }
        let keyFrame = try XCTUnwrap(transport.writes.compactMap { try? PuffinFrameCodec.decode($0.0) }
            .first { $0.rawPayload.count == 40 && $0.rawPayload[2] == 0x73 })
        XCTAssertEqual(keyFrame.rawPayload[4], 0x01)
        XCTAssertEqual(keyFrame.rawPayload[5..<37].count, 32)
        XCTAssertEqual(Array(keyFrame.rawPayload[37..<40]), [0, 0, 0])
    }

    func testValidClockIsStillSetAndSetClockBytesMatchFormat() async throws {
        let transport = MockPuffinTransport()
        transport.initialClock = UInt32(Date().timeIntervalSince1970)
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        try await handshake.start()

        XCTAssertEqual(transport.clockSetFrames.count, 1)
        let raw = Array(transport.clockSetFrames[0].rawPayload)
        XCTAssertEqual(Array(raw[0..<4]), [0x23, raw[1], 0x0A, 0x01])
        XCTAssertEqual(raw.count, 8)
        let timestamp = UInt32(raw[4]) | (UInt32(raw[5]) << 8) | (UInt32(raw[6]) << 16) | (UInt32(raw[7]) << 24)
        XCTAssertLessThanOrEqual(abs(Int64(timestamp) - Int64(Date().timeIntervalSince1970)), 2)
        let expectedPayload = Data([0x23, raw[1], 0x0A, 0x01, raw[4], raw[5], raw[6], raw[7]])
        let expectedFrame = try PuffinFrameCodec.encode(field: 1, payload: expectedPayload)
        let wireFrame = try XCTUnwrap(transport.writes.first(where: {
            (try? PuffinFrameCodec.decode($0.0).rawPayload[2]) == 0x0A
        })?.0)
        XCTAssertEqual(wireFrame, expectedFrame)
    }

    func testClockAtEpochIsSetAndVerified() async throws {
        let transport = MockPuffinTransport()
        transport.initialClock = 0
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        try await handshake.start()
        XCTAssertEqual(handshake.state, .offloadStarted)
        XCTAssertEqual(transport.clockSetFrames.count, 1)
    }

    func testGetHelloTimeoutFailsHandshake() async {
        let transport = MockPuffinTransport()
        transport.withholdHelloAck = true
        let delegate = MockHandshakeDelegate()
        let handshake = PuffinHandshake(transport: transport, delegate: delegate, timeout: 0.01)
        do {
            try await handshake.start()
            XCTFail("Era atteso un timeout")
        } catch let error as PuffinHandshakeError {
            XCTAssertEqual(error, .ackTimeout(opcode: 0x91))
            XCTAssertEqual(handshake.state, .failed(.ackTimeout(opcode: 0x91)))
            XCTAssertEqual(delegate.failures, [.ackTimeout(opcode: 0x91)])
        } catch {
            XCTFail("Errore inatteso: \(error)")
        }
    }

    func testSetClockStatusFailure() async {
        let transport = MockPuffinTransport()
        transport.failClockSet = true
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        do {
            try await handshake.start()
            XCTFail("Era atteso un ACK negativo")
        } catch let error as PuffinHandshakeError {
            XCTAssertEqual(error, .ackStatusFailure(opcode: 0x0A, status: 2))
        } catch {
            XCTFail("Errore inatteso: \(error)")
        }
    }

    func testFlagFailureRetriesOnceThenFails() async {
        let transport = MockPuffinTransport()
        transport.failFlagName = "enable_r22_packets"
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        do {
            try await handshake.start()
            XCTFail("Era atteso un ACK negativo")
        } catch let error as PuffinHandshakeError {
            XCTAssertEqual(error, .ackStatusFailure(opcode: 0x78, status: 2))
            XCTAssertEqual(transport.flagWrites.count, 2)
        } catch {
            XCTFail("Errore inatteso: \(error)")
        }
    }

    func testClockThatRemainsAtEpochDoesNotLatch() async {
        let transport = MockPuffinTransport()
        transport.clockWillLatch = false
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        do {
            try await handshake.start()
            XCTFail("Era atteso clockNotLatched")
        } catch let error as PuffinHandshakeError {
            XCTAssertEqual(error, .clockNotLatched)
        } catch {
            XCTFail("Errore inatteso: \(error)")
        }
    }

    func testFirstMetadataCursorIsSentInHistoricalAck() async throws {
        let transport = MockPuffinTransport()
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        try await handshake.start()
        let ack = try XCTUnwrap(transport.ackFrames.first)
        XCTAssertEqual(Array(ack.rawPayload[0..<4]), [0x23, ack.rawPayload[1], 0x17, 0x01])
        XCTAssertEqual(Array(ack.rawPayload[4..<12]), [0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87])
        let ackWire = try XCTUnwrap(transport.writes.last?.0)
        XCTAssertEqual(ackWire.count, 24)
        XCTAssertEqual(UInt16(ackWire[2]) | (UInt16(ackWire[3]) << 8), 16)
    }

    func testFlagFrameHasExpectedWireSizeAndLength() async throws {
        let transport = MockPuffinTransport()
        let handshake = PuffinHandshake(transport: transport, delegate: nil, timeout: 0.2)
        try await handshake.start()
        let firstFlag = try XCTUnwrap(transport.flagWrites.first)
        let flagWire = try XCTUnwrap(transport.writes.first(where: {
            guard let decoded = try? PuffinFrameCodec.decode($0.0) else { return false }
            return decoded.rawPayload.count == 40 && decoded.rawPayload[2] == 0x78
        })?.0)
        XCTAssertEqual(flagWire.count, 52)
        XCTAssertEqual(UInt16(flagWire[2]) | (UInt16(flagWire[3]) << 8), 44)
        XCTAssertEqual(firstFlag.rawPayload.count, 40)
        XCTAssertEqual(String(bytes: firstFlag.rawPayload[4..<36].prefix { $0 != 0 }, encoding: .ascii), "enable_r22_packets")
    }
}
