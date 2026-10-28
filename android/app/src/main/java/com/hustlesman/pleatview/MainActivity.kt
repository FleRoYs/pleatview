package com.hustlesman.pleatview

import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.window.OnBackInvokedDispatcher
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

class MainActivity : Activity(), Hub.Display, DashboardController.Callbacks, MediaController.Callbacks {
    private lateinit var app: PleatApp
    private lateinit var dashboard: DashboardController
    private lateinit var media: MediaController
    private lateinit var webOverlay: WebOverlay
    private lateinit var toasts: Toasts
    private lateinit var statusBanner: TextView
    private lateinit var setupScreen: View
    private lateinit var menuOverlay: View
    private lateinit var menuItems: LinearLayout
    private lateinit var curtain: View

    private val main = Handler(Looper.getMainLooper())
    private var visible = false
    private var standby = false
    private var started = false
    private var lastInput = 0L

    /** True after remote-control navigation; the idle timer then returns to the home dashboard. */
    private var userBrowsing = false

    private val config: Config get() = app.settings.config
    private val menuVisible: Boolean get() = menuOverlay.visibility == View.VISIBLE

    private val revertRunnable = Runnable { dashboard.navigate(config.homePath) }
    private val setupRefresh = object : Runnable {
        override fun run() {
            refreshSetup()
            main.postDelayed(this, 10_000)
        }
    }
    private val rotateRunnable = object : Runnable {
        override fun run() {
            val seconds = config.rotateSeconds
            if (seconds <= 0) return
            val idle = SystemClock.elapsedRealtime() - lastInput > ROTATE_INPUT_GRACE_MS
            if (visible && !standby && idle && !menuVisible && !media.isFullscreen && !webOverlay.isFullscreen) {
                cycleDashboard(+1)
            }
            main.postDelayed(this, seconds * 1000L)
        }
    }
    private val idleRunnable = object : Runnable {
        override fun run() {
            val minutes = config.returnHomeMinutes
            val idleMs = SystemClock.elapsedRealtime() - lastInput
            if (minutes > 0 && userBrowsing && idleMs > minutes * 60_000L && !media.isActive && webOverlay.current == null) {
                userBrowsing = false
                closeMenu()
                dashboard.navigate(config.homePath)
            }
            main.postDelayed(this, 30_000)
        }
    }

    override val isVisible: Boolean get() = visible

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        app = PleatApp.from(this)
        setContentView(R.layout.activity_main)
        hideSystemBars()
        if (Build.VERSION.SDK_INT >= 27) {
            setTurnScreenOn(true)
            setShowWhenLocked(true)
        }

