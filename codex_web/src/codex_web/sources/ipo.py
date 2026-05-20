import logging
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from .common import USER_AGENT


SEARCH_MAX_PAGE = 3


def get_soup(url, referer=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer or "http://www.ipostock.co.kr/sub03/ipo05.asp",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = "utf-8"
        return BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        logging.warning("[IPO] soup fetch failed: %s", exc)
        return None


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", "", text.replace("\xa0", ""))


def parse_numeric(text):
    if not text or text == "-":
        return 0
    numbers = re.findall(r"\d+", str(text).replace(",", ""))
    return int(numbers[-1]) if numbers else 0


def parse_single_numeric(text):
    if not text or text == "-":
        return 0
    numbers = re.findall(r"\d+", str(text).replace(",", ""))
    return int(numbers[0]) if len(numbers) == 1 else 0


def parse_percent(text):
    if not text or text == "-":
        return 0.0
    clean = re.sub(r"[^\d.]", "", str(text))
    return float(clean) if clean else 0.0


def find_stock_targets(year, target_date_str, max_page=SEARCH_MAX_PAGE):
    base_url = "http://www.ipostock.co.kr/sub03/ipo05.asp"
    found = []
    for page in range(1, max_page + 1):
        soup = get_soup("%s?str1=%s&str2=all&page=%s" % (base_url, year, page))
        if soup is None:
            continue
        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            if target_date_str not in clean_text(cols[0].get_text()):
                continue
            link = cols[1].find("a", href=True)
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link["href"]
            parsed = urlparse(href)
            code = parse_qs(parsed.query).get("code", ["Unknown"])[0]
            list_offer_price = cols[3].get_text(strip=True)
            item = (name, code, href, list_offer_price)
            if name and item not in found:
                found.append(item)
        time.sleep(0.25)
    return found


def get_sibling_value(soup, keyword):
    keyword_clean = clean_text(keyword)
    for td in soup.find_all("td"):
        if keyword_clean in clean_text(td.get_text()):
            next_td = td.find_next_sibling("td")
            if next_td:
                value = next_td.get_text(strip=True)
                if value:
                    return value
    return "-"


def get_shareholder_ratio(soup, keyword):
    target = clean_text(keyword)
    for td in soup.find_all("td"):
        if target not in clean_text(td.get_text()):
            continue
        for sibling in td.find_next_siblings("td"):
            value = sibling.get_text(strip=True)
            if "%" in value:
                return value
    return "-"


def crawl_details(source_href):
    domain = "http://www.ipostock.co.kr"
    source_params = parse_qs(urlparse(source_href).query)

    def build_url(view_file):
        return "%s/view_pg/%s?%s" % (domain, view_file, urlencode(source_params, doseq=True))

    result = {}
    s1 = get_soup(build_url("view_01.asp"))
    if s1:
        result["주요제품"] = get_sibling_value(s1, "주요제품")
        result["주간사"] = get_sibling_value(s1, "주간사")
        result["상장예정주식수"] = get_sibling_value(s1, "상장(예정)주식수")

    s2 = get_soup(build_url("view_02.asp"))
    if s2:
        result["기타기존주주_str"] = get_shareholder_ratio(s2, "기타기존주주")
        result["유통가능주식_str"] = get_shareholder_ratio(s2, "유통가능주식합계")

    s4 = get_soup(build_url("view_04.asp"))
    if s4:
        for key in ("확정공모가격", "확정공모가", "공모가격", "공모가", "청약경쟁률"):
            result[key] = get_sibling_value(s4, key)
    return result


def resolve_offer_price(detail, list_offer_price_text=""):
    for key in ("확정공모가격", "확정공모가"):
        price = parse_single_numeric(detail.get(key, "0"))
        if price > 0:
            return price
    list_price = parse_single_numeric(list_offer_price_text)
    if list_price > 0:
        return list_price
    for key in ("공모가격", "공모가"):
        price = parse_single_numeric(detail.get(key, "0"))
        if price > 0:
            return price
    return 0


def fetch_ipo_items(target_date):
    target_date_str = target_date.strftime("%Y.%m.%d")
    items = []
    for name, code, href, list_offer_price_text in find_stock_targets(target_date.year, target_date_str):
        detail = crawl_details(href)
        total_shares = parse_numeric(detail.get("상장예정주식수", "0"))
        offer_price = resolve_offer_price(detail, list_offer_price_text)
        old_owner_ratio = parse_percent(detail.get("기타기존주주_str", "0"))
        floating_ratio = parse_percent(detail.get("유통가능주식_str", "0"))
        market_cap = int(total_shares * offer_price)
        items.append(
            {
                "name": name,
                "code": code,
                "source_href": href,
                "target_listing_date": target_date_str,
                "main_product": detail.get("주요제품", "-"),
                "lead_manager": detail.get("주간사", "-"),
                "subscription_competition": detail.get("청약경쟁률", "-"),
                "total_shares": total_shares,
                "offer_price": offer_price,
                "market_cap": market_cap,
                "floating_ratio": floating_ratio,
                "floating_amount": int(market_cap * floating_ratio / 100),
                "old_owner_ratio": old_owner_ratio,
                "old_owner_amount": int(market_cap * old_owner_ratio / 100),
                "detail": detail,
            }
        )
        time.sleep(0.2)
    return items
