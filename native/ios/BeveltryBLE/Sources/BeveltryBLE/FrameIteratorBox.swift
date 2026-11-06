import Foundation

final class FrameIteratorBox: @unchecked Sendable {
    private var iterator: AsyncStream<(PuffinFrame, PuffinCharacteristic)>.Iterator

    init(_ stream: AsyncStream<(PuffinFrame, PuffinCharacteristic)>) {
        self.iterator = stream.makeAsyncIterator()
    }

    func next() async -> (PuffinFrame, PuffinCharacteristic)? {
        await iterator.next()
    }
}
