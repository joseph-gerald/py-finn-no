from finn import scrape_query
import time

start_time = time.time()
adverts = scrape_query("PC")

print("Found %d adverts" % len(adverts))
print("--- %s seconds ---" % (time.time() - start_time))
print("Wrote all advert ids to 'adverts.txt'")

with open("adverts.txt", "w") as f:
    for advert in adverts:
        f.write(advert.id + "\n")