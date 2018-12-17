import math
from tqdm import tqdm
from enum import Enum
from exportData.displayShapes import plotGraphObjectGroups
from exportData.exportData import saveDataToFileWithDescription
from formatData.atomicBlock import assignNeighborBlocksFromCandidateBlocks
from formatData.blockBorderGraph import BlockBorderGraph
from formatData.redistrictingGroup import validateContiguousRedistrictingGroups, RedistrictingGroup, \
    assignNeighboringRedistrictingGroupsToRedistrictingGroups, validateRedistrictingGroups
from geographyHelper import alignmentOfPolygon, Alignment, mostCardinalOfGeometries, CardinalDirection, \
    weightedForestFireFillGraphObject, polsbyPopperScoreOfPolygon, polygonFromMultipleGeometries, \
    intersectingGeometries, polygonFromMultiplePolygons, findContiguousGroupsOfGraphObjects, boundsIndexFromDirection


class District(BlockBorderGraph):
    def __init__(self, childrenGroups):
        BlockBorderGraph.__init__(self)
        self.children = childrenGroups
        self.removeOutdatedNeighborConnections()
        District.districtList.append(self)

    districtList = []

    def updateBlockContainerData(self):
        super(District, self).updateBlockContainerData()
        validateContiguousRedistrictingGroups(self.children)

    def getCutStartingCandidates(self):
        longestDirection = alignmentOfPolygon(self.geometry)

        northernStartingCandidate = mostCardinalOfGeometries(geometryList=self.borderChildren,
                                                             direction=CardinalDirection.north)
        westernStartingCandidate = mostCardinalOfGeometries(geometryList=self.borderChildren,
                                                            direction=CardinalDirection.west)
        easternStartingCandidate = mostCardinalOfGeometries(geometryList=self.borderChildren,
                                                            direction=CardinalDirection.east)
        southernStartingCandidate = mostCardinalOfGeometries(geometryList=self.borderChildren,
                                                             direction=CardinalDirection.south)
        if longestDirection == Alignment.northSouth:
            startingGroupCandidates = ((northernStartingCandidate, CardinalDirection.north),
                                       (southernStartingCandidate, CardinalDirection.south),
                                       (westernStartingCandidate, CardinalDirection.west),
                                       (easternStartingCandidate, CardinalDirection.east))
        else:
            startingGroupCandidates = ((westernStartingCandidate, CardinalDirection.west),
                                       (easternStartingCandidate, CardinalDirection.east),
                                       (northernStartingCandidate, CardinalDirection.north),
                                       (southernStartingCandidate, CardinalDirection.south))

        return startingGroupCandidates

    def splitDistrict(self,
                      numberOfDistricts,
                      populationDeviation,
                      weightingMethod,
                      breakingMethod,
                      count=None,
                      shouldMergeIntoFormerRedistrictingGroups=False,
                      shouldRefillEachPass=False,
                      shouldDrawFillAttempts=False,
                      shouldDrawEachStep=False,
                      splitBestCandidateGroup=False,
                      fastCalculations=True,
                      showDetailedProgress=False):
        if count is None:
            tqdm.write('*** Splitting into {0} districts ***'.format(numberOfDistricts))
            count = 0

        districts = []

        if numberOfDistricts == 1:
            return [self]

        aRatio = math.floor(numberOfDistricts / 2)
        bRatio = math.ceil(numberOfDistricts / 2)
        ratio = (aRatio, bRatio)

        cutDistrict = self.cutDistrictIntoExactRatio(ratio=ratio,
                                                     populationDeviation=populationDeviation,
                                                     weightingMethod=weightingMethod,
                                                     breakingMethod=breakingMethod,
                                                     shouldDrawFillAttempts=shouldDrawFillAttempts,
                                                     shouldDrawEachStep=shouldDrawEachStep,
                                                     shouldMergeIntoFormerRedistrictingGroups=shouldMergeIntoFormerRedistrictingGroups,
                                                     shouldRefillEachPass=shouldRefillEachPass,
                                                     fastCalculations=fastCalculations,
                                                     showDetailedProgress=showDetailedProgress)
        count += 1
        tqdm.write('   *** Cut district into exact ratio: {0} ***'.format(count))

        aDistrict = District(childrenGroups=cutDistrict[0])
        aDistrictSplits = aDistrict.splitDistrict(numberOfDistricts=aRatio,
                                                  populationDeviation=populationDeviation,
                                                  weightingMethod=weightingMethod,
                                                  breakingMethod=breakingMethod,
                                                  count=count,
                                                  shouldMergeIntoFormerRedistrictingGroups=shouldMergeIntoFormerRedistrictingGroups,
                                                  shouldRefillEachPass=shouldRefillEachPass,
                                                  splitBestCandidateGroup=splitBestCandidateGroup,
                                                  shouldDrawFillAttempts=shouldDrawFillAttempts,
                                                  shouldDrawEachStep=shouldDrawEachStep,
                                                  fastCalculations=fastCalculations,
                                                  showDetailedProgress=showDetailedProgress)
        districts.extend(aDistrictSplits)

        bDistrict = District(childrenGroups=cutDistrict[1])
        bDistrictSplits = bDistrict.splitDistrict(numberOfDistricts=bRatio,
                                                  populationDeviation=populationDeviation,
                                                  weightingMethod=weightingMethod,
                                                  breakingMethod=breakingMethod,
                                                  count=count,
                                                  shouldMergeIntoFormerRedistrictingGroups=shouldMergeIntoFormerRedistrictingGroups,
                                                  shouldRefillEachPass=shouldRefillEachPass,
                                                  splitBestCandidateGroup=splitBestCandidateGroup,
                                                  shouldDrawFillAttempts=shouldDrawFillAttempts,
                                                  shouldDrawEachStep=shouldDrawEachStep,
                                                  fastCalculations=fastCalculations,
                                                  showDetailedProgress=showDetailedProgress)
        districts.extend(bDistrictSplits)

        return districts

    def cutDistrictIntoExactRatio(self, ratio, populationDeviation, weightingMethod, breakingMethod,
                                  shouldDrawFillAttempts=False, shouldDrawEachStep=False,
                                  shouldMergeIntoFormerRedistrictingGroups=False, shouldRefillEachPass=False,
                                  fastCalculations=True, showDetailedProgress=False):

        ratioTotal = ratio[0] + ratio[1]
        idealDistrictASize = int(self.population / (ratioTotal / ratio[0]))
        idealDistrictBSize = int(self.population / (ratioTotal / ratio[1]))
        candidateDistrictA = []
        candidateDistrictB = []
        fillOriginDirection = None
        districtStillNotExactlyCut = True
        tqdm.write(
            '   *** Attempting forest fire fill for a {0} to {1} ratio on: ***'.format(ratio[0], ratio[1], id(self)))

        count = 1
        while districtStillNotExactlyCut:
            tqdm.write('      *** Starting forest fire fill pass #{0} ***'.format(count))

            if len(candidateDistrictA) == 0:
                districtAStartingGroup = None
            else:
                if shouldRefillEachPass:
                    districtAStartingGroup = None
                else:
                    districtAStartingGroup = candidateDistrictA

            if breakingMethod is BreakingMethod.splitBestCandidateGroup:
                returnBestCandidateGroup = True
            else:
                returnBestCandidateGroup = False

            districtCandidateResult = self.cutDistrictIntoRoughRatio(idealDistrictASize=idealDistrictASize,
                                                                     weightingMethod=weightingMethod,
                                                                     districtAStartingGroup=districtAStartingGroup,
                                                                     fillOriginDirection=fillOriginDirection,
                                                                     shouldDrawEachStep=shouldDrawEachStep,
                                                                     returnBestCandidateGroup=returnBestCandidateGroup,
                                                                     fastCalculations=fastCalculations)
            districtCandidates = districtCandidateResult[0]
            nextBestGroupForCandidateDistrictA = districtCandidateResult[1]
            fillOriginDirection = districtCandidateResult[2]

            candidateDistrictA = districtCandidates[0]
            candidateDistrictB = districtCandidates[1]

            if shouldDrawFillAttempts:
                if nextBestGroupForCandidateDistrictA is None:
                    nextBestGroupForCandidateDistrictA = []
                plotGraphObjectGroups(
                    graphObjectGroups=[candidateDistrictA, candidateDistrictB, nextBestGroupForCandidateDistrictA],
                    showDistrictNeighborConnections=True,
                    saveImages=True,
                    saveDescription='DistrictSplittingIteration-{0}-{1}'.format(id(self), count))

            candidateDistrictAPop = sum(group.population for group in candidateDistrictA)
            candidateDistrictBPop = sum(group.population for group in candidateDistrictB)

            if idealDistrictASize - populationDeviation <= candidateDistrictAPop <= idealDistrictASize + populationDeviation and \
                    idealDistrictBSize - populationDeviation <= candidateDistrictBPop <= idealDistrictBSize + populationDeviation:
                districtStillNotExactlyCut = False
            else:
                tqdm.write('      *** Unsuccessful fill attempt. {0} off the count. ***'
                           .format(abs(idealDistrictASize - candidateDistrictAPop)))
                if len(self.children) == 1:
                    # this means that the candidate couldn't fill because there a single redistricting group
                    # likely because there was a single county
                    groupsToBreakUp = [self.children[0]]
                else:
                    if breakingMethod is BreakingMethod.splitBestCandidateGroup:
                        groupsToBreakUp = nextBestGroupForCandidateDistrictA
                    elif breakingMethod is BreakingMethod.splitGroupsOnEdge:
                        groupsBetweenCandidates = getRedistrictingGroupsBetweenCandidates(candidateDistrictA,
                                                                                          candidateDistrictB)
                        # if we are refilling each time and merging after a split,
                        # we can break up groups on both sides of the boundary
                        if shouldMergeIntoFormerRedistrictingGroups and shouldRefillEachPass:
                            groupsToBreakUp = groupsBetweenCandidates
                        else:
                            groupsToBreakUp = [groupToBreakUp for groupToBreakUp in groupsBetweenCandidates
                                               if groupToBreakUp not in candidateDistrictA]
                    elif breakingMethod is BreakingMethod.splitLowestEnergySeam:
                        raise NotImplementedError('splitLowestEnergySeam not yet Implemented')
                    else:
                        raise RuntimeError('{0} is not supported'.format(breakingMethod))

                groupsCapableOfBreaking = [groupToBreakUp for groupToBreakUp in groupsToBreakUp
                                           if len(groupToBreakUp.children) > 1]
                if len(groupsCapableOfBreaking) == 0:
                    saveDataToFileWithDescription(data=[self, districtAStartingGroup,
                                                        candidateDistrictA, candidateDistrictB,
                                                        nextBestGroupForCandidateDistrictA],
                                                  censusYear='',
                                                  stateName='',
                                                  descriptionOfInfo='ErrorCase-NoGroupsCapableOfBreaking')
                    plotGraphObjectGroups([self.children, districtAStartingGroup])
                    raise RuntimeError("Groups to break up don't meet criteria. Groups: {0}".format(
                        [groupToBreakUp.graphId for groupToBreakUp in groupsToBreakUp]
                    ))

                tqdm.write(
                    '      *** Graph splitting {0} redistricting groups ***'.format(len(groupsCapableOfBreaking)))
                updatedChildren = self.children.copy()
                newRedistrictingGroups = []
                if showDetailedProgress:
                    pbar = None
                else:
                    pbar = tqdm(total=len(groupsCapableOfBreaking))
                for groupToBreakUp in groupsCapableOfBreaking:
                    if showDetailedProgress:
                        countForProgress = groupsCapableOfBreaking.index(groupToBreakUp) + 1
                    else:
                        countForProgress = None
                    smallerRedistrictingGroups = groupToBreakUp.getGraphSplits(shouldDrawGraph=shouldDrawEachStep,
                                                                               countForProgress=countForProgress)
                    updatedChildren.extend(smallerRedistrictingGroups)
                    updatedChildren.remove(groupToBreakUp)
                    RedistrictingGroup.redistrictingGroupList.remove(groupToBreakUp)

                    # assign the previous parent graphId so that we can combine the parts again after the exact split
                    for smallerRedistrictingGroup in smallerRedistrictingGroups:
                        if groupToBreakUp.previousParentId is None:
                            previousParentId = groupToBreakUp.graphId
                        else:
                            previousParentId = groupToBreakUp.previousParentId
                        smallerRedistrictingGroup.previousParentId = previousParentId

                    newRedistrictingGroups.extend(smallerRedistrictingGroups)
                    if pbar is not None:
                        pbar.update(1)
                if pbar is not None:
                    pbar.close()

                tqdm.write('      *** Re-attaching new Redistricting Groups to existing Groups ***')
                assignNeighboringRedistrictingGroupsToRedistrictingGroups(
                    changedRedistrictingGroups=newRedistrictingGroups,
                    allNeighborCandidates=updatedChildren)
                validateRedistrictingGroups(updatedChildren)

                tqdm.write('      *** Updating District Candidate Data ***')
                self.children = updatedChildren

            saveDataToFileWithDescription(data=(self, candidateDistrictA, ratio),
                                          censusYear='',
                                          stateName='',
                                          descriptionOfInfo='DistrictSplitLastIteration-{0}'.format(id(self)))
            count += 1

        if shouldMergeIntoFormerRedistrictingGroups:
            tqdm.write('      *** Merging candidates into remaining starting groups ***')
            mergedCandidates = mergeCandidatesIntoPreviousGroups(
                candidates=[candidateDistrictA, candidateDistrictB])
            candidateDistrictA = mergedCandidates[0]
            candidateDistrictB = mergedCandidates[1]
            tqdm.write('      *** Re-attaching new Redistricting Groups to existing Groups ***')
            assignNeighboringRedistrictingGroupsToRedistrictingGroups(
                changedRedistrictingGroups=candidateDistrictA,
                allNeighborCandidates=candidateDistrictA)
            assignNeighboringRedistrictingGroupsToRedistrictingGroups(
                changedRedistrictingGroups=candidateDistrictB,
                allNeighborCandidates=candidateDistrictB)
            validateRedistrictingGroups(candidateDistrictA)
            validateRedistrictingGroups(candidateDistrictB)

        tqdm.write(
            '   *** Successful fill attempt!!! *** <------------------------------------------------------------')
        return candidateDistrictA, candidateDistrictB

    def cutDistrictIntoRoughRatio(self, idealDistrictASize, weightingMethod, districtAStartingGroup=None,
                                  fillOriginDirection=None, shouldDrawEachStep=False, returnBestCandidateGroup=False,
                                  fastCalculations=True):
        if districtAStartingGroup:
            startingGroupCandidates = [(districtAStartingGroup.copy(), fillOriginDirection)]
        else:
            startingGroupCandidates = [([startingGroupCandidate], direction)
                                       for startingGroupCandidate, direction in self.getCutStartingCandidates()]

        i = 0
        candidateDistrictA = []
        nextBestGroupFromCandidateDistrictA = None
        while not candidateDistrictA and i < len(startingGroupCandidates):
            startingObjects = startingGroupCandidates[i][0]
            fillOriginDirection = startingGroupCandidates[i][1]

            def withinIdealDistrictSize(currentGroups, candidateGroups):
                currentPop = sum(group.population for group in currentGroups)
                candidatePop = sum(group.population for group in candidateGroups)
                proposedPop = currentPop + candidatePop
                isWithinIdealPop = proposedPop <= idealDistrictASize
                proposedPopDiff = idealDistrictASize - proposedPop
                return isWithinIdealPop, proposedPopDiff

            def polsbyPopperScoreOfCombinedGeometry(currentGroupPolygon, remainingGroups, candidateGroups,
                                                    fastCalculations=True):
                candidateGroupsPolygon = polygonFromMultipleGeometries(candidateGroups,
                                                                       useEnvelope=fastCalculations)
                # never useEnvelope here, because currentGroupPolygon is our cached shape
                candidatePolygon = polygonFromMultiplePolygons([currentGroupPolygon, candidateGroupsPolygon])
                combinedRemainingPolygon = polygonFromMultipleGeometries(remainingGroups,
                                                                         useEnvelope=fastCalculations)

                score = polsbyPopperScoreOfPolygon(candidatePolygon)
                remainingScore = polsbyPopperScoreOfPolygon(combinedRemainingPolygon)

                return score + remainingScore

            def distanceScoreOfCombinedGeometry(currentGroupPolygon, remainingGroups, candidateGroups,
                                                fastCalculations=True):
                candidateGroupsPolygon = polygonFromMultipleGeometries(candidateGroups,
                                                                       useEnvelope=fastCalculations)
                distance = currentGroupPolygon.centroid.distance(candidateGroupsPolygon)
                score = 1 / distance

                return score

            def cardinalDirectionScoreOfCandidateGroups(currentGroupPolygon, remainingGroups, candidateGroups,
                                                        fastCalculations=True):
                boundsIndex = boundsIndexFromDirection(fillOriginDirection)
                directionReferenceValue = self.geometry.bounds[boundsIndex]
                candidateGroupsPolygon = polygonFromMultipleGeometries(candidateGroups,
                                                                       useEnvelope=fastCalculations)
                candidateGroupsValue = candidateGroupsPolygon.bounds[boundsIndex]
                difference = directionReferenceValue - candidateGroupsValue
                difference = math.fabs(difference)
                score = 1 / difference

                return score

            if weightingMethod is WeightingMethod.distance:
                chosenWeightingAlgorithm = distanceScoreOfCombinedGeometry
            elif weightingMethod is WeightingMethod.polsbyPopper:
                chosenWeightingAlgorithm = polsbyPopperScoreOfCombinedGeometry
            elif weightingMethod is WeightingMethod.cardinalDistance:
                chosenWeightingAlgorithm = cardinalDirectionScoreOfCandidateGroups
            else:
                raise RuntimeError('Must choose a weighting method. {0} is not supported'.format(weightingMethod))

            candidateDistrictAResult = weightedForestFireFillGraphObject(candidateObjects=self.children,
                                                                         startingObjects=startingObjects,
                                                                         condition=withinIdealDistrictSize,
                                                                         weightingScore=chosenWeightingAlgorithm,
                                                                         shouldDrawEachStep=shouldDrawEachStep,
                                                                         returnBestCandidateGroup=returnBestCandidateGroup,
                                                                         fastCalculations=fastCalculations)
            candidateDistrictA = candidateDistrictAResult[0]
            nextBestGroupFromCandidateDistrictA = candidateDistrictAResult[1]
            i += 1

        candidateDistrictB = [group for group in self.children if group not in candidateDistrictA]
        return (candidateDistrictA, candidateDistrictB), nextBestGroupFromCandidateDistrictA, fillOriginDirection


