package com.hustlesman.pleatview

import android.app.Application
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Process-wide switchboard between the control API (background threads) and the
 * UI. Commands are routed to the visible [Display]; state changes are published
 * to Server-Sent Event listeners.
 */
class Hub(
    private val app: Application,
    private val settings: Settings,
    private val pairing: Pairing,
) : Api.Backend {

    /** Implemented by MainActivity. All calls happen on the main thread. */
    interface Display {
        val isVisible: Boolean
        fun handle(command: Command)
        fun onConfigChanged(old: Config, new: Config)
        fun onPairingChanged()
    }

    private val main = Handler(Looper.getMainLooper())
    private val state = StateModel()
    private val stateListeners = CopyOnWriteArrayList<(String) -> Unit>()
    private val pending = ArrayDeque<Pair<Long, Command>>()
    private var publishScheduled = false
    private val systemOverlay = SystemOverlay(app)

    @Volatile
    private var stateJson: String

    var display: Display? = null

    init {
        state.configRev = settings.config.rev
        stateJson = render()
        settings.addListener { old, new ->
            main.post {
                display?.onConfigChanged(old, new)
                update { configRev = new.rev }
            }
        }
        pairing.onChanged = { main.post { display?.onPairingChanged() } }
    }

    // ---- Api.Backend (called from server threads) ----

    override fun info(): JSONObject = JSONObject()
        .put("id", settings.deviceId)
        .put("name", settings.deviceName)
        .put("manufacturer", Build.MANUFACTURER)
        .put("model", Build.MODEL)
        .put("app_version", BuildConfig.VERSION_NAME)
        .put("api_version", Api.API_VERSION)

    override fun stateJson(): String = stateJson

    override fun addStateListener(listener: (String) -> Unit) {
        stateListeners += listener
    }

    override fun removeStateListener(listener: (String) -> Unit) {
        stateListeners -= listener
    }

    override fun dispatch(command: Command) {
        main.post { route(command) }
    }

    override fun config(): Config = settings.config

    override fun updateConfig(update: JSONObject): Config = settings.update(update)

    // ---- main thread ----

    private fun route(command: Command) {
        val display = display
        if (display != null && display.isVisible) {
            display.handle(command)
            return
        }
        when {
            command is Command.Notify -> {
                if (!systemOverlay.show(command)) Log.i(TAG, "Dropping notification: PleatView is in the background")
            }
            command.needsDisplay -> {
                if (command == Command.TurnOn) wakeScreen()
                pending.addLast(SystemClock.elapsedRealtime() to command)
                while (pending.size > MAX_PENDING) pending.removeFirst()
                bringToFront()
            }
            display != null -> display.handle(command)
        }
    }

    /** Commands that arrived while the UI was hidden; stale ones are dropped. */
    fun takePending(): List<Command> {
        val cutoff = SystemClock.elapsedRealtime() - PENDING_TTL_MS
        val commands = pending.filter { it.first >= cutoff }.map { it.second }
        pending.clear()
        return commands
    }

    /** Mutates the published state. Main thread only; changes are coalesced. */
    fun update(block: StateModel.() -> Unit) {
        state.block()
        if (publishScheduled) return
        publishScheduled = true
        main.postDelayed({
            publishScheduled = false
            val json = render()
            if (json != stateJson) {
                stateJson = json
                stateListeners.forEach { it(json) }
            }
        }, PUBLISH_DELAY_MS)
    }

    fun canDrawOverlays(): Boolean = systemOverlay.isAllowed()

    private fun render(): String =
        state.toJson().put("app_version", BuildConfig.VERSION_NAME).toString()

    private fun bringToFront() {
        val intent = Intent(app, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            app.startActivity(intent)
        } catch (e: Exception) {
            Log.w(TAG, "Could not bring PleatView to the front", e)
        }
    }

    @Suppress("DEPRECATION")
    private fun wakeScreen() {
        val power = app.getSystemService(Context.POWER_SERVICE) as PowerManager
        if (power.isInteractive) return
        power.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP or PowerManager.ON_AFTER_RELEASE,
            "pleatview:wake",
        ).acquire(5_000)
    }

    companion object {
        private const val TAG = "PleatView"
        private const val MAX_PENDING = 10
        private const val PENDING_TTL_MS = 30_000L
        private const val PUBLISH_DELAY_MS = 50L
    }
}

/** Everything Home Assistant needs to render the media_player entity. */
class StateModel {
    var foreground = false
    var power = POWER_ON
    var view = VIEW_SETUP
    var url: String? = null
    var dashboard: String? = null
    var haConnected: Boolean? = null
    var authError = false
    var lastError: String? = null
    var overlay: OverlayInfo? = null
    var media: MediaInfo? = null
    var volume = 1.0
    var muted = false
    var configRev = ""
    var overlayPermission = false

    fun toJson(): JSONObject = JSONObject()
        .put("foreground", foreground)
        .put("power", power)
        .put("view", view)
        .put("url", url ?: JSONObject.NULL)
        .put("dashboard", dashboard ?: JSONObject.NULL)
        .put("ha_connected", haConnected ?: JSONObject.NULL)
        .put("auth_error", authError)
        .put("last_error", lastError ?: JSONObject.NULL)
        .put("overlay", overlay?.toJson() ?: JSONObject.NULL)
        .put("media", media?.toJson() ?: JSONObject.NULL)
        .put("volume", volume)
        .put("muted", muted)
        .put("config_rev", configRev)
        .put("overlay_permission", overlayPermission)

    companion object {
        const val POWER_ON = "on"
        const val POWER_STANDBY = "standby"
        const val VIEW_SETUP = "setup"
        const val VIEW_DASHBOARD = "dashboard"
    }
}

data class OverlayInfo(val kind: String, val url: String, val mode: String) {
    fun toJson(): JSONObject = JSONObject().put("kind", kind).put("url", url).put("mode", mode)
}

data class MediaInfo(
    val state: String,
    val url: String,
    val mimeType: String?,
    val title: String?,
    val artist: String?,
    val imageUrl: String?,
    val mode: String,
    val position: Double,
    val duration: Double?,
    val updatedAt: Double,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("state", state)
        .put("url", url)
        .put("mime_type", mimeType ?: JSONObject.NULL)
        .put("title", title ?: JSONObject.NULL)
        .put("artist", artist ?: JSONObject.NULL)
        .put("image_url", imageUrl ?: JSONObject.NULL)
        .put("mode", mode)
        .put("position", position)
        .put("duration", duration ?: JSONObject.NULL)
        .put("updated_at", updatedAt)
}
