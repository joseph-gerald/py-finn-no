import requests
import math
import uuid
import ast
from datetime import datetime, timezone
import json
from bs4 import BeautifulSoup

import concurrent.futures
from typing import List, Tuple, Dict, Any

from . import utils

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; py-finn-no/0.0.0; +https://github.com/joseph-gerald/py-finn-no)",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Scraping

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
    :param sort: The sort order. Default is "RELEVANCE". 
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

# Non scraping

class ItemInfo:
    def __init__(self, raw_data):
        self.item_type = raw_data["itemType"]
        self.item_id = raw_data["itemId"]
        self.title = raw_data["title"]
        self.image_url = raw_data["imageUrl"]
        self.status = raw_data["status"]
        self.is_owner = raw_data["isOwner"]
        self.url = raw_data["url"]
        self.vertical = raw_data["vertical"]
        self.tracking_category = raw_data["trackingCategory"]
        
class ConversationPreview:
    def __init__(self, raw_data):
        self.conversation_id = raw_data["conversationId"]
        self.item_id = raw_data["itemId"]
        self.item_type = raw_data["itemType"]
        self.last_message_attachments_count = raw_data["lastMessageAttachmentsCount"]
        self.last_message_date = datetime.fromisoformat(raw_data["lastMessageDate"])
        self.last_message_preview = raw_data["lastMessagePreview"]
        self.last_message_outgoing = raw_data["lastMessageOutgoing"]
        self.partner_id = raw_data["partnerId"]
        self.partner_name = raw_data["partnerName"]
        self.partner_profile_picture_url = raw_data["partnerProfilePictureUrl"]
        self.partner_eid_verified = raw_data["partnerEidVerified"]
        self.partner_member_since = raw_data["partnerMemberSince"]
        self.partner_rating_score = raw_data["partnerRatingScore"]
        self.partner_rating_count = raw_data["partnerRatingCount"]
        self.unseen_counter = raw_data["unseenCounter"]

class ConversationGroup:
    def __init__(self, raw_data):
        self.item = ItemInfo(raw_data["groupBasis"]["itemInfo"])
        self.total_unseen_counter = raw_data["totalUnseenCounter"]
        self.total_number_of_conversations = raw_data["totalNumberOfConversations"]
        self.last_message_preview = raw_data["lastMessagePreview"]
        self.last_message_date = datetime.fromisoformat(raw_data["lastMessageDate"])
        self.conversations = [ConversationPreview(raw) for raw in raw_data["conversations"]]

class ConversationMessage:
    def __init__(self, raw_data):
        self.id = raw_data["id"]
        self.body = raw_data["body"]
        self.type = raw_data["type"]
        self.sent = datetime.fromisoformat(raw_data["sent"])
        self.outgoing = raw_data["outgoing"]
        self.partner_read = raw_data["partnerRead"]
        self.read = raw_data["read"]
        
        self.attachments = raw_data["attachments"]
        # e.g https://www.finn.no/messages/api/conversations/users/2565874918/attachments/57a8823e-69ee-4386-3ecc-14a954e10463?width=350&height=320
        
        self.type_properties = raw_data["typeProperties"]
        self.client_message_id = raw_data["clientMessageId"]
        
        self.system_message = False
        
        if (self.type_properties is not None and len(self.type_properties) > 0):
            self.system_message = True

class InitConversation():
    def __init__(self, raw_data):
        self.conversation_id = raw_data["conversationId"]
        self.item_id = raw_data["itemId"]
        self.item_type = raw_data["itemType"]
        self.partner_id = raw_data["partnerId"]
        self.partner_name = raw_data["partnerName"]
        self.partner_profile_picture_url = raw_data["partnerProfilePictureUrl"]
        self.partner_eid_verified = raw_data["partnerEidVerified"]
        self.partner_member_since = raw_data["partnerMemberSince"]
        self.partner_rating_score = raw_data["partnerRatingScore"]
        self.partner_rating_count = raw_data["partnerRatingCount"]


