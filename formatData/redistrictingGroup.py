from exportData.displayShapes import plotGraphObjectGroups, plotPolygons, plotRedistrictingGroups, \
    plotBlocksForRedistrictingGroup
from shapely.geometry import Polygon, MultiPolygon
from exportData.exportData import saveDataToFileWithDescription
from formatData.atomicBlock import createAtomicBlocksFromBlockList, validateAllAtomicBlocks, \
    assignNeighborBlocksFromCandidateBlocks
from formatData.blockBorderGraph import BlockBorderGraph
from formatData.graphObject import GraphObject
from geographyHelper import findContiguousGroupsOfGraphObjects, findClosestGeometry, intersectingGeometries, Alignment, \
    mostCardinalOfGeometries, CardinalDirection, polygonFromMultipleGeometries, polygonFromMultiplePolygons, \
    doesPolygonContainTheOther, getPolygonThatContainsGeometry, intersectingPolygons
from enum import Enum
from censusData import censusBlock
from multiprocessing.dummy import Pool
from itertools import repeat
from tqdm import tqdm


class RedistrictingGroup(BlockBorderGraph, GraphObject):
    def __init__(self, childrenBlocks):
        BlockBorderGraph.__init__(self)
        self.children = childrenBlocks
        GraphObject.__init__(self, centerOfObject=self.geometry.centroid)
        if len(self.children) == 0:
            raise AttributeError(
                "Can't create a redistricting group with no children. GraphId: {0}".format(self.graphId))
        RedistrictingGroup.redistrictingGroupList.append(self)

    redistrictingGroupList = []

    def __setstate__(self, state):
        RedistrictingGroup.redistrictingGroupList.append(self)
        super(RedistrictingGroup, self).__setstate__(state)

    def updateBlockContainerData(self):
        super(RedistrictingGroup, self).updateBlockContainerData()
        self.updateCenterOfObject(self.geometry.centroid)

    def removeWaterBlocks(self):
        nonWaterBlocks = [block for block in self.children if block.isWater is False]
        waterBlocks = [block for block in self.children if block.isWater is True]
        if any([waterBlock for waterBlock in waterBlocks if waterBlock.population > 0]):
            raise ValueError('Water block had a population')
        self.children = nonWaterBlocks

    def attachOrphanBlocksToClosestNeighbor(self):
        orphanBlocks = self.findOrphanBlocks()
        for orphanBlock in orphanBlocks:
            closestBlock = findClosestGeometry(originGeometry=self, otherGeometries=self.children)
            orphanBlock.addNeighbors(neighbors=[closestBlock])
            closestBlock.addNeighbors(neighbors=[orphanBlock])

    def findOrphanBlocks(self):
        return [block for block in self.children if block.hasNeighbors is False]

    def getGraphSplits(self, shouldDrawGraph=False, countForProgress=None):
        if len(self.children) == 1:
            raise RuntimeError("Can't split RedistrictingGroup with a single child. GraphId: {0}".format(self.graphId))

        if countForProgress is not None:
            tqdm.write('         *** Finding seams for graph split {0} - GraphId: {1} - Block count: {2} ***'
                       .format(countForProgress, self.graphId, len(self.children)))
        with tqdm(total=4) as pbar:
            self.fillPopulationEnergyGraph(Alignment.northSouth)
            pbar.update(1)
            northSouthSplitResult = self.getPopulationEnergySplit(Alignment.northSouth, shouldDrawGraph=shouldDrawGraph)
            northSouthSplitResultType = northSouthSplitResult[0]
            if northSouthSplitResultType is SplitType.NoSplit:
                northSouthSplit = None
            elif northSouthSplitResultType is SplitType.ForceSplitAllBlocks:
                splitGroups = []
                for redistrictingGroupChild in self.children:
                    splitGroups.append(RedistrictingGroup(childrenBlocks=[redistrictingGroupChild]))
                return splitGroups
            else:
                northSouthSplit = northSouthSplitResult[1]
            pbar.update(1)
            self.clearPopulationEnergyGraph()

            self.fillPopulationEnergyGraph(Alignment.westEast)
            pbar.update(1)
            westEastSplitResult = self.getPopulationEnergySplit(Alignment.westEast, shouldDrawGraph=shouldDrawGraph)
            westEastSplitResultType = westEastSplitResult[0]
            if westEastSplitResultType is SplitType.NoSplit:
                westEastSplit = None
            elif westEastSplitResultType is SplitType.ForceSplitAllBlocks:
                return self.children.copy()
            else:
                westEastSplit = westEastSplitResult[1]
            pbar.update(1)
            self.clearPopulationEnergyGraph()

        if countForProgress is not None:
            tqdm.write('            *** Creating new Redistricting Groups in {0} ***'.format(countForProgress))

        splitGroups = []
        if northSouthSplit and not westEastSplit:
            northSplit = RedistrictingGroup(childrenBlocks=northSouthSplit[0])
            splitGroups.append(northSplit)

            southSplit = RedistrictingGroup(childrenBlocks=northSouthSplit[1])
            splitGroups.append(southSplit)
        elif not northSouthSplit and westEastSplit:
            westSplit = RedistrictingGroup(childrenBlocks=westEastSplit[0])
            splitGroups.append(westSplit)

            eastSplit = RedistrictingGroup(childrenBlocks=westEastSplit[1])
            splitGroups.append(eastSplit)
        else:
            northWestSplitChildren = [group for group in northSouthSplit[0] if group in westEastSplit[0]]
            northEastSplitChildren = [group for group in northSouthSplit[0] if group in westEastSplit[1]]
            southWestSplitChildren = [group for group in northSouthSplit[1] if group in westEastSplit[0]]
            southEastSplitChildren = [group for group in northSouthSplit[1] if group in westEastSplit[1]]

            splitChildrenList = [northWestSplitChildren,
                                 northEastSplitChildren,
                                 southWestSplitChildren,
                                 southEastSplitChildren]

            # check for orphan blocks and attach to intersecting split
            for splitChildren in splitChildrenList:
                contiguousRegions = findContiguousGroupsOfGraphObjects(splitChildren)
                while len(contiguousRegions) > 1:
                    smallestContiguousRegion = min(contiguousRegions,
                                                   key=lambda contiguousRegion: len(contiguousRegion))
                    smallestContiguousRegionPolygon = polygonFromMultipleGeometries(smallestContiguousRegion)

                    otherSplitChildrenList = [x for x in splitChildrenList if x is not splitChildren]
                    for otherSplitChildren in otherSplitChildrenList:
                        otherSplitChildrenPolygon = polygonFromMultipleGeometries(otherSplitChildren)
                        if intersectingPolygons(smallestContiguousRegionPolygon, otherSplitChildrenPolygon):
                            for child in smallestContiguousRegion:
                                splitChildren.remove(child)
                                otherSplitChildren.append(child)
                            contiguousRegions = findContiguousGroupsOfGraphObjects(splitChildren)
                            break

            for splitChildren in splitChildrenList:
                if len(splitChildren) > 0:
                    splitGroup = RedistrictingGroup(childrenBlocks=splitChildren)
                    splitGroups.append(splitGroup)

        if countForProgress is not None:
            tqdm.write(
                '            *** Re-assigning neighboring blocks to new Redistricting Groups in {0} ***'.format(
                    countForProgress))

        for splitGroup in splitGroups:
            if shouldDrawGraph:
                plotBlocksForRedistrictingGroup(splitGroup)
            splitGroup.removeOutdatedNeighborConnections(borderBlocksOnly=True)
            splitGroup.validateBlockNeighbors()

        if shouldDrawGraph:
            plotRedistrictingGroups(redistrictingGroups=splitGroups)

        return splitGroups

    def fillPopulationEnergyGraph(self, alignment):
        remainingObjects = self.children.copy()
        if alignment is Alignment.northSouth:
            blocksToActOn = self.westernChildBlocks
        else:
            blocksToActOn = self.northernChildBlocks

        if len(blocksToActOn) > 0:
            for blockToActOn in blocksToActOn:
                blockToActOn.populationEnergy = blockToActOn.population
                remainingObjects.remove(blockToActOn)

            while len(remainingObjects) > 0:
                neighborsOfBlocks = getNeighborsForGraphObjectsInList(graphObjects=blocksToActOn,
                                                                      inList=remainingObjects)
                if len(neighborsOfBlocks) > 0:
                    blocksToActOn = neighborsOfBlocks
                else:
                    saveDataToFileWithDescription(data=self,
                                                  censusYear='',
                                                  stateName='',
                                                  descriptionOfInfo='ErrorCase-NoNeighborsForGraphGroups')
                    plotBlocksForRedistrictingGroup(self, showBlockNeighborConnections=True)
                    # plotGraphObjectGroups([self.children, blocksToActOn])
                    raise RuntimeError("Can't find neighbors for graph objects")
                filledBlocks = [block for block in self.children if block not in remainingObjects]

                for blockToActOn in blocksToActOn:
                    previousNeighbors = getNeighborsForGraphObjectsInList(graphObjects=[blockToActOn],
                                                                          inList=filledBlocks)
                    if len(previousNeighbors) is 0:
                        raise ReferenceError("Can't find previous neighbor for {0}".format(blockToActOn))

                    lowestPopulationEnergyNeighbor = min(previousNeighbors, key=lambda block: block.populationEnergy)

                    blockToActOn.populationEnergy = lowestPopulationEnergyNeighbor.populationEnergy + blockToActOn.population
                    remainingObjects.remove(blockToActOn)

    def clearPopulationEnergyGraph(self):
        for child in self.children:
            child.populationEnergy = 0

    def getPopulationEnergySplit(self, alignment, shouldDrawGraph=False):
        polygonSplitResult = self.getPopulationEnergyPolygonSplit(alignment=alignment, shouldDrawGraph=shouldDrawGraph)
        polygonSplitResultType = polygonSplitResult[0]
        if polygonSplitResultType is SplitType.NoSplit:
            return SplitType.NoSplit, None
        elif polygonSplitResultType is SplitType.ForceSplitAllBlocks:
            return SplitType.ForceSplitAllBlocks, None

        polygonSplits = polygonSplitResult[1]

        aSplitPolygon = polygonSplits[0]
        bSplitPolygon = polygonSplits[1]

        if polygonSplitResultType is SplitType.SplitIncludedInSeam:
            seamOnEdge = True
            seamSplitPolygon = None
        else:
            seamOnEdge = False
            seamSplitPolygon = polygonSplitResult[2]

        aSplit = []
        bSplit = []
        seamSplit = []
        for block in self.children:
            if doesPolygonContainTheOther(container=aSplitPolygon, target=block.geometry, ignoreInteriors=False):
                aSplit.append(block)
            elif doesPolygonContainTheOther(container=bSplitPolygon, target=block.geometry, ignoreInteriors=False):
                bSplit.append(block)
            elif not seamOnEdge and doesPolygonContainTheOther(container=seamSplitPolygon, target=block.geometry,
                                                               ignoreInteriors=False):
                seamSplit.append(block)
            else:
                plotPolygons([aSplitPolygon, bSplitPolygon, seamSplitPolygon, block.geometry])
                raise RuntimeError("Couldn't find a container for block: {0}".format(block.geometry))

        aSplitPopulation = sum(block.population for block in aSplit)
        bSplitPopulation = sum(block.population for block in bSplit)

        if aSplitPopulation < bSplitPopulation:
            aSplit += seamSplit
        else:
            bSplit += seamSplit

        if shouldDrawGraph:
            plotGraphObjectGroups(graphObjectGroups=[aSplit, bSplit])

        return SplitType.NormalSplit, (aSplit, bSplit)

    def getPopulationEnergyPolygonSplit(self, alignment, shouldDrawGraph=False):
        finishingBlocksToAvoid = []
        while True:
            lowestEnergySeamResult = self.getLowestPopulationEnergySeam(alignment=alignment,
                                                                        finishingBlocksToAvoid=finishingBlocksToAvoid)
            if lowestEnergySeamResult is None:
                return SplitType.NoSplit, None
            lowestEnergySeam = lowestEnergySeamResult[0]
            energySeamFinishingBlock = lowestEnergySeamResult[1]

            seamSplitPolygon = polygonFromMultipleGeometries(geometryList=lowestEnergySeam)
            polygonWithoutSeam = self.geometry.difference(seamSplitPolygon)

            # if the polygon without the seam is empty, that means we have a small enough redistricting group where
            # we need to break it up completely. Because our seams can no longer break up any further.
            if polygonWithoutSeam.is_empty:
                return SplitType.ForceSplitAllBlocks, None

            if type(polygonWithoutSeam) is MultiPolygon:
                seamOnEdge = False
                splitPolygons = list(polygonWithoutSeam)
            else:
                seamOnEdge = True
                splitPolygons = [polygonWithoutSeam, seamSplitPolygon]

            if alignment is Alignment.northSouth:
                aSplitRepresentativeBlockDirection = CardinalDirection.north
                bSplitRepresentativeBlockDirection = CardinalDirection.south
            else:
                aSplitRepresentativeBlockDirection = CardinalDirection.west
                bSplitRepresentativeBlockDirection = CardinalDirection.east

            # Identify which polygon is in which direction
            # Note: Need to make sure we don't select a block in the seam so we supply a list without those blocks
            #   If the seam is completely on the edge though, let's include the seam
            if seamOnEdge:
                borderChildrenRepresentativeCandidates = self.borderChildren
            else:
                borderChildrenRepresentativeCandidates = [child for child in self.borderChildren if
                                                          child not in lowestEnergySeam]
            aSplitRepresentativeBlock = mostCardinalOfGeometries(geometryList=borderChildrenRepresentativeCandidates,
                                                                 direction=aSplitRepresentativeBlockDirection)

            bSplitRepresentativeBlock = mostCardinalOfGeometries(geometryList=borderChildrenRepresentativeCandidates,
                                                                 direction=bSplitRepresentativeBlockDirection)

            aSplitPolygon = getPolygonThatContainsGeometry(polygonList=splitPolygons,
                                                           targetGeometry=aSplitRepresentativeBlock,
                                                           useTargetRepresentativePoint=True)
            bSplitPolygon = getPolygonThatContainsGeometry(polygonList=splitPolygons,
                                                           targetGeometry=bSplitRepresentativeBlock,
                                                           useTargetRepresentativePoint=True)
            leftOverPolygons = [geometry for geometry in splitPolygons if
                                geometry is not aSplitPolygon and geometry is not bSplitPolygon]
            if aSplitPolygon is None or bSplitPolygon is None:
                plotPolygons(splitPolygons + [aSplitRepresentativeBlock.geometry, bSplitRepresentativeBlock.geometry])
                saveDataToFileWithDescription(data=self,
                                              censusYear='',
                                              stateName='',
                                              descriptionOfInfo='ErrorCase-AorBSplitIsNone')
                raise RuntimeError('Split a or b not found')

            if aSplitPolygon is bSplitPolygon:
                finishingBlocksToAvoid.append(energySeamFinishingBlock)
                continue

            if len(leftOverPolygons) is not len(splitPolygons) - 2:
                saveDataToFileWithDescription(data=self,
                                              censusYear='',
                                              stateName='',
                                              descriptionOfInfo='ErrorCase-MissingPolygons')
                raise RuntimeError('Missing some polygons for mapping. Split polygons: {0} Left over polygon: {1}'
                                   .format(len(splitPolygons), len(leftOverPolygons)))

            polygonSplits = (aSplitPolygon, bSplitPolygon)

            if shouldDrawGraph:
                plotPolygons(polygonSplits)

            if seamOnEdge:
                return SplitType.SplitIncludedInSeam, polygonSplits, None
            else:
                seamSplitPolygon = polygonFromMultiplePolygons(polygonList=[seamSplitPolygon] + leftOverPolygons)
                return SplitType.NormalSplit, polygonSplits, seamSplitPolygon

    def getLowestPopulationEnergySeam(self, alignment, shouldDrawGraph=False, finishingBlocksToAvoid=None):
        if alignment is Alignment.northSouth:
            startingCandidates = self.easternChildBlocks
            borderBlocksToAvoid = self.northernChildBlocks + self.southernChildBlocks + startingCandidates
            finishCandidates = self.westernChildBlocks
        else:
            startingCandidates = self.southernChildBlocks
            borderBlocksToAvoid = self.westernChildBlocks + self.easternChildBlocks + startingCandidates
            finishCandidates = self.northernChildBlocks

        if finishingBlocksToAvoid:
            finishCandidates = [candidate for candidate in finishCandidates if candidate not in finishingBlocksToAvoid]

        if len(startingCandidates) == 0 or len(finishCandidates) == 0:
            tqdm.write("      *** Couldn't find a split for {0} ***".format(self.graphId))
            return None

        startingBlock = min(startingCandidates, key=lambda block: block.populationEnergy)
        blockToActOn = startingBlock

        lowestPopulationEnergySeam = [blockToActOn]
        failedStartingBlocks = []
        avoidingAdjacentBorderBlocks = True
        finishedSeam = False
        finishingBlock = None
        count = 1
        while not finishedSeam:
            if alignment is Alignment.northSouth:
                primaryNeighborCandidates = blockToActOn.westernNeighbors
            else:
                primaryNeighborCandidates = blockToActOn.northernNeighbors
            neighborCandidates = [block for block in primaryNeighborCandidates
                                  if block not in lowestPopulationEnergySeam and
                                  block not in borderBlocksToAvoid]

            if len(neighborCandidates) is 0:
                neighborCandidates = [block for block in blockToActOn.allNeighbors
                                      if block not in lowestPopulationEnergySeam and
                                      block not in borderBlocksToAvoid]

            # If we don't have any neighbors in the direction we're headed,
            # we need to find the next best block candidate
            if len(neighborCandidates) is 0:
                failedStartingBlocks.append(startingBlock)

                remainingStartingCandidates = [startingCandidate for startingCandidate in startingCandidates if
                                               startingCandidate not in failedStartingBlocks]

                # If there are no more starting candidates, remove the adjacent border blocks to avoid rule
                if len(remainingStartingCandidates) is 0:
                    if avoidingAdjacentBorderBlocks:
                        avoidingAdjacentBorderBlocks = False
                        borderBlocksToAvoid = startingCandidates
                        failedStartingBlocks = []
                        startingBlock = min(startingCandidates, key=lambda block: block.populationEnergy)
                        blockToActOn = startingBlock
                        lowestPopulationEnergySeam = [blockToActOn]
                        continue
                    else:  # not sure there is anything more we can do but split everything up
                        # plotGraphObjectGroups([self.children, failedStartingBlocks, finishingBlocksToAvoid])
                        tqdm.write("Can't find a {0} path through {1}. Tried and failed on {2} starting blocks"
                                   .format(alignment, self.graphId, len(failedStartingBlocks)))
                        return None

                startingBlock = min(remainingStartingCandidates, key=lambda block: block.populationEnergy)
                blockToActOn = startingBlock
                lowestPopulationEnergySeam = [blockToActOn]
                continue

            lowestPopulationEnergyNeighbor = min(neighborCandidates, key=lambda block: block.populationEnergy)
            if shouldDrawGraph:
                plotGraphObjectGroups(graphObjectGroups=[self.children,
                                                         neighborCandidates,
                                                         startingCandidates,
                                                         finishCandidates,
                                                         [],
                                                         [],
                                                         [],
                                                         lowestPopulationEnergySeam,
                                                         [lowestPopulationEnergyNeighbor],
                                                         failedStartingBlocks],
                                      showGraphHeatmapForFirstGroup=True,
                                      saveImages=True,
                                      saveDescription='SeamFinding{0}'.format(count))

            blockToActOn = lowestPopulationEnergyNeighbor

            lowestPopulationEnergySeam.append(blockToActOn)

            if blockToActOn in finishCandidates:
                finishedSeam = True
                finishingBlock = blockToActOn

            count += 1
        return lowestPopulationEnergySeam, finishingBlock

    def validateBlockNeighbors(self):
        contiguousRegions = findContiguousGroupsOfGraphObjects(self.children)
        if len(contiguousRegions) > 1:
            plotGraphObjectGroups(contiguousRegions,
                                  showDistrictNeighborConnections=True)
            raise ValueError(
                "Don't have a contiguous set of AtomicBlocks. There are {0} distinct groups".format(
                    len(contiguousRegions)))

    def assignNeighboringBlocksToBlocks(self):
        with tqdm(total=len(self.children)) as pbar:
            threadPool = Pool(4)
            threadPool.starmap(assignNeighborBlocksFromCandidateBlocks,
                               zip(self.children,
                                   repeat(self.children),
                                   repeat(pbar)))

    def __lt__(self, other):
        if isinstance(other, RedistrictingGroup):
            return self.graphId < other.graphId
        return NotImplemented('Can only do a less than comparison with another RedistrictingGroup')


