package com.hustlesman.pleatview

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import androidx.core.content.edit
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList

/** Persistent storage for the device identity, configuration and pairing tokens. */
class Settings(private val context: Context) : Pairing.Store {
    private val prefs = context.getSharedPreferences("pleatview", Context.MODE_PRIVATE)
    private val listeners = CopyOnWriteArrayList<(old: Config, new: Config) -> Unit>()

    val port: Int = DEFAULT_PORT

    val deviceId: String = prefs.getString(KEY_DEVICE_ID, null)
        ?: stableDeviceId().also { prefs.edit { putString(KEY_DEVICE_ID, it) } }

    @Volatile
    var config: Config = load()
        private set

    /** The name shown in Home Assistant: the configured name, else the TV's own device name. */
    val deviceName: String
        get() = config.deviceName.ifEmpty { systemDeviceName() }

    @Synchronized
    fun update(update: JSONObject): Config {
        val old = config
        val new = old.merge(update)
        prefs.edit { putString(KEY_CONFIG, new.toJson(includeSecrets = true).toString()) }
        config = new
        listeners.forEach { it(old, new) }
        return new
    }

    fun addListener(listener: (old: Config, new: Config) -> Unit) {
        listeners += listener
    }

    fun removeListener(listener: (old: Config, new: Config) -> Unit) {
        listeners -= listener
    }

    override fun loadTokens(): String? = prefs.getString(KEY_TOKENS, null)

    override fun saveTokens(json: String) {
        prefs.edit { putString(KEY_TOKENS, json) }
    }

    private fun load(): Config {
        val raw = prefs.getString(KEY_CONFIG, null) ?: return Config()
        return runCatching { Config.fromJson(JSONObject(raw)) }.getOrDefault(Config())
    }

    /**
     * ANDROID_ID is scoped to this app's signing key and survives reinstalls and
     * cleared data, so Home Assistant recognises the TV afterwards and only asks to
     * pair again. It is hashed because the ID is advertised on the network.
     */
    @SuppressLint("HardwareIds")
    private fun stableDeviceId(): String {
        val androidId = android.provider.Settings.Secure.getString(
            context.contentResolver, android.provider.Settings.Secure.ANDROID_ID,
        )
        if (androidId.isNullOrEmpty() || androidId == BROKEN_ANDROID_ID) {
            return UUID.randomUUID().toString().replace("-", "")
        }
        return Pairing.sha256("pleatview:$androidId").take(32)
    }

    private fun systemDeviceName(): String {
        val name = if (Build.VERSION.SDK_INT >= 25) {
            android.provider.Settings.Global.getString(
                context.contentResolver, android.provider.Settings.Global.DEVICE_NAME,
            )
        } else {
            null
        }
        return name?.takeIf { it.isNotBlank() } ?: Build.MODEL.ifBlank { "Android TV" }
    }

    companion object {
        const val DEFAULT_PORT = 8765
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_CONFIG = "config"
        private const val KEY_TOKENS = "tokens"
        private const val BROKEN_ANDROID_ID = "9774d56d682e549c" // shared by some Android 2.2 devices
    }
}
