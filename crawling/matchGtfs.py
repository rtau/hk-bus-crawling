import json
import sys
from haversine import haversine

INFINITY_DIST = 1000000
DIST_DIFF = 600

with open('gtfs.json', 'r', encoding='UTF-8') as f:
  gtfs = json.load(f)
  gtfsRoutes = gtfs['routeList']
  gtfsStops = gtfs['stopList']


def isNameMatch(name_a, name_b):
  tmp_a = name_a.lower()
  tmp_b = name_b.lower()
  return tmp_a.find(tmp_b) >= 0 or tmp_b.find(tmp_a) >= 0

# ctb routes only give list of stops in topological order
# the actual servicing routes may skip some stop in the coStops
# this DP function is trying to map the coStops back to GTFS stops


def matchStopsByDp(coStops, gtfsStops, co, debug=False):
  # handle unknown stop
  co = 'unknown' if co not in gtfsStops[0]['stopName'] else co
  if len(gtfsStops) > len(coStops) + 1:
    return [], INFINITY_DIST
  if len(gtfsStops) - len(coStops) == 1:
    gtfsStops = gtfsStops[:-1]

  # initialization
  distSum = [[INFINITY_DIST for x in range(
      len(coStops) + 1)] for y in range(len(gtfsStops) + 1)]
  for j in range(len(coStops) - len(gtfsStops) + 1):
    distSum[0][j] = 0

  # Perform DP
  for i in range(len(gtfsStops)):
    gtfsStop = gtfsStops[i]
    for j in range(len(coStops)):
      coStop = coStops[j]
      dist = (0
              if coStop['name_tc'] == gtfsStop['stopName'][co]
              else haversine(
                  (float(coStop['lat']), float(coStop['long'])),
                  (gtfsStop['lat'], gtfsStop['lng'])
              ) * 1000
              )

      distSum[i + 1][j + 1] = min(
          distSum[i][j] + dist,  # from previous stops of both sides
          distSum[i + 1][j]       # skipping current coStops
      )

  # fast return if no good result
  if not min(distSum[len(gtfsStops)]) / len(gtfsStops) < DIST_DIFF:
    return [], INFINITY_DIST

  # backtracking
  i = len(gtfsStops)
  j = len(coStops)
  ret = []
  while i > 0 and j > 0:
    if distSum[i][j] == distSum[i][j - 1]:
      j -= 1
    else:
      ret.append((i - 1, j - 1))
      i -= 1
      j -= 1
  ret.reverse()

  # penalty distance is given for not exact match route
  penalty = sum([abs(a - b) for a, b in ret]) * 0.01

  return ret, min(distSum[len(gtfsStops)]) / len(gtfsStops) + penalty


def mergeRouteAsCircularRoute(routeA, routeB):
  return {
      "co": routeA['co'],
      "route": routeA["route"],
      "bound": routeA["bound"] + routeB["bound"],
      "orig_en": routeA["orig_en"],
      "orig_tc": routeA["orig_tc"],
      "dest_en": routeB["dest_en"],
      "dest_tc": routeB["dest_tc"],
      "serviceType": routeA["serviceType"],
      "stops": routeA['stops'] + routeB['stops'],
      "virtual": True,
  }


def getVirtualCircularRoutes(routeList, routeNo):
  indices = []
  for idx, route in enumerate(routeList):
    if route['route'] == routeNo:
      indices.append(idx)
  if len(indices) != 2:
    return []

  ret = []
  routeA = routeList[indices[0]]
  routeB = routeList[indices[1]]
  if "co" not in routeA or "serviceType" not in routeA:
    return []

  return [
      mergeRouteAsCircularRoute(routeA, routeB),
      mergeRouteAsCircularRoute(routeB, routeA)
  ]


def printStopMatches(bestMatch, gtfsStops, stopList, co):
  stopPair = [(bestMatch[4][gtfsStopIdx], bestMatch[5]["stops"][routeStopIdx])
              for gtfsStopIdx, routeStopIdx in bestMatch[2]]
  print(bestMatch[3], bestMatch[0], bestMatch[1])
  print("\t|\t".join(["運輸處", co]))
  print("\n".join([str(idx + 1) + "  " + "\t|\t".join([gtfsStops[gtfsId]["stopName"][co],
        stopList[stopId]["name_tc"]]) for idx, (gtfsId, stopId) in enumerate(stopPair)]))
  print()