class SplitType(Enum):
    NoSplit = 0
    NormalSplit = 1
    SplitIncludedInSeam = 2
    ForceSplitAllBlocks = 3


def getNeighborsForGraphObjectsInList(graphObjects, inList):
    neighborList = []
    for graphObject in graphObjects:
        for neighborObject in graphObject.allNeighbors:
            if neighborObject in inList and neighborObject not in neighborList and neighborObject not in graphObjects:
                neighborList.append(neighborObject)
    return neighborList


def attachOrphanBlocksToClosestNeighborForAllRedistrictingGroups():
    for blockContainer in RedistrictingGroup.redistrictingGroupList:
        blockContainer.attachOrphanBlocksToClosestNeighbor()


def updateAllBlockContainersData():
    tqdm.write('*** Updating All Block Container Data ***')
    with tqdm(total=len(RedistrictingGroup.redistrictingGroupList)) as pbar:
        for blockContainer in RedistrictingGroup.redistrictingGroupList:
            tqdm.write('   *** One more ***')
            blockContainer.updateBlockContainerData()
            pbar.update(1)


def removeWaterBlocksFromAllRedistrictingGroups():
    tqdm.write('\n')
    tqdm.write('*** Removing Water Blocks From All Redistricting Groups ***')
    with tqdm(total=len(RedistrictingGroup.redistrictingGroupList)) as pbar:
        for redistrictingGroup in RedistrictingGroup.redistrictingGroupList:
            redistrictingGroup.removeWaterBlocks()
            pbar.update(1)


