#!/usr/bin/env python3
"""
Fashion listing scraper -> one normalized CSV/JSON.

Pulls EVERY product from each brand and sorts it into a category
automatically (see CATEGORY RULES below), so the website can filter by category.

Sites supported:
  - Shopify stores (Jaipur Handblock, Label Kanupriya): the public
    /products.json feed (all sizes, prices, stock, images).
  - Zlaata (custom site): parses its server-rendered "all products" pages.

Usage:
  pip install requests beautifulsoup4
  python scraper.py                 # scrape everything -> docs/products.json (site) + data/ (record)
  python scraper.py --renormalise   # re-apply category + colour rules, no scraping

Polite by default: checks robots.txt, 1.5s delay between requests,
identifies itself with a plain User-Agent.
"""
import argparse
import gzip
import html
import os
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; FashionAggregatorBot/0.1)"
DELAY_SEC = 1.5
TIMEOUT = 30

# ---------------------------------------------------------------------------
# BRANDS: one entry per brand. Add any Shopify brand with one line:
#   {"source": "Brand Name", "type": "shopify", "base": "https://brand.com"},
# ---------------------------------------------------------------------------
SOURCES = [
    {"source": "Jaipur Handblock", "type": "shopify", "base": "https://jaipurhandblock.in"},
    {"source": "Label Kanupriya", "type": "shopify", "base": "https://www.labelkanupriya.com"},
    {"source": "Ridhi Mehra", "type": "shopify", "base": "https://ridhimehra.com"},
    {"source": "Libas", "type": "shopify", "base": "https://www.libas.in"},
    {"source": "Aachho", "type": "shopify", "base": "https://www.aachho.com"},
    {"source": "House of Niav", "type": "shopify", "base": "https://houseofniav.com"},
    {"source": "Alaya by Stage3", "type": "shopify", "base": "https://alayabystage3.com"},
    {"source": "Lehenga Bazaar", "type": "shopify", "base": "https://lehengabazaar.co.in"},
    {"source": "Janasya", "type": "shopify", "base": "https://janasya.com"},
    {"source": "Phaelora", "type": "shopify", "base": "https://phaelora.in"},
    {"source": "Label S4U", "type": "shopify", "base": "https://label-s4u.com"},
    {"source": "Gulabo Jaipur", "type": "shopify", "base": "https://www.gulabojaipur.com"},
    {"source": "Pratapsons", "type": "shopify", "base": "https://pratapsons.com"},
    {"source": "AnarkaliSuit.in", "type": "shopify", "base": "https://anarkalisuit.in"},
    {"source": "Koskii", "type": "shopify", "base": "https://www.koskii.com"},       # custom front end: feed may be off
    {"source": "Nishorama", "type": "shopify", "base": "https://www.nishorama.com"}, # likely Shopify, unconfirmed
    {"source": "Subhvastra", "type": "shopify", "base": "https://subhvastra.in"},    # likely Shopify, unconfirmed
    {"source": "Aykaa", "type": "shopify", "base": "https://aykaa.in"},
    {"source": "Ethenika", "type": "shopify", "base": "https://ethenika.com"},
    {"source": "Mokosh", "type": "shopify", "base": "https://mokosh.in"},
    {"source": "Resha", "type": "shopify", "base": "https://www.reshaindia.in"},
    # Below: blocked AI readers, not checked yet. If one isn't Shopify, or its
    # robots.txt blocks all bots, the log says so and the run carries on.
    {"source": "Narayani Vastra", "type": "shopify", "base": "https://narayanivastra.in"},
    {"source": "House of Shrusha", "type": "shopify", "base": "https://houseofshrusha.com"},
    {"source": "Anayna", "type": "shopify", "base": "https://anayna.com"},
    {"source": "Idaho-o", "type": "shopify", "base": "https://idaho-o.com"},
    {"source": "Chhabra 555", "type": "shopify", "base": "https://www.chhabra555.com"},
    {"source": "Cotton Culture", "type": "shopify", "base": "https://www.cottonculture.co.in"},
    # Below: Shopify-style page addresses seen, platform not directly confirmed
    {"source": "Suta", "type": "shopify", "base": "https://suta.in"},
    {"source": "Okhai", "type": "shopify", "base": "https://okhai.org"},
    {"source": "Shobitam", "type": "shopify", "base": "https://shobitam.com"},
    {"source": "Kalki Fashion", "type": "shopify", "base": "https://www.kalkifashion.com"},  # shows $ abroad; rupee check guards
    {"source": "Posh Affair", "type": "shopify", "base": "https://poshaffair.co"},
    {"source": "Seher Jaipur", "type": "shopify", "base": "https://seherjaipur.com"},
    {"source": "The Gaima Label", "type": "shopify", "base": "https://thegaimalabel.com"},
    {"source": "Sheetal Batra", "type": "shopify", "base": "https://sheetalbatra.com"},
    {"source": "Idalia", "type": "shopify", "base": "https://www.idalia.in"},
    {"source": "Mansi Nagdev", "type": "shopify", "base": "https://mansinagdev.com"},
    {"source": "Misri", "type": "shopify", "base": "https://www.misri.in"},
    {"source": "Kalaloom", "type": "shopify", "base": "https://www.kalaloom.com"},
    {"source": "The Indian Ethnic Co", "type": "shopify", "base": "https://www.theindianethnicco.com"},
    {"source": "The Taram", "type": "shopify", "base": "https://www.thetaram.com"},
    {"source": "Gaia Coutures", "type": "shopify", "base": "https://gaiacoutures.com"},
    {"source": "Begum Pret", "type": "shopify", "base": "https://begumpret.com"},
    {"source": "Ranna Gill", "type": "shopify", "base": "https://rannagill.co.in"},
    {"source": "VNH Naidu Hall", "type": "shopify", "base": "https://vnhnaiduhall.com"},
    {"source": "Aarke by Ritu Kumar", "type": "shopify", "base": "https://aarke.ritukumar.com"},  # platform unconfirmed
    {"source": "Farida Gupta", "type": "shopify", "base": "https://faridagupta.com"},
    {"source": "Tjori", "type": "shopify", "base": "https://www.tjori.com"},
    {"source": "Utsav Bazar", "type": "shopify", "base": "https://utsavbazar.com"},
    {"source": "Xavielle", "type": "shopify", "base": "https://xavielle.com"},
    {"source": "Silai Studio", "type": "shopify", "base": "https://www.silaistudio.com"},
    {"source": "Aurelia", "type": "shopify", "base": "https://shopforaurelia.com"},
    {"source": "Lakshita", "type": "shopify", "base": "https://www.lakshita.com"},
    {"source": "Autumn Lane", "type": "shopify", "base": "https://autumnlane.in"},
    {"source": "Weavekala", "type": "shopify", "base": "https://weavekala.com"},
    {"source": "Bunai", "type": "shopify", "base": "https://www.bunai.com"},
    # Below: platform not confirmed - the run log shows if any fail
    {"source": "Kalmkari", "type": "shopify", "base": "https://kalmkari.in"},
    {"source": "House of Kari", "type": "shopify", "base": "https://houseofkari.in"},
    {"source": "Trendia", "type": "shopify", "base": "https://trendia.co"},
    {"source": "Kalpraag", "type": "shopify", "base": "https://kalpraag.com"},
    {"source": "Kisah", "type": "shopify", "base": "https://kisah.in"},
    {"source": "Pink Fort", "type": "shopify", "base": "https://pinkfort.co"},
    {"source": "Ensemble", "type": "shopify", "base": "https://www.ensembleindia.com"},
    {"source": "The Fashion Station", "type": "woocommerce", "base": "https://www.thefashionstation.in"},  # WordPress shop
    {"source": "Pluch Designs", "type": "shopify", "base": "https://www.pluchdesigns.com"},
    {"source": "Pastels and Pop", "type": "shopify", "base": "https://pastelsandpop.com"},
    {"source": "The Far Store", "type": "shopify", "base": "https://thefarstore.com"},
    {"source": "Sanskritam", "type": "shopify", "base": "https://mysanskritam.com"},
    {"source": "Suvasa", "type": "shopify", "base": "https://suvasa.in"},
    {"source": "House of Jamoti", "type": "shopify", "base": "https://houseofjamoti.com"},
    {"source": "Anokherang", "type": "shopify", "base": "https://www.anokherang.com"},
    {"source": "Origani", "type": "shopify", "base": "https://origanilife.com"},
    # platform not confirmed:
    {"source": "Aravalii", "type": "shopify", "base": "https://www.aravalii.com"},
    {"source": "Taroob", "type": "shopify", "base": "https://taroob.com"},
    {"source": "Divena", "type": "shopify", "base": "https://divenaworld.com"},
    {"source": "Khamaj", "type": "shopify", "base": "https://khamajindia.com"},
    # Below: platform not confirmed - the run log shows if any fail
    {"source": "Jaipur Kurti", "type": "shopify", "base": "https://jaipurkurti.com"},
    {"source": "Aramya", "type": "shopify", "base": "https://aramya.in"},
    {"source": "Garden Vareli", "type": "shopify", "base": "https://www.gardenvareli.com"},
    {"source": "Soch", "type": "shopify", "base": "https://www.soch.com"},
    {"source": "Varanga", "type": "shopify", "base": "https://varanga.in"},
    {"source": "Karaj Jaipur", "type": "shopify", "base": "https://www.karajjaipur.com"},
    {"source": "Noor Bahar", "type": "shopify", "base": "https://noorbahar.com"},
    {"source": "Global Desi", "type": "shopify", "base": "https://www.globaldesi.in"},
    {"source": "Vaayu", "type": "shopify", "base": "https://vaayu.co.in"},
    {"source": "Chidiyaa", "type": "shopify", "base": "https://chidiyaa.com"},
    {"source": "Ganga Fashions", "type": "shopify", "base": "https://gangafashions.com"},
    {"source": "Krami", "type": "shopify", "base": "https://www.kramiindia.com"},
    {"source": "Heritage", "type": "shopify", "base": "https://www.heritageofficial.com"},
    {"source": "Saadaa", "type": "shopify", "base": "https://saadaa.in"},
    {"source": "Vastranand", "type": "shopify", "base": "https://www.vastranand.in"},
    {"source": "iTokri", "type": "shopify", "base": "https://itokri.com"},
    {"source": "Kisseh", "type": "shopify", "base": "https://kisseh.in"},
    {"source": "Handme", "type": "shopify", "base": "https://handme.co.in"},
    {"source": "Calmna", "type": "woocommerce", "base": "https://www.calmna.com"},  # not Shopify (23 Nov: products.json failed)
    {"source": "Ragavi", "type": "shopify", "base": "https://www.ragavi.in"},
    {"source": "The Balaji Creation", "type": "woocommerce", "base": "https://thebalajicreation.in"},  # not Shopify (23 Nov: products.json failed)
    {"source": "Mangalmay", "type": "shopify", "base": "https://shopmangalmay.com"},
    {"source": "Teejh", "type": "shopify", "base": "https://www.teejh.com"},
    {"source": "Shrus", "type": "shopify", "base": "https://shrus.com"},
    {"source": "Manis Fashion", "type": "shopify", "base": "https://www.manisfashionshnk.com"},
    {"source": "Moolchand Mill", "type": "shopify", "base": "https://moolchandmill.com"},
    {"source": "Lashkaraa", "type": "shopify", "base": "https://www.lashkaraa.in"},
    {"source": "Palam Silk", "type": "shopify", "base": "https://www.palamsilk.com"},
    {"source": "Neerus", "type": "shopify", "base": "https://www.neerus.com"},
    {"source": "Store No 6", "type": "shopify", "base": "https://www.storeno6.com"},
    # added 4 Nov: shawls, dupattas, phulkari (platform not checked; the run log shows OK/FAILED per brand)
    {"source": "The Shawl Studio", "type": "shopify", "base": "https://theshawlstudio.in"},
    {"source": "Pashtush", "type": "shopify", "base": "https://pashtush.in"},
    {"source": "Sikh Accessories", "type": "woocommerce", "base": "https://sikhaccessories.com",
     "keep": r"phulkari"},  # Garima sent the Phulkari section only; rest is turbans, kirpans, men's wear  # WordPress URLs
    {"source": "Dupatta Bazaar", "type": "shopify", "base": "https://www.dupattabazaar.com"},
    {"source": "Gaatha", "type": "shopify", "base": "https://shop.gaatha.com"},
    {"source": "Rana Phulkari", "type": "shopify", "base": "https://ranaphulkari.com"},
    {"source": "The Amritsar Store", "type": "shopify", "base": "https://theamritsarstore.com"},
    {"source": "The Yarn Story", "type": "shopify", "base": "https://theyarnstory.com"},
    {"source": "Vastrasar", "type": "shopify", "base": "https://vastrasar.com"},
    {"source": "Gulbhahar", "type": "shopify", "base": "https://www.gulbhahar.com"},
    {"source": "Pashmoda", "type": "shopify", "base": "https://pashmoda.com"},
    {"source": "Teenbaan", "type": "shopify", "base": "https://teenbaan.com"},
    {"source": "Kinche", "type": "shopify", "base": "https://www.kinche.com"},
    {"source": "Odhni", "type": "shopify", "base": "https://shopodhni.in"},
    {"source": "Phulkari Store", "type": "woocommerce", "base": "https://phulkari.store"},  # /shop URL: likely WordPress
    {"source": "Kelin", "type": "shopify", "base": "https://kelin.in"},  # added 19 Nov; platform not checked
    {"source": "Thenmozhi Designs", "type": "shopify", "base": "https://thenmozhidesigns.com"},  # added 21 Nov; platform not checked
    {"source": "Unrush", "type": "shopify", "base": "https://shopunrush.com"},  # added 21 Nov; platform not checked
    {"source": "Yezwe", "type": "shopify", "base": "https://yezwe.com"},  # added 21 Nov; platform not checked
    {"source": "Dash and Dot", "type": "shopify", "base": "https://www.dashanddot.com"},  # added 21 Nov; platform not checked
    {"source": "Zlaata", "type": "zlaata",
     "urls": ["https://www.zlaata.com/zlaata-india/all",
              "https://www.zlaata.com/zlaata-india/all-accessories"]},
]

