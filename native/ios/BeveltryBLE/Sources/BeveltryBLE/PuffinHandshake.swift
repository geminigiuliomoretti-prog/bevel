import Foundation

public enum PuffinHandshakeError: Error, Equatable {
    case ackTimeout(opcode: UInt8)
    case ackStatusFailure(opcode: UInt8, status: UInt8)
    case clockNotLatched
    case unexpectedResponse(opcode: UInt8)
    case cancelled
    case transportFailure(String)
}

public enum HandshakeState: Equatable {
    case idle
    case connecting
    case bonding
    case subscribing
    case sendingHello
    case readingClock
    case settingClock
    case verifyingClock
    case keyExchange
    case settingFlags(current: Int, total: Int)
    case queryingRange
    case startingHistorical
    case ready
    case offloadStarted
    case failed(PuffinHandshakeError)
}

public protocol PuffinHandshakeDelegate: AnyObject {
    func handshake(_ handshake: PuffinHandshake, didChangeState state: HandshakeState)
    func handshake(_ handshake: PuffinHandshake, didReceiveRawFrame frame: PuffinFrame)
    func handshake(_ handshake: PuffinHandshake, didFailWith error: PuffinHandshakeError)
}

public final class PuffinHandshake {
    public private(set) var state: HandshakeState = .idle

    private weak var delegate: PuffinHandshakeDelegate?
    private let transport: PuffinTransport
    private let timeout: TimeInterval
    private var sequence: UInt8 = 1
    private var operation: Task<Void, Error>?
    private var didReportFailure = false

    private static let field: UInt16 = 0x0001
    private static let flags: [(String, UInt8)] = [
        ("enable_r22_packets", 2),
        ("enable_r22_v2_packets", 2),
        ("enable_r22_v3_packets", 2),
        ("enable_r22_v4_packets", 1),
        ("enable_r22_v5_packets", 2),
        ("enable_r22_v6_packets", 2),
        ("enable_r22_v8_packets", 2),
        ("make_hrfm_visible", 2),
        ("disable_pip_r26_packets", 2),
        ("wear_detect_bias", 2),
        ("hr_ch_switching", 2),
        ("ir_hw_switching", 2),
        ("enable_passive_strap_fit_gen5", 1),
        ("enable_sig11_during_sleep", 2),
        ("dorset_inhibit_wpt", 2),
        ("enable_sig12", 2)
    ]

    /// Il trasporto deve essere già connesso e bonded prima di chiamare start().
    public init(transport: PuffinTransport, delegate: PuffinHandshakeDelegate?, timeout: TimeInterval = 3) {
        self.transport = transport
        self.delegate = delegate
        self.timeout = max(0.001, timeout)
    }

    public func start() async throws {
        guard state == .idle else { throw PuffinHandshakeError.unexpectedResponse(opcode: 0) }
        let task = Task { try await self.run() }
        operation = task
        defer { operation = nil }
        do {
            try await task.value
        } catch let error as PuffinHandshakeError {
            fail(error)
            throw error
        } catch is CancellationError {
            fail(.cancelled)
            throw PuffinHandshakeError.cancelled
        } catch {
            let failure = PuffinHandshakeError.transportFailure(String(describing: error))
            fail(failure)
            throw failure
        }
    }

    public func cancel() {
        operation?.cancel()
    }