def splitNonContiguousRedistrictingGroups():
    for redistrictingGroup in RedistrictingGroup.redistrictingGroupList:
        contiguousGroups = findContiguousGroupsOfGraphObjects(redistrictingGroup.children)

        if len(contiguousGroups) > 1:
            RedistrictingGroup.redistrictingGroupList.remove(redistrictingGroup)
            for contiguousGroup in contiguousGroups:
                RedistrictingGroup(childrenBlocks=contiguousGroup)


def assignNeighboringBlocksToBlocksForAllRedistrictingGroups():
    tqdm.write('\n')
    tqdm.write('*** Assigning Neighbors To All Census Blocks ***')
    count = 1
    for redistrictingGroup in RedistrictingGroup.redistrictingGroupList:
        tqdm.write('\n')
        tqdm.write('    *** Assigning Neighbors To All Census Blocks for Redistricting Group {0} of {1} ***'
                   .format(count, len(RedistrictingGroup.redistrictingGroupList)))
        redistrictingGroup.assignNeighboringBlocksToBlocks()
        count += 1

    # find single orphaned atomic blocks and attach them to the closest neighbor.
    # That way we don't have too small of redistricting groups for splitting them in the next step.
    attachOrphanBlocksToClosestNeighborForAllRedistrictingGroups()


