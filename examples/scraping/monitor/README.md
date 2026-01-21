# Monitor
Simple monitoring script that logs new adverts (title & id) in the marketplace

```py
import logging
import finn
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

logger = logging.getLogger(__name__)

ids_seen = set()

start = time.time()
refreshes_per_log = 50

for index in range(1_000_000):
    adverts = finn.search_marketplace("")

    if (index % refreshes_per_log == refreshes_per_log - 1):
        end = time.time()
        logging.info(f"Search took {end - start:.2f} seconds for {refreshes_per_log} refreshes.")
        start = time.time()

    for advert in reversed(adverts):
        if advert.id in ids_seen:
            continue

        ids_seen.add(advert.id)

        if index == 0:
            continue

        logging.info(f"Advert with ID {advert.title} [{advert.id}] found.")
        
    if index == 0:
        logging.info("Started listening for new adverts.")
```

### Pictures
![image](https://github.com/user-attachments/assets/8503f43c-6b42-4922-aae1-5e18581f3543)

![image](https://github.com/user-attachments/assets/3a4b6530-8a46-4df8-910a-443be98aa03a)