# ---------------------------------------------------------------------------
# CATEGORY RULES: checked top to bottom, first match wins.
# Matched against the product title first, then the brand's product type,
# then its tags. Edit the word lists to fix any product in the wrong place.
# ---------------------------------------------------------------------------
CATEGORIES = ["Kurta sets", "Co-ord sets", "Kurtas", "Dresses", "Tops & shirts",
              "Pants", "Skirts", "Lehengas", "Sarees", "Jackets & overlays", "Dupattas", "Fabrics", "Footwear", "Jewellery", "Bags",
              "Nightwear & loungewear", "Menswear", "Kidswear", "Innerwear", "Home & gifts", "Accessories", "Other"]
# Still detected (so kids/men pieces don't land in Kurtas etc.) but never
# saved or shown on the site.
EXCLUDED_CATEGORIES = {"Kidswear", "Menswear", "Innerwear", "Home & gifts"}
# Brands removed from SOURCES whose old rows must be dropped from the record.
REMOVED_SOURCES = {"Style Union", "Kisah", "Kalpraag"}  # Kisah, Kalpraag: menswear labels
# A style whose own tags include exactly "Men"/"Menswear" (and no women tag) is menswear,
# even when the title doesn't say so. Whole tags only, never part of a tag.
_MEN_TAGS = {"men", "mens", "men's", "menswear", "man", "for men", "male", "gents", "groomwear", "groom wear"}
_WOMEN_TAGS = {"women", "womens", "women's", "womenswear", "woman", "ladies", "female", "for women"}


_KIDS_TAGS = {"kids", "kid", "kidswear", "kids wear", "children", "childrens", "child", "baby", "infant", "toddler", "boys", "boy"}


def tagged_kidswear(tags, sizes=""):
    """Brand's own tags: only kids (no women tag), tagged Boys, or tagged kids with no adult size
    (kids' age sizes like "2-3 Y" are dropped by the size step, so the size list is empty)."""
    t = {x.strip().lower() for x in (tags or "").split("|")}
    if not (t & _KIDS_TAGS):
        return False
    return not (t & _WOMEN_TAGS) or bool(t & {"boys", "boy"}) or not (sizes or "").strip()


# Men word anywhere in the brand's tags/product type ("festive-shoot2-men", "Mens Diwali'25",
# "RTS-MEN", type "Menswear"), with no women/unisex word in tags, type or title.
_MEN_RX = re.compile(r"(?<![a-z])(men|mens|men's|men’s|menswear|gents)(?![a-z])", re.I)
_WOMEN_RX = re.compile(r"(?<![a-z])(women|womens|women's|women’s|womenswear|woman|ladies|lady|female|"
                       r"unisex|girls?|her|she)(?![a-z])", re.I)


def tagged_menswear(tags, ptype="", title=""):
    t = {x.strip().lower() for x in (tags or "").split("|")}
    if t & _MEN_TAGS and not (t & _WOMEN_TAGS):
        return True
    s = f"{tags or ''}|{ptype or ''}"
    return bool(_MEN_RX.search(s)) and not _WOMEN_RX.search(s + "|" + (title or ""))

_KURTA_WORDS = r"kurta|kurti|anarkali|sharara|salwar|suit|kaftan|churidar|afghani|dupatta"
_SET = (r"\bsets?\b|\bcombos?\b|\bskirt\s+tops?\b|\bsuits?\b|\b3\s?-?\s?(pc|pcs|piece)\b|\btwo[- ]piece\b|"
        r"\bwith\s+(\w+\s+){0,3}(palazzo|plazzo|pants?|sharara|salwar|dupatta|churidar|farshi|farsi|skirt|trousers?)\b|"
        r"\b(kurta|kurti|kaftan|tunic|top)\s*(&|and|\+)\s*(\w+\s+){0,2}(pants?|palazzo|sharara|salwar|skirt|dupatta|trousers?)\b")
CATEGORY_RULES = [
    ("Kidswear", r"\bkids?\b|\bkids?\s?wear\b|\bgirls?\b|\bboys?\b|\binfants?\b|\btoddlers?\b|\bcrib\b|\bbaby\s?wear\b"),
    ("Menswear", r"\bmen'?s?\b|\bmale\b|\bgents\b"),
    ("Co-ord sets", r"\bco[- ]?c?ords?\b|\bcoords?\b"),
    ("Lehengas", r"\blehenga|\blehnga"),
    ("Nightwear & loungewear", r"\bnight\s?wear\b|\bnight\s?suits?\b|\bnighty\b|\bnightdress\b|\bpyjamas?\b|\bpajamas?\b|\blounge\s?wear\b|\bsleep\s?wear\b"),
    ("Sarees", r"\bsarees?\b|\bsaris?\b"),
    ("SET", _SET),  # -> Kurta sets if kurta-type words, else Co-ord sets
    ("Dresses", r"\bdress(es)?\b|\bgowns?\b|\bjumpsuits?\b|\bmaxi\b|\bmidi\b"),
    ("Kurtas", r"\b(kurta|kurti|kurtas|kurtis|anarkali|kaftan)\b"),
    ("Tops & shirts", r"\btops?\b|\bshirts?\b|\bblouses?\b|\btunics?\b|\bcrop\b|\btees?\b|\bt-shirts?\b"),
    ("Pants", r"\bpants?\b|\bpalazzos?\b|\bplazzos?\b|\btrousers?\b|\bskirts?\b|\bshorts\b|\bsharara\b|\bsalwar\b|\bleggings?\b|\bculottes?\b|\bdhoti\b|\bbottoms?\b|\bjeans\b"),
    ("Jackets & overlays", r"\bjackets?\b|\bshrugs?\b|\boverlays?\b|\bcapes?\b|\bcoats?\b|\bwaistcoats?\b|\bbandi\b|\bkimonos?\b|\bcardigans?\b|\bblazers?\b"),
    ("Accessories", r"\bbags?\b|\btotes?\b|\bpouch(es)?\b|\bpotli\b|\bclutch\b|\bjewell?e?ry\b|\bearrings?\b|\bnecklaces?\b|\bbracelets?\b|\bbangles?\b|\brings?\b|\bscrunchies?\b|\bhair\b|\bkeychains?\b|\bmasks?\b|\bstoles?\b|\bscarf\b|\bdupattas?\b|\bbelts?\b|\bwallets?\b|\bgameboard\b|\bsocks\b"),
]
_RULES = [(c, re.compile(p, re.I)) for c, p in CATEGORY_RULES]
_SOURCE_KEEP = {c["source"]: re.compile(c["keep"], re.I) for c in SOURCES if c.get("keep")}
_KURTA_RE = re.compile(r"\b(" + _KURTA_WORDS + r")s?\b", re.I)

# Zlaata's own category (from its product URLs) -> our category
ZLAATA_CATEGORY = {
    "kurta-set": "Kurta sets", "co-ords": "Co-ord sets", "kurtas-kurtis": "Kurtas",
    "dresses": "Dresses", "tops-tunics": "Tops & shirts", "bottoms": "Pants",
    "lehengas": "Lehengas", "overlays": "Jackets & overlays",
    "hair": "Accessories", "bags-pouches": "Accessories", "gameboard": "Accessories",
    "keychain": "Accessories", "all-accessories": "Accessories",
}

SKIP_TYPES = re.compile(r"gift ?card|e-?gift|insurance|shipping|donation", re.I)


# ---------------------------------------------------------------------------
# Product identification (rewritten 22 Nov after Garima's audit).
# 1. Blocks first (title + brand's product type): innerwear, men's garments,
#    baby items, home goods, gift hampers, services and test listings.
# 2. Then find WHAT the product is from its garment words, not just any word:
#    "Saree Fall" is a fall, "Combo of 3 Dupattas" is dupattas, "Kurta with
#    Palazzo & Dupatta" is a kurta set, "Set of 2 towels" is a multipack.
# Hand fixes: data/category_overrides.json {"<product url>": "<category>"}.
# ---------------------------------------------------------------------------
_R = lambda p: re.compile(p, re.I)
_INNERWEAR = _R(r"\binner\s?wear\b|\bbras?\b|\bbrassieres?\b|\bbralettes?\b|\bshape\s?wear\b|\bshapers?\b|\bpetticoats?\b|\bin[- ]?skirts?\b|"
                r"\bunder[- ]?skirts?\b|\blingerie\b|\bpant(y|ies)\b|\bsweat\s?pads?\b|\bdress\s?shields?\b|\bintimacy\b|"
                r"\bthermals?\b|\bvests?\b(?=.*\b(inner|thermal|cotton\s+vest)\b)")
_MEN_GARMENT = _R(r"\bsherwanis?\b|\bkurta\s?(pyjama|pajama|payjama)s?\b|\bpathani\b|\bachkans?\b|\bjodhpuri\b|"
                  r"\bbandh\s?galas?\b|\bturbans?\b|\bpagri\b|\bsafa\b|\bdastar\b|\bpatkas?\b|\bkirpans?\b|\bgatra\b|"
                  r"\bnihang\b|\bchola\b|\bfor\s+him\b|\bgroom\b|\bdulha\b|\bhis\s*(and|&|n)\s*hers?\b|\bnehru\s+jacket\b(?=.*\bmen\b)")
_BABY = _R(r"\bbaby\b(?!\s*(pink|blue|yellow|green|doll|lilac|peach))|\bnapp(y|ies)\b|\bnew\s?born\b|\bbibs?\b|\bjhabla\b|\boh\s+baby\b")
_HOME = _R(r"\b(bed\s?(cover|sheet|spread)s?|bedsheets?|cushions?(\s+covers?)?|pillows?(\s+covers?)?|curtains?|"
           r"table\s?(cover|runner|cloth|linen|mat)s?|napkins?(\s+rings?)?|towels?|quilts?|dohars?|razai|blankets?|coasters?|"
           r"rugs?|dhurries?|aprons?(?!\s*neck)|wall\s?hangings?|home\s?decor|placemats?|torans?|mugs?|diar(y|ies)|notebooks?|"
           r"stationery|candles?|planters?|trays?|boxes|baskets?|lamps?|frames?|rumala|throws?|gift\s?box(es)?|running\s+fabric|"
           r"rakhis?|serums?|creams?|gels?|under\s?eye|kajal|sindoor|lipsticks?|moisturi[sz]ers?|face\s?(wash|packs?|masks?)|soaps?|lip\s?balms?|perfumes?|attars?|"
           r"fragrances?|body\s?(oil|lotion|butter)|hair\s?oil|skin\s?care|skincare|glow\s?boosters?|greeting\s?cards?|"
           r"paintings?|scrolls?|brass|wooden|diyas?|idols?|dinner\s?sets?|plates?|bowls?|tea\s?cos(y|ies)|"
           r"bath\s?robes?|candles?|wax|scented|incense|agarbattis?|dhoop|kumkum|vases?|showpieces?|figurines?|wind\s?chimes?|"
           r"christmas|decorations?|wreaths?|boards?|chopping|carafes?|karaffe|decanters?|bottles?|fridge|handle\s?covers?|"
           r"toys?|dolls?|puzzles?|games?|pens?|journals?|planners?|calendars?|stickers?|pooja|puja|chowki|ornaments?|ghee\s?pots?|pots?|thali|bookmarks?|magnets?|key\s?holders?)\b")