def attachOrphanRedistrictingGroupsToClosestNeighbor():
    contiguousRegions = findContiguousGroupsOfGraphObjects(RedistrictingGroup.redistrictingGroupList)
    while len(contiguousRegions) > 1:
        for isolatedRegion in contiguousRegions:
            closestRegion = findClosestGeometry(originGeometry=isolatedRegion,
                                                otherGeometries=[region for region in contiguousRegions if
                                                                 region is not isolatedRegion])

            closestGroupInIsolatedRegion = findClosestGeometry(originGeometry=closestRegion,
                                                               otherGeometries=isolatedRegion)
            closestGroupInClosestRegion = findClosestGeometry(originGeometry=isolatedRegion,
                                                              otherGeometries=closestRegion)

            # these two may already be neighbors from a previous iteration of this loop, so we check
            if not closestGroupInIsolatedRegion.isNeighbor(closestGroupInClosestRegion):
                closestGroupInIsolatedRegion.addNeighbors(neighbors=[closestGroupInClosestRegion])
                closestGroupInClosestRegion.addNeighbors(neighbors=[closestGroupInIsolatedRegion])
        contiguousRegions = findContiguousGroupsOfGraphObjects(RedistrictingGroup.redistrictingGroupList)


def assignNeighboringRedistrictingGroupsForAllRedistrictingGroups():
    assignNeighboringRedistrictingGroupsToRedistrictingGroups(
        changedRedistrictingGroups=RedistrictingGroup.redistrictingGroupList,
        allNeighborCandidates=RedistrictingGroup.redistrictingGroupList)


