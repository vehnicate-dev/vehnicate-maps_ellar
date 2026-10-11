# Vehnicate Road Defect Auditor

Standalone Android app project for audible warnings about confirmed Vehnicate road defects.

## Build and install

Open this folder in Android Studio with JDK 17 and Android SDK Platform 36 installed, or build from PowerShell:

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

The app uses H3 4.5.0, whose Android native libraries explicitly link Android's math library, and packages the 64-bit and 32-bit ARM binaries into the APK.

The installable debug APK is written to:

```text
app\build\outputs\apk\debug\app-debug.apk
```

Install it on a connected Android device with Android Studio or `adb install -r app\build\outputs\apk\debug\app-debug.apk`. The app asks for precise location (needed for useful GPS course) and notifications when a drive starts. Keep the ongoing drive-monitor notification enabled; Android may require disabling battery optimization for this app on some phone vendors. If Android stops the app process, reopen Vehnicate and tap **Start Drive** to resume; the activity won't automatically relaunch the GPS service.

The project uses the Vehnicate Supabase project URL and its **publishable** key by default, matching the web frontend. These are public client credentials, not a service-role key. To use a different Supabase project, pass Gradle properties at build time:

```powershell
.\gradlew.bat `
  -PSUPABASE_URL=https://your-project.supabase.co `
  -PSUPABASE_PUBLISHABLE_KEY=your-publishable-key `
  :app:assembleDebug
```

The project's Supabase row-level security policy must allow this key to read `hexagons` rows with `confirmed = true`. The app reports HTTP or response errors in its status/ongoing notification; do not place a service-role key in the APK.

## Drive behavior

- Computes the current H3 cell at resolution **9**, matching `frontend/src/components/map/RoadDefectsMap.jsx` and `backend/main.py`.
- Queries Supabase `hexagons` for confirmed rows in that cell and its H3 `gridDisk` ring 1 (the center plus six neighbors). It preloads newly encountered cells before they become the current cell and keeps the current seven-cell area cached.
- Requests high-accuracy fused location updates every second (500 ms minimum), rejects stale fixes, and waits for fixes with 35 m or better reported horizontal accuracy before alerting. Actual accuracy still depends on the phone, sky view, and environment.
- Uses GPS course while moving, not a phone-compass bearing while stationary. Defects behind the vehicle or outside a narrow ahead-of-vehicle corridor are ignored.
- Announces each confirmed defect once at an approach distance based on 15 seconds of current speed (about 250 m at 60 km/h and 333 m at 80 km/h), then once at 100 m and once at 50 m. If a location update skips a threshold, only the closest already-reached stage is announced.
- The in-app logo uses `frontend/public/hn-logo_light.png`; the Android launcher icon keeps its existing image.
- These distances are straight-line GPS projections along the current heading, not road-routed or lane-level estimates. Fused high-accuracy positioning cannot guarantee Google Maps-level accuracy; GPS and the stored defect coordinates can still be off by several metres or more.
- Speaks “Road defect in X meters” with Android's installed English text-to-speech voice. A voice whose name indicates female is preferred when available; otherwise Android's default English voice is used with a slightly higher pitch. Voice and language availability depend on the phone's installed TTS engine.
- Requests transient audio focus with `MAY_DUCK` for the spoken warning, allowing compatible music apps to lower and restore their own playback volume.
- A location foreground service and partial wake lock keep monitoring active with the screen off while a drive is running. Stop the drive from the app or its persistent notification.
- Raw GPS coordinates are used on-device; Supabase receives the H3 cell IDs used for the defect query. No third-party map-matching service receives the live route.

## Carriageway matching limitation

The `hexagons` rows contain defect coordinates, `osm_way_id`, and `direction_label`. In the backend, `direction_label` is `forward` or `backward` relative to the original OSM way-node order; it is **not** a compass bearing. The app currently filters to the GPS-heading corridor, but cannot reliably compare a defect's OSM direction with the vehicle's carriageway without matching the current GPS fix to an OSM road segment and its direction. It does not send live location to a third-party map-matching service. Exact same-carriageway rejection therefore requires a future road-map-matching component.

## Project layout

This folder is self-contained: it has its own Gradle settings, Android manifest, source, tests, logo and Ledger font assets (with the font's OFL license), and APK build workflow. Copy the whole `road-defect-auditor` folder to use it independently.
