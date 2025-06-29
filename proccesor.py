import json
import finn

count = 0

with open("data.txt", "r") as f:
    data = [json.loads(line.strip()) for line in f.readlines()]

for item in data:
    advert = finn.FinnAdvert(item)
    
    filters = ["32", "GB", "RTX"]
    
    if not all(filter in advert.description for filter in filters):
        continue
    
    print()
    print(f"ID: {advert.id}")
    print(f"Title: {advert.title}")
    print(f"Price: {advert.price}")
    
    count += 1
    
print(f"Found {count} adverts with '32 GB' in the description.")