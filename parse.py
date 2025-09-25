#!/usr/bin/env python3
import argparse, json, csv, re, pathlib
from bs4 import BeautifulSoup

# --- your original, kept but supplemented ---
SELECTORS = {
    "business_name": "h1.y-css-1iiiexg, h1",  # fallback to plain h1
    "overall_rating": ".y-css-10rn8xw div[role='img'], [role='img'][aria-label*='star']",
    "total_reviews": ".y-css-1wz9c5l span.y-css-owgckf, [class*='review'] span",
    "review_container": "ul.list__09f24__ynIEd li, section[aria-label='Recommended Reviews'] article, div[class*='review-container'], li[class*='review'], article[class*='review']",
    "reviewer_handle": ".user-passport-info a.y-css-1x1e1r2, a[href*='/user_details'], a[class*='ui_header_link']",
    "review_date": ".y-css-scqtta span.y-css-1vi7y4e, [data-test-target*='review-date'], time, span[class*='ratingDate']",
    "star_rating_svg": ".y-css-scqtta div[role='img'], [aria-label*='star rating'], [role='img'][aria-label*='star'], span[class*='ui_bubble_rating']",
    "review_text": "p.comment__09f24__D0cxf span.raw__09f24__T4Ezm, q span, p, span[class*='raw__']"
}

def load_soup(path):
    with open(path, "rb") as f:
        html = f.read()
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")

def txt(el):
    return el.get_text(" ", strip=True) if el else None

def num_in(s):
    if not s: return None
    m = re.search(r"([\d\.,]+)", s)
    return m.group(1).replace(",", "") if m else None

def pf(s):
    try: return float(s)
    except: return None

def pi(s):
    try: return int(float(s))
    except: return None

def parse_rating_from_aria_label(aria_label):
    # Handles "4.5 star rating" and "4.5 of 5 bubbles"
    if not aria_label: return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:star|of 5 bubbles)", aria_label, re.I)
    return pf(m.group(1)) if m else None

def parse_jsonld(soup):
    out = {"name": None, "categories": None, "city_region": None,
           "price_range": None, "overall_rating": None, "total_review_count": None}
    for sc in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(sc.string or sc.get_text() or "{}")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for obj in items:
            at = obj.get("@type"); at = " ".join(at) if isinstance(at, list) else at
            if not at: continue
            if any(k in at for k in ["LocalBusiness","Restaurant","Hotel","Organization","TouristAttraction","Product"]):
                out["name"] = obj.get("name")
                cats = []
                for k in ("servesCuisine","category"):
                    v = obj.get(k)
                    if isinstance(v, list): cats += [str(x) for x in v]
                    elif v: cats.append(str(v))
                out["categories"] = ", ".join(cats) if cats else None
                addr = obj.get("address") or {}
                if isinstance(addr, dict):
                    city = addr.get("addressLocality") or addr.get("locality") or addr.get("addressRegion")
                    region = addr.get("addressRegion")
                    out["city_region"] = f"{city}, {region}" if city and region and city != region else (city or region)
                out["price_range"] = obj.get("priceRange")
                agg = obj.get("aggregateRating") or {}
                out["overall_rating"] = pf(agg.get("ratingValue"))
                out["total_review_count"] = pi(agg.get("reviewCount") or agg.get("ratingCount"))
                return out
    return out