def assignNeighboringRedistrictingGroupsToRedistrictingGroups(changedRedistrictingGroups, allNeighborCandidates):
    # remove outdated neighbor connections
    for redistrictingGroup in allNeighborCandidates:
        outdatedNeighborConnections = [neighbor for neighbor in redistrictingGroup.allNeighbors
                                       if neighbor not in allNeighborCandidates]
        if outdatedNeighborConnections:
            redistrictingGroup.removeNeighbors(outdatedNeighborConnections)

    # assign neighbors to changed groups and those that they touch
    for changedRedistrictingGroup in changedRedistrictingGroups:
        changedRedistrictingGroup.clearNeighborGraphObjects()
        for redistrictingGroupToCheckAgainst in [aGroup for aGroup in allNeighborCandidates
                                                 if aGroup is not changedRedistrictingGroup]:
            if intersectingGeometries(changedRedistrictingGroup, redistrictingGroupToCheckAgainst):
                changedRedistrictingGroup.addNeighbors([redistrictingGroupToCheckAgainst])
                redistrictingGroupToCheckAgainst.addNeighbors([changedRedistrictingGroup])

    attachOrphanRedistrictingGroupsToClosestNeighbor()


def getRedistrictingGroupWithCountyFIPS(countyFIPS):
    # for use when first loading redistricting group
    return next((item for item in RedistrictingGroup.redistrictingGroupList if item.FIPS == countyFIPS), None)


