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
import com.anker.esiotkit.mega.category.Category
import com.anker.esiotkit.sample.main.mega.login.business.BusinessLoginConfig
import com.anker.esiotkit.sample.support.utils.domain.DomainProfileDefaults
import com.anker.esiotkit.support.di.esInject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Swift-facing, read-only bootstrap bridge. No live sessions or device controls.
 * Receipts contain device identity and raw capability declarations, never credentials.
 */
class EvidenceGuardSDKBridge {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var generation = 0

    fun connect(userId: String, token: String, environment: String, completion: (String) -> Unit) {
        generation += 1
        val current = generation
        scope.coroutineContext.cancelChildren()
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

    fun disconnect() {
        generation += 1
        scope.coroutineContext.cancelChildren()
        if (startupEnvironment != null) runCatching { ESIotKit.logout() }
    }

    private fun strings(items: List<String>) = JsonArray(items.distinct().sorted().map(::JsonPrimitive))
    private fun failure(code: String) = buildJsonObject { put("status", "failed"); put("code", code) }.toString()

    private companion object {
        // SDK startup is process-wide. Credentials may be refreshed; an environment switch requires restart.
        var startupEnvironment: String? = null
    }
}
