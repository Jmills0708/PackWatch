"""
PackWatch affiliate link wrapper
---------------------------------
Turns a raw retailer URL into a tagged affiliate link, so every click on the
dashboard has a chance to earn commission. Drop your real IDs into
AFFILIATE_CONFIG once you're approved for each program (see
AFFILIATE_SETUP.md for how to get them).

Design: each retailer maps to a wrapping function. Unknown retailers pass
through untouched — better to show an unaffiliated link than a broken one.
"""

import os
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

# Fill these in once you're approved. Can also be set via environment
# variables of the same name, which is safer for a deployed app (no
# credentials committed to the repo).
AFFILIATE_CONFIG = {
    "amazon_tag": os.environ.get("AMAZON_ASSOCIATE_TAG", ""),        # e.g. "packwatch-20"
    "ebay_campid": os.environ.get("EBAY_CAMPAIGN_ID", ""),           # e.g. "5338xxxxxx"
    "tcgplayer_campaign_id": os.environ.get("TCGPLAYER_CAMPAIGN_ID", ""),  # from Impact
    # Manual deals with individual small shops: {"retailer name": "url_param_string"}
    "manual": {
        # "Gamers Guild AZ": "ref=packwatch",
    },
}


def _add_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query))
    query[key] = value
    new_query = urlencode(query)
    return urlunparse(parts._replace(query=new_query))


def wrap_amazon(url: str) -> str:
    tag = AFFILIATE_CONFIG["amazon_tag"]
    if not tag:
        return url
    return _add_query_param(url, "tag", tag)


def wrap_ebay(url: str) -> str:
    campid = AFFILIATE_CONFIG["ebay_campid"]
    if not campid:
        return url
    return _add_query_param(url, "campid", campid)


def wrap_tcgplayer(url: str) -> str:
    campaign_id = AFFILIATE_CONFIG["tcgplayer_campaign_id"]
    if not campaign_id:
        return url
    # Impact-style redirect wrapping. Confirm the exact link format against
    # your approved Impact/TCGPlayer dashboard — this format changes
    # depending on how the program is configured for your account.
    return f"https://tcgplayer.pxf.io/c/{campaign_id}/click?u={url}"


def wrap_manual(url: str, retailer: str) -> str:
    param_string = AFFILIATE_CONFIG["manual"].get(retailer)
    if not param_string:
        return url
    key, _, value = param_string.partition("=")
    return _add_query_param(url, key, value)


RETAILER_DOMAIN_MAP = {
    "amazon.com": wrap_amazon,
    "www.amazon.com": wrap_amazon,
    "ebay.com": wrap_ebay,
    "www.ebay.com": wrap_ebay,
    "tcgplayer.com": wrap_tcgplayer,
    "www.tcgplayer.com": wrap_tcgplayer,
}


def affiliate_link(url: str, retailer: str = "") -> str:
    """
    Main entry point: pass a raw product URL (and optionally the retailer
    name as scraped) and get back the affiliate-tagged version, or the
    original URL untouched if there's no program configured for that
    retailer yet.
    """
    if not url:
        return url

    # Manual per-store deals take priority if configured.
    if retailer in AFFILIATE_CONFIG["manual"]:
        return wrap_manual(url, retailer)

    domain = urlparse(url).netloc.lower()
    wrapper = RETAILER_DOMAIN_MAP.get(domain)
    if wrapper:
        return wrapper(url)

    return url  # unaffiliated retailer — pass through as-is


if __name__ == "__main__":
    # Quick self-test with sample URLs
    tests = [
        ("https://www.amazon.com/dp/B0EXAMPLE", "Amazon"),
        ("https://www.ebay.com/itm/123456", "eBay"),
        ("https://www.tcgplayer.com/product/123", "TCGPlayer"),
        ("https://gamersguildaz.com/products/op17-box", "Gamers Guild AZ"),
    ]
    for url, retailer in tests:
        print(f"{retailer:15s} -> {affiliate_link(url, retailer)}")
