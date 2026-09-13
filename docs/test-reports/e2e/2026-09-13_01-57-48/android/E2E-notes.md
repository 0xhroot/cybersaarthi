# E2E Audit — Live Evidence Notes (provisional)

Run: 2026-09-13_01-57-48 | State: EXISTING STATE (no pm clear)
Device: POCO miel / Android 16 API 36 / arm64-v8a | pkg io.cybersaarthi.fieldagent.debug v2.0.0-debug

## Onboarding / first-launch behavior
- App cold start (am start -W): Status ok, TotalTime 1719ms. Screenshot 01-startup.png.
- Onboarding screen: title "CyberSaarthi Field Agent", buttons [Connect to server] (540,1109) and [Work offline] (540,1572).
- OBSERVED: Tapping "Work offline" -> Field mode dashboard, "No evidence is cached on this device yet." + [Go online]. (screenshot 02)
- OBSERVED: Tapping "Go online" -> Sign-in screen, server prefilled `http://10.0.2.2:8000/api/v1` (emulator-only default; on physical device it is not reachable).
  - Note: server status chip at sign-in shows "Connected" alongside the 10.0.2.2 URL; needs deep verification whether probe ran/succeeded. (possible display/state issue to track)
  - Note: banner text shows raw "Connected to %1$s" — format placeholder not substituted (likely P3 UI text bug; verify against strings.xml).
- OBSERVED: "Change server" -> "Server address" screen, EditText prefilled with same URL. Buttons [Test connection] (540,746) [Save and continue] (540,941).

## Manual server connection
(TBD)

## Security/other
(TBD)
## Manual server connection — OBSERVED (evidence: screenshots 03-07, 04/05 error paths)
- Negative: malformed URL `notaurl` -> error "Server unreachable: Expected URL scheme 'http' or 'https' but no schem…" (rendered below button).
- Negative: unreachable port (PC firewall drop, no RST) -> probe hangs in "testing" state (no timeout feedback captured); eventually errors. Env quirk, but no timeout UX.
- Negative: http://192.168.0.102:8000 (nothing listening) -> "Server unreachable: Network unreachable."
- Positive: http://192.168.0.127:8000 -> "Server reachable / cybersaarthi v0.1.0".
- Save + continue -> returns to Sign-in.
- VERIFIED (persisted prefs via run-as): server_url=http://192.168.0.127:8000/api/v1, hostname=cybersaarthi, fingerprint=34edcf12e59a5c1b846bca384e9a89c6ecb39139c61daf14bdace2f04ef28e78 (MATCHES expected), mode=ONLINE, onboarded=true.
- DEFECT (P3, UI/stale): Sign-in screen after save still shows `http://10.0.2.2:8000/api/v1` and chip "Offline". LoginViewModel caches serverHost/status at construction; not refreshed after Change-server/Save on another nav entry. Config itself correct (prefs VERIFIED). Chip is probe-driven; should flip once heartbeat probes LAN (serverUrl good).
- DEFECT (P3, text): banner shows literal "Connected to %1$s" — format arg not substituted (strings used with stringResource has arg `%1$s` but displayed raw; verify ms_/login string). 
- Note: default server URL is the emulator-only `10.0.2.2` in debug builds — documented; physical device REQUIRES manual LAN entry.
