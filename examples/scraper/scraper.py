from finn import scrape_query
import time

start_time = time.time()
scrape_query("SSD")
print()
print("--- %s seconds ---" % (time.time() - start_time))