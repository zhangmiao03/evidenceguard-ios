@file:OptIn(com.anker.esiotkit.support.InternalIotApi::class)

package com.anker.esiotkit.sample.evidenceguard

import com.anker.esiotkit.ESIotKit
import com.anker.esiotkit.core.config.ESIotAppConfig
import com.anker.esiotkit.core.config.ESIotUserConfig
import com.anker.esiotkit.core.config.MegaAppDomain
import com.anker.esiotkit.core.device.MegaDeviceManager
import com.anker.esiotkit.core.domain.repository.DeviceRepository
import com.anker.esiotkit.domain_thing.api.internal.ESIotDeviceManagerImpl
import com.anker.esiotkit.domain_thing.model.device.MegaDevice
import com.anker.esiotkit.domain.model.MegaEvent
import com.anker.esiotkit.core.entities.event.DetectionType
import com.anker.esiotkit.event.model.EventCondition
import com.anker.esiotkit.manager.MegaEventManager
import com.anker.esiotkit.mega.category.Category
import com.anker.esiotkit.sample.main.mega.login.business.BusinessLoginConfig
import com.anker.esiotkit.sample.model.isOnline
import com.anker.esiotkit.sample.support.utils.domain.DomainProfileDefaults
import com.anker.esiotkit.support.di.esInject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.delay
import com.anker.esiotkit.media.live_stream.LiveMediaPlayer
import com.anker.esiotkit.media.live_stream.LiveParams
import com.anker.esiotkit.media.live_stream.LivePlayListener
import com.anker.esiotkit.media.live_stream.LivePlayerState
import com.anker.esiotkit.media.live_stream.LiveType
import com.anker.esiotkit.media.RecordState
import com.anker.esiotkit.media.TalkState
import com.anker.esiotkit.media.VideoInfo
import com.anker.esiotkit.support.platform.IotImage
import com.anker.esiotkit.support.platform.currentTimeMillis
import com.anker.esiotkit.security_device.p2p.P2PPingManager
import platform.UIKit.UIImage
import platform.UIKit.UIView
import platform.UIKit.UIViewController
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.window.ComposeUIViewController
import com.anker.esiotkit.sample.main.SampleApp
import com.anker.esiotkit.sample.main.iosMainViewController
import com.anker.esiotkit.sample.support.cache.InfoCache
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Swift-facing device inspection and foreground live media factory.
 * Receipts contain device identity and raw capability declarations, never credentials.
 */
class EvidenceGuardSDKBridge {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var generation = 0
    private var discoveredSn = emptySet<String>()
    private val eventCache = mutableMapOf<String, MegaEvent>()
    private var activeLive: EvidenceGuardLiveBridge? = null
    private var officialHost: EvidenceGuardOfficialHost? = null

    /** Host the same SampleApp() used by the official MainViewController.
     * Keep its entire navigator, binding flows and capability-driven settings.
     * The disposable wrapper lets Swift await Compose cleanup before reconnecting.
     */
    fun openOfficialDemo(): UIViewController {
        check(officialHost == null) { "official_demo_already_open" }
        disconnect()
        InfoCache.tokenValid = false
        InfoCache.userConfig = ""
        startupEnvironment = null
        return EvidenceGuardOfficialHost().also { officialHost = it }.controller
    }

    fun closeOfficialDemo(completion: () -> Unit) {
        val host = officialHost
        if (host == null) { completion(); return }
        host.close {
            officialHost = null
            InfoCache.tokenValid = false
            InfoCache.userConfig = ""
            runCatching { ESIotKit.logout() }
            // The official business form can change account and environment.
            // Product mode must initialize its own config again, not reuse it.
            startupEnvironment = null
            discoveredSn = emptySet()
            completion()
        }
    }

    fun createLive(sn: String): EvidenceGuardLiveBridge? {
        if (sn !in discoveredSn) return null
        val device = esInject<DeviceRepository>().getIotDeviceBy(sn)?.let { MegaDevice(it) } ?: return null
        activeLive?.stop()
        return EvidenceGuardLiveBridge(device).also { activeLive = it }
    }

    fun stopLive() {
        activeLive?.stop()
        activeLive = null
    }

