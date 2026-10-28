package com.hustlesman.pleatview

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SetupCodeTest {
    @Test
    fun urlCarriesThePinInTheFragment() {
        assertEquals("http://192.168.1.30:8765/#pin=123456", SetupCode.url("192.168.1.30", 8765, "123456"))
    }

    @Test
    fun modulesHaveAQuietZoneAndFinderPatterns() {
        val rows = SetupCode.modules(SetupCode.url("192.168.1.30", 8765, "123456"))
        assertTrue(rows.size >= 25 + 4)
        assertTrue(rows.all { it.size == rows.size })
        assertFalse(rows[0].any { it }) // quiet zone
        assertTrue(rows[2][2]) // top-left finder pattern
    }
}
