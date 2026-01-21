from finn import search_marketplace, SortOrder

results = search_marketplace("SSD", filters={
    "price_from": 0,
    "price_to": 2000
})

print()
print("First 5 results sorted by distance from 59°N, 9°E for 'SSD':")
print()

for result in results[:5]:
    print(f"Title: {result.title}")
    print(f"Location: {result.location}")
    print(f"Price: {result.price} {result.currency_code}")
    print("-" * 50)
