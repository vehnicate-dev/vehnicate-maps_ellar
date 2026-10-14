package com.vehnicate.roadauditor

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationAvailability
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.uber.h3core.H3Core
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.util.Locale
import java.util.concurrent.Executors

class DriveMonitorService : Service() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val networkExecutor = Executors.newSingleThreadExecutor()
    private val httpClient = OkHttpClient()
    private val h3 by lazy { H3Core.newSystemInstance() }
    private val confirmedDefects = linkedMapOf<String, RoadDefect>()
    private val loadedCells = mutableSetOf<Long>()
    private val pendingCells = mutableSetOf<Long>()
    private val alertedStages = mutableMapOf<String, MutableSet<DefectAlertPolicy.AlertStage>>()
    private val pendingAnnouncements = ArrayDeque<Int>()
    private val gpsHistory = ArrayDeque<RoadRoutePredictor.TrackPoint>()
    private var currentNeighborCells = emptySet<Long>()
    private var roadNetwork = RoadRoutePredictor.RoadNetwork(emptyMap(), emptyList())
    private var lastRoadFetchLocation: Location? = null
    private var roadFetchPending = false
    private var nextRoadFetchAllowedAt = 0L
    private var roadNetworkError: String? = null
    private var latestPredictedRoute = emptyList<RoadRoutePredictor.Point>()

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.locations.forEach(::onLocationUpdate)
        }

        override fun onLocationAvailability(availability: LocationAvailability) {
            if (!availability.isLocationAvailable && monitoringStarted) {
                publishStatus("Waiting for a high-accuracy GPS fix")
            }
        }
    }

    private lateinit var locationClient: FusedLocationProviderClient
    private lateinit var audioManager: AudioManager
    private var textToSpeech: TextToSpeech? = null
    private var audioFocusRequest: AudioFocusRequest? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var latestLocation: Location? = null
    private var latestCell = ""
    private var latestSpeedKmh = 0.0
    private var currentState = "Waiting for GPS"
    private var monitoringStarted = false
    private var speaking = false
    private var syncError: String? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        locationClient = LocationServices.getFusedLocationProviderClient(this)
        audioManager = getSystemService(AUDIO_SERVICE) as AudioManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopMonitoring()
            return START_NOT_STICKY
        }

        try {
            startForeground(
                NOTIFICATION_ID,
                buildNotification("Waiting for a high-accuracy GPS fix"),
            )
            configureSpeech()
            startMonitoring()
        } catch (error: RuntimeException) {
            Log.e(TAG, "Could not start drive monitoring", error)
            recordStoppedState()
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun onLocationUpdate(location: Location) {
        if (!monitoringStarted) return
        val nowNanos = SystemClock.elapsedRealtimeNanos()
        val fixAgeNanos = nowNanos - location.elapsedRealtimeNanos
        if (fixAgeNanos !in 0..MAX_LOCATION_AGE_NANOS ||
            latestLocation?.elapsedRealtimeNanos?.let { location.elapsedRealtimeNanos <= it } == true
        ) {
            return
        }
        try {
            processLocation(location)
        } catch (error: RuntimeException) {
            Log.e(TAG, "Could not process the current GPS fix", error)
            currentState = "Drive stopped: ${error.localizedMessage ?: error.javaClass.simpleName}"
            publishStatus(currentState)
            stopMonitoring()
        }
    }

    private fun processLocation(location: Location) {
        latestLocation = location
        latestSpeedKmh = if (location.hasSpeed() && location.speed.isFinite()) {
            location.speed * 3.6
        } else {
            0.0
        }

        val cell = h3.latLngToCell(location.latitude, location.longitude, H3_RESOLUTION)
        currentNeighborCells = h3.gridDisk(cell, NEIGHBOR_RING).toSet()
        loadedCells.retainAll(currentNeighborCells)
        confirmedDefects.entries.removeAll { it.value.h3Index !in currentNeighborCells }
        latestCell = h3.h3ToString(cell)
        ensureNeighborCellsLoaded(cell)
        ensureRoadNetworkLoaded(location)

        if (!location.hasAccuracy() || location.accuracy > MAX_ALERT_ACCURACY_METERS) {
            publishStatus(syncError ?: "Improving GPS accuracy before alerts")
            return
        }

        if (latestSpeedKmh < MIN_ALERT_SPEED_KMH ||
            !location.hasBearing() ||
            (location.hasBearingAccuracy() &&
                location.bearingAccuracyDegrees > MAX_BEARING_ACCURACY_DEGREES)
        ) {
            latestPredictedRoute = emptyList()
            publishStatus(syncError ?: "Waiting for a reliable direction of travel")
            return
        }

        gpsHistory.addLast(
            RoadRoutePredictor.TrackPoint(
                location.latitude,
                location.longitude,
                location.bearing.toDouble(),
            ),
        )
        while (gpsHistory.size > MAX_GPS_HISTORY_POINTS) gpsHistory.removeFirst()
        updatePredictedRoute()
        evaluateNearbyDefects(location, latestSpeedKmh)
        publishDriveStatus()
    }

    private fun startMonitoring() {
        if (monitoringStarted) return
        val fineGranted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (!fineGranted) {
            publishStatus("Precise location permission is required")
            stopSelf()
            return
        }

        monitoringStarted = true
        currentState = "Waiting for a high-accuracy GPS fix"
        acquireWakeLock()
        try {
            val request = LocationRequest.Builder(
                Priority.PRIORITY_HIGH_ACCURACY,
                LOCATION_INTERVAL_MS,
            )
                .setMinUpdateIntervalMillis(MIN_LOCATION_INTERVAL_MS)
                .setMinUpdateDistanceMeters(0f)
                .setMaxUpdateDelayMillis(0)
                .setWaitForAccurateLocation(true)
                .build()
            locationClient.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
                .addOnFailureListener(::onLocationRequestFailed)
            publishStatus(currentState)
        } catch (error: SecurityException) {
            monitoringStarted = false
            currentState = "Location permission was revoked"
            publishStatus(currentState)
            releaseWakeLock()
            stopSelf()
        }
    }

    private fun onLocationRequestFailed(error: Exception) {
        if (!monitoringStarted) return
        Log.e(TAG, "Could not request high-accuracy location updates", error)
        monitoringStarted = false
        currentState = "High-accuracy GPS unavailable: ${error.localizedMessage ?: error.javaClass.simpleName}"
        releaseWakeLock()
        recordStoppedState()
        publishStatus(currentState)
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun ensureNeighborCellsLoaded(centerCell: Long) {
        val cellsToLoad = h3.gridDisk(centerCell, NEIGHBOR_RING)
            .filter { it !in loadedCells && it !in pendingCells }
        if (cellsToLoad.isEmpty()) return

        pendingCells.addAll(cellsToLoad)
        networkExecutor.execute {
            try {
                val fetched = fetchConfirmedDefects(cellsToLoad)
                mainHandler.post {
                    pendingCells.removeAll(cellsToLoad.toSet())
                    loadedCells.addAll(cellsToLoad.filter { it in currentNeighborCells })
                    fetched.filter { it.h3Index in currentNeighborCells }
                        .forEach { confirmedDefects[it.id] = it }
                    syncError = null
                    latestLocation?.let { location ->
                        if (location.hasAccuracy() &&
                            location.accuracy <= MAX_ALERT_ACCURACY_METERS &&
                            location.hasBearing() &&
                            latestSpeedKmh >= MIN_ALERT_SPEED_KMH
                        ) {
                            evaluateNearbyDefects(location, latestSpeedKmh)
                        }
                    }
                    publishDriveStatus()
                }
            } catch (error: IOException) {
                Log.e(TAG, "Could not load confirmed defects", error)
                mainHandler.post {
                    pendingCells.removeAll(cellsToLoad.toSet())
                    syncError = "Defect sync failed: ${error.message ?: "network error"}"
                    currentState = syncError ?: "Defect sync failed"
                    publishStatus(currentState)
                }
            } catch (error: JSONException) {
                Log.e(TAG, "Could not parse confirmed defects", error)
                mainHandler.post {
                    pendingCells.removeAll(cellsToLoad.toSet())
                    syncError = "Defect sync failed: invalid server response"
                    currentState = syncError ?: "Defect sync failed"
                    publishStatus(currentState)
                }
            } catch (error: RuntimeException) {
                Log.e(TAG, "Could not process confirmed defects", error)
                mainHandler.post {
                    pendingCells.removeAll(cellsToLoad.toSet())
                    syncError = "Defect sync failed: ${error.localizedMessage ?: error.javaClass.simpleName}"
                    currentState = syncError ?: "Defect sync failed"
                    publishStatus(currentState)
                }
            }
        }
    }

    @Throws(IOException::class, JSONException::class)
    private fun fetchConfirmedDefects(cells: List<Long>): List<RoadDefect> {
        val endpoint = "${BuildConfig.SUPABASE_URL.trimEnd('/')}/rest/v1/hexagons"
            .toHttpUrl()
            .newBuilder()
            .addQueryParameter(
                "select",
                "id,h3_index,lat,lon,confirmed,jerk_values,parameter",
            )
            .addQueryParameter("confirmed", "eq.true")
            .addQueryParameter(
                "h3_index",
                "in.(${cells.joinToString(",") { h3.h3ToString(it) }})",
            )
            .build()

        val rows = mutableListOf<RoadDefect>()
        var offset = 0
        while (true) {
            val request = Request.Builder()
                .url(endpoint)
                .header("apikey", BuildConfig.SUPABASE_PUBLISHABLE_KEY)
                .header("Authorization", "Bearer ${BuildConfig.SUPABASE_PUBLISHABLE_KEY}")
                .header("Range-Unit", "items")
                .header("Range", "$offset-${offset + PAGE_SIZE - 1}")
                .get()
                .build()

            val batchSize = httpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw IOException("Supabase returned HTTP ${response.code}")
                }
                val body = response.body?.string()
                    ?: throw IOException("Supabase returned an empty response")
                val batch = JSONArray(body)
                for (index in 0 until batch.length()) {
                    val row = batch.getJSONObject(index)
                    if (!row.optBoolean("confirmed", false)) continue
                    val jerkArray = row.optJSONArray("jerk_values") ?: continue
                    val jerkValues = List(jerkArray.length()) { jerkIndex ->
                        jerkArray.optDouble(jerkIndex, Double.NaN)
                    }
                    if (!DefectAlertPolicy.hasPositiveMaximumJerk(jerkValues)) continue
                    val id = row.optString("id").takeUnless { it.isBlank() || it == "null" }
                        ?: continue
                    val h3Index = row.optString("h3_index")
                        .takeUnless { it.isBlank() || it == "null" }
                        ?: continue
                    val cell = try {
                        h3.stringToH3(h3Index)
                    } catch (error: IllegalArgumentException) {
                        throw JSONException("Supabase returned an invalid H3 index")
                    }
                    val lat = row.optDouble("lat", Double.NaN)
                    val lon = row.optDouble("lon", Double.NaN)
                    val parameter = row.optDouble("parameter", 0.0)
                    if (!lat.isFinite() || !lon.isFinite() || cell !in cells) continue
                    rows += RoadDefect(id, cell, lat, lon, parameter)
                }
                batch.length()
            }
            if (batchSize < PAGE_SIZE) break
            offset += batchSize
        }
        return rows
    }

    private fun ensureRoadNetworkLoaded(location: Location) {
        if (roadFetchPending || SystemClock.elapsedRealtime() < nextRoadFetchAllowedAt) return
        val previousFetch = lastRoadFetchLocation
        if (previousFetch != null) {
            val result = FloatArray(1)
            Location.distanceBetween(
                previousFetch.latitude,
                previousFetch.longitude,
                location.latitude,
                location.longitude,
                result,
            )
            if (result[0] < ROAD_FETCH_REFRESH_DISTANCE_METERS) return
        }

        roadFetchPending = true
        val fetchLocation = Location(location)
        networkExecutor.execute {
            try {
                val fetchedNetwork = fetchRoadNetwork(fetchLocation)
                mainHandler.post {
                    roadFetchPending = false
                    roadNetwork = fetchedNetwork
                    lastRoadFetchLocation = fetchLocation
                    roadNetworkError = null
                    latestLocation?.let { latest ->
                        updatePredictedRoute()
                        if (latest.hasAccuracy() &&
                            latest.accuracy <= MAX_ALERT_ACCURACY_METERS &&
                            latest.hasBearing() &&
                            latestSpeedKmh >= MIN_ALERT_SPEED_KMH
                        ) {
                            evaluateNearbyDefects(latest, latestSpeedKmh)
                        }
                    }
                    publishDriveStatus()
                }
            } catch (error: IOException) {
                Log.e(TAG, "Could not load nearby OpenStreetMap roads", error)
                mainHandler.post {
                    roadFetchPending = false
                    nextRoadFetchAllowedAt =
                        SystemClock.elapsedRealtime() + ROAD_FETCH_RETRY_DELAY_MS
                    roadNetworkError = "Road data unavailable: ${error.message ?: "network error"}"
                    latestPredictedRoute = emptyList()
                    publishDriveStatus()
                }
            } catch (error: JSONException) {
                Log.e(TAG, "Could not parse nearby OpenStreetMap roads", error)
                mainHandler.post {
                    roadFetchPending = false
                    nextRoadFetchAllowedAt =
                        SystemClock.elapsedRealtime() + ROAD_FETCH_RETRY_DELAY_MS
                    roadNetworkError = "Road data unavailable: invalid server response"
                    latestPredictedRoute = emptyList()
                    publishDriveStatus()
                }
            } catch (error: RuntimeException) {
                Log.e(TAG, "Could not process nearby OpenStreetMap roads", error)
                mainHandler.post {
                    roadFetchPending = false
                    nextRoadFetchAllowedAt =
                        SystemClock.elapsedRealtime() + ROAD_FETCH_RETRY_DELAY_MS
                    roadNetworkError =
                        "Road data unavailable: ${error.localizedMessage ?: error.javaClass.simpleName}"
                    latestPredictedRoute = emptyList()
                    publishDriveStatus()
                }
            }
        }
    }

    @Throws(IOException::class, JSONException::class)
    private fun fetchRoadNetwork(location: Location): RoadRoutePredictor.RoadNetwork {
        val latitude = String.format(Locale.US, "%.3f", location.latitude)
        val longitude = String.format(Locale.US, "%.3f", location.longitude)
        val query = """
            [out:json][timeout:20];
            way(around:$ROAD_FETCH_RADIUS_METERS,$latitude,$longitude)["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|road|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"];
            out body;
            >;
            out skel qt;
        """.trimIndent()
        val endpoint = OVERPASS_URL.toHttpUrl()
        val request = Request.Builder()
            .url(endpoint)
            .header("User-Agent", OVERPASS_USER_AGENT)
            .post(FormBody.Builder().add("data", query).build())
            .build()

        val responseBody = httpClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("OpenStreetMap Overpass returned HTTP ${response.code}")
            }
            response.body?.string()
                ?: throw IOException("OpenStreetMap Overpass returned an empty response")
        }
        val elements = JSONObject(responseBody).optJSONArray("elements")
            ?: throw JSONException("OpenStreetMap Overpass returned no elements")
        val nodes = mutableMapOf<Long, RoadRoutePredictor.RoadNode>()
        for (index in 0 until elements.length()) {
            val element = elements.getJSONObject(index)
            if (element.optString("type") != "node") continue
            val id = element.optLong("id", -1L)
            val latitude = element.optDouble("lat", Double.NaN)
            val longitude = element.optDouble("lon", Double.NaN)
            if (id >= 0L && latitude.isFinite() && longitude.isFinite()) {
                nodes[id] = RoadRoutePredictor.RoadNode(id, latitude, longitude)
            }
        }

        val ways = mutableListOf<RoadRoutePredictor.RoadWay>()
        for (index in 0 until elements.length()) {
            val element = elements.getJSONObject(index)
            if (element.optString("type") != "way") continue
            val tags = element.optJSONObject("tags") ?: continue
            if (tags.optString("highway") !in DRIVABLE_HIGHWAY_TYPES) continue
            val nodeArray = element.optJSONArray("nodes") ?: continue
            val nodeIds = List(nodeArray.length()) { nodeArray.getLong(it) }
                .filter { it in nodes }
            if (nodeIds.size < 2) continue
            val oneWay = tags.optString("oneway").lowercase(Locale.ROOT)
            ways += RoadRoutePredictor.RoadWay(
                id = element.optLong("id"),
                nodeIds = nodeIds,
                oneWay = oneWay in setOf("yes", "true", "1", "-1"),
                reverseOneWay = oneWay == "-1",
            )
        }
        if (ways.isEmpty()) {
            throw IOException("OpenStreetMap Overpass returned no nearby drivable roads")
        }
        return RoadRoutePredictor.RoadNetwork(nodes, ways)
    }

    private fun updatePredictedRoute() {
        latestPredictedRoute = RoadRoutePredictor.predict(
            roadNetwork,
            gpsHistory.toList(),
            PREDICTED_TRAJECTORY_METERS,
        )
    }

    private fun evaluateNearbyDefects(location: Location, speedKmh: Double) {
        if (!location.hasAccuracy() || location.accuracy > MAX_ALERT_ACCURACY_METERS) return
        if (latestPredictedRoute.size < 2) return
        val nextDefect = confirmedDefects.values
            .asSequence()
            .mapNotNull { defect ->
                val distanceAlongRoute = RoadRoutePredictor.distanceAlongRoute(
                    defect.latitude,
                    defect.longitude,
                    latestPredictedRoute,
                    (ROAD_ALERT_CORRIDOR_METERS + location.accuracy)
                        .coerceAtMost(MAX_ROAD_ALERT_CORRIDOR_METERS),
                )?.takeIf { it > location.accuracy } ?: return@mapNotNull null
                defect to distanceAlongRoute
            }
            .minByOrNull { it.second }
            ?: return

        val (defect, distanceAhead) = nextDefect
        val defectStages = alertedStages.getOrPut(defect.id) { mutableSetOf() }
        val decision = DefectAlertPolicy.nextAlertDecision(
            distanceAhead,
            speedKmh,
            defectStages,
        ) ?: return

        defectStages.addAll(decision.consumedStages)
        announceRoadDefect(decision.distanceMeters)
    }

    private fun configureSpeech() {
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
        audioFocusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(attributes)
            .setOnAudioFocusChangeListener { }
            .setWillPauseWhenDucked(false)
            .build()

        textToSpeech = TextToSpeech(this) { result ->
            if (result != TextToSpeech.SUCCESS) {
                currentState = "Speech engine could not start"
                publishStatus(currentState)
                return@TextToSpeech
            }
            try {
                val speech = textToSpeech ?: return@TextToSpeech
                val preferredLocale = Locale.Builder()
                    .setLanguage("en")
                    .setRegion("IN")
                    .build()
                if (speech.isLanguageAvailable(preferredLocale) >= TextToSpeech.LANG_AVAILABLE) {
                    speech.language = preferredLocale
                } else {
                    speech.language = Locale.US
                }
                speech.setSpeechRate(0.92f)
                speech.setPitch(1.12f)
                speech.setAudioAttributes(attributes)
                speech.voices
                    ?.filter { it.locale.language == "en" }
                    ?.sortedByDescending { it.name.contains("female", ignoreCase = true) }
                    ?.firstOrNull()
                    ?.let { speech.voice = it }
                speech.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) = Unit
                    override fun onDone(utteranceId: String?) {
                        mainHandler.post { onAnnouncementFinished() }
                    }
                    @Deprecated("Deprecated by Android.")
                    override fun onError(utteranceId: String?) {
                        mainHandler.post { onAnnouncementFinished() }
                    }
                    override fun onError(utteranceId: String?, errorCode: Int) {
                        mainHandler.post { onAnnouncementFinished() }
                    }
                })
                playNextAnnouncement()
            } catch (error: RuntimeException) {
                Log.e(TAG, "Could not configure text-to-speech", error)
                textToSpeech?.shutdown()
                textToSpeech = null
                currentState = "Speech unavailable: ${error.localizedMessage ?: error.javaClass.simpleName}"
                publishStatus(currentState)
            }
        }
    }

    private fun announceRoadDefect(distanceMeters: Int) {
        pendingAnnouncements.addLast(distanceMeters)
        playNextAnnouncement()
    }

    private fun playNextAnnouncement() {
        val speech = textToSpeech ?: return
        if (speaking || pendingAnnouncements.isEmpty()) return

        audioFocusRequest?.let { request ->
            val result = audioManager.requestAudioFocus(request)
            if (result != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                currentState = "Audio focus unavailable; alerting without ducking"
                publishStatus(currentState)
            }
        }
        val distanceMeters = pendingAnnouncements.removeFirst()
        speaking = true
        val result = speech.speak(
            "Road defect in $distanceMeters meters",
            TextToSpeech.QUEUE_FLUSH,
            null,
            UTTERANCE_ID,
        )
        if (result == TextToSpeech.ERROR) {
            speaking = false
            releaseAudioFocus()
            currentState = "Speech engine failed to play an alert"
            publishStatus(currentState)
            playNextAnnouncement()
        }
    }

    private fun onAnnouncementFinished() {
        speaking = false
        if (pendingAnnouncements.isEmpty()) {
            releaseAudioFocus()
        } else {
            playNextAnnouncement()
        }
    }

    private fun releaseAudioFocus() {
        audioFocusRequest?.let(audioManager::abandonAudioFocusRequest)
    }

    private fun acquireWakeLock() {
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "$TAG:drive-monitor",
        ).apply { acquire(MAX_WAKE_LOCK_MS) }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun stopMonitoring() {
        if (monitoringStarted) {
            locationClient.removeLocationUpdates(locationCallback)
                .addOnFailureListener { error ->
                    Log.e(TAG, "Could not remove location updates", error)
                }
        }
        monitoringStarted = false
        pendingAnnouncements.clear()
        speaking = false
        releaseWakeLock()
        releaseAudioFocus()
        networkExecutor.shutdownNow()
        textToSpeech?.stop()
        textToSpeech?.shutdown()
        textToSpeech = null
        recordStoppedState()
        publishStatus("Drive stopped")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun recordStoppedState() {
        getSharedPreferences(DRIVE_PREFERENCES, MODE_PRIVATE)
            .edit()
            .putBoolean(DRIVE_ACTIVE, false)
            .apply()
        sendBroadcast(
            Intent(ACTION_STATUS)
                .setPackage(packageName)
                .putExtra(EXTRA_STATE, getString(R.string.drive_stopped))
                .putExtra(EXTRA_RUNNING, false),
        )
    }

    private fun publishStatus(state: String) {
        currentState = state
        updateNotification(state)
        sendBroadcast(
            Intent(ACTION_STATUS)
                .setPackage(packageName)
                .putExtra(EXTRA_STATE, state)
                .putExtra(EXTRA_SPEED_KMH, latestSpeedKmh)
                .putExtra(EXTRA_CELL, latestCell)
                .putExtra(EXTRA_DEFECT_COUNT, confirmedDefects.size)
                .putExtra(EXTRA_MAP_DATA, if (monitoringStarted) buildMapData() else null)
                .putExtra(EXTRA_RUNNING, monitoringStarted),
        )
    }

    private fun buildMapData(): String? {
        val location = latestLocation ?: return null
        val cells = currentNeighborCells.ifEmpty {
            setOf(h3.latLngToCell(location.latitude, location.longitude, H3_RESOLUTION))
        }
        val trajectory = JSONArray()
        if (location.hasBearing() &&
            latestSpeedKmh >= MIN_ALERT_SPEED_KMH &&
            (!location.hasBearingAccuracy() ||
                location.bearingAccuracyDegrees <= MAX_BEARING_ACCURACY_DEGREES)
        ) {
            latestPredictedRoute.forEach { point ->
                trajectory.put(JSONArray().put(point.latitude).put(point.longitude))
            }
        }
        val payload = JSONObject()
            .put("latitude", location.latitude)
            .put("longitude", location.longitude)
            .put("trajectory", trajectory)
            .put("hexagons", JSONArray().apply {
                cells.forEach { cell ->
                    put(JSONArray().apply {
                        h3.cellToBoundary(cell).forEach { vertex ->
                            put(JSONArray().put(vertex.lat).put(vertex.lng))
                        }
                    })
                }
            })
            .put("defects", JSONArray().apply {
                confirmedDefects.values
                    .filter { it.h3Index in cells }
                    .forEach { defect ->
                        put(
                            JSONObject()
                                .put("latitude", defect.latitude)
                                .put("longitude", defect.longitude)
                                .put("parameter", defect.parameter),
                        )
                    }
            })
        return payload.toString()
    }

    private fun publishDriveStatus() {
        val state = when {
            syncError != null -> syncError
            roadNetworkError != null -> roadNetworkError
            latestPredictedRoute.size < 2 && roadFetchPending -> "Loading nearby road data"
            latestPredictedRoute.size < 2 -> "Waiting for a GPS match to a road"
            else -> "Driving · ${loadedCells.size} H3 cells ready"
        }
        publishStatus(state ?: "Waiting for a GPS match to a road")
    }

    private fun buildNotification(message: String): Notification {
        val openApp = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stopDrive = PendingIntent.getService(
            this,
            1,
            Intent(this, DriveMonitorService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("vehnicate · drive monitor")
            .setContentText(message)
            .setContentIntent(openApp)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(0, "Stop drive", stopDrive)
            .build()
    }

    private fun updateNotification(message: String) {
        if (!monitoringStarted && currentState != "Waiting for GPS") return
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(message))
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Drive monitoring",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Ongoing GPS monitoring while a drive is active"
            setSound(null, null)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    override fun onDestroy() {
        if (monitoringStarted) {
            locationClient.removeLocationUpdates(locationCallback)
                .addOnFailureListener { error ->
                    Log.e(TAG, "Could not remove location updates", error)
                }
        }
        releaseWakeLock()
        releaseAudioFocus()
        textToSpeech?.shutdown()
        networkExecutor.shutdownNow()
        super.onDestroy()
    }

    private data class RoadDefect(
        val id: String,
        val h3Index: Long,
        val latitude: Double,
        val longitude: Double,
        val parameter: Double,
    )

    companion object {
        const val ACTION_START = "com.vehnicate.roadauditor.START"
        const val ACTION_STOP = "com.vehnicate.roadauditor.STOP"
        const val ACTION_STATUS = "com.vehnicate.roadauditor.STATUS"
        const val EXTRA_STATE = "state"
        const val EXTRA_SPEED_KMH = "speed_kmh"
        const val EXTRA_CELL = "cell"
        const val EXTRA_DEFECT_COUNT = "defect_count"
        const val EXTRA_MAP_DATA = "map_data"
        const val EXTRA_RUNNING = "running"

        private const val TAG = "DriveMonitor"
        private const val DRIVE_PREFERENCES = "drive_state"
        private const val DRIVE_ACTIVE = "active"
        private const val CHANNEL_ID = "drive_monitor"
        private const val NOTIFICATION_ID = 9001
        private const val H3_RESOLUTION = 9
        private const val NEIGHBOR_RING = 1
        private const val LOCATION_INTERVAL_MS = 1_000L
        private const val MIN_LOCATION_INTERVAL_MS = 500L
        private const val MAX_LOCATION_AGE_NANOS = 2_000_000_000L
        private const val MAX_ALERT_ACCURACY_METERS = 35f
        private const val MAX_BEARING_ACCURACY_DEGREES = 30f
        private const val MIN_ALERT_SPEED_KMH = 8.0
        private const val PREDICTED_TRAJECTORY_METERS = 500.0
        private const val MAX_GPS_HISTORY_POINTS = 8
        private const val ROAD_FETCH_RADIUS_METERS = 1_500
        private const val ROAD_FETCH_REFRESH_DISTANCE_METERS = 800f
        private const val ROAD_FETCH_RETRY_DELAY_MS = 30_000L
        private const val ROAD_ALERT_CORRIDOR_METERS = 12.0
        private const val MAX_ROAD_ALERT_CORRIDOR_METERS = 40.0
        private const val OVERPASS_URL = "https://overpass-api.de/api/interpreter"
        private const val OVERPASS_USER_AGENT = "VehnicateRoadDefectAuditor/1.0"
        private val DRIVABLE_HIGHWAY_TYPES = setOf(
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
            "living_street",
            "service",
            "road",
            "motorway_link",
            "trunk_link",
            "primary_link",
            "secondary_link",
            "tertiary_link",
        )
        private const val PAGE_SIZE = 1_000
        private const val UTTERANCE_ID = "road-defect-alert"
        private const val MAX_WAKE_LOCK_MS = 12 * 60 * 60 * 1_000L
    }
}
