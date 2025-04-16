import requests
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

def search_marketplace(query: str = None, sort: str = "PUBLISHED_DESC", filters: dict = {}, page: int = None) -> dict:
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
        params["query"] = query

    if page is not None:
        params["page"] = page

    for key, value in filters.items():
        params[key] = value

    res = requests.get(f"https://www.finn.no/recommerce-search-page/api/search/SEARCH_ID_BAP_COMMON", headers=headers, params=params)

    if res.status_code != 200:
        raise Exception(f"Failed to search marketplace: {res.status_code}")

    data = res.json()
    adverts = []

    for advert in data["docs"]:
        adverts.append(AdvertSearchResult(advert))

    return adverts