def convertAllCensusBlocksToAtomicBlocks():
    tqdm.write('\n')
    tqdm.write('*** Converting All Census Blocks to Atomic Blocks ***')
    count = 1
    for blockContainer in RedistrictingGroup.redistrictingGroupList:
        tqdm.write('\n')
        tqdm.write('    *** Converting to Atomic Blocks for Redistricting Group {0} of {1} ***'
                   .format(count, len(RedistrictingGroup.redistrictingGroupList)))
        atomicBlocksForGroup = createAtomicBlocksFromBlockList(blockList=blockContainer.children)
        blockContainer.children = atomicBlocksForGroup  # this triggers a block container update
        count += 1


def validateAllRedistrictingGroups():
    validateContiguousRedistrictingGroups(RedistrictingGroup.redistrictingGroupList)

    for redistrictingGroup in RedistrictingGroup.redistrictingGroupList:
        redistrictingGroup.validateNeighborLists()
        if type(redistrictingGroup.geometry) is not Polygon:
            raise RuntimeError(
                "Found a redistricting group without a Polygon geometry: {0}".format(redistrictingGroup.graphId))


def validateContiguousRedistrictingGroups(groupList):
    contiguousRegions = findContiguousGroupsOfGraphObjects(groupList)
    if len(contiguousRegions) > 1:
        plotGraphObjectGroups(contiguousRegions,
                              showDistrictNeighborConnections=True)
        raise ValueError("Don't have a contiguous set of RedistrictingGroups. There are {0} distinct groups".format(
            len(contiguousRegions)))


