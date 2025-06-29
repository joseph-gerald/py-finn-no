import requests
import math
import ast
from datetime import datetime
import json
from bs4 import BeautifulSoup

from . import utils

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; py-finn-no/0.0.0; +https://github.com/joseph-gerald/py-finn-no)",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

class SortOrder:
    RELEVANCE = "RELEVANCE"
    OLDEST = "PUBLISHED_ASC"
    LATEST = "PUBLISHED_DESC"

    CLOSEST = "CLOSEST"

    PRICE_ASC = "PRICE_ASC"
    PRICE_DESC = "PRICE_DESC"

class FinnLocation:
    def __init__(self, raw_data):
        self.postal_code = raw_data["postalCode"]
        self.postal_name = raw_data["postalName"]
        self.country_code = raw_data["countryCode"]
        self.country_name = raw_data["countryName"]

        position = raw_data["position"]
        
        self.latitude = position["lat"]
        self.longitude = position["lng"]
        self.accuracy = position["accuracy"]
        self.map_image_url = position["mapImage"]

    def __str__(self):
        return f"{self.postal_code}, {self.postal_name} ({self.latitude}, {self.longitude})"

class FinnAdvert:
    def __init__(self, raw_data):
        if "loaderData" not in raw_data:
            raise ValueError("Invalid data format: 'loaderData' key not found in raw_data")
        
        if "item-recommerce" not in raw_data["loaderData"]:
            if "item-bap" in raw_data["loaderData"]:
                raise utils.BAPItemError("This advert is a BAP item, not a ReCommerce item.")
        
        self.raw_data = raw_data
        
        data = raw_data["loaderData"]["item-recommerce"]

        # Item Data

        item_data = data["itemData"]

        self.title = item_data["title"]

        if "price" in item_data:
            self.price = item_data["price"]

        self.disposed = item_data["disposed"]
        self.type = item_data["adViewTypeLabel"] # e.g "Til Salgs"
        self.description = item_data["description"]
        self.is_webstore = item_data["isWebstore"]

        self.location = FinnLocation(item_data["location"])

        # Extras

        self.extras = item_data["extras"]

        # Metadata

        metadata = item_data["meta"]
        
        self.id = metadata["adId"]
        
        if "ownerId" in metadata:
            self.owner_id = metadata["ownerId"]
        else:
            self.owner_id = None
        
        self.userOwner = metadata["userOwner"]
        self.hasBeenPublished = metadata["hasBeenPublished"]
        self.last_edited = datetime.fromisoformat(metadata["edited"])
        self.schema_name = metadata["schemaName"]
        self.is_inactive = metadata["isInactive"]
        self.is_legacy_schema = metadata["isLegacySchema"]
        self.is_own_ad = metadata["isOwnAd"]
        self.should_index = metadata["shouldIndex"]

        # SEO Metadata

        metadata = data["meta"]

        self.seo_title = metadata["title"]
        self.seo_description = metadata["description"]
        self.url = metadata["canonical"]

        # Category

        category = item_data["category"]

        self.category_id = category["id"]
        self.category_name = category["value"]
        self.category_path = [[self.category_id, self.category_name]]

        while "parent" in category:
            category = category["parent"]
            self.category_path.append([category["id"], category["value"]])

        self.category_path.reverse()
        
        self.images = item_data["images"]
        self.image_urls = [image["uri"] for image in self.images]

        # Transaction Data

        transaction_data = data["transactableData"]

        # self.transactable = transaction_data["transactable"] # 99% sure this dosen't do anything
        self.seller_pays_shipping = transaction_data["sellerPaysShipping"]
        self.buy_now = transaction_data["buyNow"]

class AdvertSearchResult:
    def __init__(self, raw_data):
        self.id = raw_data["id"]
        self.title = raw_data["heading"]
        self.location = raw_data["location"]
        self.url = raw_data["canonical_url"]

        if "image" in raw_data:
            self.image = raw_data["image"]
            self.image_url = raw_data["image"]["url"]
        else:
            self.image = None
            self.image_url = None

        self.flags = raw_data["flags"]
        self.labels = raw_data["labels"]
        self.timestamp = datetime.fromtimestamp(raw_data["timestamp"] / 1000)
        self.coordinates = raw_data["coordinates"]

        self.price = raw_data["price"]["amount"]
        self.currency_code = raw_data["price"]["currency_code"]
        self.trade_type = raw_data["trade_type"]

    def __str__(self):
        return f"{self.title} ({self.price} {self.currency_code}) - {self.location} ({self.timestamp})"
    
    def __repr__(self):
        return f"AdvertSearchResult({self.id})"

