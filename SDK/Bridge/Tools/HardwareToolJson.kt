package evidenceguard.tools

import kotlinx.serialization.json.*

/** Same closed wire format for Kotlin hosts. No arbitrary reflection/TD invocation. */
class HardwareToolJson(private val bridge: OfficialSdkBridge, private val model: String) {
    suspend fun manifest(ready: Boolean): String = buildJsonObject {
        put("privacy", bridge.privacyState())
        put("routes", buildJsonObject {
            bridge.implementedTools.forEach { name -> put(name, buildJsonObject {
                // A directory entry alone does not prove a reply is prepared for playback.
                put("ready", ready && name != "doorbell_reply_play")
                put("sdkMapping", "OfficialSdkBridge.$name")
                if (name == "camera_ptz_step") {
                    put("motionModes", JsonArray(listOf("step", "continuous").map(::JsonPrimitive)))
                    put("maxContinuousMs", MAX_CONTINUOUS_PTZ_MS)
                }
            }) }
            // onRate/onVideoInfo are not decoded-frame progress. Keep the
            // ordinary read-only image path; strict control references await
            // a verified native decoder callback, not a timer-generated counter.
            put("camera_observe", buildJsonObject { put("ready", false); put("sdkMapping", "native_decoder_progress_required") })
        })
        put("fields", buildJsonObject {
            listOf("microphoneEnabled", "audioRecordEnabled", "statusLED").forEach { field ->
                put(field, buildJsonObject { put("writable", ready); put("schema", buildJsonObject { put("type", "boolean") }) })
            }
            if (model == "T8171") put("ptzSpeed", buildJsonObject {
                put("writable", ready)
                put("schema", buildJsonObject { put("type", "integer"); put("minimum", 1); put("maximum", 5) })
            })
        })
    }.toString()

    suspend fun execute(commandJSON: String): String {
        val envelope = Json.parseToJsonElement(commandJSON).jsonObject
        val op = envelope.getValue("operation").jsonObject
        val command = BridgeCommand(
            op.getValue("tool").jsonPrimitive.content,
            op.getValue("arguments").jsonObject.mapValues { (_, value) -> if (value is JsonPrimitive) value.content else value.toString() },
            op.getValue("resolvedReferences").jsonObject.mapNotNull { (key, value) ->
                value.jsonObject["vendorHandle"]?.jsonPrimitive?.contentOrNull?.let { key to it }
            }.toMap(),
            (op.getValue("deadline").jsonPrimitive.double * 1000).toLong(),
            !op["approvedBy"]?.jsonPrimitive?.contentOrNull.isNullOrBlank(),
        )
        val result = if (envelope.getValue("command").jsonPrimitive.content == "stop") bridge.stop(command) else bridge.execute(command)
        return buildJsonObject {
            put("status", result.status); put("sdkUsed", result.sdkUsed); put("simulated", false)
            put("sdkAccepted", result.sdkAccepted?.let(::JsonPrimitive) ?: JsonNull)
            result.stopState?.let { state -> put("stopResult", buildJsonObject {
                put("state", state); put("sdkCode", result.stopSdkCode?.let(::JsonPrimitive) ?: JsonNull)
            }) }
            put("sdkResult", buildJsonObject {
                put("source", "ESIotKit / OfficialSdkBridge")
                put("code", result.sdkCode?.let(::JsonPrimitive) ?: JsonNull)
                put("message", result.message.take(1000))
            })
            put("data", buildJsonObject { result.data.forEach { (k, v) -> put(k, v) } })
            put("references", JsonArray(result.references.map { ref -> buildJsonObject {
                put("kind", ref.kind); put("label", ref.label); put("vendorHandle", ref.vendorHandle)
                put("ready", ref.ready); put("allowedTools", JsonArray(ref.allowedTools.map(::JsonPrimitive)))
                put("sourceTimestamp", ref.sourceTimestamp?.let(::JsonPrimitive) ?: JsonNull)
                put("sourceTimeKind", ref.sourceTimeKind)
            } }))
            result.errorCode?.let { code -> put("error", buildJsonObject { put("code", code); put("message", result.message.take(1000)) }) }
        }.toString()
    }
}