def createRedistrictingGroupsWithAtomicBlocksFromCensusData(censusData):
    tqdm.write('\n')
    tqdm.write('*** Creating Redistricting Groups from Census Data ***')
    with tqdm(total=len(censusData)) as pbar:
        for censusBlockDict in censusData:
            redistrictingGroupWithCountyFIPS = getRedistrictingGroupWithCountyFIPS(censusBlockDict['county'])
            if redistrictingGroupWithCountyFIPS is None:
                redistrictingGroupWithCountyFIPS = RedistrictingGroup(childrenBlocks=[])
                redistrictingGroupWithCountyFIPS.FIPS = censusBlockDict['county']

            isWater = False
            if censusBlockDict['block'][0] == '0':
                isWater = True
            blockFromData = censusBlock.CensusBlock(countyFIPS=censusBlockDict['county'],
                                                    tractFIPS=censusBlockDict['tract'],
                                                    blockFIPS=censusBlockDict['block'],
                                                    population=int(censusBlockDict['P0010001']),
                                                    isWater=isWater,
                                                    geoJSONGeometry=censusBlockDict['geometry'])
            redistrictingGroupWithCountyFIPS.children.append(blockFromData)
            pbar.update(1)

    # remove FIPS info from the groups to not pollute data later
    for redistrictingGroup in RedistrictingGroup.redistrictingGroupList:
        del redistrictingGroup.FIPS

    # convert census blocks to atomic blocks
    convertAllCensusBlocksToAtomicBlocks()

    return RedistrictingGroup.redistrictingGroupList


def prepareGraphsForAllRedistrictingGroups():
    # remove water blocks
    removeWaterBlocksFromAllRedistrictingGroups()

    # assign neighboring blocks to atomic blocks
    assignNeighboringBlocksToBlocksForAllRedistrictingGroups()

    # split non-contiguous redistricting groups
    splitNonContiguousRedistrictingGroups()

    # find and set neighboring geometries
    assignNeighboringRedistrictingGroupsForAllRedistrictingGroups()

    validateAllRedistrictingGroups()
    validateAllAtomicBlocks()

    return RedistrictingGroup.redistrictingGroupList
