package evidenceguard.tools

import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/** Application policy, not a motor speed/angle or measured physical stop deadline. */
const val MAX_CONTINUOUS_PTZ_MS = 1100L
const val PTZ_STOP_TIMEOUT_MS = 2500L

/** The start budget includes SDK latency. STOP is attempted once even on throw/timeout/cancel.
 * Cancellation of an SDK suspend function does not prove cancellation of its physical command.
 * Process death, an uncooperative SDK or an unreachable device still requires manual recovery.
 */
suspend fun boundedPTZ(
    durationMs: Long,
    start: suspend () -> BridgeResult,
    stop: suspend () -> BridgeResult,
): BridgeResult {
    require(durationMs in 100..MAX_CONTINUOUS_PTZ_MS)
    var started: BridgeResult? = null
    var stopped: BridgeResult? = null
    try {
        withTimeoutOrNull(durationMs) {
            started = start()
            if (started?.status == "acknowledged") delay(durationMs)
        }
    } finally {
        // Do not put this in the cancelled movement coroutine's context.
        stopped = withContext(NonCancellable) {
            withTimeoutOrNull(PTZ_STOP_TIMEOUT_MS) {
                try { stop() } catch (e: Exception) {
                    BridgeResult("unknown", errorCode = "STOP_UNVERIFIED", message = "Stop threw ${e::class.simpleName}")
                }
            }
        }
    }
    val stopAck = stopped?.status in listOf("acknowledged", "stopped")
    val startAck = started?.status == "acknowledged"
    return BridgeResult(
        status = if (!stopAck || started == null) "unknown" else if (startAck) "acknowledged" else "failed",
        sdkCode = started?.sdkCode,
        errorCode = if (!stopAck) "STOP_UNVERIFIED" else if (started == null) "START_UNCONFIRMED" else started?.errorCode,
        message = "Bounded SDK movement; physical displacement and stopping need separate observation",
        data = mapOf("motionMode" to "continuous", "requestedWindowMs" to "$durationMs", "windowIncludesSdkLatency" to "true", "physicalStopLatencyMs" to "unknown"),
        sdkAccepted = started?.sdkAccepted ?: if (startAck) true else null,
        stopState = if (stopAck) "acknowledged" else "unknown",
        stopSdkCode = stopped?.sdkCode,
    )
}