_NONSALE = _R(r"^\W*(\d+\s+)?test(\s+test)*\W*$|\b(at|for)\s+just\s+(₹|rs)|\bon\s+orders\s+above\b|\bgift\s?wraps?\b|\bhampers?\b|\b(stitching|tailoring|alteration)\b|\bsample\s+sarees?\b|\bworking\s+bar\b|\be-?gift\b|\bgift\s?cards?\b")
_FOOTWEAR = _R(r"\b(jut+is?|juti|mojr?is?|mojaris?|mojdis?|khussas?|nagras?|peshawaris?|bellies|loafers?|mules|sandals?|heels|"
               r"shoes?|kolhapuris?|footwear|slippers?|chappals?|sneakers?|boots?|wedges|stilettos?|flip[- ]?flops?)\b")
_JEWELLERY = _R(r"\b(jewell?e?ry|jewelry|oxidi[sz]ed|earrings?|jhumkas?|jhumkis?|studs|necklaces?|chokers?|bangles?|bracelets?|"
                r"kadas?|(?<!napkin\s)(?<!key\s)rings?|finger\s?rings?|anklets?|payals?|nose\s?(pins?|rings?)|maang\s?tikkas?|haath\s?phool|pendants?|kundan|polki)\b")
_BAGS = _R(r"\b(bags?|handbags?|potlis?|clutch(es)?|totes?|wallets?|purses?|pouch(es)?|slings?|backpacks?|satchels?|batuas?|"
           r"(laptop|i-?pad|tablet|mobile)\s?(sleeves?|covers?|cases?))\b")
_ACC_FIRST = _R(r"\b(hair|scrunchies?|clips?|bows?|neck\s?warmers?|bag\s?charms?|key\s?(chains?|rings?)|keychains?|"
                r"spectacle|chashma|eyewear|sunglasses)\b")
_BAG_ETC = _R(r"\b(hair|scrunchies?|clips?|masks?|keychains?|belts?|socks|"
              r"caps?|hats?|visors?|gloves|umbrellas?|brooch(es)?|latkans?|tassels?)\b")
_FABRIC = _R(r"\bfabrics?\b|\b(running|yardage)\b|\bby\s+the\s+met(er|re)\b|\bper\s+met(er|re)\b|\bwidth\s*-?\s*\d+\s*in\b")
_SAREE_ADDON = _R(r"\b(sarees?|saris?)\s+(falls?|pins?|brooch(es)?|tassels?|belts?|covers?|bags?|clips?|organi[sz]ers?|holders?)\b|"
                  r"\b(falls?|pico)\s+(for\s+)?(sarees?|saris?)\b")

# garment words: what the product is made of
_G = {
    "lehenga": _R(r"\blehe?n?ga|\bghagras?\b|\bchaniya\b"),
    "saree": _R(r"\bsarees?\b|\bsaris?\b"),
    "material": _R(r"\bdress\s?materials?\b|\bsuit\s?(materials?|pieces?|fabric)\b|\bunstitched\b|\bsemi[- ]?stitched\b"),
    "kurta": _R(r"\b(kurtas?|kurtis?|anarkalis?|kameez|angrakhas?|kaftans?|afghani|chogas?|pherans?|phirans?)\b"),
    "suit": _R(r"\b(salwar\s+)?suits?\b|\bpatiala\b"),
    "top": _R(r"\b(tops?|shirts?|tunics?|blouses?|crop|peplums?|cuffs?|bustiers?|corsets?|camis?|tees?|t-shirts?|cholis?)\b"),
    "bottom": _R(r"\b(pants?|palazzos?|plazzos?|pallazos?|trousers?|sharara|gharara|salwar|churidars?|skirts?|dhoti|leggings?|"
                 r"culottes?|shorts|jeans|bottoms?|farshi|farsi|tights?|jeggings?|joggers?)\b"),
    "dupatta": _R(r"\b(dupattas?|odhnis?|chunnis?)\b"),
    "stole": _R(r"\b(stoles?|shawls?|scarf|scarves|wraps?|mufflers?|baghs?|vehl|phulkari)\b"),
    "dress": _R(r"\b(dress(es)?|gowns?|jumpsuits?|playsuits?)\b(?!\s?materials?)|\b(maxi|midi)\b(?!\s+skirts?)"),
    "jacket": _R(r"\b(jackets?|shrugs?|overlays?|capes?|coats?|waistcoats?|bandi|kimonos?|cardigans?|blazers?)\b"),
    "coord": _R(r"\bco[- ]?c?ords?\b|\bcoords?\b"),
    "piece3": _R(r"\b3\s?-?\s?(pc|pcs|piece)s?\b|\bthree[- ]piece\b"),
    "set": _R(r"\bsets?\b|\bcombos?\b|\b2\s?-?\s?(pc|pcs|piece)s?\b|\btwo[- ]piece\b|\bwith\b|&|\band\b|\+"),
    "night": _R(r"\bnight\s?wear\b|\bnight\s?suits?\b|\bnighty\b|\bnightdress\b|\bpyjamas?\b|\bpajamas?\b|\blounge\s?wear\b|"
                r"\bsleep\s?wear\b|\bnight\s?gowns?\b"),
}
_MULTIPACK = _R(r"\b(set|pack|combo)\s+of\s+\d+\b|\b\d+\s*(pcs?|pieces?)\s+set\b|\bcombo\b")


def _what(text):
    """Category from what the product IS (garment words), or None."""
    if not text:
        return None
    t = text
    if _INNERWEAR.search(t):
        return "Innerwear"
    if _SAREE_ADDON.search(t):
        return "Accessories"
    if _NONSALE.search(t):
        return "Home & gifts"
    g = {k: bool(rx.search(t)) for k, rx in _G.items()}
    if g["night"]:
        return "Nightwear & loungewear"
    garment = any(g[k] for k in ("lehenga", "saree", "material", "kurta", "suit", "top", "bottom", "dress", "jacket", "coord", "piece3"))
    if not garment:
        if re.search(r"\b(rakhis?|christmas|santa|podi|pickles?|masalas?|spices?|chutneys?|honey|ghee|"
                     r"tea|coffee|snacks?|sweets|namkeen|papad)\b", t, re.I):  # gifts and food, even with a potli or brooch
            return "Home & gifts"
        if _ACC_FIRST.search(t):  # "Hair Clip with Scarf", bows, neck warmers, bag charms
            return "Accessories"
        if _JEWELLERY.search(t):  # "Fabric & Wood Statement Necklace"
            return "Jewellery"
        if _BAGS.search(t):
            return "Bags"
        if _FOOTWEAR.search(t):  # "Phulkari Shoe" is a shoe, not a phulkari shawl
            return "Footwear"
        if g["dupatta"] or g["stole"]:  # "Gift Box of Pashmina Stole" is a stole
            return "Dupattas"
        if _HOME.search(t):  # before Fabrics: "Kalamkari Fabric Cover Notebook"
            return "Home & gifts"
        if _FABRIC.search(t):
            return "Fabrics"
        if _FOOTWEAR.search(t):
            return "Footwear"
        if _JEWELLERY.search(t):
            return "Jewellery"
        if _BAG_ETC.search(t):
            return "Accessories"
        return None
    if g["lehenga"]:
        return "Lehengas"
    if g["saree"]:
        # "Saree Blouse" / "Saree Blouse Piece" with no saree in the deal = a blouse
        rest = re.sub(r"\b(sarees?|saris?)\s+blouses?\b|\bfor\b[^|.]{0,40}?\b(sarees?|saris?)\b", " blouse ", t, flags=re.I)
        rest = rest if re.search(r"\bblouses?\b", t, re.I) else t
        if g["top"] and not _G["saree"].search(rest):
            return "Tops & shirts"
        return "Sarees"
    if re.search(r"\bblouse\s+(piece|material|fabric)s?\b", t, re.I):
        return "Tops & shirts"
    if g["material"]:
        return "Kurta sets"
    if g["kurta"]:
        if g["bottom"] or g["dupatta"] or g["suit"] or g["piece3"] or g["coord"] or re.search(r"\bsets?\b", t, re.I):
            return "Kurta sets"
        return "Kurtas"
    if g["suit"] and not g["jacket"]:
        return "Kurta sets"
    if g["coord"] or g["piece3"] or (g["top"] and g["bottom"]):
        # a 3-piece or any set with a dupatta is an Indian suit set
        return "Kurta sets" if (g["dupatta"] or g["piece3"]) else "Co-ord sets"
    if g["dress"]:
        return "Dresses"
    if g["jacket"]:  # "Cape Set" = a whole outfit
        return "Co-ord sets" if re.search(r"\bsets?\b", t, re.I) else "Jackets & overlays"
    if g["top"]:
        return "Tops & shirts"
    if g["bottom"]:
        # "Palazzo Set", "Sharara Set", "Pant Set" = a whole outfit; "Pack of 2 leggings" = bottoms
        if re.search(r"\bsets?\b", t, re.I) and re.search(r"\b(salwar|sharara|gharara|farshi|farsi|patiala)\b", t, re.I):
            return "Kurta sets"
        if re.search(r"\bsets?\b", t, re.I) and not _MULTIPACK.search(t):
            return "Kurta sets" if re.search(r"\b(salwar|sharara|gharara|farshi|farsi|churidars?|patiala)\b", t, re.I) or g["dupatta"] else "Co-ord sets"
        if re.search(r"\b(salwar|sharara|gharara)\b.*\b(with|&|and)\b|\b(with|&|and)\b.*\b(salwar|sharara|gharara)\b", t, re.I):
            return "Kurta sets"
        return "Skirts" if re.search(r"\bskirts?\b", t, re.I) else "Pants"
    return None


def _match(text):  # kept for old callers
    return _what(text)


_CATEGORY_OVERRIDES = None


def category_override(url):
    global _CATEGORY_OVERRIDES
    if _CATEGORY_OVERRIDES is None:
        try:
            with open("data/category_overrides.json", encoding="utf-8") as fh:
                _CATEGORY_OVERRIDES = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
        except (OSError, ValueError):
            _CATEGORY_OVERRIDES = {}
    return _CATEGORY_OVERRIDES.get(url or "")


def classify(title, product_type="", tags="", hint=None):
    """Return one of CATEGORIES for a product."""
    head = f"{title} {product_type}"
    # blocks first, from title + the brand's own product type (tags are often noisy)
    for cat in ("Kidswear", "Menswear"):
        rx = dict(_RULES)[cat]
        if rx.search(head):
            return cat
    if _MEN_GARMENT.search(head):
        return "Menswear"
    if _BABY.search(head):
        return "Kidswear"
    if _INNERWEAR.search(head):
        return "Innerwear"
    if hint:
        w = _what(title)
        if (w == "Kurta sets" and hint == "Co-ord sets") or (hint == "Pants" and w == "Skirts"):
            return w
        return hint
    # what the title says it is; then the brand's product type; tags last
    for text in (title, product_type, tags):
        cat = _what(text)
        if cat:
            return cat
    return "Other"


FIELDS = ["source", "category", "product_type", "product_id", "title", "brand", "url",
          "price", "mrp", "discount_pct", "sizes_available", "sizes_all",
          "colour", "colour_raw", "in_stock", "image", "tags", "desc_attrs", "published_at", "scraped_at"]