    fun connect(userId: String, token: String, environment: String, completion: (String) -> Unit) {
        if (officialHost != null) { completion(failure("official_demo_active")); return }
        stopLive()
        generation += 1
        val current = generation
        scope.coroutineContext.cancelChildren()
        discoveredSn = emptySet()
        eventCache.clear()
        if (userId.isBlank() || token.isBlank() || environment !in listOf("PR", "QA")) {
            completion(failure("invalid_configuration")); return
        }
        if (startupEnvironment != null && startupEnvironment != environment) {
            completion(failure("environment_restart_required")); return
        }
        scope.launch {
            try {
                if (startupEnvironment == null) {
                    val config = ESIotAppConfig().apply {
                        appName = if (environment == "QA") BusinessLoginConfig.EnvQA.APP_NAME else BusinessLoginConfig.EnvPR.APP_NAME
                        clientId = if (environment == "QA") BusinessLoginConfig.EnvQA.CLIENT_ID else BusinessLoginConfig.EnvPR.CLIENT_ID
                    }
                    ESIotKit.start(config)
                    startupEnvironment = environment
                }
                val host = if (environment == "QA") BusinessLoginConfig.EnvQA.APP_DOMAIN else BusinessLoginConfig.EnvPR.APP_DOMAIN
                val preset = if (environment == "QA") DomainProfileDefaults.QA else DomainProfileDefaults.US
                ESIotKit.setUserConfig(ESIotUserConfig().apply {
                    this.userId = userId.trim()
                    authorization = token.trim()
                    presetKey = preset
                    deviceDomain = if (environment == "QA") BusinessLoginConfig.EnvQA.DEVICE_DOMAIN else BusinessLoginConfig.EnvPR.DEVICE_DOMAIN
                    appDomain = MegaAppDomain().apply {
                        setMegaDomain(host)
                        setDomainBy(Category.Security, host, preset)
                    }
                })
                val result = withTimeout(30_000) { MegaDeviceManager.refreshDeviceList().await() }
                if (current != generation) return@launch
                if (result.code != 0 || result.data == null) {
                    completion(failure("device_query_${result.code}")); return@launch
                }
                discoveredSn = result.data.orEmpty()
                    .filter { it.devicePn in listOf("T8171", "T8214") }.map { it.deviceSn }.toSet()
                val manager = ESIotDeviceManagerImpl { sn ->
                    esInject<DeviceRepository>().getIotDeviceBy(sn)?.let { MegaDevice(it) }
                }
                val devices = result.data.orEmpty().map { device ->
                    val capabilities = manager.capability(device.deviceSn).getCapabilities()
                    buildJsonObject {
                        put("sn", device.deviceSn)
                        put("model", device.devicePn)
                        put("name", device.iotDevice.deviceName)
                        val online = runCatching { device.isOnline() }.getOrNull()
                        put("online", online?.let(::JsonPrimitive) ?: JsonNull)
                        put("capabilitiesReady", capabilities != null)
                        put("properties", strings(capabilities?.properties.orEmpty().map { it.identifier }))
                        put("actions", strings(capabilities?.actions.orEmpty().map { it.identifier }))
                        put("events", strings(capabilities?.events.orEmpty().map { it.identifier }))
                    }
                }
                completion(buildJsonObject {
                    put("status", "success")
                    put("devices", JsonArray(devices))
                }.toString())
            } catch (cancelled: CancellationException) {
                // A timeout is a failure; a replaced or disconnected request is discarded.
                if (current == generation) completion(failure("query_timeout"))
            } catch (_: Exception) {
                if (current == generation) completion(failure("query_failed"))
            }
        }
    }

