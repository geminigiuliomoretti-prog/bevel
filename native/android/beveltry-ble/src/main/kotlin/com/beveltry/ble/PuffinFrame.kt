package com.beveltry.ble

data class PuffinFrame(
    val field: Int,
    /** Payload logico con gli zeri finali di padding rimossi. */
    val payload: ByteArray,
    /** Payload esattamente trasmesso, padding incluso. */
    val rawPayload: ByteArray,
    val headerCRC: Int,
    val payloadCRC: Long,
)