# ---------------------------------------------------------------------------
# Size normalisation: "S (36)", "S - 36", "SMALL", "36" -> "S".
# "Set of 3", "Unstitched", kids' ages etc. are not sizes and are dropped.
# ---------------------------------------------------------------------------
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "7XL", "8XL", "Free size"]
_BUST = {30: "XXS", 32: "XXS", 34: "XS", 36: "S", 38: "M", 40: "L", 42: "XL", 44: "XXL",
         46: "3XL", 48: "4XL", 50: "5XL", 52: "6XL", 54: "7XL", 56: "8XL"}


def normalise_size(raw):
    t = re.sub(r"[^A-Z0-9]+", " ", str(raw).upper()).strip()
    if not t:
        return None
    if re.search(r"\bFREE\b|\bONE SIZE\b|\bFS\b|\bFREESIZE\b", t):
        return "Free size"
    if re.search(r"\bSET\b|STITCH|\bYRS?\b|\bYEARS?\b|\bMONTHS?\b|\bKIDS?\b", t):
        return None
    m = re.search(r"\b([2-8])\s?XL\b", t)
    if m:
        return "XXL" if m.group(1) == "2" else m.group(1) + "XL"
    m = re.search(r"\b(X{3,8})L\b", t)
    if m:
        return f"{len(m.group(1))}XL"
    for pat, size in [(r"\bXXL\b|\bXX L\b|\bDOUBLE XL\b", "XXL"), (r"\bXL\b|\bEXTRA LARGE\b|\bX LARGE\b", "XL"),
                      (r"\bXXS\b", "XXS"), (r"\bXS\b|\bEXTRA SMALL\b|\bX SMALL\b", "XS"),
                      (r"\bS\b|\bSMALL\b", "S"), (r"\bM\b|\bMEDIUM\b", "M"), (r"\bL\b|\bLARGE\b", "L")]:
        if re.search(pat, t):
            return size
    m = re.search(r"\b(\d{2})\b", t)
    if m and int(m.group(1)) in _BUST:
        return _BUST[int(m.group(1))]
    return None


def normalise_sizes(values):
    out = []
    for v in values:
        z = normalise_size(v)
        if z and z not in out:
            out.append(z)
    return sorted(out, key=SIZE_ORDER.index)


def is_size_option(name):
    return "size" in name


def is_colour_option(name):
    return "colo" in name  # color / colour / Select Colour ...


# ---------------------------------------------------------------------------
# Colour normalisation: every brand's colour words -> one short list.
# Edit COLOUR_WORDS to add new words you see in the data.
# ---------------------------------------------------------------------------
COLOUR_WORDS = {
    "Black": ["black", "charcoal", "jet"],
    "White": ["white", "off-white", "off white", "ivory", "pearl"],
    "Beige": ["beige", "cream", "ecru", "nude", "sand", "khaki", "tan", "camel", "fawn"],
    "Brown": ["brown", "walnut", "coffee", "chocolate", "mocha", "rust", "copper"],
    "Red": ["red", "scarlet", "cherry", "crimson", "tomato"],
    "Maroon": ["maroon", "wine", "burgundy", "oxblood"],
    "Pink": ["pink", "rani", "rose", "blush", "coral", "fuchsia", "magenta", "salmon"],
    "Orange": ["orange", "peach", "tangerine", "apricot"],
    "Yellow": ["yellow", "mustard", "lemon", "haldi", "ochre"],
    "Green": ["green", "sage", "mint", "olive", "jade", "emerald", "pista",
              "pistachio", "mehendi", "lime", "bottle green"],
    "Blue": ["blue", "navy", "indigo", "aqua", "turquoise", "teal", "sky",
             "cobalt", "denim", "firozi", "jade blue"],
    "Purple": ["purple", "lavender", "lilac", "jamuni", "violet", "mauve",
               "plum", "grape", "grapewine", "orchid", "onion"],
    "Grey": ["grey", "gray", "silver", "ash", "steel"],
    "Gold": ["gold", "golden"],
    "Multicolour": ["multicolor", "multicolour", "multi-color", "multi colour",
                    "multi-colour", "multi color", "multi"],
}
# "onion pink" should be Pink, not Purple: longer phrases win at the same spot
COLOUR_WORDS["Pink"] += ["onion pink", "dusty pink", "hot pink", "baby pink"]
_COLOUR_PATTERNS = sorted(
    ((w, c) for c, ws in COLOUR_WORDS.items() for w in ws),
    key=lambda x: -len(x[0]))


def normalise_colour(text):
    """Return the canonical colour for the earliest colour word in text."""
    if not text:
        return ""
    t = text.lower()
    best = None  # (start, -len, colour)
    for word, colour in _COLOUR_PATTERNS:
        for m in re.finditer(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", t):
            cand = (m.start(), -len(word), colour)
            if best is None or cand < best:
                best = cand
    return best[2] if best else ""


def colour_for(raw_option, title):
    return normalise_colour(raw_option) or normalise_colour(title) or "Other"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
class Fetcher:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.robots = {}
        self.last = 0.0

    def allowed(self, url):
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self.robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.s.get(root + "/robots.txt", timeout=TIMEOUT)
                rp.parse(r.text.splitlines() if r.ok else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[root] = rp
        return self.robots[root].can_fetch(USER_AGENT, url)

    def get(self, url, **kw):
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        wait = DELAY_SEC - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=TIMEOUT, **kw)
                self.last = time.time()
                if r.status_code == 429:
                    time.sleep(10 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if attempt == 2 or (code and 400 <= code < 500):
                    raise  # "not found" / "forbidden" won't change on a retry
                print(f"  retry {attempt + 1} for {url}: {e}", file=sys.stderr)
                time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"failed: {url}")


# ---------------------------------------------------------------------------
# Indian-wear attributes: work, print, fabric, shape, bottom, dupatta,
# neckline, sleeves, occasion, stitching. Matched from product text.
# ---------------------------------------------------------------------------
# group -> list of (value, regex). Order inside a group = display order.
ATTR_RULES = {
    "work": [
        ("Chikankari", r"chikan\w*|lucknowi"),
        ("Gota patti", r"gota|gotta"),
        ("Zari & zardozi", r"zari|zardo[sz]i|zardozi|dabka|dabaka|tilla|marodi|kasab"),
        ("Mirror work", r"mirror|sheesha|shisha|abla"),
        ("Sequins", r"sequin\w*|sequen\w*|sitara|mukaish|mukesh|badla"),
        ("Thread & resham", r"thread\s?work|resham|aari|kashidakari|kashida|kantha|phulkari|kutch\w* work|sozni|parsi|cross[- ]?stitch"),
        ("Beads & pearls", r"bead\w*|pearl\w*|moti\b|stone\s?work|cut\s?dana|cutdana|kundan|crystal\w*"),
        ("Lace & trims", r"lace\w*|tassel\w*|piping|pompom|pom[- ]pom|fringe"),
        ("Pintucks & pleats", r"pin\s?tuck\w*|pleat\w*|smock\w*|shirr\w*"),
        ("Cutwork & applique", r"cut\s?work|applique|appliqu\w*|patch\s?work|schiffli|eyelet|hakoba"),
        ("Embroidered & embellished", r"embroider\w*|embelli\w*|handwork|hand\s?work|work(?:ed)?\s+(?:kurta|set|suit)"),
    ],
    "print": [
        ("Hand block print", r"hand[- ]?block|block[- ]?print\w*|blockprint\w*|sanganeri|bagru|dabu|daboo|indigo dabu|kalamkari|kalmkari"),
        ("Ajrakh", r"ajrakh|ajrak"),
        ("Bandhani & leheriya", r"bandhan[ie]|bandhej|bandej|lehe?riya|leheria"),
        ("Tie-dye & shibori", r"tie[- ]?(?:and[- ])?dye|tie[- ]dyed|shibori|clamp[- ]dye"),
        ("Ikat", r"ikat|ikkat|pochampally|patola"),
        ("Hand painted", r"hand[- ]?paint\w*|pichwai|madhubani"),
        ("Woven & jacquard", r"woven|jacquard|jaquard|brocade|banaras\w*|benaras\w*|jamdani|kota\s?doria|zari\s?woven"),
        ("Floral", r"floral\w*|flower\w*|bloom\w*|botanical|roses|lotus"),
        ("Paisley", r"paisley|buta|butti|booti|keri|kairi"),
        ("Geometric & abstract", r"geometric|abstract|chevron|polka|dots?\b|dotted"),
        ("Stripes & checks", r"stripe\w*|striped|check\w*|plaid|gingham|houndstooth"),
        ("Motifs & animals", r"animal|bird\w*|elephant|parrot|leopard|motif\w*|ethnic motif"),
        ("Solid", r"\bsolid\b|\bplain\b"),
        ("Printed", r"print\w*"),
    ],
    "fabric": [
        ("Chanderi", r"chanderi"),
        ("Maheshwari", r"maheshwari"),
        ("Banarasi", r"banaras\w*|benaras\w*"),
        ("Silk", r"silk"),
        ("Cotton", r"cotton|mul\s?mul|mal\s?mal|khadi|cambric|poplin|voile|lawn|kota\b"),
        ("Linen", r"linen"),
        ("Georgette", r"georgette|gorgette"),
        ("Chiffon", r"chiffon|chinon"),
        ("Organza", r"organza|organdy"),
        ("Crepe", r"crepe|crape"),
        ("Rayon & viscose", r"rayon|viscose|liva\b|lyocell|tencel"),
        ("Modal", r"modal"),
        ("Muslin", r"muslin"),
        ("Satin", r"satin|charmeuse|shantoon|shantung"),
        ("Velvet", r"velvet|velour"),
        ("Net & tulle", r"\bnet\b|tulle|mesh"),
        ("Tissue", r"tissue"),
        ("Tussar", r"tussar|tussah|tussore"),
        ("Denim", r"denim"),
        ("Polyester & blends", r"polyester|poly\s?blend|lycra|spandex|nylon"),
    ],
    "silhouette": [
        ("Anarkali", r"anarkali|anarakali|kalidar|kalidaar|kalis?\b|panelled|paneled|panel\b"),
        ("A-line", r"a[- ]?line|aline"),
        ("Straight", r"straight"),
        ("Angrakha", r"angrakha|angarkha|wrap|overlap"),
        ("Kaftan & choga", r"kaftan|caftan|choga|chauga"),
        ("Flared", r"flare\w*|flair\w*|umbrella|ghera|gher"),
        ("Peplum", r"peplum"),
        ("Short kurti", r"short\s?kurt\w*|kurti\s?top|tunic"),
        ("Asymmetric & high-low", r"asymmetr\w*|high[- ]low|hi[- ]lo"),
        ("Tiered", r"tier\w*"),
        ("Empire & gathered", r"empire|gather\w*"),
        ("Pathani", r"pathani"),
        ("Jacket & layered", r"jacket|shrug|cape\b|layered"),
    ],
    "bottom": [
        ("Palazzo", r"pal+az+o\w*|palaz+o|pallazo"),
        ("Sharara", r"sharara"),
        ("Gharara", r"gharara|garara"),
        ("Farshi salwar", r"farshi"),
        ("Salwar & patiala", r"salwar|shalwar|patiala|dhoti\s?salwar|afghani"),
        ("Churidar", r"churidar|churidaar|leggings?"),
        ("Dhoti", r"dhoti"),
        ("Skirt", r"skirt|lehenga|ghagra|ghaghra"),
        ("Pants & trousers", r"pant\w*|trouser\w*|cigarette|straight\s?bottom|bottoms?\b"),
    ],
    "dupatta": [
        ("With dupatta", r"dupatta|dupata|duppatta|stole|odhni|\b3\s?-?\s?(?:pc|pcs|piece)s?\b|three[- ]piece"),
    ],
    "neck": [
        ("V-neck", r"v[- ]?neck"),
        ("Round neck", r"round\s?neck"),
        ("Collar & mandarin", r"collar\w*|mandarin|band\s?neck|chinese\s?neck"),
        ("Sweetheart", r"sweetheart"),
        ("Square neck", r"square\s?neck"),
        ("Boat neck", r"boat\s?neck|bateau"),
        ("Keyhole & notch", r"key\s?hole|notch\w*|placket"),
        ("Halter & off-shoulder", r"halter|off[- ]?shoulder|strap\w*|spaghetti"),
        ("U-neck & scoop", r"u[- ]?neck|scoop"),
    ],
    "sleeve": [
        ("Sleeveless", r"sleeveless|sleeve\s?less|strappy"),
        ("Short sleeves", r"short\s?sleeve\w*|half\s?sleeve\w*|cap\s?sleeve\w*"),
        ("3/4 sleeves", r"3\s?/\s?4|three[- ]quarter|elbow"),
        ("Full sleeves", r"full\s?sleeve\w*|long\s?sleeve\w*"),
        ("Bell & flared sleeves", r"bell\s?sleeve\w*|flared\s?sleeve\w*|bell\b"),
        ("Puff sleeves", r"puff\w*\s?sleeve\w*|puff\b|bishop|balloon"),
    ],
    "occasion": [
        ("Wedding & bridal", r"wedding|bridal|bride\w*|trousseau|sangeet|haldi|mehendi|mehndi|cocktail"),
        ("Festive", r"festive|festival|diwali|eid|puja|pooja|navratri|garba|rakhi|karwa|teej|onam|pongal|celebration"),
        ("Party", r"\bparty\b|evening|occasion"),
        ("Office", r"office|work\s?wear|workwear|formal"),
        ("Casual & daily", r"casual|daily|everyday|lounge|comfort|summer essential|basics?"),
    ],
    "stitch": [
        ("Unstitched", r"unstitch\w*|un-stitch\w*|dress\s?material|ready\s?to\s?stitch|semi[- ]stitch\w*|fabric\s?set"),
    ],
}
COMPILED = {g: [(v, re.compile(r"\b(?:" + p + r")", re.I)) for v, p in rules] for g, rules in ATTR_RULES.items()}

# Which groups are shown / computed for which categories
GROUPS_FOR = {
    "Kurta sets": ["work", "print", "fabric", "silhouette", "bottom", "dupatta", "neck", "sleeve", "occasion", "stitch"],
    "Kurtas": ["work", "print", "fabric", "silhouette", "neck", "sleeve", "occasion"],
    "Co-ord sets": ["work", "print", "fabric", "bottom", "neck", "sleeve", "occasion"],
    "Dresses": ["work", "print", "fabric", "neck", "sleeve", "occasion"],
    "Tops & shirts": ["work", "print", "fabric", "neck", "sleeve", "occasion"],
    "Lehengas": ["work", "print", "fabric", "occasion"],
    "Sarees": ["work", "print", "fabric", "occasion"],
    "Pants": ["work", "print", "fabric", "bottom"],
    "Skirts": ["work", "print", "fabric"],
    "Jackets & overlays": ["work", "print", "fabric", "sleeve", "occasion"],
}

# Words that read like attributes but name a collection/person; strip before matching
NOISE = re.compile(r"\b(?:sheetal batra|silsila|gulshan bagh|rose\s?gold)\b", re.I)


def match_group(group, text):
    found = []
    for v, rx in COMPILED[group]:
        if rx.search(text):
            found.append(v)
    # "Embroidered"/"Printed" are catch-alls: drop them when a specific value matched
    if group == "work" and len(found) > 1 and "Embroidered & embellished" in found:
        found.remove("Embroidered & embellished")
    if group == "print":
        specific = [f for f in found if f not in ("Printed", "Solid")]
        if specific:
            found = specific
    return found


# Which groups count for which categories (others get no attributes)
ATTR_LABELS = {"work": "Work & embroidery", "print": "Print & craft", "fabric": "Fabric",
               "silhouette": "Shape", "bottom": "Bottom style", "dupatta": "Dupatta",
               "neck": "Neckline", "sleeve": "Sleeves", "occasion": "Occasion", "stitch": "Stitching"}
# From the title + product type only. Brand tags are too often store-wide
# collection labels ("Gota Patti Kurtis" on a plain kurta), so they are used
# only for occasion and unstitched.
_TAG_GROUPS = ("occasion", "stitch")
# Description text is used for these when the title doesn't say
_DESC_GROUPS = ("neck", "sleeve", "fabric")
_FABRIC_LINE = re.compile(r"(?:fabric|material|composition)\s*[:\-–]?\s*([^.;\n]{2,80})", re.I)


def desc_attrs(html):
    """Neckline / sleeves / fabric / crafts stated in a product description -> 'group:value|...'."""
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)[:3000]
    found = []
    for g in ("neck", "sleeve"):
        found += [f"{g}:{v}" for v in match_group(g, text)]
    fab = " ".join(m.group(1) for m in _FABRIC_LINE.finditer(text))
    found += [f"fabric:{v}" for v in match_group("fabric", fab)]
    found += [f"craft:{i}" for i in match_crafts(text)]
    # what the product is, from the first line of the description (Kisseh etc. put
    # "Pure Katan Silk Banarasi Saree" right under a name-only title)
    first = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0][:200]
    cat = _what(first) or _what(text[:600])
    if cat:
        found.append(f"cat:{cat}")
    return "|".join(found)


