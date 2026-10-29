package com.hustlesman.pleatview

/** When PleatView comes back by itself after someone left it for another app. */
object Reopen {
    /**
     * Due once PleatView has been off screen for [minutes] and nothing has played sound for
     * as long: someone switched to another app and isn't watching anything there.
     *
     * @param hiddenSince when PleatView left the screen, 0 while it's on screen
     * @param lastSound when another app last played sound, 0 if never
     */
    fun due(now: Long, hiddenSince: Long, lastSound: Long, minutes: Int, allowed: Boolean): Boolean {
        if (!allowed || minutes <= 0 || hiddenSince == 0L) return false
        val wait = minutes * 60_000L
        return now - hiddenSince >= wait && now - lastSound >= wait
    }
}
