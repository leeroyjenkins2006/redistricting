from formatData.graphObject import GraphObject
from formatData.censusContainer import CensusContainer
from geographyHelper import doesGeographyContainTheOther, intersectingGeometries, distanceBetweenGeometries, \
    findContiguousGroupsOfGraphObjects, polygonFromMultipleGeometries, intersectingPolygons
from tqdm import tqdm


class AtomicBlock(CensusContainer, GraphObject):
    def __init__(self, childrenBlocks):
        CensusContainer.__init__(self)
        self.children = childrenBlocks
        GraphObject.__init__(self, self.geometry.centroid)
        self.isWater = self.getWaterPropertyFromBlocks()
        AtomicBlock.atomicBlockList.append(self)

    atomicBlockList = []

    def updateBlockContainerData(self):
        super(AtomicBlock, self).updateBlockContainerData()
        self.updateCenterOfObject(self.geometry.centroid)

    def importCensusBlock(self, censusBlock):
        self.children.append(censusBlock)
        self.isWater = self.getWaterPropertyFromBlocks()
        self.updateBlockContainerData()

    def getWaterPropertyFromBlocks(self):
        return all(block.isWater for block in self.children)


def assignNeighborBlocksFromCandidateBlocks(block, candidateBlocks, progressObject=None):
    block.clearNeighborGraphObjects()
    neighborBlocks = []
    for candidateBlock in candidateBlocks:
        if candidateBlock is not block:
            if intersectingGeometries(block, candidateBlock):
                neighborBlocks.append(candidateBlock)
    block.addNeighbors(neighbors=neighborBlocks)

    for neighborBlock in neighborBlocks:
        if block not in neighborBlock.allNeighbors:
            neighborBlock.addNeighbor(block)

    if progressObject:
        progressObject.update(1)


def reorganizeAtomicBlockGroups(atomicBlockGroups):
    for block in [block for atomicBlockGroup in atomicBlockGroups for block in atomicBlockGroup]:
        block.removeNonIntersectingNeighbors()

    for atomicBlockGroup in atomicBlockGroups:
        contiguousRegions = findContiguousGroupsOfGraphObjects(atomicBlockGroup)
        while len(contiguousRegions) > 1:
            smallestContiguousRegion = min(contiguousRegions,
                                           key=lambda contiguousRegion: len(contiguousRegion))
            smallestContiguousRegionPolygon = polygonFromMultipleGeometries(smallestContiguousRegion)

            otherSplitChildrenList = [x for x in atomicBlockGroups if x is not atomicBlockGroup]
            for otherSplitChildren in otherSplitChildrenList:
                otherSplitChildrenPolygon = polygonFromMultipleGeometries(otherSplitChildren)
                if intersectingPolygons(smallestContiguousRegionPolygon, otherSplitChildrenPolygon):
                    for childBlock in smallestContiguousRegion:
                        atomicBlockGroup.remove(childBlock)
                        childBlock.removeNeighborConnections()

                        otherSplitChildren.append(childBlock)
                        assignNeighborBlocksFromCandidateBlocks(block=childBlock, candidateBlocks=otherSplitChildren)
                    contiguousRegions = findContiguousGroupsOfGraphObjects(atomicBlockGroup)
                    break

    return atomicBlockGroups


def createAtomicBlockFromCensusBlock(censusBlock):
    newAtomicBlock = AtomicBlock(childrenBlocks=[censusBlock])
    return newAtomicBlock


def atomicBlockWithBlock(block, atomicBlockList):
    return next((atomicBlock for atomicBlock in atomicBlockList if block in atomicBlock.children), None)


def createAtomicBlocksFromBlockList(blockList):
    atomicBlockList = []
    with tqdm(total=len(blockList)) as pbar:
        for i in reversed(range(len(blockList))):
            block = blockList[i]
            convertedAtomicBlock = createAtomicBlockFromCensusBlock(block)
            atomicBlockList.append(convertedAtomicBlock)
            for j in reversed(range(len(blockList))):
                otherBlock = blockList[j]
                if block != otherBlock:
                    if doesGeographyContainTheOther(container=block, target=otherBlock):
                        convertedAtomicBlock.importCensusBlock(otherBlock)
                        del blockList[blockList.index(otherBlock)]

                        atomicBlockThatAlreadyExists = atomicBlockWithBlock(block=otherBlock,
                                                                            atomicBlockList=atomicBlockList)
                        if atomicBlockThatAlreadyExists:
                            del atomicBlockList[atomicBlockList.index(atomicBlockThatAlreadyExists)]
            pbar.update(1)

    return atomicBlockList


def validateAllAtomicBlocks():
    for atomicBlock in AtomicBlock.atomicBlockList:
        atomicBlock.validateNeighborLists()