def product_attrs(r):
    """All Indian-wear attributes for one record -> list of 'group:value'."""
    groups = GROUPS_FOR.get(r.get("category"))
    if not groups:
        return []
    base = NOISE.sub(" ", f"{r.get('title', '')} ; {r.get('product_type', '')}")
    tagtext = base + " ; " + (r.get("tags") or "").replace("|", " ; ")
    from_desc = {}
    for item in (r.get("desc_attrs") or "").split("|"):
        if ":" in item:
            g, v = item.split(":", 1)
            from_desc.setdefault(g, []).append(v)
    out = []
    for g in groups:
        vals = match_group(g, tagtext if g in _TAG_GROUPS else base)
        if not vals and g in _DESC_GROUPS:
            vals = from_desc.get(g, [])
        if g == "stitch" and not vals and r.get("category") in ("Kurta sets", "Kurtas", "Co-ord sets"):
            vals = ["Ready to wear"]
        out += [f"{g}:{v}" for v in vals]
    out += [f"craft:{CRAFT_NAME[i]}" for i in product_crafts(r)]
    return out


# ---------------------------------------------------------------------------
# CRAFTS: one fixed id per craft. Every clothing style gets one or more crafts,
# or exactly one bucket (embroidered / printed / solid / not specified).
# Matched on title + product type; the description is used only when the title
# names no craft. Brand tags and brand-wide defaults are NOT used.
# Hand fixes: data/craft_overrides.json  {"<product url>": {"add": [ids], "remove": [ids]}}
# Names / write-ups for each id: data/crafts.json
# ---------------------------------------------------------------------------
CRAFT_RULES = [  # (id, name, family, regex) - order = display order
    ("chikankari", "Chikankari", "Embroidery", r"chikan\w*|lucknowi"),
    ("gota-patti", "Gota patti", "Embroidery", r"gota|gotta"),
    ("zardozi", "Zari & zardozi", "Embroidery", r"zardo[sz]i|dabka|dabaka|tilla|marodi|kasab|zari\s?(?:work|embroider\w*)|zari\b(?!\s?(?:woven|weave|border|butti|buti))"),
    ("mukaish", "Mukaish & badla", "Embroidery", r"mukaish|mukesh|badla"),
    ("mirror-work", "Mirror work", "Embroidery", r"mirror|sheesha|shisha|abla\b"),
    ("aari", "Aari", "Embroidery", r"aari\b"),
    ("kantha", "Kantha", "Embroidery", r"kantha"),
    ("phulkari", "Phulkari", "Embroidery", r"phulkari"),
    ("kashmiri", "Kashmiri (sozni & kashida)", "Embroidery", r"sozni|kashida\w*|kashmiri"),
    ("kutch", "Kutch & Banjara", "Embroidery", r"kutch\w*|kachchh\w*|banjara|rabari"),
    ("thread-resham", "Thread & resham", "Embroidery", r"thread\s?work|resham|cross[- ]?stitch|french\s?knot"),
    ("sequins", "Sequins", "Embroidery", r"sequin\w*|sequen\w*|sitara"),
    ("beads-stones", "Beads, pearls & stones", "Embroidery", r"bead\w*|pearl\w*|moti\b|cut\s?dana|cutdana|kundan|crystal\w*|stone\s?work"),
    ("cutwork-applique", "Cutwork, applique & schiffli", "Embroidery", r"cut\s?work|appliqu\w*|patch\s?work|schiffli|eyelet|hakoba"),
    ("hand-block", "Hand block print", "Print & dye", r"hand[- ]?block|block[- ]?print\w*|blockprint\w*"),
    ("sanganeri", "Sanganeri", "Print & dye", r"sanganer\w*"),
    ("bagru", "Bagru", "Print & dye", r"bagru"),
    ("dabu", "Dabu", "Print & dye", r"dabu\b|daboo"),
    ("kalamkari", "Kalamkari", "Print & dye", r"kalamkari|kalmkari"),
    ("ajrakh", "Ajrakh", "Print & dye", r"ajrakh?\b"),
    ("bagh", "Bagh print", "Print & dye", r"bagh\s?print"),
    ("bandhani", "Bandhani", "Print & dye", r"bandhan[ie]|bandhej|bandej"),
    ("leheriya", "Leheriya", "Print & dye", r"lehe?riya|leheria|lehriya"),
    ("shibori", "Shibori & tie-dye", "Print & dye", r"tie[- ]?(?:and[- ])?dye\w*|shibori|clamp[- ]dye"),
    ("hand-painted", "Hand painted", "Print & dye", r"hand[- ]?paint\w*"),
    ("madhubani", "Madhubani", "Print & dye", r"madhubani"),
    ("pichwai", "Pichwai", "Print & dye", r"pichwai"),
    ("ikat", "Ikat", "Weave", r"ikat|ikkat|pochampall?y"),
    ("patola", "Patola", "Weave", r"patola"),
    ("banarasi", "Banarasi", "Weave", r"banaras\w*|benaras\w*"),
    ("kanjeevaram", "Kanjeevaram", "Weave", r"kanj[ie]e?varam|kanchipuram|kanchi\s?pattu"),
    ("paithani", "Paithani", "Weave", r"paithani"),
    ("jamdani", "Jamdani", "Weave", r"jamdani"),
    ("chanderi", "Chanderi", "Weave", r"chanderi"),
    ("maheshwari", "Maheshwari", "Weave", r"maheshwari(?!\s+in\b)"),  # "<Name> Maheshwari in ..." = a person
    ("kota-doria", "Kota doria", "Weave", r"kota\s?doriy?a|kota\b"),
    ("khadi", "Khadi", "Weave", r"khadi"),
    ("handloom", "Handloom (other)", "Weave", r"handloom|hand[- ]?woven"),
    ("jacquard-brocade", "Jacquard & brocade", "Weave", r"jacquard|jaquard|brocade"),
]
CRAFT_BUCKETS = [  # only when no craft matched; first match wins
    ("embroidered", "Embroidered (other)", r"embroider\w*|embelli\w*|hand\s?work|handwork"),
    ("printed", "Printed (other)", r"print\w*|floral|paisley|geometric|abstract|stripe\w*|check\w*|polka|motif\w*"),
    ("solid", "Solid & plain", r"solid|plain"),
]
NOT_SPECIFIED = ("not-specified", "Not specified")
# "Bandhani print", "Ajrakh pattern" = printed imitations: not the craft, goes to Printed (other)
_CRAFT_IMITATION = re.compile(r"\b(?:bandhan[ie]|bandhej|bandej|lehe?riya|leheria|ajrakh?|ikat|ikkat|patola|kalamkari|kalmkari|"
                              r"shibori|tie[- ]?dye\w*|chikan\w*|madhubani|pichwai|banaras\w*|benaras\w*)\s?(?:style\s)?"
                              r"(?:print\w*|pattern\w*|design\w*|inspired)\b", re.I)
_CRAFT_RX = [(i, re.compile(r"\b(?:" + p + r")", re.I)) for i, _, _, p in CRAFT_RULES]
_BUCKET_RX = [(i, re.compile(r"\b(?:" + p + r")", re.I)) for i, _, p in CRAFT_BUCKETS]
CRAFT_IDS = [i for i, _, _, _ in CRAFT_RULES]
CRAFT_NAME = {i: n for i, n, _, _ in CRAFT_RULES}
CRAFT_NAME.update({i: n for i, n, _ in CRAFT_BUCKETS})
CRAFT_NAME[NOT_SPECIFIED[0]] = NOT_SPECIFIED[1]
CRAFT_ORDER = [CRAFT_NAME[i] for i in CRAFT_NAME]
# Only these categories get crafts (tiles, craft pages, Others). Bottoms, jackets, accessories etc. stay out.
CRAFT_CATEGORIES = {"Kurtas", "Kurta sets", "Sarees", "Co-ord sets", "Dresses", "Tops & shirts", "Lehengas"}
CRAFT_OVERRIDES_FILE = "data/craft_overrides.json"
CRAFT_INFO_FILE = "data/crafts.json"


