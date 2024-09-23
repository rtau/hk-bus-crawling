# -*- coding: utf-8 -*-
# Check route latest update time

import asyncio
import logging
import httpx
import json
import os
import time
import xxhash
import re

from crawl_utils import emitRequest

async def routeCompare():
  a_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, pool=None))
  r = await emitRequest("https://data.hkbus.app/routeFareList.min.json", a_client)
  r.encoding = 'utf-8'
  oldDb = r.json()
  newDb = json.load(open('routeFareList.min.json', 'r', encoding='UTF-8'))

  os.makedirs("route-ts", exist_ok=True)

  def isRouteEqual(a, b):
    return xxhash.xxh3_64(str(a)).hexdigest() == xxhash.xxh3_64(str(b)).hexdigest()

  for newKey in newDb['routeList']:
    if newKey not in oldDb['routeList'] or not isRouteEqual(oldDb['routeList'][newKey], newDb['routeList'][newKey]):
      filename = re.sub(r'[\\\/\:\*\?\"\<\>\|]', '', newKey).upper()
      with open(os.path.join("route-ts", filename), "w", encoding='utf-8') as f:
        f.write(str(int(time.time())))

  for oldKey in oldDb['routeList']:
    if oldKey not in newDb['routeList']:
      filename = re.sub(r'[\\\/\:\*\?\"\<\>\|]', '', oldKey).upper()
      with open(os.path.join("route-ts", filename), "w", encoding='utf-8') as f:
        f.write(str(int(time.time())))

if __name__=='__main__':
  logging.basicConfig(level=logging.INFO)
  logging.getLogger('httpx').setLevel(logging.WARNING)
  logger = logging.getLogger(__name__)
  asyncio.run(routeCompare())