def createDistrictFromRedistrictingGroups(redistrictingGroups):
    initialDistrict = District(childrenGroups=redistrictingGroups)
    return initialDistrict


def getRedistrictingGroupsBetweenCandidates(aCandidate, bCandidate):
    groupsBetween = []

    for aGroup in aCandidate:
        for bGroup in bCandidate:
            if intersectingGeometries(aGroup, bGroup):
                if aGroup not in groupsBetween:
                    groupsBetween.append(aGroup)
                if bGroup not in groupsBetween:
                    groupsBetween.append(bGroup)

    return groupsBetween


def mergeCandidatesIntoPreviousGroups(candidates):
    mergedCandidates = []
    for candidate in candidates:

        # group redistricting groups together based on previous parent
        parentDict = {}
        for redistrictingGroup in candidate:
            # if it doesn't have a previous parent, that means it wasn't broken up, so we will just let is pass through
            if redistrictingGroup.previousParentId is None:
                parentDict[redistrictingGroup.graphId] = [redistrictingGroup]
            else:
                if redistrictingGroup.previousParentId in parentDict:
                    parentDict[redistrictingGroup.previousParentId].append(redistrictingGroup)
                else:
                    parentDict[redistrictingGroup.previousParentId] = [redistrictingGroup]

        # merge the grouped groups together
        mergedRedistrictingGroups = []
        with tqdm(total=len(parentDict)) as pbar:
            for redistrictingGroupList in parentDict.values():
                if len(redistrictingGroupList) == 1:
                    mergedRedistrictingGroups.append(redistrictingGroupList[0])
                else:
                    allBorderBlocks = []
                    allBlocks = []
                    for redistrictingGroup in redistrictingGroupList:
                        allBorderBlocks.extend(redistrictingGroup.borderChildren)
                        allBlocks.extend(redistrictingGroup.children)

                    # assign block neighbors to former border blocks
                    for formerBorderBlock in allBorderBlocks:
                        assignNeighborBlocksFromCandidateBlocks(block=formerBorderBlock,
                                                                candidateBlocks=allBlocks)

                    contiguousRegions = findContiguousGroupsOfGraphObjects(allBlocks)

                    mergedRedistrictingGroupsForPrevious = []
                    for contiguousRegion in contiguousRegions:
                        contiguousRegionGroup = RedistrictingGroup(childrenBlocks=contiguousRegion)
                        # assign block neighbors to former border blocks
                        for borderBlock in contiguousRegionGroup.borderChildren:
                            assignNeighborBlocksFromCandidateBlocks(block=borderBlock,
                                                                    candidateBlocks=contiguousRegionGroup.children)
                        contiguousRegionGroup.validateBlockNeighbors()
                        mergedRedistrictingGroupsForPrevious.append(contiguousRegionGroup)
                    mergedRedistrictingGroups.extend(mergedRedistrictingGroupsForPrevious)
                pbar.update(1)

        mergedCandidates.append(mergedRedistrictingGroups)

    return mergedCandidates


class WeightingMethod(Enum):
    distance = 0
    polsbyPopper = 1
    cardinalDistance = 2


class BreakingMethod(Enum):
    splitBestCandidateGroup = 0
    splitGroupsOnEdge = 1
    splitLowestEnergySeam = 2