def match_crafts(text):
    """Craft ids named in a piece of text (imitation prints removed first)."""
    text = _CRAFT_IMITATION.sub(" print ", text or "")
    return [i for i, rx in _CRAFT_RX if rx.search(text)]


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


_OVERRIDES = None


def product_crafts(r):
    """Craft ids for one record: title/type first, then description, then hand fixes, else one bucket."""
    global _OVERRIDES
    if _OVERRIDES is None:
        _OVERRIDES = {k: v for k, v in _load_json(CRAFT_OVERRIDES_FILE, {}).items() if not k.startswith("_")}
    if r.get("category") not in CRAFT_CATEGORIES:
        return []
    text = NOISE.sub(" ", f"{r.get('title', '')} ; {r.get('product_type', '')}")
    ids = match_crafts(text)
    if not ids:  # crafts found in the description at scrape time, stored as craft:<id>
        ids = [v for g, _, v in (x.partition(":") for x in (r.get("desc_attrs") or "").split("|"))
               if g == "craft" and v in CRAFT_NAME]
    fix = _OVERRIDES.get(r.get("url") or "")
    if fix:
        drop = set(fix.get("remove", []))
        ids = [i for i in ids if i not in drop] + [i for i in fix.get("add", []) if i not in ids]
    ids = [i for i in ids if i in CRAFT_IDS]
    if ids:
        return ids
    bucket_text = _CRAFT_IMITATION.sub(" print ", text)
    for i, rx in _BUCKET_RX:
        if rx.search(bucket_text):
            return [i]
    return [NOT_SPECIFIED[0]]


def to_num(x):
    if x in (None, ""):
        return None
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def disc(price, mrp):
    if price and mrp and mrp > price:
        return round((mrp - price) / mrp * 100)
    return 0


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------
def parse_shopify_product(p, base, source):
    opts = [o.get("name", "").strip().lower() for o in p.get("options", [])]
    size_idx = next((i for i, n in enumerate(opts) if is_size_option(n)), None)
    col_idx = next((i for i, n in enumerate(opts) if is_colour_option(n)), None)

    variants = p.get("variants", [])
    prices = [to_num(v.get("price")) for v in variants if to_num(v.get("price"))]
    mrps = [to_num(v.get("compare_at_price")) for v in variants
            if to_num(v.get("compare_at_price"))]
    price = min(prices) if prices else None
    mrp = max(mrps) if mrps else price

    def opt(v, i):
        return v.get(f"option{i + 1}") if i is not None else None

    sizes_all, sizes_avail, colours = [], [], []
    for v in variants:
        s = opt(v, size_idx)
        if s and s not in sizes_all:
            sizes_all.append(s)
        if s and v.get("available") and s not in sizes_avail:
            sizes_avail.append(s)
        c = opt(v, col_idx)
        if c and c not in colours:
            colours.append(c)

    tags = p.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    imgs = p.get("images") or []
    return {
        "source": source,
        "category": classify(p.get("title", ""), p.get("product_type", ""), " ".join(tags)),
        "product_type": p.get("product_type", ""),
        "product_id": str(p.get("id")),
        "title": p.get("title", "").strip(),
        "brand": p.get("vendor") or source,
        "url": f"{base.rstrip('/')}/products/{p.get('handle')}",
        "price": price,
        "mrp": mrp,
        "discount_pct": disc(price, mrp),
        "sizes_available": "|".join(normalise_sizes(sizes_avail)),
        "sizes_all": "|".join(normalise_sizes(sizes_all)),
        "colour": colour_for(colours[0] if colours else "", p.get("title", "")),
        "colour_raw": "|".join(colours),
        "in_stock": any(v.get("available") for v in variants),
        "image": imgs[0]["src"] if imgs else "",
        "tags": "|".join(tags),
        "desc_attrs": desc_attrs(p.get("body_html")),
        "published_at": p.get("published_at") or p.get("created_at") or "",
        "scraped_at": now(),
    }


def scrape_shopify(f, cfg):
    base = cfg["base"].rstrip("/")
    out, page = [], 1
    while True:
        try:
            r = f.get(f"{base}/products.json", params={"limit": 250, "page": page})
            products = r.json().get("products", [])
        except Exception as e:
            if page == 1:
                raise
            # Shopify stops paging after page 100 (25,000 products); keep what we have
            print(f"  stopped at page {page} ({e}); keeping {len(out)} products")
            break
        if not products:
            break
        for p in products:
            if SKIP_TYPES.search(p.get("product_type", "") + " " + p.get("title", "")):
                continue
            out.append(parse_shopify_product(p, base, cfg["source"]))
        print(f"  page {page}: {len(products)} products")
        if len(products) < 250:
            break
        page += 1
    return out


# ---------------------------------------------------------------------------
# WooCommerce (WordPress shops): public Store API, /wp-json/wc/store/v1/products
# ---------------------------------------------------------------------------
def _woo_money(prices, key):
    v = (prices or {}).get(key)
    if v in (None, ""):
        return None
    try:
        return int(v) / (10 ** int((prices or {}).get("currency_minor_unit", 2)))
    except (TypeError, ValueError):
        return None


def parse_woo_product(p, source):
    prices = p.get("prices") or {}
    price = _woo_money(prices, "price")
    mrp = _woo_money(prices, "regular_price") or price
    sizes, colours = [], []
    for a in p.get("attributes") or []:
        name = (a.get("name") or "").lower()
        terms = [t.get("name", "") for t in a.get("terms") or []]
        if "size" in name:
            sizes += terms
        elif "colo" in name:
            colours += terms
    cats = " ".join(c.get("name", "") for c in p.get("categories") or [])
    title = BeautifulSoup(p.get("name") or "", "html.parser").get_text().strip()
    imgs = p.get("images") or []
    in_stock = bool(p.get("is_in_stock", True))
    sz = normalise_sizes(sizes)
    return {
        "source": source,
        "category": classify(title, cats),
        "product_type": cats,
        "product_id": str(p.get("id")),
        "title": title,
        "brand": source,
        "url": p.get("permalink") or "",
        "price": price,
        "mrp": mrp,
        "discount_pct": disc(price, mrp),
        # the listing API doesn't say which sizes are in stock, so show all
        "sizes_available": "|".join(sz) if in_stock else "",
        "sizes_all": "|".join(sz),
        "colour": colour_for(colours[0] if colours else "", title),
        "colour_raw": "|".join(colours),
        "in_stock": in_stock,
        "image": imgs[0].get("src", "") if imgs else "",
        "tags": "|".join(t.get("name", "") for t in p.get("tags") or []),
        "desc_attrs": desc_attrs((p.get("short_description") or "") + " " + (p.get("description") or "")),
        "published_at": "",
        "scraped_at": now(),
    }


def scrape_woocommerce(f, cfg, max_pages=200):
    base = cfg["base"].rstrip("/")
    out, page = [], 1
    while page <= max_pages:
        r = f.get(f"{base}/wp-json/wc/store/v1/products", params={"per_page": 100, "page": page})
        items = r.json()
        if not isinstance(items, list) or not items:
            break
        out += [parse_woo_product(p, cfg["source"]) for p in items if p.get("prices")]
        print(f"  page {page}: {len(items)} products")
        if len(items) < 100:
            break
        page += 1
    return out


# ---------------------------------------------------------------------------
# Zlaata (server-rendered HTML)
# Product links look like: /zlaata-india/<cat>/<slug>/<id>/select
# Price text looks like:   "₹1649 ₹3188 (48% OFF)"  or  "₹2299"
# Parsing is anchored on the link pattern, not CSS class names, so it
# survives most theme changes.
# ---------------------------------------------------------------------------
ZLAATA_LINK = re.compile(r"/zlaata-india/([^/]+)/[^/]+/(\d+)/select/?$")
RUPEE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")


def find_card(a):
    """Walk up from a product link to the smallest ancestor holding a ₹ price."""
    node = a
    for _ in range(6):
        if node.parent is None:
            break
        node = node.parent
        if "₹" in node.get_text(" ", strip=True):
            return node
    return a


