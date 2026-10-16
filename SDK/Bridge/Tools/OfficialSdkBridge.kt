package evidenceguard.tools

import com.anker.esiotkit.domain_thing.api.ESIotDeviceManager
import com.anker.esiotkit.domain_thing.api.domain.PTZDirection
import com.anker.esiotkit.domain_thing.api.model.ThingResult
import com.anker.esiotkit.domain_thing.model.device.MegaDevice
import com.anker.esiotkit.core.constants.ServiceConstants
import com.anker.esiotkit.core.iotmodel.default_service.QuickResponseService
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/** Trusted executor input, constructed ONLY from a leased service command, never from LLM text. */
data class BridgeCommand(
    val tool: String,
    val arguments: Map<String, String>,
    val referenceHandles: Map<String, String>,
    val deadlineEpochMs: Long,
    val humanApproved: Boolean,
)

data class BridgeReference(
    val kind: String,
    val label: String,
    val vendorHandle: String,
    val allowedTools: List<String> = emptyList(),
    val ready: Boolean = true,
    val sourceTimestamp: Double? = null,
    val sourceTimeKind: String = "unknown",
)

data class BridgeResult(
    val status: String,
    val sdkCode: Int? = null,
    val message: String = "",
    val errorCode: String? = null,
    val data: Map<String, String> = emptyMap(),
    val references: List<BridgeReference> = emptyList(),
    val sdkUsed: Boolean = true,
)

/**
 * A small, closed KMP facade over delivered 2.2.7 APIs. Android JVM typecheck is separate
 * from iOS linking and hardware validation. The host owns SDK login and MegaDevice lifetime.
 * It must register only [implementedTools], and mark ready only after TD is prepared.
 */