class FinnSession:
    def __init__(self, __flt_cookie: str):
        self.session = requests.Session()
        self.flt = __flt_cookie
        self.session.cookies.set('__flt', self.flt)
        self.session.headers.update(headers)
        
        soup = BeautifulSoup(self.session.get("https://www.finn.no/").text, 'html.parser')
        
        meta_tag = soup.find('meta', attrs={'name': 'nmp:tracking:login-id'})
        self.login_id = meta_tag['content'] if meta_tag else None
    
    def get_account_info(self) -> dict:
        res = self.session.get('https://www.finn.no/my-page/my-account')
        
        if res.status_code != 200:
            raise Exception(f"Failed to get account info: {res.status_code}")
        
        soup = BeautifulSoup(res.text, 'html.parser')
        section = soup.find('section', {'aria-labelledby': 'account-settings-heading'})
        
        if not section:
            raise Exception("Failed to find account settings section in the page.")
        
        info_elements = section.select('.text-s.truncate')
        info_map = ["email", "password", "phone", "name", "display_name", "year_of_birth", "gender", "address", "postal_code", "postal_name", "country"]
        
        account_info = {}
        
        for elem, key in zip(info_elements, info_map):
            account_info[key] = elem.get_text(strip=True)

        return account_info

    def get_listings(self):
        # TODO: actually implement this -> https://www.finn.no/my-items/api/summary?limit=30&offset=0&facet=DRAFT
        pass
    
    def create_listing(self):
        # TODO: impl
        pass
    
    def get_conversations(self):
        res = self.session.get(f"https://www.finn.no/messages/api/conversations/users/{self.login_id}/conversationgroups?offset=0&limit=20&numberOfConversationsInGroup=10")
        
        """
        [
  {
    "groupBasis": {
      "itemInfo": {
        "itemType": "ad",
        "itemId": "413743205",
        "title": "Selvbygget gaming/virtualiserings PC",
        "imageUrl": "https://images.finncdn.no/dynamic/default/f1/f1892ada-74b0-4035-8b07-ae2e0c56df41",
        "status": {
          "type": "WARNING",
          "text": "Solgt"
        },
        "isOwner": false,
        "url": "https://www.finn.no/413743205",
        "vertical": "recommerce",
        "trackingCategory": "recommerce > recommerce-sell > Elektronikk og hvitevarer > Data"
      }
    },
    "totalUnseenCounter": 0,
    "totalNumberOfConversations": 1,
    "lastMessagePreview": "Jeg kommer ned! Leiligheten er rotete pga. flytting.",
    "lastMessageDate": "2025-06-29T15:05:04.648598",
    "conversations": [
      {
        "conversationId": "cCnIrEefFuLf6eSdQtf4tPOL-9HGnppEMQED5FJZ4TodBSl6Lv1MpKOTK0NiMvll5jVmHQq_0w2oxPL2Fe2SedwY0xlRgDT1H1CUYZVVOLo",
        "itemId": "413743205",
        "itemType": "ad",
        "lastMessageAttachmentsCount": 0,
        "lastMessageDate": "2025-06-29T15:05:04.648598",
        "lastMessagePreview": "Jeg kommer ned! Leiligheten er rotete pga. flytting.",
        "lastMessageOutgoing": false,
        "partnerId": "1098470717",
        "partnerName": "Stian Jørgensen",
        "partnerProfilePictureUrl": "https://images.finncdn.no/dynamic/default/2016/8/profilbilde/08/7/109/847/071/7_327796717.jpg",
        "partnerEidVerified": true,
        "partnerMemberSince": 2016,
        "partnerRatingScore": "10",
        "partnerRatingCount": 12,
        "unseenCounter": 0
      }
    ]
  },
  {
    "groupBasis": {
      "itemInfo": {
        "itemType": "ad",
        "itemId": "405008603",
        "title": "270 poker chips.",
        "imageUrl": "https://images.finncdn.no/dynamic/default/1d/1da3f1ef-d66b-4d47-9ca4-58942b599f7c",
        "status": {
          "type": "WARNING",
          "text": "Solgt"
        },
        "isOwner": false,
        "url": "https://www.finn.no/405008603",
        "vertical": "recommerce",
        "trackingCategory": "recommerce > recommerce-sell > Fritid, hobby og underholdning > Brettspill og bordspill"
      }
    },
    "totalUnseenCounter": 0,
    "totalNumberOfConversations": 1,
    "lastMessagePreview": "Bidra til å gjøre FINN til en bedre markedsplass ved å dele hvordan det var å kjøpe fra khj.",
    "lastMessageDate": "2025-05-21T15:08:54.080107",
    "conversations": [
      {
        "conversationId": "1gsHk51G9J9-ExbVBVxpUTaRJUFYcu3y7OeP5peAm2p9UFWmwoNtvY-i1v3CrnRRe7BHlIjDIB0l5psvXUsbv6V-Nk4G7iDL83XLp4iFJIo",
        "itemId": "405008603",
        "itemType": "ad",
        "lastMessageAttachmentsCount": 0,
        "lastMessageDate": "2025-05-21T15:08:54.080107",
        "lastMessagePreview": "Bidra til å gjøre FINN til en bedre markedsplass ved å dele hvordan det var å kjøpe fra khj.",
        "lastMessageOutgoing": false,
        "partnerId": "1830559658",
        "partnerName": "khj",
        "partnerProfilePictureUrl": null,
        "partnerEidVerified": true,
        "partnerMemberSince": 2018,
        "partnerRatingScore": "9,9",
        "partnerRatingCount": 18,
        "unseenCounter": 0
      }
    ]
  }
]
        """
        
        
        data = res.json()
        conversations = [ConversationGroup(raw) for raw in data]
        
        return conversations
    
    def get_conversation(self, conversation_id: str):
        # https://www.finn.no/messages/api/conversations/users/1565874918/conversations/1gsHk51G9J9-ExbVBVxpUTaRJUFYcu3y7OeP5peAm2p9UFWmwoNtvY-i1v3CrnRRe7BHlIjDIB0l5psvXUsbv6V-Nk4G7iDL83XLp4iFJIo/messages?order=asc&size=50
        
        res = self.session.get(f"https://www.finn.no/messages/api/conversations/users/{self.login_id}/conversations/{conversation_id}/messages?order=asc&size=50")
        
        """
        EXAMPLE 1:
        {"messageResponseList":[{"id":"60f7e3a2-2cb0-11f0-8d15-e948581fd6bd","body":"Pengene er reservert. Selgeren har 48 timer på å godkjenne. Hvis selger ikke godkjenner blir pengene tilgjengelig på din konto igjen.","type":"systemMessage","sent":"2025-05-09T08:34:10.122006","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{"sendEmail":false,"bypassUserBlocking":false,"displayName":null,"link":"https://www.finn.no/transaksjonsoversikt/kjop/transaksjon/481dcc22-5093-464e-bcc3-6cb9054d3a05?transactionId=481dcc22-5093-464e-bcc3-6cb9054d3a05","header":"Du har lagt inn en forespørsel på 75 kr","sendPushNotification":false,"text":"Pengene er reservert. Selgeren har 48 timer på å godkjenne. Hvis selger ikke godkjenner blir pengene tilgjengelig på din konto igjen.","label":"Se status","type":"TJT_NEW_BID_BUYER","subText":"","tracking":{"view":{"name":"TJT system message","object":{"name":"New bid - buyer","type":"UIElement","elementType":"System message"}},"click":{"name":"TJT system message","object":{"name":"New bid - buyer","type":"UIElement","elementType":"System message"},"target":{"id":"405008603","name":"Transaction journey torget","type":"ProcessFlow","provider":null}}}},"clientMessageId":null},{"id":"96ae5cc5-2cb4-11f0-9f7f-7fa44252603f","body":"khj sender pakken med Posten, senest 20.05.2025.","type":"systemMessage","sent":"2025-05-09T09:04:18.223308","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{"sendEmail":false,"bypassUserBlocking":false,"displayName":null,"link":"https://www.finn.no/transaksjonsoversikt/kjop/transaksjon/481dcc22-5093-464e-bcc3-6cb9054d3a05?transactionId=481dcc22-5093-464e-bcc3-6cb9054d3a05","header":"Hurra, varen er din! 🎉","sendPushNotification":false,"text":"khj sender pakken med Posten, senest 20.05.2025.","label":"Se status på kjøpet","type":"TJT_BID_ACCEPTED_BUYER","subText":"","tracking":{"view":{"name":"TJT system message","object":{"name":"Transaction accepted - buyer","type":"UIElement","elementType":"System message"}},"click":{"name":"TJT system message","object":{"name":"Transaction accepted - buyer","type":"UIElement","elementType":"System message"},"target":{"id":"405008603","name":"Transaction journey torget","type":"ProcessFlow","provider":null}}}},"clientMessageId":null},{"id":"175a78be-2cd0-11f0-a530-15bf70ca4043","body":"khj har sendt pakken med Posten.","type":"systemMessage","sent":"2025-05-09T12:21:10.511872","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{"sendEmail":false,"bypassUserBlocking":false,"displayName":null,"link":"https://sporing.posten.no/sporing/LL085822923NO","header":"Pakken er på vei!","sendPushNotification":false,"text":"khj har sendt pakken med Posten.","label":"Spor pakken din","type":"TJT_SHIPMENT_IN_TRANSIT_BUYER","subText":"","tracking":{"view":{"name":"TJT system message","object":{"name":"Shipment is in transit - buyer","type":"UIElement","elementType":"System message"}},"click":{"name":"TJT system message","object":{"name":"Shipment is in transit - buyer","type":"UIElement","elementType":"System message"},"target":{"id":"405008603","name":"Transaction journey torget","type":"ProcessFlow","provider":null}}}},"clientMessageId":null},{"id":"1bf617d0-103e-4acb-834d-0c5447555a70","body":"Du kan spore din pakke på Posten sitt nettsted ved å bruke din fraktkode: LL085822923NO.","type":"systemMessage","sent":"2025-05-20T14:00:10.120378","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{"sendEmail":false,"bypassUserBlocking":false,"displayName":null,"link":"https://www.finn.no/transaksjonsoversikt/kjop/transaksjon/481dcc22-5093-464e-bcc3-6cb9054d3a05?transactionId=481dcc22-5093-464e-bcc3-6cb9054d3a05","header":"Sending tar lenger tid enn vanlig","sendPushNotification":false,"text":"Du kan spore din pakke på Posten sitt nettsted ved å bruke din fraktkode: LL085822923NO.","label":"Vis status","type":"TJT_PACKAGE_IS_DELAYED","subText":"Hvis du allerede har mottatt pakken, kan du bekrefte det på statussiden.","tracking":{"view":{"name":"TJT system message","object":{"name":"Shipment is delayed - buyer","type":"UIElement","elementType":"System message"}},"click":{"name":"TJT system message","object":{"name":"Shipment is delayed - buyer","type":"UIElement","elementType":"System message"},"target":{"id":"405008603","name":"Transaction journey torget","type":"ProcessFlow","provider":null}}}},"clientMessageId":null},{"id":"2965ace5-7e85-4d0f-91c3-3f82136c2dec","body":"Vi håper du er fornøyd med varen du har mottatt. Hvis det er noe galt, er det viktig at du går til statussiden og melder fra om problemet innen 24 timer.","type":"systemMessage","sent":"2025-05-20T16:19:44.321593","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{"sendEmail":false,"bypassUserBlocking":false,"displayName":null,"link":"https://www.finn.no/transaksjonsoversikt/kjop/transaksjon/481dcc22-5093-464e-bcc3-6cb9054d3a05?transactionId=481dcc22-5093-464e-bcc3-6cb9054d3a05","header":"Bekreftelse på mottatt pakke","sendPushNotification":false,"text":"Vi håper du er fornøyd med varen du har mottatt. Hvis det er noe galt, er det viktig at du går til statussiden og melder fra om problemet innen 24 timer.","label":"Se status på kjøpet","type":"TJT_SHIPMENT_DELIVERED_BUYER","subText":"","tracking":{"view":{"name":"TJT system message","object":{"name":"Shipment delivered - buyer","type":"UIElement","elementType":"System message"}},"click":{"name":"TJT system message","object":{"name":"Shipment delivered - buyer","type":"UIElement","elementType":"System message"},"target":{"id":"405008603","name":"Transaction journey torget","type":"ProcessFlow","provider":null}}}},"clientMessageId":null},{"id":"7b22abfd-dc49-409e-ba87-d58187e56782","body":"Bidra til å gjøre FINN til en bedre markedsplass ved å dele hvordan det var å kjøpe fra khj.","type":"systemMessage","sent":"2025-05-21T15:08:54.080107","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{"sendEmail":false,"bypassUserBlocking":false,"displayName":"Finn.no","link":"https://finn.no/give-review?tradeId=24014504","header":"Hvordan var det å kjøpe fra khj?","sendPushNotification":true,"text":"Bidra til å gjøre FINN til en bedre markedsplass ved å dele hvordan det var å kjøpe fra khj.","label":"Gi en vurdering nå","type":"TRUST_REVIEW_SYSTEM_MESSAGE","subText":"","tracking":{"view":{"name":"Review seller","object":{"name":"Feedback opened - Recommerce - transactional with shipping","type":"UIElement","elementType":"System message"}},"click":{"name":"Review seller","object":{"name":"Feedback opened - Recommerce - transactional with shipping","type":"UIElement","elementType":"System message"},"target":{"id":"24014504","name":"GiveReview","type":"GiveReviewPage"}}}},"clientMessageId":null}],"expandedMessageData":null}

        EXAMPLE 2:
        {"messageResponseList":[{"id":"320ddc4a-af02-4365-befd-28e2f3397fa0","body":"Hey! Har den en OS installert (linux, win)?","type":"textMessage","sent":"2025-06-25T17:51:14.175548","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"e9b606a9-7ea3-49ad-ab07-fd9404add420","body":"Hei! Ja, Windows 11 er installert på NVMe-disken","type":"textMessage","sent":"2025-06-25T18:05:25.087317","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"00294A45-BFAF-4960-AD4A-85A3A32C9937"},{"id":"da335655-79ad-4889-a61d-9d2d87ccb5d2","body":"Perfect, kan vi gjøre 2000?","type":"textMessage","sent":"2025-06-25T19:12:40.06215","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"03393bc4-c636-44bd-9e04-aaba833ab9a0","body":"2500? Jeg har allerede redusert prisen med 1500, så jeg vil egentlig ikke gå noe lavere enn det.","type":"textMessage","sent":"2025-06-25T20:08:44.576828","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"5396F9D1-933E-44C4-BBA8-8633A3DD2387"},{"id":"49a871f1-35e8-4386-9325-e124bc42b18a","body":"2500 høres bra ut. Kan jeg hente den på søndag (8-9 PM)?","type":"textMessage","sent":"2025-06-26T09:53:45.592175","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"24e381c8-6a88-494a-b07c-825cf9a5b32c","body":"Ja, søndag passer bra! Da rekker jeg også å wipe diskene og nullstille Windows","type":"textMessage","sent":"2025-06-26T09:58:44.12894","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"3BD0AE7E-F01E-44F5-BB52-FB1C8FD10A96"},{"id":"bfa15f77-e2c3-4947-b0f1-d1a0e1dcbceb","body":"Hey, jeg kommer litt tidligere (5-7 PM) og hvor i Rælingen skal vi møtes?","type":"textMessage","sent":"2025-06-29T11:48:49.578001","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"50355a9b-2d6b-4014-8ae0-8da04cb94ebe","body":"Hey, det er helt i orden! Jeg bor i Tristilvegen 25, 2008 Fjerdingby , den kan plukkes opp her \uD83D\uDE42","type":"textMessage","sent":"2025-06-29T11:56:13.25636","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"DAFE5371-270F-4E12-8EDA-EE059841BB21"},{"id":"6a50e495-6f3f-45a8-bf7b-e9e020c2f478","body":"Perfect! Da ses vi","type":"textMessage","sent":"2025-06-29T12:06:03.752404","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"a01cb69f-cfcf-4e70-b97c-7433077f40a9","body":"Herlig! For å komme til hovedinngangen må man kjøre rundt blokkene, på gangveien","type":"textMessage","sent":"2025-06-29T12:10:48.098938","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"9724CA24-F427-4DEE-A7B8-E59F08AB7D70"},{"id":"fbc2adc4-2579-4fbe-8e61-1c217c0be484","body":"","type":"textMessage","sent":"2025-06-29T12:10:57.241246","partnerRead":true,"read":true,"outgoing":false,"attachments":[{"objectId":"57a8823e-69ee-4386-aecc-14a954e10463","contentType":"image/jpeg","name":null}],"typeProperties":{},"clientMessageId":"1F3D95D8-E8F2-4968-8C25-7D220F5AF8AE"},{"id":"0aab1956-b36b-4931-851a-79aa44865517","body":"\uD83D\uDC4D","type":"textMessage","sent":"2025-06-29T14:30:01.252932","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"7d9a7ce8-1bd0-489d-86de-575a73aa0271","body":"Hey, hvilket bygg er det?","type":"textMessage","sent":"2025-06-29T15:03:01.010055","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"9396de96-f863-45b0-b590-f65e35884e3a","body":"Det er det først bygget på bildet her, det står 25 på inngangsdøra når du kjører rundt. Er du fremme nå?","type":"textMessage","sent":"2025-06-29T15:04:18.653322","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"7EE8597B-3E4E-49C0-A646-692D242B1A9E"},{"id":"6eda3372-bec1-4fb5-aa81-3eab3b096fb8","body":"Ja er utenfor","type":"textMessage","sent":"2025-06-29T15:04:39.59987","partnerRead":true,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":null},{"id":"4ed7d0d1-91c6-4299-bc59-a2dc6cabaed6","body":"Jeg kommer ned! Leiligheten er rotete pga. flytting.","type":"textMessage","sent":"2025-06-29T15:05:04.648598","partnerRead":true,"read":true,"outgoing":false,"attachments":[],"typeProperties":{},"clientMessageId":"DD5BE7DA-2F11-4419-80CA-3630A1C7894A"}],"expandedMessageData":null}
        """
        
        if res.status_code != 200:
            raise Exception(f"Failed to get conversation {conversation_id}: {res.status_code}")
        
        messages = res.json().get("messageResponseList", [])
        conversation_messages = [ConversationMessage(raw) for raw in messages]
        
        return conversation_messages
    
    def init_conversation(self, advert_id: str, message: str, advert_type: str = "ad"):
        res = self.session.post(f"https://www.finn.no/messages/api/conversations/users/{self.login_id}/conversations", json={
            "item": {
                "id": advert_id,
                "type": advert_type
            },
            "message": {
                "body": message,
                "messageType": "textMessage",
                "attachments": [],
                "clientMessageId": str(uuid.uuid4())
            }
        })
        
        # {"id":"w8ZPiZ-4icmeMqxPvmuFNlsicTbcN7CcR-olQlzF--lYhuSKve1AURNpRPcCPLVEyYL1UJTEa215aPFuekuXaWthc6Dtzeq8-ATo81qcL2g","item":{"id":"427606901","type":"ad"},"ownerId":"731326576","partner":{"id":"1565874918","name":"Joseph T","profilePictureUrl":"https://images.finncdn.no/dynamic/default/avatar-1736695815432-2d3c7c60-773f-4df3-9253-483bb992e721","eidVerified":true},"messages":[{"id":"a44c453b-4aa7-42c6-9cc4-3cc1135740f3","body":"test","type":"textMessage","sent":"2025-11-26T17:18:23.167147086","partnerRead":false,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":"64dfdd1f-5add-4573-81d4-9fd3da6dc9e0"}]}
        
        if res.status_code != 200:
            raise Exception(f"Failed to init conversation for advert {advert_id}: {res.status_code}")
        
        return InitConversation(res.json())

    def send_message(self, conversation_id: str, message: str):
        """
        {
  "clientMessageId": "1ef2e707-0a2f-4174-a4c4-3be894521a7c",
  "body": "test",
  "messageType": "textMessage",
  "sent": "2025-11-26T17:24:31.921",
  "attachments": []
}
        """
        
        res = self.session.post(f"https://www.finn.no/messages/api/conversations/users/{self.login_id}/conversations/{conversation_id}/messages", json={
            "clientMessageId": str(uuid.uuid4()),
            "body": message,
            "messageType": "textMessage",
            "sent": datetime.now(timezone.utc).isoformat(),
            "attachments": []
        })

        
        # {"id":"d3f3e1b4-1c8e-4f3e-9f4a-5e2b6c3d9f7e","body":"Hello again!","type":"textMessage","sent":"2025-11-26T17:20:45.123456789","partnerRead":false,"read":true,"outgoing":true,"attachments":[],"typeProperties":{},"clientMessageId":"123e4567-e89b-12d3-a456-426614174000"}

        if res.status_code != 200:
            raise Exception(f"Failed to send message to conversation {conversation_id}: {res.status_code}")
