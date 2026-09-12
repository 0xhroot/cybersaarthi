import { describe, expect, it } from "vitest";
import {
  buildPairingUri,
  computeServerFingerprint,
  normalizeApiBase,
  randomHex,
  sha256Hex,
  toBase64Url,
} from "./pairing";

describe("sha256Hex", () => {
  it("matches the standard vectors", () => {
    expect(sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    expect(sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });

  it("matches the canonical identity string used by the Android app", () => {
    // PairingManager.computeServerFingerprint("cybersaarthi", "0.1.0") => this digest.
    expect(computeServerFingerprint("cybersaarthi", "0.1.0")).toBe(
      "34edcf12e59a5c1b846bca384e9a89c6ecb39139c61daf14bdace2f04ef28e78",
    );
  });
});

describe("toBase64Url", () => {
  it("produces unpadded URL-safe encoding", () => {
    expect(toBase64Url("http://192.168.0.127:8000/api/v1")).toBe(
      Buffer.from("http://192.168.0.127:8000/api/v1", "utf8").toString("base64url"),
    );
    expect(toBase64Url("hello")).toBe("aGVsbG8");
  });

  it("survives a round trip through the Android decode path", () => {
    const raw = "http://10.0.0.5:8000/api/v1";
    const encoded = toBase64Url(raw);
    const decoded = Buffer.from(encoded.replace(/-/g, "+").replace(/_/g, "/") + "==", "base64").toString();
    expect(decoded).toBe(raw);
  });
});

describe("normalizeApiBase", () => {
  it("adds a scheme when missing", () => {
    expect(normalizeApiBase("192.168.0.127:8000")).toBe("http://192.168.0.127:8000/api/v1");
  });

  it("appends the api/v1 path and keeps the scheme/port", () => {
    expect(normalizeApiBase("https://field.example.com:8443")).toBe("https://field.example.com:8443/api/v1");
  });

  it("does not duplicate an existing api/v1 path", () => {
    expect(normalizeApiBase("http://localhost:8000/api/v1/")).toBe("http://localhost:8000/api/v1");
    expect(normalizeApiBase("http://localhost:8000/api/v1")).toBe("http://localhost:8000/api/v1");
  });
});

describe("buildPairingUri", () => {
  it("encodes the cybersaarthi://connect payload with u/fp/nonce/exp", () => {
    const baseUrl = "http://192.168.0.127:8000/api/v1";
    const fingerprint = "34EDCF12e59a5c1b846bca384e9a89c6ecb39139c61daf14bdace2f04ef28e78";
    const nonce = "ab12cd34ef56";
    const exp = 1776000000000;
    const uri = buildPairingUri({ baseUrl, fingerprint, nonce, expiresAtEpochMillis: exp });

    expect(uri.startsWith("cybersaarthi://connect?")).toBe(true);
    const params = new URLSearchParams(uri.split("?")[1]);
    expect(params.get("u")).toBe(toBase64Url(baseUrl));
    expect(params.get("fp")).toBe(fingerprint.toLowerCase());
    expect(params.get("nonce")).toBe(nonce);
    expect(params.get("exp")).toBe(String(exp));
    expect(params.get("fp")).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("randomHex", () => {
  it("returns the requested number of hex characters", () => {
    expect(randomHex(16)).toMatch(/^[0-9a-f]{32}$/);
    expect(randomHex(16)).not.toBe(randomHex(16));
  });
});