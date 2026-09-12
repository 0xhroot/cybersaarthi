package io.cybersaarthi.fieldagent.data.cache

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Offline cache of the cases the current authenticated user is authorized to
 * see. Case lists are only ever written from a live, authenticated response, so
 * the cache inherits the server's user/role/membership checks. The cache is
 * wiped on logout so a different operator never inherits another user's cases.
 */
data class CachedCase(
    val id: String,
    val caseNumber: String,
    val title: String,
    val status: String,
    val cachedAtEpochMillis: Long = System.currentTimeMillis()
) {
    fun toJson() = JSONObject().apply {
        put("id", id)
        put("case_number", caseNumber)
        put("title", title)
        put("status", status)
        put("cached_at", cachedAtEpochMillis)
    }

    companion object {
        fun fromJson(o: JSONObject) = CachedCase(
            id = o.getString("id"),
            caseNumber = o.getString("case_number"),
            title = o.getString("title"),
            status = o.getString("status"),
            cachedAtEpochMillis = o.optLong("cached_at", System.currentTimeMillis())
        )
    }
}

class CaseCache(private val file: File) {

    init {
        file.parentFile?.mkdirs()
    }

    /** Replaces the whole cache with an (re-)authenticated case list. */
    fun saveAll(cases: List<CachedCase>) {
        if (cases.isEmpty()) {
            clear()
            return
        }
        val arr = JSONArray()
        cases.forEach { arr.put(it.toJson()) }
        file.writeText(JSONObject().apply { put("cases", arr) }.toString())
    }

    fun append(case: CachedCase) {
        val existing = all().toMutableList()
        existing.removeAll { it.id == case.id }
        existing.add(0, case)
        saveAll(existing)
    }

    fun all(): List<CachedCase> {
        if (!file.exists()) return emptyList()
        return runCatching {
            val arr = JSONObject(file.readText()).getJSONArray("cases")
            (0 until arr.length()).map { CachedCase.fromJson(arr.getJSONObject(it)) }
        }.getOrDefault(emptyList())
    }

    fun byId(id: String): CachedCase? = all().firstOrNull { it.id == id }

    fun clear() {
        file.delete()
    }
}