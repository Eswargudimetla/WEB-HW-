#!/usr/bin/env python3
import json, csv, re
from bs4 import BeautifulSoup

INPUT = "listing.html"
OUT_JSON = "parsed.json"
OUT_CSV  = "parsed.csv"

def txt(el): 
    return el.get_text(" ", strip=True) if el else None

def load_soup(p):
    with open(p, "rb") as f: h = f.read()
    try: return BeautifulSoup(h, "lxml")
    except Exception: return BeautifulSoup(h, "html.parser")

def parse_rating_from_aria_label(s):
    if not s: return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)   # keep exact float (e.g., 4.3 / 4.5)
    return float(m.group(1)) if m else None

# -------- categories (uses your selector first, then fallbacks) --------
import json as _json
def extract_categories(soup):
    # 1) your selector
    hits = soup.select("div[data-testid='biz-meta-info'] a[href*='cflt=']")
    if hits:
        cats = [txt(h) for h in hits if txt(h)]
        if cats: return ", ".join(dict.fromkeys(cats))
    # 2) JSON-LD
    for sc in soup.select('script[type="application/ld+json"]'):
        try: data = _json.loads(sc.string or sc.get_text() or "{}")
        except Exception: continue
        items = data if isinstance(data, list) else [data]
        cats = []
        for obj in items:
            at = obj.get("@type"); at = " ".join(at) if isinstance(at, list) else at
            if at and any(k in at for k in ["LocalBusiness","Restaurant","Hotel","Organization","TouristAttraction","Product"]):
                for k in ("servesCuisine","category"):
                    v = obj.get(k)
                    if isinstance(v, list): cats += [str(x) for x in v if x]
                    elif v: cats.append(str(v))
        if cats: return ", ".join(dict.fromkeys(cats))
    # 3) generic fallbacks
    for sel in ["a[href*='/search?cflt=']","a[class*='category']","a[data-analytics*='category']"]:
        hits = soup.select(sel)
        cats = [txt(h) for h in hits if txt(h)]
        if cats: return ", ".join(dict.fromkeys(cats))
    return None

# -------- business info --------
def extract_business(soup):
    name = txt(soup.select_one("h1.y-css-1iiiexg, h1"))
    category = extract_categories(soup) or "N/A"
    star = soup.select_one('[role="img"][aria-label*="star"], [aria-label*="of 5 bubbles"]')
    overall = parse_rating_from_aria_label(star["aria-label"]) if (star and star.has_attr("aria-label")) else None
    return {
        "business_name": name or "N/A",
        "business_category": category,
        "overall_rating": overall if overall is not None else "N/A",
    }

# -------- reviews --------
def extract_reviews(soup):
    out = []
    # Anchor on actual profile links
    candidates = soup.select('.user-passport-info a[href*="/user_details"]')
    if not candidates:
        containers = soup.select('section[aria-label="Recommended Reviews"] article, div[class*="review-container"], li[class*="review"], article[class*="review"]')
        for c in containers: out.extend(parse_block(c))
        return postprocess(out)
    for a in candidates:
        block = a.find_parent("li") or a.find_parent("article") or a.find_parent("div")
        if block: out.extend(parse_block(block, forced_name=txt(a)))
    return postprocess(out)

def parse_block(block, forced_name=None):
    rows = []
    reviewer_name = forced_name or txt(block.select_one('a[href*="/user_details"]'))

    # ✅ reviewer location (from your screenshot)
    loc_el = block.select_one('[data-testid="UserPassportInfoTextContainer"] span, div[data-testid="UserPassportInfoTextContainer"]')
    reviewer_location = txt(loc_el) or "N/A"

    # date
    d = block.select_one('[data-test-target*="review-date"], .y-css-scqtta span.y-css-1vi7y4e, time, span[class*="ratingDate"]')
    date = txt(d)
    if date:
        m = re.search(r"(\b\w+\s+\d{1,2},\s*\d{4}\b|\b\d{1,2}\s\w+\s\d{4}\b|\b\d{4}-\d{2}-\d{2}\b)", date)
        if m: date = m.group(1)

    # per-review rating
    star_el = block.select_one('[role="img"][aria-label*="star"], [aria-label*="star"], span[class*="ui_bubble_rating"]')
    star_rating = None
    if star_el and star_el.has_attr("aria-label"):
        star_rating = parse_rating_from_aria_label(star_el["aria-label"])
    else:
        cls = " ".join(star_el.get("class", [])) if star_el else ""
        m = re.search(r"bubble_(\d+)", cls)
        if m: star_rating = int(m.group(1)) / 10.0

    # text
    text_el = block.select_one('p.comment__09f24__D0cxf span.raw__09f24__T4Ezm, q span, p, span[class*="raw__"]')
    review_text = txt(text_el)

    # skip junk/short rows
    if review_text and len(review_text) >= 20 and not any(k in review_text.lower() for k in ["things to do","best of"]):
        rows.append({
            "date": date or "N/A",
            "reviewer_name": reviewer_name or "N/A",
            "reviewer_location": reviewer_location,
            "review": review_text,
            "star_rating": star_rating if star_rating is not None else "N/A",
        })
    return rows

def postprocess(rows):
    # De-dup by (text, date)
    seen, out = set(), []
    for r in rows:
        key = (r.get("review",""), r.get("date",""))
        if key in seen: continue
        seen.add(key); out.append(r)
    return out

def main():
    soup = load_soup(INPUT)
    biz = extract_business(soup)
    reviews = extract_reviews(soup)

    rows = []
    for r in reviews:
        rows.append({
            "business_name": biz["business_name"],
            "business_category": biz["business_category"],
            "date": r["date"],
            "reviewer_name": r["reviewer_name"],
            "reviewer_location": r["reviewer_location"],
            "review": r["review"],
            "star_rating": r["star_rating"],
            "overall_rating": biz["overall_rating"],
        })

    # write JSON
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # write CSV
    cols = ["business_name","business_category","date","reviewer_name","reviewer_location","review","star_rating","overall_rating"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "N/A") for k in cols})

    print(f"Wrote {OUT_CSV} and {OUT_JSON} with {len(rows)} reviews.")

if __name__ == "__main__":
    main()