    fun queryEvents(sn: String, startMs: Long, endMs: Long, completion: (String) -> Unit) {
        if (sn !in discoveredSn || startMs < 0 || endMs <= startMs || endMs - startMs > 172_800_000) {
            completion(failure("invalid_event_query")); return
        }
        val current = generation
        scope.launch {
            try {
                val condition = EventCondition().setDeviceSnList(listOf(sn))
                    .setStartTime(startMs).setEndTime(endMs).setCount(50)
                val events = withTimeout(30_000) {
                    suspendCancellableCoroutine<List<MegaEvent>> { continuation ->
                        MegaEventManager.query(condition, refresh = true, lastEventTime = 0L,
                            onSuccess = { if (continuation.isActive) continuation.resume(it) },
                            onFailure = { code, _ ->
                                if (continuation.isActive) continuation.resumeWithException(EventQueryError(code))
                            })
                    }
                }.filter { it.deviceSn == sn && it.startTimestamp >= startMs && it.startTimestamp < endMs }
                    .distinctBy { it.megaEventId }.sortedByDescending { it.startTimestamp }.take(50)
                if (current != generation) return@launch
                eventCache.clear()
                eventCache.putAll(events.associateBy { it.megaEventId })
                completion(buildJsonObject {
                    put("status", "success")
                    put("events", JsonArray(events.map { event -> buildJsonObject {
                        put("id", event.megaEventId)
                        put("deviceSn", event.deviceSn)
                        put("startMs", event.startTimestamp)
                        put("endMs", maxOf(event.startTimestamp, event.endTimestamp))
                        put("detectionType", when (event.thumbnail.detectionType) {
                            DetectionType.PACKAGE_PUT.value -> "package_put"
                            DetectionType.PACKAGE_TAKE.value -> "package_take"
                            DetectionType.HUMAN.value, DetectionType.FACE.value -> "human"
                            DetectionType.MOTION.value -> "motion"
                            DetectionType.CAR.value -> "vehicle"
                            DetectionType.PET.value -> "pet"
                            DetectionType.RING.value -> "ring"
                            else -> "unknown"
                        })
                        put("hasVideo", event.videoPath.isNotBlank())
                        put("hasThumbnail", event.thumbnail.picturePath.isNotBlank() ||
                            event.pictures.any { it.picturePath.isNotBlank() })
                    } }))
                }.toString())
            } catch (error: EventQueryError) {
                if (current == generation) completion(failure("event_query_${error.code}"))
            } catch (_: CancellationException) {
                if (current == generation) completion(failure("event_query_timeout"))
            } catch (_: Exception) {
                if (current == generation) completion(failure("event_query_failed"))
            }
        }
    }

    fun readPicture(sn: String, eventId: String?, completion: (String) -> Unit) {
        if (sn !in discoveredSn) { completion(failure("device_not_discovered")); return }
        val current = generation
        scope.launch {
            try {
                var source = "device_thumbnail"
                val image = withTimeout(30_000) {
                    if (eventId != null) {
                        val event = eventCache[eventId]?.takeIf { it.deviceSn == sn }
                            ?: throw IllegalArgumentException("event_not_in_query")
                        source = "event_thumbnail"
                        val picture = event.thumbnail.takeIf { it.picturePath.isNotBlank() && it.parentSn.isNotBlank() }
                            ?: event.pictures.firstOrNull { it.picturePath.isNotBlank() && it.parentSn.isNotBlank() }
                            ?: throw IllegalArgumentException("thumbnail_unavailable")
                        requestImage(picture.picturePath, picture.parentSn)
                    } else {
                        val manager = ESIotDeviceManagerImpl { deviceSn ->
                            esInject<DeviceRepository>().getIotDeviceBy(deviceSn)?.let { MegaDevice(it) }
                        }
                        var path = manager.picture(sn).getThumbnailPath()
                        if (path.isNullOrBlank()) {
                            source = "cached_cover"
                            path = manager.picture(sn).getCachedCoverPath()
                        }
                        if (path.isNullOrBlank()) throw IllegalArgumentException("thumbnail_unavailable")
                        requestImage(path, sn)
                    }
                }
                if (current != generation) return@launch
                if (image.isBlank() || image.length > 14_000_000) {
                    completion(failure("invalid_thumbnail")); return@launch
                }
                completion(buildJsonObject {
                    put("status", "success")
                    put("base64", image)
                    put("imageSource", source)
                    // A successful read is not proof of a fresh capture.
                }.toString())
            } catch (_: CancellationException) {
                if (current == generation) completion(failure("picture_timeout"))
            } catch (_: Exception) {
                if (current == generation) completion(failure("picture_unavailable"))
            }
        }
    }

    private suspend fun requestImage(path: String, sn: String): String =
        suspendCancellableCoroutine { continuation ->
            MegaEventManager.getEventImageBase64(path, sn,
                onSuccess = { if (continuation.isActive) continuation.resume(it) },
                onFailure = { code, _ ->
                    if (continuation.isActive) continuation.resumeWithException(EventQueryError(code))
                })
        }

    private class EventQueryError(val code: Int) : Exception()

    fun cancelInspection() {
        generation += 1
        scope.coroutineContext.cancelChildren()
        eventCache.clear()
    }

    fun disconnect() {
        stopLive()
        generation += 1
        scope.coroutineContext.cancelChildren()
        discoveredSn = emptySet()
        eventCache.clear()
        if (startupEnvironment != null) runCatching { ESIotKit.logout() }
    }

