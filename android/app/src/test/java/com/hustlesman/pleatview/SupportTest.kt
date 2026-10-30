package com.hustlesman.pleatview

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SupportTest {
    private val url = "https://pleatview.hustlesman.com/donate"

    @Test
    fun `the GitHub download offers it when sideloaded`() {
        assertTrue(Support.offered(url, null))
        assertTrue(Support.offered(url, "com.esaba.downloader"))
        assertTrue(Support.offered(url, "com.android.shell"))
    }

    @Test
    fun `a store build never offers it`() {
        assertFalse(Support.offered("", null))
    }

    @Test
    fun `an install from a store never offers it`() {
        assertFalse(Support.offered(url, "com.android.vending"))
        assertFalse(Support.offered(url, "com.amazon.venezia"))
    }
}