    private func run() async throws {
        do {
            let reader = FrameIteratorBox(transport.incomingFrames)
            transition(.subscribing)
            try await transport.subscribe(to: .cmdFromStrap)
            try await transport.subscribe(to: .eventsFromStrap)
            try await transport.subscribe(to: .dataFromStrap)

            transition(.sendingHello)
            let helloSequence = nextSequence()
            try await sendAndAcknowledge(
                payload: [0x23, helloSequence, 0x91, 0x01], opcode: 0x91, sequence: helloSequence,
                reader: reader
            )

            transition(.readingClock)
            _ = try await readClock(reader: reader)

            transition(.settingClock)
            let setTimestamp = UInt32(Date().timeIntervalSince1970)
            let clockSequence = nextSequence()
            var clockPayload: [UInt8] = [0x23, clockSequence, 0x0A, 0x01]
            appendLE(setTimestamp, to: &clockPayload)
            try await sendAndAcknowledge(
                payload: clockPayload, opcode: 0x0A, sequence: clockSequence, reader: reader
            )

            transition(.verifyingClock)
            let verifiedClock = try await readClock(reader: reader)
            // Tolleranza di un secondo per il passaggio del confine Unix tra SET_CLOCK e GET_CLOCK.
            guard verifiedClock == setTimestamp || verifiedClock == setTimestamp &+ 1 else {
                throw PuffinHandshakeError.clockNotLatched
            }

            transition(.keyExchange)
            var keyPayload: [UInt8] = [0x23, nextSequence(), 0x73, 0x01, 0x01]
            keyPayload.append(contentsOf: (0..<32).map { _ in UInt8.random(in: 0...255) })
            let keySequence = keyPayload[1]
            try await sendAndAcknowledge(
                payload: keyPayload, opcode: 0x73, sequence: keySequence, reader: reader
            )

            for (index, flag) in Self.flags.enumerated() {
                transition(.settingFlags(current: index + 1, total: Self.flags.count))
                // L'app ufficiale invia ogni flag due volte; ogni invio ha una propria sequenza e ACK.
                for _ in 0..<2 {
                    let flagSequence = nextSequence()
                    var payload: [UInt8] = [0x23, flagSequence, 0x78, 0x01]
                    let name = Array(flag.0.utf8.prefix(32))
                    payload.append(contentsOf: name)
                    payload.append(contentsOf: Array(repeating: UInt8(0), count: 32 - name.count))
                    payload.append(flag.1)
                    try await sendAndAcknowledge(
                        payload: payload, opcode: 0x78, sequence: flagSequence,
                        reader: reader, retryOnce: true
                    )
                }
            }

            transition(.queryingRange)
            let rangeSequence = nextSequence()
            let rangeFrame = try encode([0x23, rangeSequence, 0x22, 0x00])
            try await transport.write(rangeFrame, to: .cmdToStrap)
            _ = try await waitForResponse(opcode: 0x22, sequence: rangeSequence, reader: reader)

            transition(.ready)
            transition(.startingHistorical)
            let historicalSequence = nextSequence()
            try await transport.write(try encode([0x23, historicalSequence, 0x16, 0x00]), to: .cmdToStrap)
            let metadata = try await waitForFirstMetadata(reader: reader)
            guard metadata.rawPayload.count >= 21 else {
                throw PuffinHandshakeError.unexpectedResponse(opcode: 0x31)
            }

            let ackSequence = nextSequence()
            var ackPayload: [UInt8] = [0x23, ackSequence, 0x17, 0x01]
            ackPayload.append(contentsOf: metadata.rawPayload[13..<21])
            try await transport.write(try encode(ackPayload), to: .cmdToStrap)
            transition(.offloadStarted)
        } catch let error as PuffinHandshakeError {
            fail(error)
            throw error
        } catch is CancellationError {
            fail(.cancelled)
            throw PuffinHandshakeError.cancelled
        } catch {
            let failure = PuffinHandshakeError.transportFailure(String(describing: error))
            fail(failure)
            throw failure
        }
    }

    private func readClock(reader: FrameIteratorBox) async throws -> UInt32 {
        let seq = nextSequence()
        let response = try await sendAndAcknowledge(
            payload: [0x23, seq, 0x0B, 0x00], opcode: 0x0B, sequence: seq,
            reader: reader, returnsFrame: true
        )
        guard let response, response.rawPayload.count >= 8 else {
            throw PuffinHandshakeError.unexpectedResponse(opcode: 0x0B)
        }
        let bytes = response.rawPayload
        guard bytes[3] == 0x01 else {
            throw PuffinHandshakeError.ackStatusFailure(opcode: 0x0B, status: bytes[3])
        }
        return UInt32(bytes[4]) | (UInt32(bytes[5]) << 8) | (UInt32(bytes[6]) << 16) | (UInt32(bytes[7]) << 24)
    }

