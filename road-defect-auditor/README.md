# vehnicate Road Defect Auditor

Standalone Android app project for audible warnings about confirmed vehnicate road defects.

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

Install it on a connected Android device with Android Studio or `adb install -r app\build\outputs\apk\debug\app-debug.apk`. The app asks for precise location (needed for useful GPS course) and notifications when a drive starts. Keep the ongoing drive-monitor notification enabled; Android may require disabling battery optimization for this app on some phone vendors. If Android stops the app process, reopen vehnicate and tap **Start Drive** to resume; the activity won't automatically relaunch the GPS service.

The project uses the vehnicate Supabase project URL and its **publishable** key by default, matching the web frontend. These are public client credentials, not a service-role key. To use a different Supabase project, pass Gradle properties at build time:

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
- Shows a live, full-screen map while a drive is active, styled to match the Vehnicate map page's light theme, with its blue H3 cell outlines, parameter-colored confirmed defects, and a dotted blue predicted route following connected OpenStreetMap roads up to 500 m. The rider marker follows live GPS; a Vehnicate logo/title overlays the top and a stop-drive control sits at the bottom.
- Requests high-accuracy fused location updates every second (500 ms minimum), rejects stale fixes, and waits for fixes with 35 m or better reported horizontal accuracy before alerting. Actual accuracy still depends on the phone, sky view, and environment.
- Fetches nearby drivable OSM road geometry from the public Overpass API, then matches recent GPS fixes and predicts the route through the local road graph on-device. The request sends the approximate current area to Overpass; GPS history and predicted route stay on-device.
- Uses GPS course while moving, not a phone-compass bearing while stationary. Defects outside a narrow corridor around the predicted road route are ignored.
- Alerts only the nearest confirmed defect along the predicted road route. At speeds of 40 km/h or more, that defect is announced at 250 m, 100 m, and 50 m; below 40 km/h, it is announced at 100 m and 50 m. Once the nearest defect has passed, the next defect on the route becomes eligible. If a location update skips multiple thresholds, it announces only once for that fix and marks the skipped stages as passed.
- The in-app logo uses `frontend/public/hn-logo_light.png`; the Android launcher icon keeps its existing image.
- The dotted route follows the locally fetched OSM road graph for up to 500 m; at junctions it favors the straight continuation and the recently travelled road. It is a prediction, not turn-by-turn navigation or a guarantee of the rider's future path. Fused high-accuracy positioning cannot guarantee Google Maps-level accuracy; GPS and stored defect coordinates can still be off by several metres or more.
- Speaks “Road defect in X meters” with Android's installed English text-to-speech voice. A voice whose name indicates female is preferred when available; otherwise Android's default English voice is used with a slightly higher pitch. Voice and language availability depend on the phone's installed TTS engine.
- Requests transient audio focus with `MAY_DUCK` for the spoken warning, allowing compatible music apps to lower and restore their own playback volume.
- A location foreground service and partial wake lock keep monitoring active with the screen off while a drive is running. Stop the drive from the app or its persistent notification.
- Raw GPS history and route prediction are processed on-device. Supabase receives the H3 cell IDs used for the defect query, and the Overpass API receives the approximate current area to return nearby OSM road geometry. The predicted route is not sent to either service.

## Carriageway matching limitation

The `hexagons` rows contain defect coordinates, `osm_way_id`, and `direction_label`. The app now matches fixes to OSM road geometry and respects roads tagged one-way when building its local prediction. Defect rows do not currently include enough linked road-node data to prove they belong to the exact same carriageway as the predicted route; alerts therefore use distance to the route with a GPS-accuracy-aware corridor.

## Project layout

This folder is self-contained: it has its own Gradle settings, Android manifest, source, tests, logo and Ledger font assets (with the font's OFL license), and APK build workflow. Copy the whole `road-defect-auditor` folder to use it independently.
