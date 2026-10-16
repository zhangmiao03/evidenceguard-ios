package evidenceguard.tools

import com.anker.esiotkit.domain.model.MegaEvent
import com.anker.esiotkit.domain_thing.model.device.MegaDevice
import com.anker.esiotkit.event.model.EventCondition
import com.anker.esiotkit.mega.event.MegaEventManager
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/** Read-only SDK event adapter. Never falls back to demo events or silently reports an empty list on failure. */
class NativeEventBridge(private val device: MegaDevice, private val now: () -> Long) {
    private val events = mutableMapOf<String, Pair<MegaEvent, Long>>()

    suspend fun execute(command: BridgeCommand): BridgeResult = when (command.tool) {
        "camera_events_query" -> query(command)
        "camera_event_get" -> detail(command.referenceHandles["eventRef"])
        else -> BridgeResult("failed", errorCode = "SDK_ENTRY_UNCONFIRMED", sdkUsed = false)
    }

    private suspend fun query(command: BridgeCommand): BridgeResult {
        val from = command.arguments["from"]?.toLongOrNull()?.times(1000) ?: (now() - 3600000)
        val to = command.arguments["to"]?.toLongOrNull()?.times(1000) ?: now()
        val cursor = command.arguments["cursor"]?.removePrefix("event-ms:")?.toLongOrNull() ?: 0L
        if (from < 0 || to < from || to - from > 86400000 || (cursor != 0L && cursor !in from..to))
            return BridgeResult("failed", errorCode = "UNSUPPORTED_PARAMETER", message = "Use a valid interval <= 24 hours and its returned cursor", sdkUsed = false)
        if (command.arguments["types"]?.let { it != "[]" } == true)
            return BridgeResult("failed", errorCode = "UNSUPPORTED_PARAMETER", message = "Detection type mapping has not been validated", sdkUsed = false)
        // The two current models are standalone devices. HomeBase/sub-device expansion is excluded.
        val condition = EventCondition(_parentSnList = listOf(device.deviceSn), _startTime = from, _endTime = to)
        val timeout = minOf(8000L, command.deadlineEpochMs - now())
        if (timeout <= 0) return BridgeResult("failed", errorCode = "DEADLINE_EXCEEDED", sdkUsed = false)
        return withTimeoutOrNull(timeout) {
            suspendCancellableCoroutine { continuation ->
                val job = MegaEventManager.query(condition, true, cursor,
                    onSuccess = { list ->
                        if (continuation.isActive) {
                            val selected = list.filter { it.deviceSn == device.deviceSn }.distinctBy { it.megaEventId }.take(64)
                            events.entries.removeAll { now() - it.value.second > 300000 }
                            selected.forEach { events[it.megaEventId] = it to now() }
                            val references = selected.map { BridgeReference("event", "Event ${it.triggerTypeValue}", it.megaEventId,
                                sourceTimestamp = it.startTimestamp.toDouble(), sourceTimeKind = "sdk_event_milliseconds") }
                            val data = mutableMapOf("source" to "MegaEventManager.query(refresh=true)", "completeness" to "sdk_page_unverified",
                                "returnedCount" to "${selected.size}", "timeUnit" to "milliseconds", "deviceFiltered" to "true")
                            selected.minOfOrNull { it.startTimestamp }?.let { data["nextCursorCandidate"] = "event-ms:$it" }
                            continuation.resume(BridgeResult("acknowledged", data = data, references = references))
                        }
                    }, onFailure = { code, message ->
                        if (continuation.isActive) continuation.resume(BridgeResult("failed", sdkCode = code, errorCode = "SDK_ERROR", message = message))
                    })
                continuation.invokeOnCancellation { job.cancel() }
            }
        } ?: BridgeResult("failed", errorCode = "EVENT_QUERY_TIMEOUT", message = "SDK event request timed out; no fabricated empty result")
    }

    private fun detail(handle: String?): BridgeResult {
        val entry = events[handle]
        if (entry == null || now() - entry.second > 300000) return BridgeResult("failed", errorCode = "STALE_REFERENCE", message = "Query the device event again", sdkUsed = false)
        val event = entry.first
        return BridgeResult("acknowledged", data = mapOf(
            "source" to "scoped_sdk_query_snapshot", "fetchedAtMilliseconds" to "${entry.second}",
            "startTimestampMilliseconds" to "${event.startTimestamp}", "endTimestampMilliseconds" to "${event.endTimestamp}",
            "triggerTypeValue" to "${event.triggerTypeValue}", "hasVideo" to event.videoPath.isNotBlank().toString(),
            "pictureCount" to "${event.pictures.size}", "downloadImplemented" to "false"
        ), sdkUsed = false)
    }
}