    private fun strings(items: List<String>) = JsonArray(items.distinct().sorted().map(::JsonPrimitive))
    private fun failure(code: String) = buildJsonObject { put("status", "failed"); put("code", code) }.toString()

    private companion object {
        // SDK startup is process-wide. Credentials may be refreshed; an environment switch requires restart.
        var startupEnvironment: String? = null
    }
}

/** Same official root as Main.kt; no recreation of the vendor's UI/actions. */
private class EvidenceGuardOfficialHost {
    private val visible = mutableStateOf(true)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var closeStarted = false
    private var contentMounted = false
    private var callback: (() -> Unit)? = null
    val controller: UIViewController = ComposeUIViewController {
        if (visible.value) {
            DisposableEffect(Unit) {
                contentMounted = true
                onDispose { finishClose() }
            }
            SampleApp()
        }
    }.apply { iosMainViewController = this }

    fun close(completion: () -> Unit) {
        if (closeStarted) return
        closeStarted = true
        callback = completion
        visible.value = false
        if (!contentMounted) finishClose()
    }

    private fun finishClose() {
        if (!closeStarted) return
        val done = callback ?: return
        callback = null
        scope.launch {
            // Official live/event/preset/download composables dispose their
            // players and jobs; give their deferred native release time to run.
            delay(700)
            if (iosMainViewController == controller) iosMainViewController = null
            done()
        }
    }
}

/** One foreground player. UIImage samples are client readouts, not sensor timestamps.
 * Main-thread ownership matches the official iOS renderer. The vendor shutdown
 * grace period is retained using coroutine delay instead of blocking NSThread.
 */
class EvidenceGuardLiveBridge internal constructor(private val device: MegaDevice) {
    private val player = LiveMediaPlayer(device)
    private val pingManager: P2PPingManager = esInject()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var callback: ((String) -> Unit)? = null
    private var started = false
    private var stopping = false
    private var playing = false
    private var resolutionReady = false
    private var lastActivity = 0L
    private var activity = 0

    fun activitySequence(): Int = activity

    private fun markActivity() {
        lastActivity = currentTimeMillis()
        activity += 1
    }

    fun renderView(): UIView = player.getRenderView()

    fun start(onState: (String) -> Unit) {
        if (started || stopping) return
        started = true
        callback = onState
        onState("connecting")
        player.setPlayListener(object : LivePlayListener {
            override fun onPlayState(status: LivePlayerState, message: String) {
                scope.launch {
                    if (stopping) return@launch
                    playing = status == LivePlayerState.Playing
                    if (!playing) resolutionReady = false
                    callback?.invoke(when (status) {
                        LivePlayerState.Playing -> "playing"
                        LivePlayerState.Loading -> "connecting"
                        LivePlayerState.Failed, LivePlayerState.Timeout -> "failed"
                        LivePlayerState.Stop -> "stopped"
                        else -> "connecting"
                    })
                }
            }
            override fun onResolution(width: Int, height: Int) {
                scope.launch { if (!stopping && width > 0 && height > 0) { resolutionReady = true; markActivity() } }
            }
            override fun onRate(rate: Int) {
                scope.launch { if (!stopping && rate > 0) markActivity() }
            }
            override fun onVideoInfo(info: VideoInfo) {
                scope.launch { if (!stopping && info.width > 0 && info.height > 0) { resolutionReady = true; markActivity() } }
            }
            override fun onSpeakState(status: TalkState, message: String) {}
            override fun onRecordState(status: RecordState, timeStamp: Long, message: String) {}
            override fun onMuteState(isMute: Boolean) {}
            override fun onCutImage(image: IotImage) {}
        })
        val params = LiveParams().apply { liveType = LiveType.Hotspot }
        // Competition models use the official default main/composite layout;
        // do not invent a second independently subscribable doorbell stream.
        runCatching { pingManager.startForeverPing(device.iotDevice); player.startPlay(params) }.onFailure { onState("failed") }
    }

    fun capture(): UIImage? {
        if (stopping || !playing || !resolutionReady || currentTimeMillis() - lastActivity > 4000) return null
        return runCatching { player.cutImage() }.getOrNull()
    }

    fun stop() {
        if (stopping) return
        stopping = true
        playing = false
        resolutionReady = false
        callback = null
        runCatching { pingManager.stopForeverPing(device.iotDevice) }
        runCatching { player.stopPlay() }
        scope.launch {
            delay(500)
            runCatching { player.release() }
        }
    }
}
