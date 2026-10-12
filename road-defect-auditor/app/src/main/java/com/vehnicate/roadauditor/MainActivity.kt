package com.vehnicate.roadauditor

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.content.ContextCompat
import androidx.core.view.setPadding
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var stateText: TextView
    private lateinit var detailsText: TextView
    private lateinit var driveButton: Button
    private lateinit var mapView: WebView
    private var driveActive = false
    private var mapPageReady = false
    private var pendingMapData: String? = null

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != DriveMonitorService.ACTION_STATUS) return
            stateText.text = intent.getStringExtra(DriveMonitorService.EXTRA_STATE)
                ?: getString(R.string.drive_active)
            driveActive = intent.getBooleanExtra(DriveMonitorService.EXTRA_RUNNING, driveActive)
            saveDriveState()
            updateButton()
            val speed = intent.getDoubleExtra(DriveMonitorService.EXTRA_SPEED_KMH, 0.0)
            val cell = intent.getStringExtra(DriveMonitorService.EXTRA_CELL).orEmpty()
            val count = intent.getIntExtra(DriveMonitorService.EXTRA_DEFECT_COUNT, 0)
            detailsText.text = when {
                !driveActive -> getString(R.string.gps_monitoring_off)
                cell.isBlank() -> getString(R.string.waiting_for_gps)
                else -> getString(R.string.drive_details, speed, count, cell)
            }
            updateDriveMap(intent.getStringExtra(DriveMonitorService.EXTRA_MAP_DATA))
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        driveActive = getSharedPreferences(PREFERENCES, MODE_PRIVATE)
            .getBoolean(DRIVE_ACTIVE, false)
        buildScreen()
        updateButton()
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(DriveMonitorService.ACTION_STATUS)
        ContextCompat.registerReceiver(
            this,
            statusReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
    }

    override fun onStop() {
        unregisterReceiver(statusReceiver)
        super.onStop()
    }

    override fun onDestroy() {
        mapView.stopLoading()
        mapView.destroy()
        super.onDestroy()
    }

    private fun buildScreen() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28))
            setBackgroundColor(Color.BLACK)
        }

        val logo = ImageView(this).apply {
            setImageResource(R.drawable.in_app_logo)
            contentDescription = getString(R.string.brand_logo_description)
            scaleType = ImageView.ScaleType.FIT_CENTER
        }
        root.addView(logo, LinearLayout.LayoutParams(dp(104), dp(104)).apply {
            bottomMargin = dp(18)
        })

        val title = TextView(this).apply {
            text = "vehnicate"
            textSize = 30f
            letterSpacing = 0.04f
            typeface = Typeface.createFromAsset(assets, "fonts/Ledger-Regular.ttf")
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        root.addView(title, matchWrap())

        stateText = TextView(this).apply {
            text = getString(
                if (driveActive) R.string.drive_active else R.string.ready_when_you_are,
            )
            textSize = 12f
            letterSpacing = 0.12f
            setTextColor(Color.LTGRAY)
            gravity = Gravity.CENTER
        }
        root.addView(stateText, LinearLayout.LayoutParams(-1, -2).apply {
            topMargin = dp(42)
        })

        detailsText = TextView(this).apply {
            text = getString(R.string.initial_details)
            textSize = 12f
            setTextColor(Color.GRAY)
            gravity = Gravity.CENTER
            setLineSpacing(dp(5).toFloat(), 1f)
        }
        root.addView(detailsText, LinearLayout.LayoutParams(-1, -2).apply {
            topMargin = dp(12)
            bottomMargin = dp(32)
        })

        mapView = WebView(this).apply {
            setBackgroundColor(0xFFE2E8F0.toInt())
            settings.javaScriptEnabled = true
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    mapPageReady = true
                    pendingMapData?.let(::renderDriveMap)
                }
            }
            val mapHtml = assets.open("drive_map.html").bufferedReader().use { it.readText() }
            loadDataWithBaseURL("https://vehnicate.com/", mapHtml, "text/html", "UTF-8", null)
        }
        root.addView(mapView, LinearLayout.LayoutParams(-1, 0, 1f).apply {
            bottomMargin = dp(20)
        })
        mapView.visibility = if (driveActive) ViewGroup.VISIBLE else ViewGroup.GONE

        driveButton = Button(this).apply {
            textSize = 14f
            letterSpacing = 0.08f
            setTextColor(Color.BLACK)
            setBackgroundColor(Color.WHITE)
            setPadding(dp(28), dp(14), dp(28), dp(14))
            setOnClickListener { onDriveButtonPressed() }
        }
        root.addView(driveButton, LinearLayout.LayoutParams(-1, dp(58)))
        setContentView(root)
    }

    private fun onDriveButtonPressed() {
        if (driveActive) {
            stopMonitorService()
            driveActive = false
            saveDriveState()
            stateText.text = getString(R.string.drive_stopped)
            detailsText.text = getString(R.string.gps_monitoring_off)
            updateButton()
            return
        }
        if (!hasLocationPermission()) {
            val permissions = mutableListOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            )
            if (Build.VERSION.SDK_INT >= 33 && !hasNotificationPermission()) {
                permissions += Manifest.permission.POST_NOTIFICATIONS
            }
            requestPermissions(permissions.toTypedArray(), PERMISSION_REQUEST)
            return
        }
        if (Build.VERSION.SDK_INT >= 33 && !hasNotificationPermission()) {
            requestPermissions(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                PERMISSION_REQUEST,
            )
            return
        }
        startDrive()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_REQUEST) return
        if (hasLocationPermission()) {
            startDrive()
        } else {
            stateText.text = getString(R.string.location_permission_required)
        }
    }

    private fun startDrive() {
        driveActive = true
        saveDriveState()
        stateText.text = getString(R.string.starting_gps)
        detailsText.text = getString(R.string.startup_notification_hint)
        updateButton()
        try {
            startMonitorService()
        } catch (error: RuntimeException) {
            driveActive = false
            saveDriveState()
            stateText.text = getString(R.string.drive_start_failed)
            detailsText.text = error.localizedMessage ?: error.javaClass.simpleName
            updateButton()
        }
    }

    private fun startMonitorService() {
        ContextCompat.startForegroundService(
            this,
            Intent(this, DriveMonitorService::class.java)
                .setAction(DriveMonitorService.ACTION_START),
        )
    }

    private fun stopMonitorService() {
        startService(
            Intent(this, DriveMonitorService::class.java)
                .setAction(DriveMonitorService.ACTION_STOP),
        )
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private fun hasNotificationPermission(): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun saveDriveState() {
        getSharedPreferences(PREFERENCES, MODE_PRIVATE)
            .edit()
            .putBoolean(DRIVE_ACTIVE, driveActive)
            .apply()
    }

    private fun updateButton() {
        driveButton.text = getString(
            if (driveActive) R.string.stop_drive else R.string.start_drive,
        )
        driveButton.setTextColor(if (driveActive) Color.WHITE else Color.BLACK)
        driveButton.setBackgroundColor(if (driveActive) 0xFF242424.toInt() else Color.WHITE)
        mapView.visibility = if (driveActive) ViewGroup.VISIBLE else ViewGroup.GONE
    }

    private fun updateDriveMap(mapData: String?) {
        if (mapData.isNullOrBlank()) return
        pendingMapData = mapData
        if (mapPageReady) renderDriveMap(mapData)
    }

    private fun renderDriveMap(mapData: String) {
        mapView.evaluateJavascript(
            "window.updateDriveMap(${JSONObject.quote(mapData)})",
            null,
        )
    }

    private fun matchWrap() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    )

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val PREFERENCES = "drive_state"
        private const val DRIVE_ACTIVE = "active"
        private const val PERMISSION_REQUEST = 61
    }
}