def matchRoutes(co):
  print(co)
  with open('routeList.%s.json' % co, 'r', encoding="utf-8") as f:
    routeList = json.load(f)
  with open('stopList.%s.json' % co, 'r', encoding="utf-8") as f:
    stopList = json.load(f)

  routeCandidates = []
  # one pass to find matches of co vs gtfs by DP
  for gtfsId, gtfsRoute in gtfsRoutes.items():
    debug = False and gtfsId == '1047' and gtfsRoute['orig']['zh'] == '沙田站'
    if co == 'gmb' and co in gtfsRoute['co']:  # handle for gmb
      for route in routeList:
        if route['gtfsId'] == gtfsId:
          route['fares'] = [gtfsRoute['fares']['1'][0]
                            for i in range(len(route['stops']) - 1)]
    elif (co == "sunferry" or co == "fortuneferry") and "ferry" in gtfsRoute['co']:
      for route in routeList:
        if route['gtfsId'] == gtfsId:
          route['fares'] = [gtfsRoute['fares']['1'][0]
                            for i in range(len(route['stops']) - 1)]
    # handle for other companies
    elif co in gtfsRoute['co'] or (co == "hkkf" and 'ferry' in gtfsRoute['co']):
      for bound, stops in gtfsRoute['stops'].items():
        bestMatch = (-1, INFINITY_DIST)
        for route in routeList + \
                getVirtualCircularRoutes(routeList, gtfsRoute['route']):
          if (
              co in gtfsRoute['co'] and route['route'] == gtfsRoute['route']) or (
              co == 'hkkf' and (
                  (route["orig_tc"].startswith(
                      gtfsRoute['orig']['zh']) and route["dest_tc"].startswith(
                      gtfsRoute['dest']['zh'])) or (
                      route["orig_tc"].startswith(
                          gtfsRoute['dest']['zh']) and route["dest_tc"].startswith(
                          gtfsRoute['orig']['zh'])))):
            ret, avgDist = matchStopsByDp([stopList[stop] for stop in route['stops']], [
                                          gtfsStops[stop] for stop in stops], co, debug)
            if avgDist < bestMatch[1]:
              bestMatch = (gtfsId, avgDist, ret, bound, stops, route)

        # assume matching to be avg stop distance diff is lower than 100
        if bestMatch[1] < DIST_DIFF:
          ret, bound, stops, route = bestMatch[2:]

          routeCandidate = route.copy()
          if (
              len(ret) == len(
                  route['stops']) or len(ret) +
              1 == len(
                  route['stops'])) and 'gtfs' not in route and "virtual" not in route:
            routeCandidate['fares'] = [gtfsRoute['fares'][bound][i] for i, j in ret[:-1]
                                       ] if len(ret[:-1]) < len(gtfsRoute["fares"][bound]) + 1 else None
            routeCandidate['freq'] = gtfsRoute['freq'][bound]
            routeCandidate['jt'] = gtfsRoute['jt']
            routeCandidate['co'] = gtfsRoute['co'] if co in gtfsRoute['co'] else (
                gtfsRoute['co'] + [co])
            routeCandidate['stops'] = [route['stops'][j] for i, j in ret]
            routeCandidate['gtfs'] = [gtfsId]
            route['found'] = True
          else:
            routeCandidate['stops'] = [route['stops'][j] for i, j in ret]
            routeCandidate['fares'] = [gtfsRoute['fares'][bound][i] for i, j in ret[:-1]
                                       ] if len(ret[:-1]) < len(gtfsRoute["fares"][bound]) + 1 else None
            routeCandidate['freq'] = gtfsRoute['freq'][bound]
            routeCandidate['jt'] = gtfsRoute['jt']
            routeCandidate['co'] = gtfsRoute['co']
            routeCandidate['orig_tc'] = stopList[routeCandidate['stops'][0]]['name_tc']
            routeCandidate['orig_en'] = stopList[routeCandidate['stops'][0]]['name_en']
            routeCandidate['dest_tc'] = stopList[routeCandidate['stops']
                                                 [-1]]['name_tc']
            routeCandidate['dest_en'] = stopList[routeCandidate['stops']
                                                 [-1]]['name_en']
            routeCandidate['service_type'] = "2" if 'found' in route else "1"
            routeCandidate['gtfs'] = [gtfsId]
            # mark the route has mapped to GTFS, mainly for ctb routes
            route['found'] = True
          routeCandidates.append(routeCandidate)
          if '_route' not in gtfsRoute:
            gtfsRoute['_route'] = {}
          gtfsRoute['_route'][co] = route.copy()
        elif co in gtfsRoute['co']:
          print(
              co,
              gtfsRoute['route'],
              'cannot match any in GTFS',
              file=sys.stderr)

  for route in routeList:
    if 'gtfs' not in route:
      route['co'] = [co]

  print(co,
        len([route for route in routeList if 'gtfs' not in route]),
        'out of',
        len(routeList),
        'not match')
  if co != 'mtr':
    routeList.extend(routeCandidates)
  # skipping routes that just partially mapped to GTFS
  routeList = [
      route for route in routeList if 'found' not in route or 'fares' in route]

  with open('routeFareList.%s.json' % co, 'w', encoding='UTF-8') as f:
    f.write(json.dumps(routeList, ensure_ascii=False))


matchRoutes('kmb')
matchRoutes('ctb')
matchRoutes('nlb')
matchRoutes('lrtfeeder')
matchRoutes('gmb')
matchRoutes('lightRail')
matchRoutes('mtr')
matchRoutes('sunferry')
matchRoutes('fortuneferry')
matchRoutes('hkkf')

'''
for routeId, route in gtfsRoutes.items():
  if '_route' not in route and route['co'][0] in ['ctb', 'kmb', 'nlb']:
    print(routeId + ': ' + route['route'] + " " + route['orig']['zh'] + ' - ' + route['dest']['zh'] + ' not found')
'''

routeFareList = {}


with open('routeGtfs.all.json', 'w', encoding='UTF-8') as f:
  f.write(json.dumps(gtfsRoutes, ensure_ascii=False, indent=4))
