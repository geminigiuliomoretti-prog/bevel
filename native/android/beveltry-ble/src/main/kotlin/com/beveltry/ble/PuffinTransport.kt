package com.beveltry.ble

import kotlinx.coroutines.flow.Flow

enum class PuffinCharacteristic {
    CMD_TO_STRAP,
    CMD_FROM_STRAP,
    EVENTS_FROM_STRAP,
    DATA_FROM_STRAP,
    MEMFAULT,
}

interface PuffinTransport {
    suspend fun write(frame: ByteArray, characteristic: PuffinCharacteristic)
    suspend fun subscribe(characteristic: PuffinCharacteristic)
    fun incomingFrames(): Flow<Pair<PuffinFrame, PuffinCharacteristic>>
}

