from finn import search_marketplace, SortOrder

results = search_marketplace("SSD", sort=SortOrder.CLOSEST, filters={
    "lat": 59.75,
    "lon": 9.75,
    "radius": 10_000 # 10,000m
})

print()
print("First 5 results within 10km from 59°N, 9°E for 'SSD':")
print()

for result in results[:5]:
    print(f"Title: {result.title}")
    print(f"Location: {result.location}")
    print(f"Price: {result.price} {result.currency_code}")
    print("-" * 50)
