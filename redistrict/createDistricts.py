from us import states
from exportData.displayShapes import plotDistricts, plotPolygons
from exportData.exportData import loadDataFromFileWithDescription, saveDataToFileWithDescription
from redistrict.district import createDistrictFromRedistrictingGroups

stateAbbreviation = 'MI'
stateInfo = states.lookup(stateAbbreviation)
censusYear = 2010
descriptionToWorkWith = 'All'

redistrictingGroups = loadDataFromFileWithDescription(censusYear=censusYear,
                                                      stateName=stateInfo.name,
                                                      descriptionOfInfo='{0}RedistrictingGroup'.format(
                                                          descriptionToWorkWith))

initialDistrict = createDistrictFromRedistrictingGroups(redistrictingGroups=redistrictingGroups)

districts = initialDistrict.splitDistrict(numberOfDistricts=14,
                                          populationDeviation=1,
                                          splitBestCandidateGroup=False,
                                          shouldMergeIntoFormerRedistrictingGroups=True,
                                          shouldRefillEachPass=True,
                                          fastCalculations=False,
                                          showDetailedProgress=False,
                                          useDistanceScoring=True)
saveDataToFileWithDescription(data=districts,
                              censusYear=censusYear,
                              stateName=stateInfo,
                              descriptionOfInfo='{0}-InitialDistrictSplitExactly'.format(descriptionToWorkWith))
plotDistricts(districts=districts,
              showPopulationCounts=False,
              showDistrictNeighborConnections=False)
districtPolygons = [district.geometry for district in districts]
plotPolygons(districtPolygons)
