package com.vehnicate.roadauditor

import com.uber.h3core.H3Core
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class DefectAlertPolicyTest {
    @Test
    fun onlyDefectsWithPositiveMaximumJerkAreEligibleForAlerts() {
        assertTrue(DefectAlertPolicy.hasPositiveMaximumJerk(listOf(-2.0, 0.1, 0.0)))
        assertFalse(DefectAlertPolicy.hasPositiveMaximumJerk(listOf(-2.0, 0.0)))
        assertFalse(DefectAlertPolicy.hasPositiveMaximumJerk(emptyList()))
        assertFalse(DefectAlertPolicy.hasPositiveMaximumJerk(listOf(Double.NaN, Double.NEGATIVE_INFINITY)))
    }

    @Test
    fun approachWarningUsesTheFortyKilometersPerHourThreshold() {
        assertEquals(100, DefectAlertPolicy.approachDistanceMeters(39.99))
        assertEquals(250, DefectAlertPolicy.approachDistanceMeters(40.0))
        assertEquals(250, DefectAlertPolicy.approachDistanceMeters(60.0))
        assertEquals(250, DefectAlertPolicy.approachDistanceMeters(80.0))
    }

    @Test
    fun highSpeedAlertsAreIssuedAtTwoHundredFiftyOneHundredAndFiftyMeters() {
        val noAlerts = emptySet<DefectAlertPolicy.AlertStage>()
        val approach = DefectAlertPolicy.nextAlertDecision(250.0, 80.0, noAlerts)
        assertEquals(250, approach?.distanceMeters)
        assertEquals(
            setOf(DefectAlertPolicy.AlertStage.APPROACH),
            approach?.consumedStages,
        )

        val near = DefectAlertPolicy.nextAlertDecision(
            100.0,
            80.0,
            approach?.consumedStages.orEmpty(),
        )
        assertEquals(100, near?.distanceMeters)

        val immediate = DefectAlertPolicy.nextAlertDecision(
            50.0,
            80.0,
            approach?.consumedStages.orEmpty() + near?.consumedStages.orEmpty(),
        )
        assertEquals(50, immediate?.distanceMeters)

        assertEquals(
            null,
            DefectAlertPolicy.nextAlertDecision(
                40.0,
                80.0,
                approach?.consumedStages.orEmpty() +
                    near?.consumedStages.orEmpty() +
                    immediate?.consumedStages.orEmpty(),
            ),
        )
    }

    @Test
    fun skippedMilestonesOnlyIssueTheClosestReachedAlert() {
        val decision = DefectAlertPolicy.nextAlertDecision(
            80.0,
            80.0,
            emptySet(),
        )

        assertEquals(80, decision?.distanceMeters)
        assertEquals(
            setOf(
                DefectAlertPolicy.AlertStage.APPROACH,
                DefectAlertPolicy.AlertStage.NEAR,
            ),
            decision?.consumedStages,
        )
    }

    @Test
    fun lowSpeedUsesHundredMetersAsItsFirstWarning() {
        val decision = DefectAlertPolicy.nextAlertDecision(
            100.0,
            20.0,
            emptySet(),
        )

        assertEquals(100, decision?.distanceMeters)
        assertEquals(
            setOf(DefectAlertPolicy.AlertStage.APPROACH, DefectAlertPolicy.AlertStage.NEAR),
            decision?.consumedStages,
        )
    }

    @Test
    fun lowSpeedHasOnlyTheHundredAndFiftyMeterAlerts() {
        val firstAlert = DefectAlertPolicy.nextAlertDecision(100.0, 39.99, emptySet())
        assertEquals(
            null,
            DefectAlertPolicy.nextAlertDecision(
                90.0,
                40.0,
                firstAlert?.consumedStages.orEmpty(),
            ),
        )
        val finalAlert = DefectAlertPolicy.nextAlertDecision(
            50.0,
            39.99,
            firstAlert?.consumedStages.orEmpty(),
        )

        assertEquals(100, firstAlert?.distanceMeters)
        assertEquals(50, finalAlert?.distanceMeters)
        assertEquals(
            setOf(
                DefectAlertPolicy.AlertStage.APPROACH,
                DefectAlertPolicy.AlertStage.NEAR,
                DefectAlertPolicy.AlertStage.IMMEDIATE,
            ),
            firstAlert?.consumedStages.orEmpty() + finalAlert?.consumedStages.orEmpty(),
        )
        assertEquals(
            null,
            DefectAlertPolicy.nextAlertDecision(
                40.0,
                39.99,
                firstAlert?.consumedStages.orEmpty() + finalAlert?.consumedStages.orEmpty(),
            ),
        )
    }

    @Test
    fun onlyDefectsAheadInTheTravelCorridorAreEligible() {
        assertTrue(DefectAlertPolicy.isAheadInTravelCorridor(100.0, 2.0, 0.0, 5.0))
        assertFalse(DefectAlertPolicy.isAheadInTravelCorridor(100.0, 90.0, 0.0, 5.0))
        assertFalse(DefectAlertPolicy.isAheadInTravelCorridor(100.0, 180.0, 0.0, 5.0))
    }

    @Test
    fun headingComparisonWrapsAcrossNorth() {
        assertTrue(DefectAlertPolicy.isAheadInTravelCorridor(100.0, 2.0, 358.0, 5.0))
    }

    @Test
    fun alertDistanceUsesForwardProjection() {
        assertEquals(
            100.0,
            DefectAlertPolicy.distanceAheadInTravelCorridor(100.0, 0.0, 0.0, 5.0)!!,
            0.01,
        )
    }

    @Test
    fun predictedRouteFollowsConnectedRoadGeometryForFiveHundredMeters() {
        val network = RoadRoutePredictor.RoadNetwork(
            nodes = mapOf(
                1L to roadNode(1L, 13.0, 80.0),
                2L to roadNode(2L, 13.0, 80.003),
                3L to roadNode(3L, 13.0, 80.006),
                4L to roadNode(4L, 13.0, 80.009),
            ),
            ways = listOf(RoadRoutePredictor.RoadWay(10L, listOf(1L, 2L, 3L, 4L))),
        )

        val route = RoadRoutePredictor.predict(
            network,
            listOf(
                RoadRoutePredictor.TrackPoint(13.0, 80.001, 90.0),
            ),
        )

        assertTrue(route.size >= 3)
        assertEquals(13.0, route.first().latitude, 0.001)
        assertEquals(80.001, route.first().longitude, 0.001)
        assertTrue(route.last().longitude > 80.005)
        assertTrue(route.last().longitude < 80.006)
    }

    @Test
    fun predictedRouteChoosesTheStraightConnectedRoadAtAJunction() {
        val network = RoadRoutePredictor.RoadNetwork(
            nodes = mapOf(
                1L to roadNode(1L, 13.0, 80.0),
                2L to roadNode(2L, 13.0, 80.003),
                3L to roadNode(3L, 13.0, 80.006),
                4L to roadNode(4L, 13.003, 80.003),
            ),
            ways = listOf(
                RoadRoutePredictor.RoadWay(10L, listOf(1L, 2L, 3L)),
                RoadRoutePredictor.RoadWay(11L, listOf(2L, 4L)),
            ),
        )

        val route = RoadRoutePredictor.predict(
            network,
            listOf(RoadRoutePredictor.TrackPoint(13.0, 80.001, 90.0)),
        )

        assertTrue(route.last().longitude > 80.005)
        assertEquals(13.0, route.last().latitude, 0.001)
    }

    @Test
    fun predictedRouteUsesRecentPathToChooseBetweenParallelRoads() {
        val network = RoadRoutePredictor.RoadNetwork(
            nodes = mapOf(
                1L to roadNode(1L, 13.0, 80.0),
                2L to roadNode(2L, 13.0, 80.006),
                3L to roadNode(3L, 13.00025, 80.0),
                4L to roadNode(4L, 13.00025, 80.006),
            ),
            ways = listOf(
                RoadRoutePredictor.RoadWay(10L, listOf(1L, 2L)),
                RoadRoutePredictor.RoadWay(11L, listOf(3L, 4L)),
            ),
        )

        val route = RoadRoutePredictor.predict(
            network,
            listOf(
                RoadRoutePredictor.TrackPoint(13.0, 80.001, 90.0),
                RoadRoutePredictor.TrackPoint(13.000125, 80.0012, 90.0),
            ),
        )

        assertEquals(13.0, route.first().latitude, 0.00001)
    }

    @Test
    fun predictedRouteRespectsOneWayRoadDirection() {
        val network = RoadRoutePredictor.RoadNetwork(
            nodes = mapOf(
                1L to roadNode(1L, 13.0, 80.0),
                2L to roadNode(2L, 13.0, 80.003),
                3L to roadNode(3L, 13.0, 80.006),
            ),
            ways = listOf(
                RoadRoutePredictor.RoadWay(10L, listOf(1L, 2L, 3L), oneWay = true),
            ),
        )

        assertTrue(
            RoadRoutePredictor.predict(
                network,
                listOf(RoadRoutePredictor.TrackPoint(13.0, 80.001, 90.0)),
            ).isNotEmpty(),
        )
        assertTrue(
            RoadRoutePredictor.predict(
                network,
                listOf(RoadRoutePredictor.TrackPoint(13.0, 80.005, 270.0)),
            ).isEmpty(),
        )
    }

    @Test
    fun defectDistanceUsesRoadRouteAndRejectsDefectsOutsideItsCorridor() {
        val route = listOf(
            RoadRoutePredictor.Point(13.0, 80.0),
            RoadRoutePredictor.Point(13.0, 80.002),
        )

        val alongDistance = RoadRoutePredictor.distanceAlongRoute(
            13.000045,
            80.001,
            route,
            15.0,
        )
        assertEquals(108.0, alongDistance!!, 1.0)
        assertEquals(
            null,
            RoadRoutePredictor.distanceAlongRoute(13.001, 80.001, route, 15.0),
        )
    }

    @Test
    @Throws(IOException::class)
    fun h3ResolutionNineCellAndFirstRingContainSevenCells() {
        val h3 = H3Core.newInstance()
        val center = h3.latLngToCell(13.0827, 80.2707, 9)
        assertEquals(9, h3.getResolution(center))
        assertEquals(7, h3.gridDisk(center, 1).size)
    }

    private fun roadNode(id: Long, latitude: Double, longitude: Double) =
        RoadRoutePredictor.RoadNode(id, latitude, longitude)
}