class QueryMetadata:
    def __init__(self, raw_data):
        self.current_page = raw_data["current_page"]
        self.last_page = raw_data["last_page"]
        self.end_of_paging = raw_data["end_of_paging"]
        self.total_query_hits = raw_data["total_query_hits"]

    def __str__(self):
        return f"Page {self.current_page} of {self.last_page} - {self.total_query_hits} results"
    
    def __repr__(self):
        return f"QueryMetadata({self.current_page}, {self.last_page}, {self.total_query_hits})"

def get_advert(ad_id: int | str) -> FinnAdvert | None:
    """
    Get an advert by its ID.
    :param ad_id: The ID of the advert.
    :return: A FinnAdvert object.
    """
    res = requests.get(f"https://www.finn.no/recommerce/forsale/item/{str(ad_id)}", headers=headers)
    
    if res.status_code == 404:
        return None

    if res.status_code != 200:
        raise Exception(f"Failed to get advert with ID {ad_id}: {res.status_code}")

    soup = BeautifulSoup(res.text, 'html.parser')
    script_tags = soup.find_all('script')

    for script in script_tags:
        if not script.string or "window.__staticRouterHydrationData" not in script.string:
            continue

        script: str = script.string

        start_idx = script.find('JSON.parse(')
        if start_idx == -1:
            continue

        end_idx = script.find(');', start_idx)

        script = script[start_idx + len('JSON.parse('):end_idx]
        script = ast.literal_eval(script)
        
        data = json.loads(script)
        
        return FinnAdvert(data)

def search_marketplace(query: str = None, sort: str = SortOrder.RELEVANCE, filters: dict = {}, page: int = None, return_metadata=False, attempt=0) -> list[AdvertSearchResult] | tuple[list[AdvertSearchResult], QueryMetadata]:
    """
    Search the marketplace for a given query.

    :param query: The search query.
    :param sort: The sort order. Default is "PUBLISHED_DESC". 
    :param filters: A dictionary of filters to apply to the search.
    :param page: The page number to retrieve. Default is 1.
    :return: A dictionary containing the search results.
    """

    params = {
        "sort": sort,
    }

    if query is not None:
        params["q"] = query

    if page is not None:
        params["page"] = page

    for key, value in filters.items():
        params[key] = value

    try:
        res = requests.get(f"https://www.finn.no/recommerce-search-page/api/search/SEARCH_ID_BAP_COMMON", headers=headers, params=params)
    except requests.RequestException as e:
        if attempt < 3:
            print(f"Request failed: {e}. Retrying... (Attempt {attempt + 1})")
            return search_marketplace(query, sort, filters, page, return_metadata, attempt + 1)
        else:
            raise Exception(f"Failed to search marketplace after 3 attempts: {e}")

    if res.status_code != 200:
        raise Exception(f"Failed to search marketplace: {res.status_code}")

    data = res.json()
    adverts = []
    
    metadata = data["metadata"]
    paging = metadata["paging"]

    current_page, last_page = int(paging["current"]), int(paging["last"])
    end_of_paging = metadata["is_end_of_paging"]
    total_query_hits = metadata["tracking"]["object"]["numItems"]

    for advert in data["docs"]:
        adverts.append(AdvertSearchResult(advert))

    if return_metadata:
        return adverts, QueryMetadata({
            "current_page": current_page,
            "last_page": last_page,
            "end_of_paging": end_of_paging,
            "total_query_hits": total_query_hits
        })
    
    return adverts






import concurrent.futures
from typing import List, Tuple, Dict, Any

def scrape_query(query: str, base_filters: dict = {}, sort: str = "RELEVANCE", max_workers: int = 8) -> list:
    """
    Scrape the entire marketplace for a given query using price range partitioning with parallelization.
    
    :param query: The search query.
    :param base_filters: A dictionary of filters to apply to the search.
    :param sort: The sort order. Default is "RELEVANCE".
    :param max_workers: Maximum number of parallel workers. Default is 8.
    :return: A list of AdvertSearchResult objects.
    """
    MAX_PER_QUERY = 2500
    
    filter_copy = base_filters.copy()
    filter_copy["price_to"] = min(base_filters.get("price_to", 1_000_000_000), 1_000_000_000)
    _, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
    target_hits = metadata.total_query_hits
    
    if target_hits <= MAX_PER_QUERY:
        adverts, _ = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
        return adverts
    
    min_price = base_filters.get("price_from", 0)
    max_price = base_filters.get("price_to", 1_000_000_000)
    
    # First, determine all the price ranges we need to search
    price_ranges = partition_price_ranges(query, base_filters, sort, min_price, max_price, MAX_PER_QUERY, target_hits, max_workers=max_workers)
    
    # Then, parallelize the searches for each price range
    all_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_range = {
            executor.submit(
                search_price_range, 
                query, 
                base_filters.copy(), 
                sort, 
                price_from, 
                price_to, 
                i, 
                len(price_ranges)
            ): (i, price_from, price_to) 
            for i, (price_from, price_to) in enumerate(price_ranges, 1)
        }
        
        for future in concurrent.futures.as_completed(future_to_range):
            range_idx, price_from, price_to = future_to_range[future]
            try:
                results = future.result()
                all_results.extend(results)
                print(f"Completed range {range_idx}/{len(price_ranges)}: {price_from} - {price_to}, found {len(results)} results")
            except Exception as exc:
                print(f"Search for range {range_idx} generated an exception: {exc}")
    
    return all_results

