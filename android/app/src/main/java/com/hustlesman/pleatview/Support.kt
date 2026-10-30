package com.hustlesman.pleatview

import android.content.Context
import android.os.Build

/**
 * "Support PleatView" in the menu: a QR code for the donation page. Only the GitHub
 * download has the address; store builds are made without it. As a second guard, an
 * install that came from a store never shows it.
 */
object Support {
    private val STORES = setOf("com.android.vending", "com.amazon.venezia")

    fun offered(donateUrl: String, installer: String?): Boolean = donateUrl.isNotEmpty() && installer !in STORES

    fun installer(context: Context): String? = try {
        if (Build.VERSION.SDK_INT >= 30) {
            context.packageManager.getInstallSourceInfo(context.packageName).installingPackageName
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.getInstallerPackageName(context.packageName)
        }
    } catch (e: Exception) {
        null
    }
}
