import Foundation

public struct PuffinFrame: Sendable {
    public let field: UInt16
    /// Payload logico con gli zeri finali di padding rimossi.
    public let payload: Data
    /// Payload esattamente come trasmesso, padding incluso.
    public let rawPayload: Data
    public let headerCRC: UInt16
    public let payloadCRC: UInt32

    public init(field: UInt16, payload: Data, rawPayload: Data, headerCRC: UInt16, payloadCRC: UInt32) {
        self.field = field
        self.payload = payload
        self.rawPayload = rawPayload
        self.headerCRC = headerCRC
        self.payloadCRC = payloadCRC
    }
}