def search_price_range(query, base_filters, sort, price_from, price_to, range_idx, total_ranges):
    """Helper function to search a specific price range for parallelization."""
    filter_copy = base_filters.copy()
    filter_copy["price_from"] = price_from
    filter_copy["price_to"] = price_to
    print(f"Searching range {range_idx}/{total_ranges}: {price_from} - {price_to}")
    
    adverts, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
    
    if metadata.total_query_hits == 0:
        return []
    
    total_hits = metadata.total_query_hits
    adverts = []
    page = 1
    
    total_pages = metadata.last_page

    page_args = []
    for p in range(1, total_pages + 1):
        arg = filter_copy.copy()
        arg["page"] = p
        page_args.append(arg)

    def fetch_page(args):
        results, _ = search_marketplace(query, filters=args, sort=sort, return_metadata=True)
        return results

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_page = {executor.submit(fetch_page, args): args["page"] for args in page_args}
        for future in concurrent.futures.as_completed(future_to_page):
            try:
                results = future.result()
                adverts.extend(results)
            except Exception as exc:
                print(f"Exception fetching page {future_to_page[future]}: {exc}")
    
    return adverts

def partition_price_ranges(query, base_filters, sort, min_price, max_price, max_per_query, target_hits, max_workers=4):
    """
    Efficiently partition the price range to ensure each partition returns less than max_per_query results.
    
    Uses a parallel approach to identify multiple price boundaries simultaneously.
    
    :param max_workers: Maximum number of parallel workers for boundary finding. Default is 4.
    """
    ranges = []
    current_min = min_price
    total_hits = 0
    
    # We'll use a two-phase approach:
    # 1. First, get a rough estimate of ranges by dividing the price space
    # 2. Then refine these ranges in parallel
    
    # Phase 1: Create initial rough partitions
    # Estimate the number of partitions needed
    estimated_partitions = (target_hits + max_per_query - 1) // max_per_query
    
    # Create rough price points as starting estimates
    if estimated_partitions <= 1:
        price_points = [max_price]
    else:
        # Create evenly spaced price points as initial guesses
        price_range = max_price - min_price
        price_points = [
            min_price + (price_range * i // estimated_partitions)
            for i in range(1, estimated_partitions + 1)
        ]
        # Ensure the last point is exactly max_price
        price_points[-1] = max_price
    
    # Phase 2: Refine all partitions in parallel
    # Create tuples of (current_min, next_guess_max, target_results) for each partition
    boundary_search_params = []
    partition_target = max_per_query
    
    boundary_min = min_price
    for i, boundary_max_guess in enumerate(price_points):
        # For the last partition, adjust target to remaining hits
        if i == len(price_points) - 1:
            remaining = target_hits - total_hits
            if remaining <= 0:
                break
            partition_target = min(max_per_query, remaining)
            
        boundary_search_params.append((boundary_min, boundary_max_guess, partition_target))
        boundary_min = boundary_max_guess + 1
    
    print(f"Starting parallel boundary search for {len(boundary_search_params)} initial partitions")
    boundaries = parallel_find_price_boundaries(
        query, base_filters, sort, boundary_search_params, max_workers
    )
    
    # Phase 3: Process the boundaries and build the final ranges
    current_min = min_price
    for i, boundary in enumerate(boundaries):
        if boundary is None:
            continue
            
        if current_min > boundary:
            continue
            
        filter_copy = base_filters.copy()
        filter_copy["price_from"] = current_min
        filter_copy["price_to"] = boundary
        
        _, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
        range_hits = metadata.total_query_hits
        
        if range_hits > 0:  # Only add ranges that have results
            ranges.append((current_min, boundary))
            total_hits += range_hits
            
        current_min = boundary + 1
        
        if current_min > max_price or total_hits >= target_hits:
            break
    
    # Check if we need to add one more range to cover any remaining gap
    if current_min <= max_price and total_hits < target_hits:
        filter_copy = base_filters.copy()
        filter_copy["price_from"] = current_min
        filter_copy["price_to"] = max_price
        
        adverts, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
        range_hits = metadata.total_query_hits
        
        if range_hits > 0:
            ranges.append((current_min, max_price))
            total_hits += range_hits
    
    print(f"Partitioning complete: Found {len(ranges)} price ranges covering {total_hits} results")
    return ranges

def find_next_price_boundary(query, base_filters, sort, min_price, max_price, target_results):
    """
    Find the highest price that keeps results under target_results.
    Uses adaptive search to quickly find a reasonable boundary.
    
    :param target_results: The maximum number of results we want in this price range
    """
    # Special case: if min_price and max_price are close, just use max_price
    if max_price - min_price < 1000:
        filter_copy = base_filters.copy()
        filter_copy["price_from"] = min_price
        filter_copy["price_to"] = max_price
        
        _, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
        result_count = metadata.total_query_hits
        
        if result_count <= target_results:
            return max_price
    
    # Try binary search with optimized initial bounds
    # This avoids the exponential search phase which can be slow
    
    # Start with an intelligent guess about the price range
    # If we know target_results, we can estimate the price range proportionally
    price_range = max_price - min_price
    
    # Initial binary search bounds
    low = min_price
    high = max_price
    
    # Pre-check the max price to see if the whole range satisfies target
    filter_copy = base_filters.copy()
    filter_copy["price_from"] = min_price
    filter_copy["price_to"] = max_price
    
    _, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
    total_results = metadata.total_query_hits
    
    if total_results <= target_results:
        return max_price
    
    # If we have a rough idea of total results, we can estimate a better initial guess
    # for where the boundary might be
    if total_results > 0:
        # Estimate initial point proportionally 
        initial_guess = min_price + int(price_range * (target_results / total_results))
        # Clamp the guess to ensure it's within bounds
        initial_guess = max(min_price, min(max_price, initial_guess))
        
        # Check this initial guess
        filter_copy = base_filters.copy()
        filter_copy["price_from"] = min_price
        filter_copy["price_to"] = initial_guess
        
        _, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
        result_count = metadata.total_query_hits
        
        if result_count == target_results:
            return initial_guess
            
        if result_count < target_results:
            # We need to search higher
            low = initial_guess + 1
        else:
            # We need to search lower
            high = initial_guess - 1
    
    # Now perform binary search with our refined bounds
    binary_steps = 0
    last_good_price = None
    last_good_count = 0
    
    max_binary_steps = 20  # Limit binary search steps to avoid too many API calls
    
    while low <= high and binary_steps < max_binary_steps:
        binary_steps += 1
        mid = (low + high) // 2
        
        filter_copy = base_filters.copy()
        filter_copy["price_from"] = min_price
        filter_copy["price_to"] = mid
        
        _, metadata = search_marketplace(query, filters=filter_copy, sort=sort, return_metadata=True)
        result_count = metadata.total_query_hits
        
        if result_count == target_results:
            return mid
        
        if result_count < target_results:
            last_good_price = mid
            last_good_count = result_count
            low = mid + 1
        else:
            high = mid - 1
    
    # Return the best result we found
    if last_good_price is not None:
        return last_good_price
    elif high >= min_price:
        return high
    else:
        # If all else fails, return a reasonable default
        return min_price + (max_price - min_price) // 2

def parallel_find_price_boundaries(query, base_filters, sort, price_ranges, max_workers=4):
    """
    Parallelize the process of finding price boundaries for multiple ranges.
    
    :param price_ranges: List of (min_price, max_price, target_results) tuples
    :param max_workers: Maximum number of parallel workers
    :return: List of found price boundaries in the same order as input
    """
    # Create a map to preserve the original order
    range_to_index = {params: i for i, params in enumerate(price_ranges)}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_params = {
            executor.submit(
                find_next_price_boundary, 
                query, 
                base_filters.copy(), 
                sort, 
                min_price, 
                max_price, 
                target_results
            ): (min_price, max_price, target_results)
            for min_price, max_price, target_results in price_ranges
        }
        
        # Initialize results array with None for each input range
        boundaries = [None] * len(price_ranges)
        
        # Process futures as they complete
        for i, future in enumerate(concurrent.futures.as_completed(future_to_params)):
            params = future_to_params[future]
            original_idx = range_to_index[params]
            try:
                boundary = future.result()
                boundaries[original_idx] = boundary
                print(f"Boundary found ({i+1}/{len(price_ranges)}): min={params[0]}, boundary={boundary}, target={params[2]}")
            except Exception as exc:
                print(f"Price boundary search generated an exception: {exc}")
                boundaries[original_idx] = None
                
    return boundaries