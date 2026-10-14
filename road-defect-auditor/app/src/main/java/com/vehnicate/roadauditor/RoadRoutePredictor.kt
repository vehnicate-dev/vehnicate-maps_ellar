package com.vehnicate.roadauditor

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

internal object RoadRoutePredictor {
    data class Point(val latitude: Double, val longitude: Double)

    data class TrackPoint(
        val latitude: Double,
        val longitude: Double,
        val bearingDegrees: Double,
    )

    data class RoadNode(
        val id: Long,
        val latitude: Double,
        val longitude: Double,
    )

    data class RoadWay(
        val id: Long,
        val nodeIds: List<Long>,
        val oneWay: Boolean = false,
        val reverseOneWay: Boolean = false,
    )

    data class RoadNetwork(
        val nodes: Map<Long, RoadNode>,
        val ways: List<RoadWay>,
    )

    fun predict(
        network: RoadNetwork,
        history: List<TrackPoint>,
        maximumDistanceMeters: Double = DEFAULT_MAXIMUM_DISTANCE_METERS,
    ): List<Point> {
        if (history.isEmpty() || maximumDistanceMeters <= 0.0) return emptyList()
        val graph = buildDirectedGraph(network)
        if (graph.edges.isEmpty()) return emptyList()
        val edgesByWay = graph.edges.groupBy { it.wayId }
        val historyDistanceByWay = history.asReversed().take(MAX_HISTORY_POINTS)
            .mapIndexed { index, point ->
                val weight = HISTORY_WEIGHTS.getOrElse(index) { HISTORY_WEIGHTS.last() }
                edgesByWay.mapValues { (_, wayEdges) ->
                    wayEdges.minOf { edge ->
                        val start = network.nodes[edge.from]!!
                        val end = network.nodes[edge.to]!!
                        project(point.latitude, point.longitude, start, end).distanceMeters
                    }.coerceAtMost(HISTORY_DISTANCE_PENALTY_CAP_METERS) * weight
                }
            }
        val current = history.last()
        val start = graph.edges
            .asSequence()
            .mapNotNull { edge ->
                val from = network.nodes[edge.from] ?: return@mapNotNull null
                val to = network.nodes[edge.to] ?: return@mapNotNull null
                val projection = project(current.latitude, current.longitude, from, to)
                val bearing = bearingDegrees(from.latitude, from.longitude, to.latitude, to.longitude)
                val difference = angleDifference(bearing, current.bearingDegrees)
                if (projection.distanceMeters > MAX_MATCH_DISTANCE_METERS ||
                    difference > MAX_MATCH_HEADING_DIFFERENCE_DEGREES
                ) {
                    return@mapNotNull null
                }
                val historyPenalty = historyDistanceByWay.sumOf { it[edge.wayId] ?: 0.0 }
                StartCandidate(edge, projection.point, projection.distanceMeters +
                    difference * HEADING_PENALTY_PER_DEGREE + historyPenalty)
            }
            .minByOrNull { it.score }
            ?: return emptyList()

        val route = mutableListOf(start.point)
        val from = network.nodes[start.edge.from] ?: return emptyList()
        val to = network.nodes[start.edge.to] ?: return emptyList()
        var distance = haversineMeters(start.point.latitude, start.point.longitude, to.latitude, to.longitude)
        route += Point(to.latitude, to.longitude)
        if (distance >= maximumDistanceMeters) {
            return trimRoute(route, maximumDistanceMeters)
        }

        var previousNode = start.edge.from
        var currentNode = start.edge.to
        var currentBearing = bearingDegrees(from.latitude, from.longitude, to.latitude, to.longitude)
        val visited = mutableSetOf(start.edge.key)
        while (distance < maximumDistanceMeters) {
            val options = graph.outgoing[currentNode].orEmpty()
                .filter { it.to != previousNode && it.key !in visited }
                .ifEmpty {
                    graph.outgoing[currentNode].orEmpty()
                        .filter { it.key !in visited }
                }
            val next = options.minByOrNull { edge ->
                val nextNode = network.nodes[edge.to] ?: return@minByOrNull Double.POSITIVE_INFINITY
                val nextBearing = bearingDegrees(
                    network.nodes[currentNode]?.latitude ?: return@minByOrNull Double.POSITIVE_INFINITY,
                    network.nodes[currentNode]?.longitude ?: return@minByOrNull Double.POSITIVE_INFINITY,
                    nextNode.latitude,
                    nextNode.longitude,
                )
                angleDifference(currentBearing, nextBearing) +
                    if (edge.wayId == start.edge.wayId) -SAME_WAY_BONUS_DEGREES else 0.0
            } ?: break
            val nextNode = network.nodes[next.to] ?: break
            val node = network.nodes[currentNode] ?: break
            val segmentLength = haversineMeters(
                node.latitude,
                node.longitude,
                nextNode.latitude,
                nextNode.longitude,
            )
            if (!segmentLength.isFinite() || segmentLength <= 0.0) break

            visited += next.key
            distance += segmentLength
            route += Point(nextNode.latitude, nextNode.longitude)
            previousNode = currentNode
            currentNode = next.to
            currentBearing = bearingDegrees(
                node.latitude,
                node.longitude,
                nextNode.latitude,
                nextNode.longitude,
            )
        }
        return trimRoute(route, maximumDistanceMeters)
    }