    @discardableResult
    private func sendAndAcknowledge(
        payload: [UInt8], opcode: UInt8, sequence: UInt8, reader: FrameIteratorBox,
        retryOnce: Bool = false, returnsFrame: Bool = false
    ) async throws -> PuffinFrame? {
        let frame = try encode(payload)
        var lastError: PuffinHandshakeError = .ackTimeout(opcode: opcode)
        for attempt in 0..<(retryOnce ? 2 : 1) {
            if attempt > 0 { try Task.checkCancellation() }
            try await transport.write(frame, to: .cmdToStrap)
            do {
                let response = try await waitForResponse(opcode: opcode, sequence: sequence, reader: reader)
                let status = response.rawPayload.count > 3 ? response.rawPayload[3] : 0
                guard status == 0x01 else {
                    lastError = .ackStatusFailure(opcode: opcode, status: status)
                    if retryOnce && attempt == 0 { continue }
                    throw lastError
                }
                return returnsFrame ? response : nil
            } catch let error as PuffinHandshakeError {
                lastError = error
                if retryOnce && attempt == 0 { continue }
                throw error
            }
        }
        throw lastError
    }

    private func waitForResponse(
        opcode: UInt8, sequence: UInt8, reader: FrameIteratorBox
    ) async throws -> PuffinFrame {
        while true {
            let (frame, characteristic) = try await nextIncoming(opcode: opcode, reader: reader)
            delegate?.handshake(self, didReceiveRawFrame: frame)
            let raw = frame.rawPayload
            guard characteristic == .cmdFromStrap, raw.count >= 3, raw[0] == 0x24, raw[1] == sequence else {
                continue
            }
            guard raw[2] == opcode else { throw PuffinHandshakeError.unexpectedResponse(opcode: raw[2]) }
            return frame
        }
    }

    private func waitForFirstMetadata(reader: FrameIteratorBox) async throws -> PuffinFrame {
        while true {
            let (frame, characteristic) = try await nextIncoming(opcode: 0x31, reader: reader)
            delegate?.handshake(self, didReceiveRawFrame: frame)
            if characteristic == .dataFromStrap, frame.rawPayload.first == 0x31 { return frame }
        }
    }

    private func nextIncoming(
        opcode: UInt8, reader: FrameIteratorBox
    ) async throws -> (PuffinFrame, PuffinCharacteristic) {
        try await withThrowingTaskGroup(of: (PuffinFrame, PuffinCharacteristic)?.self) { group in
            group.addTask { await reader.next() }
            group.addTask {
                try await Task.sleep(nanoseconds: UInt64(self.timeout * 1_000_000_000))
                throw PuffinHandshakeError.ackTimeout(opcode: opcode)
            }
            defer { group.cancelAll() }
            guard let result = try await group.next(), let incoming = result else {
                throw PuffinHandshakeError.ackTimeout(opcode: opcode)
            }
            return incoming
        }
    }

    private func encode(_ payload: [UInt8]) throws -> Data {
        try PuffinFrameCodec.encode(field: Self.field, payload: Data(payload))
    }

    private func nextSequence() -> UInt8 {
        defer { sequence = sequence == 0xFF ? 1 : sequence &+ 1 }
        return sequence
    }

    private func transition(_ newState: HandshakeState) {
        state = newState
        delegate?.handshake(self, didChangeState: newState)
    }

    private func fail(_ error: PuffinHandshakeError) {
        guard !didReportFailure else { return }
        didReportFailure = true
        transition(.failed(error))
        delegate?.handshake(self, didFailWith: error)
    }

    private func appendLE(_ value: UInt32, to bytes: inout [UInt8]) {
        bytes.append(UInt8(truncatingIfNeeded: value))
        bytes.append(UInt8(truncatingIfNeeded: value >> 8))
        bytes.append(UInt8(truncatingIfNeeded: value >> 16))
        bytes.append(UInt8(truncatingIfNeeded: value >> 24))
    }
}
