import finn
import json
from concurrent.futures import ThreadPoolExecutor
import threading

lock = threading.Lock()

with open("adverts.txt", "r") as f:
    advert_ids = [line.strip() for line in f.readlines()]

print("Found %d advert ids" % len(advert_ids))

def process_advert(advert_id):
    print(f"Fetching advert {advert_id}... ", end="")
    try:
        advert = finn.get_advert(advert_id)
        
        with lock:
            with open("processed_adverts.txt", "a") as f:
                f.write(advert_id + "\n")
            with open("data.txt", "a") as f:
                f.write(json.dumps(advert.raw_data) + "\n")
        
    except finn.BAPItemError:
        # not a marketplace advert
        pass

with ThreadPoolExecutor(max_workers=50) as executor:
    executor.map(process_advert, advert_ids)