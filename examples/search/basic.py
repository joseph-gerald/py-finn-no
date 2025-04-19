from finn import search_marketplace, SortOrder

results = search_marketplace("SSD")

print()
print("First 5 results sorted by relevance for 'SSD':")
print()

for result in results[:5]:
    print(f"Title: {result.title}")
    print(f"Location: {result.location}")
    print(f"Price: {result.price} {result.currency_code}")
    print("-" * 50)
