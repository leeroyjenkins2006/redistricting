from formatData.blockGraphObject import BlockGraphObject
from formatData.censusBlockContainer import CensusBlockContainer
from geographyHelper import doesGeographyContainTheOther, intersectingGeometries
from tqdm import tqdm


class AtomicBlock(CensusBlockContainer, BlockGraphObject):
    def __init__(self, childrenBlocks):
        CensusBlockContainer.__init__(self)
        self.blocks = childrenBlocks
        BlockGraphObject.__init__(self, self.geometry.centroid)
        self.isWater = self.getWaterPropertyFromBlocks()
        AtomicBlock.atomicBlockList.append(self)

    atomicBlockList = []


    def updateBlockContainerData(self):
        super(AtomicBlock, self).updateBlockContainerData()
        self.updateCenterOfObject(self.geometry.centroid)


    def importCensusBlock(self, censusBlock):
        self.blocks.append(censusBlock)
        self.isWater = self.getWaterPropertyFromBlocks()
        self.updateBlockContainerData()


    def getWaterPropertyFromBlocks(self):
        return all(block.isWater for block in self.blocks)


    def assignNeighborBlocksFromCandiateBlocks(self, candidateBlocks):
        neighborBlocks = []
        for candidateBlock in candidateBlocks:
            if candidateBlock is not self:
                if intersectingGeometries(self, candidateBlock):
                    if candidateBlock == self:
                        temp=0
                    neighborBlocks.append(candidateBlock)
        self.addNeighborBlocks(neighborBlocks=neighborBlocks)


def createAtomicBlockFromCensusBlock(censusBlock):
    newAtomicBlock = AtomicBlock(childrenBlocks=[censusBlock])
    return newAtomicBlock


def atomicBlockWithBlock(block, atomicBlockList):
    return next((atomicBlock for atomicBlock in atomicBlockList if block in atomicBlock.blocks), None)


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
                        #blockGeoJSON = shapelyGeometryToGeoJSON(block.geometry)
                        #otherBlockGeoJSON = shapelyGeometryToGeoJSON(otherBlock.geometry)
                        convertedAtomicBlock.importCensusBlock(otherBlock)
                        del blockList[blockList.index(otherBlock)]

                        atomicBlockThatAlreadyExists = atomicBlockWithBlock(block=otherBlock, atomicBlockList=atomicBlockList)
                        if atomicBlockThatAlreadyExists:
                            del atomicBlockList[atomicBlockList.index(atomicBlockThatAlreadyExists)]
            pbar.update(1)

    return atomicBlockList