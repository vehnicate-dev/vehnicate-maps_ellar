package com.vehnicate.roadauditor

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.roundToInt

internal object DefectAlertPolicy {
    enum class AlertStage {
        APPROACH,
        NEAR,
        IMMEDIATE,
    }

    data class AlertDecision(
        val distanceMeters: Int,
        val consumedStages: Set<AlertStage>,
    )

    fun nextAlertDecision(
        distanceAheadMeters: Double,
        speedKmh: Double,
        alertedStages: Set<AlertStage>,
    ): AlertDecision? {
        if (!distanceAheadMeters.isFinite() || distanceAheadMeters <= 0.0) return null

        val milestones = buildList {
            add(AlertStage.APPROACH to approachDistanceMeters(speedKmh))
            add(AlertStage.NEAR to NEAR_DISTANCE_METERS)
            add(AlertStage.IMMEDIATE to IMMEDIATE_DISTANCE_METERS)
        }
        val reached = milestones
            .filter { (stage, threshold) ->
                stage !in alertedStages && distanceAheadMeters <= threshold
            }
            .minByOrNull { it.second }
            ?: return null
        val consumedStages = milestones
            .filter { (_, threshold) -> distanceAheadMeters <= threshold }
            .mapTo(mutableSetOf()) { it.first }

        return AlertDecision(distanceAheadMeters.roundToInt().coerceAtLeast(1), consumedStages)
    }

    fun approachDistanceMeters(speedKmh: Double): Int =
        if (speedKmh >= HIGH_SPEED_THRESHOLD_KMH) {
            HIGH_SPEED_APPROACH_DISTANCE_METERS
        } else {
            NEAR_DISTANCE_METERS
        }

    fun hasPositiveMaximumJerk(jerkValues: List<Double>): Boolean =
        jerkValues.any { it.isFinite() && it > 0.0 }

    fun distanceAheadInTravelCorridor(
        distanceMeters: Double,
        bearingToDefectDegrees: Double,
        headingDegrees: Double,
        horizontalAccuracyMeters: Double,
    ): Double? {
        if (!distanceMeters.isFinite() || distanceMeters <= 0.0) return null
        val angle = abs(signedAngle(bearingToDefectDegrees - headingDegrees))
        if (angle > MAX_FORWARD_ANGLE_DEGREES) return null

        val forwardMeters = distanceMeters * cos(Math.toRadians(angle))
        val crossTrackMeters = distanceMeters * abs(sin(Math.toRadians(angle)))
        val corridorWidth = (ROAD_CORRIDOR_METERS + horizontalAccuracyMeters)
            .coerceAtMost(MAX_CORRIDOR_METERS)
        if (forwardMeters <= horizontalAccuracyMeters || crossTrackMeters > corridorWidth) {
            return null
        }
        return forwardMeters
    }

    fun isAheadInTravelCorridor(
        distanceMeters: Double,
        bearingToDefectDegrees: Double,
        headingDegrees: Double,
        horizontalAccuracyMeters: Double,
    ): Boolean = distanceAheadInTravelCorridor(
        distanceMeters,
        bearingToDefectDegrees,
        headingDegrees,
        horizontalAccuracyMeters,
    ) != null

    private fun signedAngle(degrees: Double): Double = ((degrees + 540.0) % 360.0) - 180.0

    private const val HIGH_SPEED_THRESHOLD_KMH = 40.0
    private const val HIGH_SPEED_APPROACH_DISTANCE_METERS = 250
    private const val NEAR_DISTANCE_METERS = 100
    private const val IMMEDIATE_DISTANCE_METERS = 50
    private const val MAX_FORWARD_ANGLE_DEGREES = 55.0
    private const val ROAD_CORRIDOR_METERS = 18.0
    private const val MAX_CORRIDOR_METERS = 30.0
}
