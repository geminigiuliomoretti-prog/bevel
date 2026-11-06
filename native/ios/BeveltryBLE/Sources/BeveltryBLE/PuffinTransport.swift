import Foundation

public enum PuffinCharacteristic: Equatable, Sendable {
    case cmdToStrap
    case cmdFromStrap
    case eventsFromStrap
    case dataFromStrap
    case memfault
}

public protocol PuffinTransport: AnyObject {
    func write(_ frame: Data, to characteristic: PuffinCharacteristic) async throws
    func subscribe(to characteristic: PuffinCharacteristic) async throws
    var incomingFrames: AsyncStream<(PuffinFrame, PuffinCharacteristic)> { get }
}
