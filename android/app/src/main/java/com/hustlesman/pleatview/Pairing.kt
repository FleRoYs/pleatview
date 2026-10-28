package com.hustlesman.pleatview

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * PIN-based pairing. The PIN is shown on the TV; a client that knows it receives a
 * bearer token for the control API. Only SHA-256 hashes of tokens are stored.
 */
class Pairing(
    private val store: Store,
    private val clock: () -> Long = System::currentTimeMillis,
    private val random: SecureRandom = SecureRandom(),
) {
    interface Store {
        fun loadTokens(): String?
        fun saveTokens(json: String)
    }

    sealed interface Result {
        data class Paired(val token: String) : Result
        object InvalidPin : Result
        data class LockedOut(val retryAfterSeconds: Int) : Result
    }

    private data class Record(val hash: String, val client: String, val created: Long)

    private val records = mutableListOf<Record>()
    private var failures = 0
    private var lockedUntil = 0L

    @Volatile
    var pin: String = newPin()
        private set

    /** Called (on an arbitrary thread) whenever the PIN or the set of paired clients changes. */
    @Volatile
    var onChanged: (() -> Unit)? = null

    init {
        store.loadTokens()?.let { raw ->
            runCatching {
                val array = JSONArray(raw)
                for (i in 0 until array.length()) {
                    val o = array.getJSONObject(i)
                    records += Record(o.getString("hash"), o.optString("client"), o.optLong("created"))
                }
            }
        }
    }

    val isPaired: Boolean @Synchronized get() = records.isNotEmpty()

    @Synchronized
    fun pair(candidate: String, client: String): Result {
        val now = clock()
        if (now < lockedUntil) return Result.LockedOut(((lockedUntil - now + 999) / 1000).toInt())
        val digits = candidate.filter(Char::isDigit)
        if (!MessageDigest.isEqual(digits.toByteArray(), pin.toByteArray())) {
            failures++
            if (failures >= MAX_FAILURES) {
                failures = 0
                lockedUntil = now + LOCKOUT_MS
                rotatePin()
            }
            return Result.InvalidPin
        }
        failures = 0
        val token = newToken()
        records += Record(sha256(token), client.trim().take(64).ifEmpty { "client" }, now)
        while (records.size > MAX_TOKENS) records.removeAt(0)
        persist()
        rotatePin()
        return Result.Paired(token)
    }

    @Synchronized
    fun isValid(token: String?): Boolean {
        if (token.isNullOrEmpty()) return false
        val hash = sha256(token).toByteArray()
        // Compare against every record so timing doesn't reveal which one matched.
        var match = false
        for (record in records) match = MessageDigest.isEqual(record.hash.toByteArray(), hash) or match
        return match
    }

    @Synchronized
    fun revoke(token: String) {
        val hash = sha256(token)
        if (records.removeAll { it.hash == hash }) persist()
        onChanged?.invoke()
    }

    @Synchronized
    fun revokeAll() {
        records.clear()
        persist()
        rotatePin()
    }

    @Synchronized
    private fun rotatePin() {
        pin = newPin()
        onChanged?.invoke()
    }

    private fun persist() {
        val array = JSONArray()
        records.forEach {
            array.put(JSONObject().put("hash", it.hash).put("client", it.client).put("created", it.created))
        }
        store.saveTokens(array.toString())
    }

    private fun newPin(): String = (0 until PIN_LENGTH).joinToString("") { random.nextInt(10).toString() }

    private fun newToken(): String {
        val bytes = ByteArray(32).also(random::nextBytes)
        return hex(bytes)
    }

    companion object {
        const val PIN_LENGTH = 6
        const val MAX_FAILURES = 5
        const val LOCKOUT_MS = 60_000L
        const val MAX_TOKENS = 8

        fun sha256(value: String): String = hex(MessageDigest.getInstance("SHA-256").digest(value.toByteArray()))

        private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }
    }
}