def parse_zlaata_page(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    seen, items = set(), {}
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        m = ZLAATA_LINK.search(urlparse(href).path)
        if not m:
            continue
        zcat, pid = m.group(1), m.group(2)
        card = find_card(a)
        rec = items.get(pid)
        if rec is None:
            rec = {"source": "Zlaata", "category": "", "product_type": zcat, "product_id": pid,
                   "title": "", "brand": "Zlaata", "url": href, "price": None,
                   "mrp": None, "discount_pct": 0, "sizes_available": "",
                   "sizes_all": "", "colour": "", "colour_raw": "", "in_stock": True,
                   "image": "", "tags": "", "scraped_at": now()}
            items[pid] = rec
        # title: link text, else img alt, else title attr
        text = a.get_text(" ", strip=True)
        if text and "₹" not in text and len(text) > len(rec["title"]):
            rec["title"] = text
        img = (a.find("img") or card.find("img"))
        if img and not rec["image"]:
            src = img.get("data-src") or img.get("src") or ""
            if src and not src.startswith("data:"):
                rec["image"] = urljoin(page_url, src)
            if not rec["title"] and img.get("alt"):
                rec["title"] = img["alt"].strip()
        if rec["price"] is None and pid not in seen:
            nums = [to_num(n) for n in RUPEE.findall(card.get_text(" ", strip=True))]
            nums = [n for n in nums if n]
            if nums:
                rec["price"] = nums[0]
                rec["mrp"] = nums[1] if len(nums) > 1 and nums[1] > nums[0] else nums[0]
                rec["discount_pct"] = disc(rec["price"], rec["mrp"])
                seen.add(pid)
        ct = card.get_text(" ", strip=True).lower()
        if "sold out" in ct or "out of stock" in ct:
            rec["in_stock"] = False
    for rec in items.values():
        if not rec["title"]:  # fall back to slug
            slug = urlparse(rec["url"]).path.rstrip("/").split("/")[-3]
            rec["title"] = slug.replace("-", " ").title()
        rec["colour"] = colour_for("", rec["title"])
        rec["category"] = classify(rec["title"], hint=ZLAATA_CATEGORY.get(rec["product_type"]))
    return list(items.values())


def scrape_zlaata(f, cfg, max_pages=150):
    out, ids = [], set()
    for url in cfg["urls"]:
        page = 1
        while page <= max_pages:
            r = f.get(url, params={"page": page})
            items = parse_zlaata_page(r.text, r.url)
            new = [i for i in items if i["product_id"] not in ids]
            print(f"  {urlparse(url).path.rsplit('/', 1)[-1]} page {page}: {len(new)} new products")
            if not new:
                break
            ids.update(i["product_id"] for i in new)
            out.extend(new)
            page += 1
    return out


# ---------------------------------------------------------------------------
_PHOTO = None
_img_key = lambda u: re.sub(r"^https?:", "", u).split("?")[0]
_PHOTO_CAT = {"Kurta set": "Kurta sets", "Saree": "Sarees", "Lehenga": "Lehengas", "Kurta": "Kurtas", "Dress": "Dresses",
              "Co-ord set": "Co-ord sets", "Top": "Tops & shirts", "Jacket": "Jackets & overlays"}


_GENDER = None
_WOMEN_TITLE = re.compile(r"\b(women|womens|women's|woman|ladies|lady|her|she)\b", re.I)


def photo_shows_man(r):
    """Free image check (data/image_gender.json.gz): photo >= 85% a man, and the title doesn't say women.
    Wrongly hidden? Put the product link in data/category_overrides.json."""
    global _GENDER
    if _GENDER is None:
        try:
            with gzip.open("data/image_gender.json.gz", "rt") as fh:
                _GENDER = {_img_key(k): v for k, v in json.load(fh).items()}
        except (OSError, ValueError):
            _GENDER = {}
    g = _GENDER.get(_img_key(r.get("image") or ""))
    if not (g and g[0] >= 0.85) or _WOMEN_RX.search(r.get("title") or ""):
        return False
    s = f"{r.get('tags') or ''}|{r.get('product_type') or ''}"
    t = {x.strip().lower() for x in (r.get("tags") or "").split("|")}
    if _MEN_RX.search(s) and not (t & _WOMEN_TAGS):  # photo + a men tag (Tjori "Gender_Men"); men+women tags = unisex, keep
        return True
    # photo alone: only for brands that sell menswear, and no women/unisex tag on the product.
    # Women-only labels (Gulabo Jaipur, Sheetal Batra, Dupatta Bazaar...) never lose a product on the photo alone.
    return r.get("source") in _MEN_BRANDS and not _WOMEN_RX.search(s)


_AGE = None


def photo_shows_child(r):
    """Free image check (data/image_age.json.gz: [p_child, p_adult, p_innerwear, p_none]): photo >= 85% a child,
    only for brands that sell kidswear, and no women/adult word on the product. Wrongly hidden? -> category_overrides.json."""
    global _AGE
    if _AGE is None:
        try:
            with gzip.open("data/image_age.json.gz", "rt") as fh:
                _AGE = {_img_key(k): v for k, v in json.load(fh).items()}
        except (OSError, ValueError):
            _AGE = {}
    a = _AGE.get(_img_key(r.get("image") or ""))
    if not (a and a[0] >= 0.85) or r.get("source") not in _KID_BRANDS:
        return False
    return not _WOMEN_RX.search(f"{r.get('tags') or ''}|{r.get('product_type') or ''}|{r.get('title') or ''}")


def placed_from_description_or_photo(r):
    """For a product the title/type rules couldn't place: the description's first line,
    then the free image check (data/image_checks.json.gz) when it is >= 90% sure of a garment."""
    global _PHOTO
    for x in (r.get("desc_attrs") or "").split("|"):
        if x.startswith("cat:") and x[4:] in CATEGORIES:
            return x[4:]
    if _PHOTO is None:
        try:
            with gzip.open("data/image_checks.json.gz", "rt") as fh:
                _PHOTO = {_img_key(k): v for k, v in json.load(fh).items()}
        except (OSError, ValueError):
            _PHOTO = {}
    res = _PHOTO.get(_img_key(r.get("image") or ""))
    if res and res[1] >= 0.9 and res[0] in _PHOTO_CAT:
        return _PHOTO_CAT[res[0]]
    return None


_MEN_BRANDS = set()
_KID_BRANDS = set()
BRAND_LINES = "data/brand_lines.json"


def write_out(rows, out):
    seen, uniq = set(), []
    _MEN_BRANDS.update(r.get("source") for r in rows
                       if tagged_menswear(r.get("tags"), r.get("product_type"), r.get("title")))
    _KID_BRANDS.update(r.get("source") for r in rows
                       if r.get("category") == "Kidswear" or tagged_kidswear(r.get("tags"), r.get("sizes_all")))
    # remembered across runs: the saved record drops hidden rows, so a rebuild alone can't see them
    try:
        with open(BRAND_LINES, encoding="utf-8") as fh:
            saved = json.load(fh)
        _MEN_BRANDS.update(saved.get("menswear", [])); _KID_BRANDS.update(saved.get("kidswear", []))
    except (OSError, ValueError):
        pass
    _MEN_BRANDS.discard(None); _KID_BRANDS.discard(None)
    with open(BRAND_LINES, "w", encoding="utf-8") as fh:
        json.dump({"_readme": "Brands that also sell menswear / kidswear: only these lose products on the photo check alone.",
                   "menswear": sorted(_MEN_BRANDS), "kidswear": sorted(_KID_BRANDS)}, fh, indent=1)
    for r in rows:  # never write the same product twice
        ov = category_override(r.get("url"))
        if ov:
            r["category"] = ov
        elif tagged_menswear(r.get("tags"), r.get("product_type"), r.get("title")):
            r["category"] = "Menswear"
        elif tagged_kidswear(r.get("tags"), r.get("sizes_all")):
            r["category"] = "Kidswear"
        elif photo_shows_man(r):
            r["category"] = "Menswear"
        elif photo_shows_child(r):
            r["category"] = "Kidswear"
        elif r["category"] == "Other":
            r["category"] = placed_from_description_or_photo(r) or "Other"
        if r["category"] in EXCLUDED_CATEGORIES or r["source"] in REMOVED_SOURCES:
            continue
        keep = _SOURCE_KEEP.get(r["source"])
        if keep and not keep.search(f"{r.get('product_type') or ''} {r.get('title') or ''}"):
            continue
        key = (r["source"], str(r["product_id"]))
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    rows = uniq
    order = {c: i for i, c in enumerate(CATEGORIES)}
    rows = sorted(rows, key=lambda r: (r["source"], order.get(r["category"], 99)))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out + ".csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # the scraper's own record, compressed (~12x smaller) so the repo stays small
    with gzip.open(out + ".json.gz", "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
    write_site_data(rows, SITE_DATA)
    write_brand_data(rows)
    print(f"\n{len(rows)} products -> {out}.json.gz / {out}.csv")
    for src in sorted({r["source"] for r in rows}):
        mine = [r for r in rows if r["source"] == src]
        cats = {}
        for r in mine:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        print(f"  {src}: {len(mine)}  (" + ", ".join(
            f"{c} {n}" for c, n in sorted(cats.items(), key=lambda x: order.get(x[0], 99))) + ")")


# ---------------------------------------------------------------------------
# Site data: a compact file the website loads (docs/products.json).
# Short format + lookup tables keeps it small; brands are interleaved so the
# default "Recommended" view mixes brands instead of showing one at a time.
# ---------------------------------------------------------------------------
def mixed_order(rows):
    by_src = {}
    for r in rows:
        by_src.setdefault(r["source"], []).append(r)
    for lst in by_src.values():  # in stock, newest, then biggest discount first
        lst.sort(key=lambda r: (not r.get("in_stock"), _neg_date(r.get("published_at")),
                                -(r.get("discount_pct") or 0)))
    queues = sorted(by_src.values(), key=len, reverse=True)
    out, i = [], 0
    while queues:
        nxt = []
        for q in queues:
            if i < len(q):
                out.append(q[i])
            if i + 1 < len(q):
                nxt.append(q)
        queues, i = nxt, i + 1
    return out


def _neg_date(d):
    # newest first: invert the ISO date string's characters for descending sort
    return "".join(chr(0x10FFFF - ord(c)) for c in (d or "")[:19]) if d else "\U0010ffff"


# ---------------------------------------------------------------------------
# Colour versions: many brands list each colour of one design as a separate
# product ("Gerua Sea Green Printed Kaftan", "Gerua Blue Printed Kaftan").
# Same brand + category + price + title apart from the colour = one card with
# colour dots. Big matches (generic titles like "Printed Cotton Kurta") are
# different designs, so they are left alone.
# ---------------------------------------------------------------------------
GROUP_MAX = 8
_SHADE_WORDS = ["light", "dark", "sea", "dusty", "deep", "pale", "bright", "hot", "baby", "royal",
                "powder", "bottle", "coloured", "colored", "colour", "color", "shade"]
_COLOUR_STRIP = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(
    {w for ws in COLOUR_WORDS.values() for w in ws} | set(_SHADE_WORDS), key=len, reverse=True)) + r")\b", re.I)


def design_key(r):
    t = (r.get("title") or "").lower().replace(r["source"].lower(), " ")
    t = _COLOUR_STRIP.sub(" ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return (r["source"], r.get("category"), t, round(float(r["price"])))


def group_colours(rows):
    """[(primary, [other colour versions])] in the given order."""
    groups, order = {}, []
    for r in rows:
        k = design_key(r)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    out = []
    for k in order:
        g = groups[k]
        if len(g) == 1 or len(g) > GROUP_MAX or not k[2]:
            out += [(r, []) for r in g]
        else:
            g = sorted(g, key=lambda r: not r.get("in_stock"))  # in-stock version shown first
            out.append((g[0], g[1:]))
    return out


FIRST_PART = 1500
SITE_DATA = "docs/products.json"   # what the website loads


def write_site_data(rows, path):
    sources, src_ix = [], {}
    for r in rows:
        if r["source"] not in src_ix:
            src_ix[r["source"]] = len(sources)
            base = re.match(r"https?://[^/]+", r["url"] or "")
            sources.append({"n": r["source"], "b": base.group(0) if base else ""})
    cats = [c for c in CATEGORIES if c not in EXCLUDED_CATEGORIES] + sorted({r["category"] for r in rows} - set(CATEGORIES))
    cat_ix = {c: i for i, c in enumerate(cats)}
    colours = list(COLOUR_WORDS) + ["Other"]
    col_ix = {c: i for i, c in enumerate(colours)}
    attrs, attr_ix = [], {}
    products = []
    for r, others in group_colours(mixed_order([r for r in rows if r.get("price")])):
        si = src_ix[r["source"]]
        base = sources[si]["b"]
        url = r["url"] or ""
        if base and url.startswith(base):
            url = url[len(base):]  # store the path only
        img = re.sub(r"^https?:", "", r.get("image") or "")
        img = re.sub(r"[?&]v=\d+$", "", img)  # cache-buster not needed
        mask = 0
        for z in (r.get("sizes_available") or "").split("|"):
            if z in SIZE_ORDER:
                mask |= 1 << SIZE_ORDER.index(z)
        price = round(float(r["price"]))
        mrp = round(float(r.get("mrp") or price))
        ai = []
        for a in product_attrs(r):
            if a not in attr_ix:
                attr_ix[a] = len(attrs)
                attrs.append(a)
            ai.append(attr_ix[a])
        # other colour versions: [colour, url path, image, in stock]
        vs = []
        for o in others:
            ou = o["url"] or ""
            if base and ou.startswith(base):
                ou = ou[len(base):]
            oi = re.sub(r"[?&]v=\d+$", "", re.sub(r"^https?:", "", o.get("image") or ""))
            vs.append([col_ix.get(o.get("colour") or "Other", len(colours) - 1), ou, oi, 1 if o.get("in_stock") else 0])
            for z in (o.get("sizes_available") or "").split("|"):
                if z in SIZE_ORDER:
                    mask |= 1 << SIZE_ORDER.index(z)
        stock = 1 if r.get("in_stock") or any(v[3] for v in vs) else 0
        products.append([si, cat_ix.get(r["category"], len(cats) - 1), html.unescape(r["title"]), url, price,  # some stores send "&amp;"
                         mrp if mrp > price else 0, col_ix.get(r.get("colour") or "Other", len(colours) - 1),
                         mask, stock, img, ai, vs])
    data = {"v": 2, "updated": now(), "sources": sources, "cats": cats, "colours": colours,
            "sizes": SIZE_ORDER, "attrs": attrs, "attr_labels": dict(ATTR_LABELS, craft="Craft"),
            "attr_order": dict({g: [v for v, _ in rules] + (["Ready to wear"] if g == "stitch" else [])
                                for g, rules in ATTR_RULES.items()}, craft=CRAFT_ORDER),
            "groups_for": GROUPS_FOR,
            "fields": ["source", "cat", "title", "url", "price", "mrp", "colour", "sizes", "stock", "image", "attrs", "colour_versions"],
            "p": products}
    data["total"] = len(products)
    data["listings"] = len(products) + sum(len(p[11]) for p in products)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    # first part: the top of the brand-mixed list, so the page shows products instantly
    first = dict(data, p=products[:FIRST_PART], part="first")
    with open(path.replace(".json", "-first.json"), "w", encoding="utf-8") as fh:
        json.dump(first, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"site data: {len(products)} cards ({data['listings']} listings, colour versions grouped) -> {path} (+ first {min(FIRST_PART, len(products))} in a quick-load file)")
    write_craft_data(products, attrs, os.path.join(os.path.dirname(path), "crafts.json"))


def write_craft_data(products, attrs, path):
    """Craft pages: id, name, family, write-up, sources and in-stock count (docs/crafts.json)."""
    info = {k: v for k, v in _load_json(CRAFT_INFO_FILE, {}).items() if not k.startswith("_")}
    ix = {a[len("craft:"):]: i for i, a in enumerate(attrs) if a.startswith("craft:")}
    count = {n: 0 for n in CRAFT_NAME.values()}
    for p in products:
        if p[8]:
            for n, i in ix.items():
                if i in p[10]:
                    count[n] += 1
    family = {i: f for i, _, f, _ in CRAFT_RULES}
    out = []
    for cid, name in CRAFT_NAME.items():
        e = info.get(cid, {})
        out.append({"id": cid, "name": name, "family": family.get(cid, "Other"), "bucket": cid not in family,
                    "region": e.get("region", ""), "blurb": e.get("blurb", ""), "sources": e.get("sources", []),
                    "in_stock": count.get(name, 0)})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"updated": now(), "min_styles": 20, "crafts": out}, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"craft data: {sum(1 for c in out if not c['bucket'] and c['in_stock'] >= 20)} craft pages -> {path}")