        statusBanner = findViewById(R.id.status_banner)
        setupScreen = findViewById(R.id.setup_screen)
        menuOverlay = findViewById(R.id.menu_overlay)
        menuItems = findViewById(R.id.menu_items)
        curtain = findViewById(R.id.standby_curtain)
        toasts = Toasts(findViewById(R.id.toast_layer))
        dashboard = DashboardController(this, findViewById(R.id.dashboard_container), app.hub, this)
        media = MediaController(
            this, findViewById(R.id.media_container), findViewById(R.id.player_view),
            NowPlaying(findViewById(R.id.now_playing)), app.hub, this,
        )
        webOverlay = WebOverlay(this, findViewById(R.id.web_overlay_container), app.hub) { onLayerClosed() }
        menuOverlay.setOnClickListener { closeMenu() }

        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT) { handleBack() }
        }

        app.hub.display = this
        ControlService.start(this)
        applyConfig(null, config)
        main.postDelayed(idleRunnable, 30_000)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
        drainPending()
    }

    override fun onStart() {
        super.onStart()
        visible = true
        ControlService.start(this)
        dashboard.onResume()
        applyKeepScreenOn()
        val overlays = app.hub.canDrawOverlays()
        app.hub.update {
            foreground = true
            overlayPermission = overlays
        }
        drainPending()
    }

    override fun onStop() {
        visible = false
        media.stop()
        webOverlay.close()
        closeMenu()
        dashboard.onPause()
        app.hub.update { foreground = false }
        super.onStop()
    }

    override fun onDestroy() {
        if (app.hub.display === this) app.hub.display = null
        main.removeCallbacksAndMessages(null)
        media.release()
        webOverlay.close()
        dashboard.destroy()
        super.onDestroy()
    }

    // ---- Hub.Display ------------------------------------------------------------------

    override fun handle(command: Command) {
        if (standby && command.needsDisplay) wake()
        when (command) {
            is Command.ShowDashboard -> {
                closeFullscreenLayers()
                closeMenu()
                userBrowsing = false
                dashboard.navigate(command.path)
                main.removeCallbacks(revertRunnable)
                command.duration?.let { main.postDelayed(revertRunnable, it * 1000L) }
            }
            is Command.ShowWeb -> {
                if (command.layout.mode == Command.Mode.FULLSCREEN && media.isFullscreen) media.stop()
                webOverlay.show(command)
            }
            is Command.PlayMedia -> {
                if (!command.announce && command.layout.mode == Command.Mode.FULLSCREEN && webOverlay.isFullscreen) {
                    webOverlay.close()
                }
                media.play(command)
            }
            is Command.Notify -> toasts.show(command)
            is Command.Seek -> media.seek(command.position)
            is Command.SetVolume -> media.setVolume(command.level)
            is Command.Mute -> media.setMuted(command.muted)
            Command.Home -> goHome()
            Command.Reload -> dashboard.reload()
            Command.Play -> media.resume()
            Command.Pause -> media.pause()
            Command.Stop -> {
                media.stop()
                webOverlay.close()
            }
            Command.TurnOn -> wake()
            Command.TurnOff -> enterStandby()
            Command.NextDashboard -> cycleDashboard(+1)
            Command.PreviousDashboard -> cycleDashboard(-1)
        }
    }

    override fun onConfigChanged(old: Config, new: Config) = applyConfig(old, new)

    override fun onPairingChanged() {
        if (setupScreen.visibility == View.VISIBLE) refreshSetup()
        if (menuVisible) openMenu()
    }

    // ---- Callbacks from controllers -------------------------------------------------

    override fun onStatus(message: String?) {
        statusBanner.text = message
        statusBanner.visibility = if (message == null) View.GONE else View.VISIBLE
    }

    override fun onMediaClosed() = onLayerClosed()

    override fun onMediaError(message: String) {
        toasts.show(Command.Notify(null, getString(R.string.playback_failed, message), null, 8, Command.Position.TOP_RIGHT))
    }

    private fun onLayerClosed() {
        if (!media.isFullscreen && !webOverlay.isFullscreen && !menuVisible) dashboard.focus()
    }

    // ---- Configuration ----------------------------------------------------------------

    private fun applyConfig(old: Config?, new: Config) {
        showSetup(!new.isConfigured)
        if (new.isConfigured) {
            if (!started || old == null) {
                dashboard.start(new)
                started = true
            } else {
                dashboard.applyConfig(old, new)
            }
        }
        applyKeepScreenOn()
        main.removeCallbacks(rotateRunnable)
        if (new.rotateSeconds > 0) main.postDelayed(rotateRunnable, new.rotateSeconds * 1000L)
    }

    private fun showSetup(show: Boolean) {
        setupScreen.visibility = if (show) View.VISIBLE else View.GONE
        main.removeCallbacks(setupRefresh)
        if (show) main.post(setupRefresh)
        app.hub.update { view = if (show) StateModel.VIEW_SETUP else StateModel.VIEW_DASHBOARD }
    }

    private fun refreshSetup() {
        val ip = NetUtil.localIpv4()
        val port = app.settings.port
        findViewById<TextView>(R.id.setup_address).text =
            if (ip != null) "Host  $ip     Port  $port" else getString(R.string.setup_no_network)
        findViewById<TextView>(R.id.setup_pin).text = formatPin(app.pairing.pin)
        findViewById<TextView>(R.id.setup_manual).text =
            getString(R.string.setup_manual, if (ip != null) "http://$ip:$port" else "http://<tv-address>:$port")
        findViewById<TextView>(R.id.setup_device).text =
            getString(R.string.setup_device, app.settings.deviceName, BuildConfig.VERSION_NAME)
    }

    private fun applyKeepScreenOn() {
        if (config.keepScreenOn && !standby) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    // ---- Navigation -----------------------------------------------------------------

    private fun goHome() {
        main.removeCallbacks(revertRunnable)
        closeMenu()
        media.stop()
        webOverlay.close()
        userBrowsing = false
        dashboard.navigate(config.homePath)
    }

    private fun closeFullscreenLayers() {
        if (media.isFullscreen) media.stop()
        if (webOverlay.isFullscreen) webOverlay.close()
    }

    private fun cycleDashboard(step: Int) {
        val list = config.dashboards
        if (list.isEmpty()) return
        val index = list.indexOfFirst { it.path == dashboard.lastTarget }
        val next = if (index < 0) (if (step > 0) 0 else list.size - 1) else (index + step + list.size) % list.size
        dashboard.navigate(list[next].path)
    }

    private fun handleIntent(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme != "pleatview") return
        when (data.host) {
            "home" -> handle(Command.Home)
            "reload" -> handle(Command.Reload)
            "dashboard" -> {
                val path = data.getQueryParameter("path") ?: data.path
                if (!path.isNullOrBlank() && path != "/") handle(Command.ShowDashboard(Config.normalizeTarget(path), null))
            }
        }
        setIntent(Intent(intent).setData(null))
    }

    private fun drainPending() {
        if (!visible) return
        app.hub.takePending().forEach(::handle)
    }

    // ---- Remote control ---------------------------------------------------------------

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        // API 33+ delivers Back through OnBackInvokedCallback instead of key events.
        if (event.keyCode == KeyEvent.KEYCODE_BACK && Build.VERSION.SDK_INT < 33) {
            if (event.action == KeyEvent.ACTION_UP && !event.isCanceled) handleBack()
            return true
        }
        if (event.action == KeyEvent.ACTION_DOWN) {
            lastInput = SystemClock.elapsedRealtime()
            if (standby) {
                wake()
                return true
            }
            when (event.keyCode) {
                KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_SETTINGS -> {
                    if (menuVisible) closeMenu() else openMenu()
                    return true
                }
                KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE,
                KeyEvent.KEYCODE_MEDIA_STOP, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD, KeyEvent.KEYCODE_MEDIA_REWIND,
                -> if (media.isActive) {
                    when (event.keyCode) {
                        KeyEvent.KEYCODE_MEDIA_PLAY -> media.resume()
                        KeyEvent.KEYCODE_MEDIA_PAUSE -> media.pause()
                        KeyEvent.KEYCODE_MEDIA_STOP -> media.stop()
                        KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> media.seekBy(SEEK_STEP_MS)
                        KeyEvent.KEYCODE_MEDIA_REWIND -> media.seekBy(-SEEK_STEP_MS)
                        else -> media.togglePlayPause()
                    }
                    return true
                }
                KeyEvent.KEYCODE_CHANNEL_UP, KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_MEDIA_NEXT -> {
                    userBrowsing = true
                    cycleDashboard(+1)
                    return true
                }
                KeyEvent.KEYCODE_CHANNEL_DOWN, KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_MEDIA_PREVIOUS -> {
                    userBrowsing = true
                    cycleDashboard(-1)
                    return true
                }
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_LEFT,
                KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                -> if (!menuVisible) userBrowsing = true
            }
        }
        return super.dispatchKeyEvent(event)
    }

    private fun handleBack() {
        lastInput = SystemClock.elapsedRealtime()
        when {
            standby -> wake()
            menuVisible -> closeMenu()
            media.isFullscreen -> media.stop()
            webOverlay.current != null -> webOverlay.close()
            media.isActive -> media.stop()
            !config.isConfigured -> openMenu()
            dashboard.goBack() -> Unit
            dashboard.lastTarget != config.homePath -> {
                userBrowsing = false
                dashboard.navigate(config.homePath)
            }
            else -> openMenu()
        }
    }

    // ---- Menu -------------------------------------------------------------------------

    private fun openMenu() {
        menuItems.removeAllViews()
        val ip = NetUtil.localIpv4() ?: "?"
        val info = getString(
            R.string.menu_info, app.settings.deviceName, "$ip:${app.settings.port}",
            formatPin(app.pairing.pin), BuildConfig.VERSION_NAME,
        )
        menuItems.addView(menuText(info, 15f))
        if (config.isConfigured) menuItems.addView(menuText(config.haUrl, 13f))
        if (!app.hub.canDrawOverlays()) menuItems.addView(menuText(getString(R.string.menu_overlay_missing), 13f))

        var first: Button? = null
        if (config.isConfigured) {
            first = addMenuButton(getString(R.string.menu_home)) { goHome() }
            config.dashboards.forEach { d ->
                addMenuButton(d.title) {
                    userBrowsing = true
                    dashboard.navigate(d.path)
                }
            }
            addMenuButton(getString(R.string.menu_reload)) { dashboard.reload() }
        }
        val exit = addMenuButton(getString(R.string.menu_exit)) { finish() }
        menuOverlay.visibility = View.VISIBLE
        (first ?: exit).requestFocus()
    }

    private fun closeMenu() {
        if (!menuVisible) return
        menuOverlay.visibility = View.GONE
        dashboard.focus()
    }

    private fun menuText(text: String, sizeSp: Float) = TextView(this).apply {
        this.text = text
        textSize = sizeSp
        setTextColor(getColor(R.color.text_secondary))
        setPadding(0, 0, 0, (12 * resources.displayMetrics.density).toInt())
    }

    private fun addMenuButton(label: String, action: () -> Unit): Button {
        val button = Button(this, null, 0, R.style.PleatView_MenuButton)
        button.text = label
        button.setOnClickListener {
            closeMenu()
            action()
        }
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        params.topMargin = (8 * resources.displayMetrics.density).toInt()
        menuItems.addView(button, params)
        return button
    }

    // ---- Standby ----------------------------------------------------------------------

    private fun enterStandby() {
        if (standby) return
        standby = true
        closeMenu()
        media.stop()
        webOverlay.close()
        curtain.visibility = View.VISIBLE
        dashboard.onPause()
        applyKeepScreenOn() // lets the TV's own screensaver/sleep timer take over
        app.hub.update { power = StateModel.POWER_STANDBY }
    }

    private fun wake() {
        if (!standby) return
        standby = false
        curtain.visibility = View.GONE
        dashboard.onResume()
        dashboard.focus()
        applyKeepScreenOn()
        app.hub.update { power = StateModel.POWER_ON }
    }

    private fun hideSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    private fun formatPin(pin: String) = pin.chunked(3).joinToString(" ")

    companion object {
        private const val ROTATE_INPUT_GRACE_MS = 60_000L
        private const val SEEK_STEP_MS = 10_000L
    }
}
