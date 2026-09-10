package io.cybersaarthi.fieldagent.hashing

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class EvidenceHasherTest {

    @Test
    fun `sha256 hex matches known vector`() {
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            EvidenceHasher.sha256Hex("abc".toByteArray())
        )
    }

    @Test
    fun `sha256 file matches expected digest`() {
        val file = File.createTempFile("alpha", ".txt")
        try {
            file.writeText("The quick brown fox jumps over the lazy dog")
            assertEquals(
                "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
                EvidenceHasher.sha256File(file)
            )
        } finally {
            file.delete()
        }
    }

    @Test
    fun `empty input hash is the standard zero hash`() {
        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            EvidenceHasher.sha256Hex(ByteArray(0))
        )
    }

    @Test
    fun `sha256 bytes are hex decoded to 32 bytes`() {
        val raw = EvidenceHasher.sha256Bytes("abc".toByteArray())
        assertEquals(32, raw.size)
    }
}