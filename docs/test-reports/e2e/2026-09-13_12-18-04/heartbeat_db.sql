SELECT serial, status, last_seen_at, now()-last_seen_at AS ago
FROM field_devices WHERE serial='ANDROID-B20771B1330137BC';
