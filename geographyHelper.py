from shapely.geometry import shape, mapping, MultiPolygon, LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import cascaded_union
from enum import Enum
from math import atan2, degrees, pi
from json import dumps


# On Windows, I needed to install Shapely manually
# Found whl file here: https://www.lfd.uci.edu/~gohlke/pythonlibs/#shapely
# And then ran:
# from pip._internal import main
# def install_whl(path):
#     main(['install', path])
# install_whl("path_to_file\\Shapely-1.6.4.post1-cp37-cp37m-win32.whl")
# but not sure if this worked...

def convertGeoJSONToShapely(geoJSON):
    shapelyShape = shape(geoJSON)
    return shapelyShape


def intersectingGeometries(a, b):
    return a.geometry.intersects(b.geometry)


def doesEitherGeographyContainTheOther(a, b):
    aContainsBBoundary = doesGeographyContainTheOther(container=a, target=b)
    bContainsABoundary = doesGeographyContainTheOther(container=b, target=a)
    return aContainsBBoundary or bContainsABoundary


def doesGeographyContainTheOther(container, target):
    if type(container.geometry) is MultiPolygon:
        containerPolygons = list(container.geometry)
    else:
        containerPolygons = [container.geometry]

    containsTargetBoundary = False
    for containerPolygon in containerPolygons:
        if containerPolygon.interiors:
            containsTargetBoundary = containsTargetBoundary or containerPolygon.boundary.contains(target.geometry.boundary)
        else:
            containsTargetBoundary = containsTargetBoundary or containerPolygon.contains(target.geometry)
    return containsTargetBoundary


def isBoundaryGeometry(parent, child):
    return parent.geometry.boundary.intersects(child.geometry.boundary)


def geometryFromMultipleGeometries(geometryList):
    polygons = [geometry.geometry for geometry in geometryList]
    union = cascaded_union(polygons)
    union = union.simplify(tolerance=0.0) #to remove excessive points
    return union


class CardinalDirection(Enum):
    north = 1
    west = 3
    east = 0
    south = 4


class Alignment(Enum):
    northSouth = 1
    westEast = 2


def findDirection(basePoint, targetPoint):
    if basePoint == targetPoint:
        return CardinalDirection.north

    xDiff = targetPoint.x - basePoint.x
    yDiff = targetPoint.y - basePoint.y
    radianDiff = atan2(yDiff, xDiff)

    # rotate 90 degrees for easier angle matching
    radianDiff = radianDiff - (pi / 2)

    if radianDiff < 0:
        radianDiff = radianDiff + (2 * pi)

    degDiff = degrees(radianDiff)

    if 45 <= degDiff and degDiff < 135:
        return CardinalDirection.west
    elif 135 <= degDiff and degDiff < 225:
        return CardinalDirection.south
    elif 225 <= degDiff and degDiff < 315:
        return CardinalDirection.east
    else:
        return CardinalDirection.north


def findDirectionOfShape(baseShape, targetShape):
    basePoint = baseShape.centroid
    targetPoint = targetShape.centroid
    direction = findDirection(basePoint=basePoint, targetPoint=targetPoint)
    return direction


def findDirectionOfShapeFromPoint(basePoint, targetShape):
    targetPoint = targetShape.centroid
    direction = findDirection(basePoint=basePoint, targetPoint=targetPoint)
    return direction


def findDirectionOfShapesInRect(rect, targetShapes):
    rectPoints = list(rect.exterior.coords)
    northernLine = LineString([rectPoints[0], rectPoints[1]])
    easternLine = LineString([rectPoints[1], rectPoints[2]])
    southernLine = LineString([rectPoints[2], rectPoints[3]])
    westernLine = LineString([rectPoints[3], rectPoints[4]])
    directionalLines = [northernLine, easternLine, southernLine, westernLine]

    directionOfShapes = []
    for targetShape in targetShapes:
        closestShape = findClosestGeometry(originGeometry=targetShape, otherGeometries=directionalLines)
        direction = None
        if closestShape is northernLine:
            direction = CardinalDirection.north
        elif closestShape is easternLine:
            direction = CardinalDirection.east
        elif closestShape is southernLine:
            direction = CardinalDirection.south
        elif closestShape is westernLine:
            direction = CardinalDirection.west
        directionOfShapes.append((targetShape, direction))
    return directionOfShapes

    # targetPoint = targetShape.centroid
    # direction = findDirection(basePoint=basePoint, targetPoint=targetPoint)
    # return direction


def shapelyGeometryToGeoJSON(geometry):
    geoDict = mapping(geometry)
    geoString = dumps(geoDict)
    return geoString


def distanceBetweenGeometries(a, b):
    if type(a) is list:
        a = geometryFromMultipleGeometries(a)
    elif isinstance(a, BaseGeometry):
        a = a
    else:
        a = a.geometry

    if type(b) is list:
        b = geometryFromMultipleGeometries(b)
    elif isinstance(b, BaseGeometry):
        b = b
    else:
        b = b.geometry
    return a.distance(b)


def findClosestGeometry(originGeometry, otherGeometries):
    candidateGeometries = [block for block in otherGeometries if block is not originGeometry]
    distanceDict = {}
    for candidateGeometry in candidateGeometries:
        distance = distanceBetweenGeometries(originGeometry, candidateGeometry)
        distanceDict[distance] = candidateGeometry
    shortestDistance = min(distanceDict.keys())
    closestGeometry = distanceDict[shortestDistance]
    return closestGeometry


def findContiguousGroupsOfGraphObjects(graphObjects):
    if graphObjects:
        remainingObjects = graphObjects.copy()
        contiguousObjectGroups = []
        while len(remainingObjects) > 0:
            contiguousObjectGroups.append(floodFillGraphObject(remainingObjects=remainingObjects))
        return contiguousObjectGroups
    else:
        return []


def floodFillGraphObject(remainingObjects):
    floodFilledObjects = []
    floodQueue = []
    floodQueue.append(remainingObjects[0])

    while len(floodQueue) > 0:
        graphObject = floodQueue.pop(0)
        remainingObjects.remove(graphObject)
        floodFilledObjects.append(graphObject)

        directionSets = graphObject.directionSets
        for directionSet in directionSets:
            for neighborObject in directionSet:
                if neighborObject in remainingObjects and neighborObject not in floodQueue:
                    floodQueue.append(neighborObject)

    return floodFilledObjects


def alignmentOfGeometry(geometry):
    minX = geometry.bounds[0]
    minY = geometry.bounds[1]
    maxX = geometry.bounds[2]
    maxY = geometry.bounds[3]
    if maxY - minY > maxX - minX:
        return Alignment.northSouth
    else:
        return Alignment.westEast
