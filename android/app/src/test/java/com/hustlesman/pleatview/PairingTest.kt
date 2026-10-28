package com.hustlesman.pleatview

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingTest {
    private class MemoryStore : Pairing.Store {
        var json: String? = null
        override fun loadTokens() = json
        override fun saveTokens(json: String) {
            this.json = json
        }
    }

    private var now = 1_000_000L
    private val store = MemoryStore()
    private fun pairing() = Pairing(store, clock = { now })

    @Test
    fun `correct pin issues a token and rotates the pin`() {
        val pairing = pairing()
        val pin = pairing.pin
        val result = pairing.pair(pin.chunked(3).joinToString(" "), "Home Assistant") as Pairing.Result.Paired
        assertTrue(pairing.isValid(result.token))
        assertFalse(pairing.isValid("nope"))
        assertNotEquals(pin, pairing.pin)
        assertTrue(pairing.isPaired)
        assertFalse(store.json!!.contains(result.token)) // only hashes are stored
        assertTrue(pairing().isValid(result.token)) // survives restarts
    }

    @Test
    fun `repeated failures lock pairing and change the pin`() {
        val pairing = pairing()
        val pin = pairing.pin
        val wrong = if (pin == "000000") "111111" else "000000"
        repeat(Pairing.MAX_FAILURES) { assertEquals(Pairing.Result.InvalidPin, pairing.pair(wrong, "x")) }
        assertNotEquals(pin, pairing.pin)
        assertTrue(pairing.pair(pairing.pin, "x") is Pairing.Result.LockedOut)
        now += Pairing.LOCKOUT_MS + 1
        assertTrue(pairing.pair(pairing.pin, "x") is Pairing.Result.Paired)
    }

    @Test
    fun `revoking removes only that token`() {
        val pairing = pairing()
        val a = (pairing.pair(pairing.pin, "a") as Pairing.Result.Paired).token
        val b = (pairing.pair(pairing.pin, "b") as Pairing.Result.Paired).token
        pairing.revoke(a)
        assertFalse(pairing.isValid(a))
        assertTrue(pairing.isValid(b))
        pairing.revokeAll()
        assertFalse(pairing.isValid(b))
    }
}
