import Foundation

public enum PuffinFrameError: Error, Equatable {
    case invalidSOF
    case invalidVersion
    case invalidPayloadLength
    case frameTooShort
    case headerCRCInvalid(expected: UInt16, actual: UInt16)
    case payloadCRCInvalid(expected: UInt32, actual: UInt32)
}

public enum PuffinFrameCodec {
    private static let headerSize = 8
    private static let minimumPayloadLength = 8 // 4 byte payload minimo + CRC32

    public static func encode(field: UInt16, payload: Data) throws -> Data {
        let padding = (4 - payload.count % 4) % 4
        let rawPayload = payload + Data(repeating: 0, count: padding)
        let payloadLength = rawPayload.count + 4 // il campo include il CRC32
        guard payloadLength <= Int(UInt16.max) else { throw PuffinFrameError.invalidPayloadLength }
        guard headerSize + payloadLength > 15 else { throw PuffinFrameError.frameTooShort }

        var frame = Data([0xAA, 0x01])
        appendLE(UInt16(payloadLength), to: &frame)
        appendLE(field, to: &frame)
        appendLE(CRC.crc16Modbus(frame), to: &frame)
        frame.append(rawPayload)
        appendLE(CRC.crc32IEEE(rawPayload), to: &frame)
        return frame
    }

    public static func decode(_ frame: Data) throws -> PuffinFrame {
        guard frame.count >= 2 else { throw PuffinFrameError.frameTooShort }
        guard frame[frame.startIndex] == 0xAA else { throw PuffinFrameError.invalidSOF }
        guard frame[frame.startIndex + 1] == 0x01 else { throw PuffinFrameError.invalidVersion }
        guard frame.count >= headerSize else { throw PuffinFrameError.frameTooShort }

        let payloadLength = Int(readU16(frame, 2))
        guard payloadLength >= 4, payloadLength % 4 == 0 else {
            throw PuffinFrameError.invalidPayloadLength
        }
        guard headerSize + payloadLength > 15 else { throw PuffinFrameError.frameTooShort }
        guard frame.count == headerSize + payloadLength else { throw PuffinFrameError.frameTooShort }

        let expectedHeaderCRC = CRC.crc16Modbus(frame.prefix(6))
        let actualHeaderCRC = readU16(frame, 6)
        guard expectedHeaderCRC == actualHeaderCRC else {
            throw PuffinFrameError.headerCRCInvalid(expected: expectedHeaderCRC, actual: actualHeaderCRC)
        }

        let rawPayloadLength = payloadLength - 4
        let rawPayload = Data(frame[8..<(8 + rawPayloadLength)])
        let expectedPayloadCRC = CRC.crc32IEEE(rawPayload)
        let actualPayloadCRC = readU32(frame, 8 + rawPayloadLength)
        guard expectedPayloadCRC == actualPayloadCRC else {
            throw PuffinFrameError.payloadCRCInvalid(expected: expectedPayloadCRC, actual: actualPayloadCRC)
        }

        var payload = rawPayload
        while payload.last == 0 { payload.removeLast() }
        return PuffinFrame(
            field: readU16(frame, 4), payload: payload, rawPayload: rawPayload,
            headerCRC: actualHeaderCRC, payloadCRC: actualPayloadCRC
        )
    }

    fileprivate static func appendLE(_ value: UInt16, to data: inout Data) {
        data.append(UInt8(truncatingIfNeeded: value))
        data.append(UInt8(truncatingIfNeeded: value >> 8))
    }

    fileprivate static func appendLE(_ value: UInt32, to data: inout Data) {
        data.append(UInt8(truncatingIfNeeded: value))
        data.append(UInt8(truncatingIfNeeded: value >> 8))
        data.append(UInt8(truncatingIfNeeded: value >> 16))
        data.append(UInt8(truncatingIfNeeded: value >> 24))
    }

    fileprivate static func readU16(_ data: Data, _ offset: Int) -> UInt16 {
        UInt16(data[offset]) | (UInt16(data[offset + 1]) << 8)
    }

    fileprivate static func readU32(_ data: Data, _ offset: Int) -> UInt32 {
        UInt32(data[offset]) | (UInt32(data[offset + 1]) << 8)
            | (UInt32(data[offset + 2]) << 16) | (UInt32(data[offset + 3]) << 24)
    }
}

public final class PuffinFrameReassembler {
    private var buffer = Data()

    public init() {}

    public func reset() { buffer.removeAll(keepingCapacity: true) }

    public func feed(_ chunk: Data) -> [PuffinFrame] {
        buffer.append(chunk)
        var frames: [PuffinFrame] = []

        while true {
            guard let start = findSOF(in: buffer) else {
                // Conserva un AA terminale: potrebbe essere il primo byte SOF del chunk successivo.
                let keepAA = buffer.last == 0xAA
                buffer = keepAA ? Data([0xAA]) : Data()
                break
            }
            if start > 0 { buffer.removeFirst(start) }
            guard buffer.count >= 2 else { break }
            guard buffer[1] == 0x01 else { buffer.removeFirst(); continue }
            guard buffer.count >= 8 else { break }

            let declaredLength = Int(PuffinFrameCodec.readU16(buffer, 2))
            guard declaredLength >= 4, declaredLength % 4 == 0 else {
                buffer.removeFirst(); continue
            }
            let expectedHeader = CRC.crc16Modbus(buffer.prefix(6))
            guard expectedHeader == PuffinFrameCodec.readU16(buffer, 6) else {
                buffer.removeFirst(); continue
            }
            let totalLength = 8 + declaredLength
            guard totalLength > 15 else { buffer.removeFirst(); continue }
            guard buffer.count >= totalLength else { break }

            let candidate = Data(buffer.prefix(totalLength))
            if let decoded = try? PuffinFrameCodec.decode(candidate) {
                frames.append(decoded)
                buffer.removeFirst(totalLength)
            } else {
                // Su CRC32 errato riprende la ricerca dal byte successivo al SOF.
                buffer.removeFirst()
            }
        }
        return frames
    }

    private func findSOF(in data: Data) -> Int? {
        guard data.count >= 2 else { return nil }
        for index in 0..<(data.count - 1) where data[index] == 0xAA && data[index + 1] == 0x01 {
            return index
        }
        return nil
    }
}