class OfficialSdkBridge(
    private val manager: ESIotDeviceManager,
    private val device: MegaDevice,
    private val model: String,
    private val nowEpochMs: () -> Long,
    private val preparedReplyIds: () -> Set<Int> = { emptySet() },
) {
    private val live get() = manager.liveStream(device.deviceSn)
    private val night get() = manager.nightVision(device.deviceSn)
    private val privacy get() = manager.privacyMask(device.deviceSn)
    private val events = NativeEventBridge(device, nowEpochMs)

    val implementedTools: List<String> get() = listOf(
        "device_state_get", "device_settings_get", "device_settings_set", "camera_set_night_vision", "camera_events_query", "camera_event_get",
    ) + if (model == "T8171") listOf("camera_ptz_step", "camera_presets_list", "camera_goto_preset")
        else if (model == "T8214") listOf("camera_light_set", "doorbell_light_set", "camera_dual_mode_set", "doorbell_replies_list", "doorbell_reply_play") else emptyList()

    private fun reject(code: String, message: String) = BridgeResult("failed", errorCode = code, message = message, sdkUsed = false)
    private fun <T> result(r: ThingResult<T>, success: (T) -> BridgeResult = { BridgeResult("acknowledged") }): BridgeResult = when (r) {
        is ThingResult.Success -> success(r.data)
        is ThingResult.Error -> BridgeResult("failed", sdkCode = r.code, message = r.message ?: "SDK error", errorCode = when (r.code) {
            -1004 -> "PRIVACY_BLOCKED"
            -1002 -> "CAPABILITY_NOT_READY" // Unsupported and not-yet-ready are not distinguishable here.
            else -> "SDK_ERROR"
        })
    }

    suspend fun privacyState(): String = when (val r = privacy.isPrivacyModeEnabled()) {
        is ThingResult.Success -> if (r.data) "on" else "off"
        is ThingResult.Error -> "unknown"
    }

    suspend fun execute(command: BridgeCommand): BridgeResult {
        if (nowEpochMs() >= command.deadlineEpochMs) return reject("DEADLINE_EXCEEDED", "Late command rejected before SDK call")
        if (model != "T8171" && model != "T8214") return reject("MODEL_NOT_APPLICABLE", "Unregistered model")
        if (command.tool !in implementedTools) return reject("SDK_ENTRY_UNCONFIRMED", "No implemented bridge route for this tool")
        val readOnly = command.tool in listOf("device_state_get", "device_settings_get", "camera_presets_list", "doorbell_replies_list", "camera_events_query", "camera_event_get")
        if (!readOnly && !command.humanApproved) return reject("APPROVAL_REQUIRED", "This bridge requires a server-confirmed command")
        if (!readOnly && privacyState() != "off") return reject("PRIVACY_BLOCKED", "Privacy enabled or could not be read")
        // This second deadline check accounts for the asynchronous privacy query.
        if (nowEpochMs() >= command.deadlineEpochMs) return reject("DEADLINE_EXCEEDED", "Command expired during preflight")
        val a = command.arguments
        val refs = command.referenceHandles
        return when (command.tool) {
            "camera_events_query", "camera_event_get" -> events.execute(command)
            "doorbell_replies_list" -> replies(command.deadlineEpochMs)
            "doorbell_reply_play" -> {
                val id = refs["replyRef"]?.removePrefix("reply:")?.toIntOrNull()
                val directory = replies(command.deadlineEpochMs)
                if (directory.status != "acknowledged") directory
                else if (id == null || id !in preparedReplyIds() || directory.references.none { it.vendorHandle == "reply:$id" && it.ready }) reject("CAPABILITY_NOT_READY", "Reply must still exist and be verified prepared on this device")
                else if (nowEpochMs() >= command.deadlineEpochMs) reject("DEADLINE_EXCEEDED", "Expired during reply directory query")
                else result(live.sendQuickResponse(id))
            }
            "device_state_get" -> result(privacy.isPrivacyModeEnabled()) { enabled ->
                BridgeResult("acknowledged", data = mapOf("privacy" to if (enabled) "on" else "off", "source" to "PrivacyMaskAPI.isPrivacyModeEnabled", "battery" to "UNKNOWN", "storage" to "UNKNOWN", "network" to "UNKNOWN"))
            }
            "device_settings_get" -> settings()
            "camera_presets_list" -> result(live.queryPresetPositions()) { positions ->
                BridgeResult("acknowledged", references = positions.map { BridgeReference("preset", "Preset $it", "preset:$it") })
            }
            "camera_ptz_step" -> {
                if (!live.supportsPTZ()) reject("CAPABILITY_NOT_READY", "PTZ not ready")
                else {
                    val direction = PTZDirection.entries.firstOrNull { it.name == a["direction"] }
                    if (direction == null) reject("UNSUPPORTED_PARAMETER", "Invalid direction") else result(live.controlPTZ(direction))
                }
            }
            "camera_goto_preset" -> {
                val index = refs["presetRef"]?.removePrefix("preset:")?.toIntOrNull()
                when (val current = live.queryPresetPositions()) {
                    is ThingResult.Error -> result(current)
                    is ThingResult.Success -> if (nowEpochMs() >= command.deadlineEpochMs) reject("DEADLINE_EXCEEDED", "Expired during directory lookup")
                    else if (index == null || index !in current.data) reject("STALE_REFERENCE", "Preset is no longer in device directory") else result(live.jumpToPreset(index, 0))
                }
            }
            "camera_set_night_vision" -> {
                val mode = refs["optionRef"]?.removePrefix("night:")?.toIntOrNull()
                if (a["scope"] != "persistent" || mode == null || night.getModeOptions().none { it.key == mode }) reject("UNSUPPORTED_PARAMETER", "Use an option returned by this NightVisionAPI route")
                else when (val write = night.setMode(mode)) {
                    is ThingResult.Error -> result(write)
                    is ThingResult.Success -> result(night.getMode()) { actual -> BridgeResult("acknowledged", data = mapOf("requested" to "$mode", "readback" to "$actual", "readbackMatches" to "${mode == actual}", "physicalEffect" to "unverified")) }
                }
            }
            "camera_light_set", "doorbell_light_set" -> {
                val enabled = a["enabled"]?.toBooleanStrictOrNull()
                if (enabled == null || refs["channelRef"] != "live:spotlight") reject("UNSUPPORTED_PARAMETER", "Unregistered lighting channel")
                else result(live.toggleLight(enabled))
            }
            "camera_dual_mode_set" -> {
                val mode = refs["modeRef"]?.removePrefix("dual:")?.toIntOrNull()
                when (val modes = live.getSupportedVideoModes()) {
                    is ThingResult.Error -> result(modes)
                    is ThingResult.Success -> if (nowEpochMs() >= command.deadlineEpochMs) reject("DEADLINE_EXCEEDED", "Expired during mode lookup")
                    else if (mode == null || mode !in modes.data) reject("STALE_REFERENCE", "Mode is no longer available")
                    else result(live.changeVideoMode(mode, 0)) { change ->
                        // Match the official T8214 sample: the device changes its
                        // composite pipeline in place; restarting the player can
                        // interfere with that transition. Preserve the SDK result.
                        BridgeResult("acknowledged", data = mapOf(
                            "previousMode" to "${change.previousMode}",
                            "mode" to "${change.newMode}",
                            "sdkStreamRestartRequired" to "${change.streamRestartRequired}",
                            "requiresNewMediaSession" to "false",
                            "restartPolicy" to "doorbell_in_place",
                            "physicalEffect" to "unverified",
                        ))
                    }
                }
            }
            "device_settings_set" -> setField(a)
            else -> reject("SDK_ENTRY_UNCONFIRMED", "Route not implemented")
        }
    }

    private suspend fun replies(deadline: Long): BridgeResult {
        val service = device.iotDevice.getService<QuickResponseService>(ServiceConstants.QUICK_RESPONSE)
            ?: return reject("CAPABILITY_NOT_READY", "QuickResponseService is not prepared")
        val timeout = minOf(8000L, deadline - nowEpochMs())
        if (timeout <= 0) return reject("DEADLINE_EXCEEDED", "Reply request expired")
        return withTimeoutOrNull(timeout) {
            suspendCancellableCoroutine { continuation ->
                service.getQuickResponseList(success = { list ->
                    if (continuation.isActive) continuation.resume(BridgeResult("acknowledged", references = list.orEmpty()
                        .filter { it.deviceSn.isEmpty() || it.deviceSn == device.deviceSn }
                        .map { BridgeReference("reply", it.desc.ifEmpty { "Voice ${it.voiceId}" }, "reply:${it.voiceId}", ready = it.voiceId in preparedReplyIds()) },
                        data = mapOf("preparationSource" to "host_verified_ids", "ttsStreaming" to "false")))
                }, onFailure = { code, _ ->
                    if (continuation.isActive) continuation.resume(BridgeResult("failed", errorCode = "SDK_ERROR", message = code.toString()))
                })
                // SDK exposes no cancellation handle here. Late callbacks are ignored.
            }
        } ?: BridgeResult("failed", errorCode = "REPLY_DIRECTORY_TIMEOUT", message = "SDK callback deadline exceeded")
    }

    private suspend fun settings(): BridgeResult {
        val refs = night.getModeOptions().map { BridgeReference("option", it.displayName, "night:${it.key}", listOf("camera_set_night_vision")) }.toMutableList()
        val data = mutableMapOf("nightVisionRoute" to "NightVisionAPI", "fieldRanges" to "must_be_validated_before_registration")
        when (val current = night.getMode()) {
            is ThingResult.Success -> data["nightVision"] = "${current.data}"
            is ThingResult.Error -> { data["nightVision"] = "UNKNOWN"; data["nightVisionError"] = "${current.code}" }
        }
        if (model == "T8214") {
            when (val modes = live.getSupportedVideoModes()) {
                is ThingResult.Success -> refs.addAll(modes.data.map { BridgeReference("mode", "Layout $it", "dual:$it", listOf("camera_dual_mode_set")) })
                is ThingResult.Error -> data["dualModesError"] = "${modes.code}"
            }
            // Channel is a typed lighting route; it is NOT the device status indicator.
            refs.add(BridgeReference("light", "Spotlight (requires hardware validation)", "live:spotlight", listOf("camera_light_set", "doorbell_light_set")))
        }
        return BridgeResult("acknowledged", data = data, references = refs)
    }

    private suspend fun setField(a: Map<String, String>): BridgeResult {
        val value = a["value"] ?: return reject("UNSUPPORTED_PARAMETER", "Missing value")
        val b = value.toBooleanStrictOrNull()
        return when (a["field"]) {
            "ptzSpeed" -> {
                val speed = value.toIntOrNull()
                if (model != "T8171" || speed == null || speed !in 1..5) reject("UNSUPPORTED_PARAMETER", "PTZ speed requires T8171 and range 1..5")
                else result(live.setPTZSpeed(speed))
            }
            "microphoneEnabled" -> if (b == null) reject("UNSUPPORTED_PARAMETER", "Expected Boolean") else result(manager.audio(device.deviceSn).setMicrophoneEnabled(b))
            "audioRecordEnabled" -> if (b == null) reject("UNSUPPORTED_PARAMETER", "Expected Boolean") else result(manager.audio(device.deviceSn).setAudioRecording(b))
            "statusLED" -> if (b == null) reject("UNSUPPORTED_PARAMETER", "Expected Boolean") else result(manager.info(device.deviceSn).setLedStatus(b))
            else -> reject("UNSUPPORTED_PARAMETER", "Field is not implemented/validated in this bridge")
        }
    }

    /** STOP is deliberately independent of privacyState(): SDK may still reject it with -1004. */
    suspend fun stop(command: BridgeCommand): BridgeResult {
        if (model != "T8171" || command.tool !in listOf("camera_ptz_step", "camera_goto_preset"))
            return reject("STOP_UNVERIFIED", "No interrupt route for this operation; do not infer physical stop")
        // Preset travel has no direction in its command contract. The deprecated
        // no-argument overload sends a fixed legacy command, so it cannot prove
        // that an arbitrary preset move was stopped. Keep the operation unresolved.
        if (command.tool != "camera_ptz_step")
            return reject("STOP_UNVERIFIED", "Preset cancellation has no verified directional SDK stop route")
        val direction = PTZDirection.entries.firstOrNull { it.name == command.arguments["direction"] }
            ?: return reject("STOP_UNVERIFIED", "The original PTZ direction is unavailable")
        val stopped = live.stopPTZMovement(direction)
        return result(stopped) { BridgeResult("stopped", data = mapOf("physicalEffect" to "unverified")) }
    }
}