    fun distanceAlongRoute(
        latitude: Double,
        longitude: Double,
        route: List<Point>,
        corridorWidthMeters: Double,
    ): Double? {
        if (route.size < 2 || corridorWidthMeters < 0.0) return null
        var cumulativeDistance = 0.0
        var bestDistance = Double.POSITIVE_INFINITY
        var bestAlongDistance: Double? = null
        for (index in 0 until route.lastIndex) {
            val start = route[index]
            val end = route[index + 1]
            val projection = project(latitude, longitude, start, end)
            if (projection.distanceMeters < bestDistance) {
                bestDistance = projection.distanceMeters
                val segmentLength = haversineMeters(
                    start.latitude,
                    start.longitude,
                    end.latitude,
                    end.longitude,
                )
                bestAlongDistance = cumulativeDistance + segmentLength * projection.fraction
            }
            cumulativeDistance += haversineMeters(
                start.latitude,
                start.longitude,
                end.latitude,
                end.longitude,
            )
        }
        return bestAlongDistance?.takeIf { bestDistance <= corridorWidthMeters }
    }

    private fun buildDirectedGraph(network: RoadNetwork): DirectedGraph {
        val outgoing = mutableMapOf<Long, MutableList<Edge>>()
        val edges = mutableListOf<Edge>()
        network.ways.forEach { way ->
            val nodeIds = if (way.reverseOneWay) way.nodeIds.asReversed() else way.nodeIds
            nodeIds.zipWithNext().forEach { (from, to) ->
                if (from !in network.nodes || to !in network.nodes || from == to) return@forEach
                val forward = Edge(way.id, from, to)
                edges += forward
                outgoing.getOrPut(from) { mutableListOf() } += forward
                if (!way.oneWay && !way.reverseOneWay) {
                    val reverse = Edge(way.id, to, from)
                    edges += reverse
                    outgoing.getOrPut(to) { mutableListOf() } += reverse
                }
            }
        }
        return DirectedGraph(edges, outgoing)
    }

    private fun project(
        latitude: Double,
        longitude: Double,
        start: RoadNode,
        end: RoadNode,
    ): Projection = project(
        latitude,
        longitude,
        Point(start.latitude, start.longitude),
        Point(end.latitude, end.longitude),
    )

    private fun project(
        latitude: Double,
        longitude: Double,
        start: Point,
        end: Point,
    ): Projection {
        val referenceLatitude = Math.toRadians(latitude)
        val xScale = EARTH_RADIUS_METERS * cos(referenceLatitude) * Math.PI / 180.0
        val yScale = EARTH_RADIUS_METERS * Math.PI / 180.0
        val startX = (start.longitude - longitude) * xScale
        val startY = (start.latitude - latitude) * yScale
        val endX = (end.longitude - longitude) * xScale
        val endY = (end.latitude - latitude) * yScale
        val dx = endX - startX
        val dy = endY - startY
        val lengthSquared = dx * dx + dy * dy
        val fraction = if (lengthSquared == 0.0) 0.0 else {
            ((-startX * dx - startY * dy) / lengthSquared).coerceIn(0.0, 1.0)
        }
        val projectedX = startX + fraction * dx
        val projectedY = startY + fraction * dy
        return Projection(
            Point(
                latitude + projectedY / yScale,
                longitude + projectedX / xScale,
            ),
            fraction,
            hypot(projectedX, projectedY),
        )
    }

