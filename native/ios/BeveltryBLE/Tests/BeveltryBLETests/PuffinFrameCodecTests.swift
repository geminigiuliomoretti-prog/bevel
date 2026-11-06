import Foundation
import XCTest
@testable import BeveltryBLE

final class PuffinFrameCodecTests: XCTestCase {
    private let hello = Data([0xAA, 0x01, 0x08, 0x00, 0x00, 0x01, 0xE6, 0x71,
                              0x23, 0x01, 0x91, 0x01, 0x36, 0x3E, 0x5C, 0x8D])

    func testKnownHelloEncodeAndDecode() throws {
        XCTAssertEqual(try PuffinFrameCodec.encode(field: 1, payload: Data([0x23, 0x01, 0x91, 0x01])), hello)
        let decoded = try PuffinFrameCodec.decode(hello)
        XCTAssertEqual(decoded.field, 1)
        XCTAssertEqual(decoded.payload, Data([0x23, 0x01, 0x91, 0x01]))
        XCTAssertEqual(decoded.rawPayload, decoded.payload)
    }

    func testOneBytePayloadIsPaddedAndFrameIsSixteenBytes() throws {
        let frame = try PuffinFrameCodec.encode(field: 1, payload: Data([0x23]))
        XCTAssertEqual(frame.count, 16)
        XCTAssertEqual(Array(frame[2..<4]), [0x08, 0x00])
        XCTAssertEqual(Array(frame[8..<12]), [0x23, 0x00, 0x00, 0x00])
        XCTAssertEqual(try PuffinFrameCodec.decode(frame).payload, Data([0x23]))
    }

    func testEncodeEmptyPayloadIsTooShort() {
        XCTAssertThrowsError(try PuffinFrameCodec.encode(field: 1, payload: Data())) { error in
            XCTAssertEqual(error as? PuffinFrameError, .frameTooShort)
        }
    }

    func testRoundTrip() throws {
        let payload = Data([0x10, 0x22, 0x33, 0x44, 0x55])
        let decoded = try PuffinFrameCodec.decode(PuffinFrameCodec.encode(field: 0x1234, payload: payload))
        XCTAssertEqual(decoded.field, 0x1234)
        XCTAssertEqual(decoded.payload, payload)
    }

    func testInvalidSOFAndVersion() throws {
        var badSof = hello; badSof[0] = 0
        XCTAssertThrowsError(try PuffinFrameCodec.decode(badSof)) { XCTAssertEqual($0 as? PuffinFrameError, .invalidSOF) }
        var badVersion = hello; badVersion[1] = 2
        XCTAssertThrowsError(try PuffinFrameCodec.decode(badVersion)) { XCTAssertEqual($0 as? PuffinFrameError, .invalidVersion) }
    }

    func testInvalidLengthAndChecksums() throws {
        var badLength = hello; badLength[2] = 7
        XCTAssertThrowsError(try PuffinFrameCodec.decode(badLength)) { XCTAssertEqual($0 as? PuffinFrameError, .invalidPayloadLength) }
        var badHeader = hello; badHeader[6] ^= 1
        XCTAssertThrowsError(try PuffinFrameCodec.decode(badHeader)) {
            guard let error = $0 as? PuffinFrameError, case .headerCRCInvalid = error else {
                return XCTFail("CRC header atteso")
            }
        }
        var badPayload = hello; badPayload[8] ^= 1
        XCTAssertThrowsError(try PuffinFrameCodec.decode(badPayload)) {
            guard let error = $0 as? PuffinFrameError, case .payloadCRCInvalid = error else {
                return XCTFail("CRC payload atteso")
            }
        }
    }

    func testReassemblerCompleteFragmentedAndBackToBack() throws {
        let codec = PuffinFrameReassembler()
        XCTAssertEqual(codec.feed(hello).count, 1)
        codec.reset()
        XCTAssertEqual(codec.feed(hello.prefix(4)).count, 0)
        XCTAssertEqual(codec.feed(hello[4..<11]).count, 0)
        XCTAssertEqual(codec.feed(hello[11...]).count, 1)
        XCTAssertEqual(codec.feed(hello + hello).count, 2)
    }

    func testReassemblerWaitsForEntireHeaderBeforeCheckingHeaderCRC() {
        let codec = PuffinFrameReassembler()
        XCTAssertEqual(codec.feed(hello.prefix(6)).count, 0)
        XCTAssertEqual(codec.feed(hello[6..<8]).count, 0)
        XCTAssertEqual(codec.feed(hello[8...]).count, 1)
    }

    func testReassemblerSkipsNoiseAndDoesNotParsePayloadSOF() throws {
        let codec = PuffinFrameReassembler()
        XCTAssertEqual(codec.feed(Data([0x00, 0xFF, 0xAA, 0xAA]) + hello).count, 1)
        codec.reset()
        let embedded = try PuffinFrameCodec.encode(field: 1, payload: Data([0xAA, 0x01, 0xAA, 0x01]))
        XCTAssertEqual(codec.feed(embedded).count, 1)
    }

    func testResetClearsPartialFrame() {
        let codec = PuffinFrameReassembler()
        XCTAssertEqual(codec.feed(hello.prefix(9)).count, 0)
        codec.reset()
        XCTAssertEqual(codec.feed(hello.suffix(from: 9)).count, 0)
        XCTAssertEqual(codec.feed(hello).count, 1)
    }
}