def guess_business_from_dom(soup):
    name = txt(soup.select_one(SELECTORS["business_name"]))
    price = txt(soup.select_one('span[class*="price"]'))
    if not price:
        m = re.search(r"\${1,4}", soup.get_text()); price = m.group(0) if m else None
    # rating
    overall = None
    star_el = soup.select_one(SELECTORS["overall_rating"])
    if star_el and star_el.has_attr("aria-label"):
        overall = parse_rating_from_aria_label(star_el["aria-label"])
    if overall is None:
        bubbles = soup.select_one('span[aria-label*="of 5 bubbles"]')
        if bubbles and bubbles.has_attr("aria-label"):
            overall = parse_rating_from_aria_label(bubbles["aria-label"])
    # total reviews (best effort)
    total = None
    for t in soup.find_all(string=re.compile(r"\breviews?\b", re.I)):
        n = pi(num_in(str(t)))
        if n: total = n; break
    # categories + city/region (best effort)
    cats = []
    for a in soup.select('a[href*="/c/"], a[class*="category"], a[data-analytics*="category"]'):
        t = txt(a)
        if t and len(t) < 40: cats.append(t)
    cats = ", ".join(dict.fromkeys(cats)) if cats else None
    city = txt(soup.select_one('[data-testid*="address"], address, span[class*="address"], div[class*="address"]'))
    return {"name": name, "categories": cats, "city_region": city,
            "price_range": price, "overall_rating": overall, "total_review_count": total}

def parse_reviews_from_dom(soup, limit=200):
    rows = []
    blocks = soup.select(SELECTORS["review_container"]) or soup.select("article, div, li")
    for b in blocks[:limit]:
        # require a reviewer or text to avoid junk items
        reviewer = txt(b.select_one(SELECTORS["reviewer_handle"]))
        text = txt(b.select_one(SELECTORS["review_text"]))
        if not reviewer and not text:
            continue

        # stars
        stars = None
        star_el = b.select_one(SELECTORS["star_rating_svg"])
        if star_el and star_el.has_attr("aria-label"):
            stars = parse_rating_from_aria_label(star_el["aria-label"])
        else:
            # TripAdvisor bubble class, e.g., bubble_40 -> 4.0
            bubble = b.select_one('span[class*="ui_bubble_rating"]')
            if bubble and bubble.has_attr("class"):
                cls = " ".join(bubble["class"])
                m = re.search(r"bubble_(\d+)", cls)
                if m: stars = int(m.group(1)) / 10.0

        # date
        date_el = b.select_one(SELECTORS["review_date"])
        date = txt(date_el)
        if date:
            m = re.search(r"(\b\w+\s+\d{1,2},\s*\d{4}\b|\b\d{1,2}\s\w+\s\d{4}\b|\b\d{4}-\d{2}-\d{2}\b)", date)
            if m: date = m.group(1)

        # simple junk filters
        junk = {"back to search", "verified"}
        if text and any(k in text.lower() for k in junk):
            continue

        if any([reviewer, stars, date, text]):
            rows.append({"reviewer_handle": reviewer, "star_rating": stars, "date": date, "review_text": text})
    return rows

def dedupe(revs):
    seen, out = set(), []
    for r in revs:
        key = ((r.get("review_text") or "").strip(), r.get("date") or "")
        if key in seen: continue
        seen.add(key); out.append(r)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="input_path", default="listing.html")
    ap.add_argument("--out", dest="out_base", default="parsed")
    args = ap.parse_args()

    soup = load_soup(args.input_path)

    # Business info: JSON-LD first, then DOM
    ld = parse_jsonld(soup)
    dom = guess_business_from_dom(soup)
    business = {
        "business_name": ld.get("name") or dom.get("name"),
        "categories": ld.get("categories") or dom.get("categories"),
        "city_region": ld.get("city_region") or dom.get("city_region"),
        "price_range": ld.get("price_range") or dom.get("price_range"),
        "overall_rating": ld.get("overall_rating") or dom.get("overall_rating"),
        "total_reviews": ld.get("total_review_count") or dom.get("total_review_count"),
    }

    # Reviews (DOM + whatever JSON-LD might include in some pages)
    dom_reviews = parse_reviews_from_dom(soup, limit=200)
    rows = []
    for r in dedupe(dom_reviews):
        rows.append({**business, **r})

    out_dir = pathlib.Path(args.out_base)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "parsed.json"
    csv_path = out_dir / "parsed.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    cols = ["business_name","categories","city_region","price_range","overall_rating",
            "total_reviews","reviewer_handle","star_rating","date","review_text"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k: r.get(k) for k in cols})

    print(f"Wrote {csv_path} and {json_path} with {len(rows)} rows.")

if __name__ == "__main__":
    main()