    private fun trimRoute(route: List<Point>, maximumDistanceMeters: Double): List<Point> {
        if (route.size < 2) return route
        val trimmed = mutableListOf(route.first())
        var distance = 0.0
        for (index in 1 until route.size) {
            val start = route[index - 1]
            val end = route[index]
            val segmentLength = haversineMeters(
                start.latitude,
                start.longitude,
                end.latitude,
                end.longitude,
            )
            if (distance + segmentLength >= maximumDistanceMeters) {
                val fraction = (maximumDistanceMeters - distance) / segmentLength
                trimmed += Point(
                    start.latitude + (end.latitude - start.latitude) * fraction,
                    start.longitude + (end.longitude - start.longitude) * fraction,
                )
                return trimmed
            }
            trimmed += end
            distance += segmentLength
        }
        return trimmed
    }

    private fun bearingDegrees(
        fromLatitude: Double,
        fromLongitude: Double,
        toLatitude: Double,
        toLongitude: Double,
    ): Double {
        val fromLat = Math.toRadians(fromLatitude)
        val toLat = Math.toRadians(toLatitude)
        val deltaLongitude = Math.toRadians(toLongitude - fromLongitude)
        val y = sin(deltaLongitude) * cos(toLat)
        val x = cos(fromLat) * sin(toLat) -
            sin(fromLat) * cos(toLat) * cos(deltaLongitude)
        return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
    }

    private fun angleDifference(first: Double, second: Double): Double =
        abs(((first - second + 540.0) % 360.0) - 180.0)

    private fun haversineMeters(
        latitude1: Double,
        longitude1: Double,
        latitude2: Double,
        longitude2: Double,
    ): Double {
        val latitudeDelta = Math.toRadians(latitude2 - latitude1)
        val longitudeDelta = Math.toRadians(longitude2 - longitude1)
        val latitude1Radians = Math.toRadians(latitude1)
        val latitude2Radians = Math.toRadians(latitude2)
        val a = sin(latitudeDelta / 2) * sin(latitudeDelta / 2) +
            cos(latitude1Radians) * cos(latitude2Radians) *
            sin(longitudeDelta / 2) * sin(longitudeDelta / 2)
        return 2.0 * EARTH_RADIUS_METERS * atan2(kotlin.math.sqrt(a), kotlin.math.sqrt(1.0 - a))
    }

    private data class Edge(val wayId: Long, val from: Long, val to: Long) {
        val key: String get() = "$wayId:$from:$to"
    }

    private data class DirectedGraph(
        val edges: List<Edge>,
        val outgoing: Map<Long, List<Edge>>,
    )

    private data class Projection(
        val point: Point,
        val fraction: Double,
        val distanceMeters: Double,
    )

    private data class StartCandidate(
        val edge: Edge,
        val point: Point,
        val score: Double,
    )

    private const val EARTH_RADIUS_METERS = 6_371_000.0
    private const val DEFAULT_MAXIMUM_DISTANCE_METERS = 500.0
    private const val MAX_MATCH_DISTANCE_METERS = 50.0
    private const val MAX_MATCH_HEADING_DIFFERENCE_DEGREES = 70.0
    private const val HEADING_PENALTY_PER_DEGREE = 1.0
    private const val MAX_HISTORY_POINTS = 5
    private const val HISTORY_DISTANCE_PENALTY_CAP_METERS = 25.0
    private const val SAME_WAY_BONUS_DEGREES = 25.0
    private val HISTORY_WEIGHTS = listOf(0.1, 0.15, 0.2, 0.25, 0.3)
}