CRAFTS = {"Chikankari", "Gota patti", "Zari & zardozi", "Mirror work", "Thread & resham", "Sequins",
          "Cutwork & applique", "Hand block print", "Ajrakh", "Bandhani & leheriya", "Tie-dye & shibori",
          "Ikat", "Hand painted", "Woven & jacquard"}
STORIES_FILE = "data/brand_stories.json"   # short brand stories, written from each brand's own site


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def write_brand_data(rows, path="docs/brands.json"):
    """Per-brand facts for the home page and brand directory."""
    def load(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}
    info, stories = load(BRANDS_FILE), load(STORIES_FILE)
    by = {}
    for r in rows:
        by.setdefault(r["source"], []).append(r)
    out = []
    for name, rs in by.items():
        live = [r for r in rs if r.get("in_stock") and r.get("price")] or [r for r in rs if r.get("price")]
        prices = sorted(float(r["price"]) for r in live)
        cats, crafts = {}, {}
        for r in live:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
            for a in product_attrs(r):
                g, v = a.split(":", 1)
                if g != "craft" and v in CRAFTS:
                    crafts[v] = crafts.get(v, 0) + 1
        imgs, seen_cat = [], set()
        for r in sorted(live, key=lambda r: _neg_date(r.get("published_at"))):
            if r.get("image") and r["category"] not in seen_cat and len(imgs) < 4:
                imgs.append(re.sub(r"^https?:", "", r["image"]))
                seen_cat.add(r["category"])
        i, st = info.get(name, {}), stories.get(name, {})
        base = re.match(r"https?://[^/]+", rs[0].get("url") or "")
        out.append({
            "n": name, "slug": slugify(name), "site": i.get("base") or (base.group(0) if base else ""),
            "styles": len(rs), "in_stock": sum(1 for r in rs if r.get("in_stock")),
            "price_min": round(prices[0]) if prices else None,
            "price_med": round(prices[len(prices) // 2]) if prices else None,
            "price_max": round(prices[-1]) if prices else None,
            "cats": [c for c, _ in sorted(cats.items(), key=lambda x: -x[1])[:5]],
            "crafts": [c for c, n in sorted(crafts.items(), key=lambda x: -x[1]) if n >= 5][:5],
            "images": imgs, "logo": i.get("logo", ""), "instagram": i.get("instagram", ""),
            "story": st.get("story", ""), "founders": st.get("founders", ""), "founded": st.get("founded", ""),
            "based": st.get("based", ""), "story_source": st.get("source", ""),
        })
    out.sort(key=lambda b: b["n"].lower())
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"updated": now(), "brands": out}, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"brand data: {len(out)} brands -> {path}")


def load_previous(out):
    """Last run's record. Older versions kept it uncompressed in docs/."""
    for path in (out + ".json.gz", out + ".json", "docs/listings.json"):
        try:
            if path.endswith(".gz"):
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    return json.load(fh)
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            continue
    return []


def renormalise(rows):
    """Re-apply category + colour rules to already-scraped rows."""
    seen, outr = set(), []
    for r in rows:
        key = (r["source"], str(r["product_id"]))
        if key in seen:  # old files could hold one product under 2 categories
            continue
        seen.add(key)
        raw = r.get("colour_raw")
        if raw is None:
            raw = r.get("colour", "")
        r["colour_raw"] = raw
        r["colour"] = colour_for(raw.split("|")[0] if raw else "", r["title"])
        for k in ("sizes_available", "sizes_all"):
            r[k] = "|".join(normalise_sizes((r.get(k) or "").split("|")))
        ptype = r.get("product_type", "")
        if r["source"] == "Zlaata":
            if not ptype:
                m = ZLAATA_LINK.search(urlparse(r["url"]).path)
                ptype = m.group(1) if m else ""
            r["product_type"] = ptype
            r["category"] = classify(r["title"], hint=ZLAATA_CATEGORY.get(ptype))
        else:
            r["product_type"] = ptype
            r["category"] = classify(r["title"], ptype, r.get("tags", "").replace("|", " "))
        outr.append(r)
    return outr


# ---------------------------------------------------------------------------
# Brand info for the brands page: description, logo, Instagram and the text
# of the brand's own About / Our story page. Refreshed weekly, not every run.
# ---------------------------------------------------------------------------
BRANDS_FILE = "data/brands.json"
BRAND_INFO_DAYS = 7
_ABOUT_WORDS = re.compile(r"about|our[- ]?story|story|founder|journey|who[- ]we[- ]are|our[- ]brand|legacy|heritage|philosophy", re.I)
_ABOUT_SKIP = re.compile(r"privacy|terms|policy|shipping|return|refund|faq|contact|track|career|size[- ]?chart|store[- ]locat|blog|news", re.I)
_ABOUT_GUESSES = ["/pages/about-us", "/pages/about", "/pages/our-story", "/pages/story", "/about-us", "/about"]


def _page_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "form", "svg", "iframe"]):
        t.decompose()
    main = soup.find("main") or soup.find(id=re.compile("MainContent|main", re.I)) or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
    return text[:6000]


def _meta(soup, *names):
    for n in names:
        m = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if m and m.get("content"):
            return m["content"].strip()
    return ""


def brand_info(f, base):
    home = f.get(base + "/").text
    soup = BeautifulSoup(home, "html.parser")
    info = {"base": base, "fetched_at": now(),
            "site_title": (soup.title.get_text(strip=True) if soup.title else "")[:200],
            "description": _meta(soup, "og:description", "description")[:600],
            "image": _meta(soup, "og:image", "og:image:secure_url"),
            "logo": "", "instagram": "", "about_url": "", "about_text": ""}
    # 1) the logo shown in the site header, 2) the logo in the page's structured data
    img = soup.select_one(".header__heading-logo, header a[href='/'] img, header img[class*=logo i], "
                          "img[class*=logo i], img[alt*=logo i], header img")
    if img:
        src = img.get("src") or img.get("data-src") or (img.get("srcset") or "").split(" ")[0]
        if src and not src.startswith("data:"):
            info["logo"] = urljoin(base + "/", src)
    if not info["logo"]:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "")
            except ValueError:
                continue
            for item in d if isinstance(d, list) else [d]:
                if isinstance(item, dict) and isinstance(item.get("logo"), (str, dict)):
                    lg = item["logo"]
                    info["logo"] = lg if isinstance(lg, str) else lg.get("url", "")
                    break
            if info["logo"]:
                break
    ig = soup.find("a", href=re.compile(r"instagram\.com/[^/?#]+", re.I))
    if ig:
        info["instagram"] = ig["href"].split("?")[0]
    # the brand's own About / Story page
    cands = []
    for a in soup.find_all("a", href=True):
        href, label = a["href"], a.get_text(" ", strip=True)
        full = urljoin(base + "/", href)
        if urlparse(full).netloc != urlparse(base).netloc or _ABOUT_SKIP.search(href):
            continue
        if _ABOUT_WORDS.search(href) or _ABOUT_WORDS.search(label):
            if full not in cands:
                cands.append(full)
    cands += [base + g for g in _ABOUT_GUESSES if base + g not in cands]
    texts, guesses = [], {base + g for g in _ABOUT_GUESSES}
    for url in cands[:6]:
        if texts and url in guesses:
            break
        try:
            t = _page_text(f.get(url).text)
        except Exception:
            continue
        if len(t) > 300:
            info["about_url"] = info["about_url"] or url
            texts.append(t)
            if len(texts) == 2:
                break
    info["about_text"] = " ||| ".join(texts)[:9000]
    return info


def update_brand_info(f):
    try:
        with open(BRANDS_FILE, encoding="utf-8") as fh:
            brands = json.load(fh)
    except (OSError, ValueError):
        brands = {}
    cutoff = time.time() - BRAND_INFO_DAYS * 86400
    print("\n[brand info]")
    for cfg in SOURCES:
        name = cfg["source"]
        base = (cfg.get("base") or "https://www.zlaata.com").rstrip("/")
        old = brands.get(name) or {}
        try:
            fresh = datetime.fromisoformat(old.get("fetched_at", "")).timestamp() > cutoff
        except ValueError:
            fresh = False
        if fresh and old.get("base") == base:
            continue
        try:
            brands[name] = brand_info(f, base)
            print(f"  {name}: about page {'found' if brands[name]['about_text'] else 'not found'}")
        except Exception as e:
            print(f"  {name}: FAILED {e}", file=sys.stderr)
    os.makedirs(os.path.dirname(BRANDS_FILE), exist_ok=True)
    with open(BRANDS_FILE, "w", encoding="utf-8") as fh:
        json.dump(brands, fh, ensure_ascii=False, indent=1, sort_keys=True)


def probe(urls):
    """Which platform each site runs on (no scraping): python scraper.py --probe URL ..."""
    f = Fetcher()
    for u in urls:
        base = u.strip().strip("/").lstrip("/")
        if not base.startswith("http"):
            base = "https://" + base
        base = re.match(r"https?://[^/]+", base).group(0)
        res = "unknown"
        for kind, path, key in (("shopify", "/products.json?limit=3", "products"),
                                ("woocommerce", "/wp-json/wc/store/v1/products?per_page=3", None)):
            try:
                r = f.get(base + path)
                d = r.json()
                items = d.get(key) if key else d
                if isinstance(items, list) and items:
                    p = items[0]
                    price = (p.get("variants") or [{}])[0].get("price") if kind == "shopify" else (p.get("prices") or {}).get("price")
                    res = f"{kind.upper()} OK  e.g. {(p.get('title') or p.get('name') or '')[:50]!r} price={price}"
                    break
                res = f"{kind}: empty"
            except Exception as e:
                res = f"{kind}: {str(e)[:90]}"
        print(f"PROBE {base} -> {res}")


def main():
    sys.stdout.reconfigure(line_buffering=True)  # show progress live in the GitHub log
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/listings",
                    help="record path without extension (default data/listings)")
    ap.add_argument("--probe", nargs="+", help="only check which platform these sites use")
    ap.add_argument("--renormalise", action="store_true",
                    help="don't scrape; re-apply category + colour rules to the existing file")
    args = ap.parse_args()
    if args.probe:
        probe(args.probe)
        return
    previous = load_previous(args.out)

    if args.renormalise:
        write_out(renormalise(previous), args.out)
        return

    f = Fetcher()
    rows, failed = [], []
    for cfg in SOURCES:
        print(f"[{cfg['source']}]")
        got = []
        try:
            if cfg["type"] == "shopify":
                got = scrape_shopify(f, cfg)
            elif cfg["type"] == "zlaata":
                got = scrape_zlaata(f, cfg)
            elif cfg["type"] == "woocommerce":
                got = scrape_woocommerce(f, cfg)
        except Exception as e:  # keep going if one site fails
            print(f"  FAILED: {e}", file=sys.stderr)
        prices = sorted(r["price"] for r in got if r.get("price"))
        if prices and prices[len(prices) // 2] < 300:
            # e.g. a store priced in US dollars: ₹45 would be wrong, so drop it
            print(f"  SKIPPED: median price {prices[len(prices) // 2]} looks like a non-rupee store")
            got = []
        if not got:
            # Site failed or returned nothing: keep its last good data
            # so the website never suddenly loses a whole brand.
            got = renormalise([r for r in previous if r["source"] == cfg["source"]])
            if got:
                print(f"  keeping {len(got)} products from the last good run")
            failed.append(cfg["source"])
        rows += got

    if not rows:
        print("No products at all - not overwriting the output.", file=sys.stderr)
        sys.exit(1)
    write_out(rows, args.out)
    try:
        update_brand_info(f)
    except Exception as e:  # never let this break the product refresh
        print(f"brand info step failed: {e}", file=sys.stderr)
    if failed:
        print("\nWARNING - no fresh data for: " + ", ".join(failed), file=sys.stderr)


if __name__ == "__main__":
    main()
