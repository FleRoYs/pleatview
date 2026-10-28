package com.hustlesman.pleatview

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/** Starts the control service after boot/updates and, if allowed, opens the dashboard. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        ControlService.start(context)

        val app = PleatApp.from(context)
        val config = app.settings.config
        if (action == Intent.ACTION_BOOT_COMPLETED && config.launchOnBoot && config.isConfigured &&
            app.hub.canOpenFromBackground()
        ) {
            try {
                context.startActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            } catch (e: Exception) {
                Log.w("PleatView", "Could not open PleatView after boot", e)
            }
        }
    }
}
