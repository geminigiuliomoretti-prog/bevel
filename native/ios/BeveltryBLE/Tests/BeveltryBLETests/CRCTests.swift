import Foundation
import XCTest
@testable import BeveltryBLE

final class CRCTests: XCTestCase {
    func testKnownCRCValues() {
        let input = Data("123456789".utf8)
        XCTAssertEqual(CRC.crc16Modbus(input), 0x4B37)
        XCTAssertEqual(CRC.crc32IEEE(input), 0xCBF4_3926)
    }

    func testClientHelloHeaderCRC() {
        XCTAssertEqual(CRC.crc16Modbus(Data([0xAA, 0x01, 0x08, 0x00, 0x00, 0x01])), 0x71E6)
    }
}
