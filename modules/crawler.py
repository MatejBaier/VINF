import random
import re
import time
from collections import deque
from datetime import datetime

import requests

import config
from modules.utils import append_line, load_lines, save_raw_page





# single animal page: https://a-z-animals.com/animals/<slug>/
ANIMAL_URL_REGEX = re.compile(r"^https://a-z-animals\.com/animals/([a-zA-Z0-9-]+)/$")

# href attributes
HREF_REGEX = re.compile(r"""href\s*=\s*["']([^"'#\s]+)["']""", re.IGNORECASE)

# other file extension than HTML
FILE_EXTENSIONS_REGEX = re.compile(r"\.(?:jpe?g|png|gif|webp|avif|svg|css|js|xml|pdf|zip|mp4|ico)$", re.IGNORECASE)

# splits URL to domain and path
DOMAIN_PATH_SPLITTER_REGEX = re.compile(r"^https?://(?:www\.)?([^/]+)(/.*)?$", re.IGNORECASE)
HOST = "a-z-animals.com"

MAX_PATH_DEPTH = 3      # protection from crawler traps





def normalize_url(url):
    url = url.strip()       # remove whitespaces

    # from HREF turn relative to absolute path
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = config.BASE_URL + url

    # ignore query links (contains ?), crawler traps
    if "?" in url or "&" in url:
        return None

    # remove page anchors (#)
    url = url.split("#")[0]



    # split into host and path
    url_split = DOMAIN_PATH_SPLITTER_REGEX.match(url)
    
    if not url_split or url_split.group(1).lower() != HOST:     # do not crawl other domains
        return None

    if url_split.group(2):
        path = url_split.group(2)
    else:
        path = "/"

    if FILE_EXTENSIONS_REGEX.search(path):      # do not download other files than HTML
        return None
    
    if not path.endswith("/"):
        path += "/"                             # normalize so every site ends with /
    
    segment_count = 0
    for part in path.split("/"):
        if part != "":
            segment_count += 1

    if segment_count > MAX_PATH_DEPTH:
        return None

    return (config.BASE_URL + path).lower()


def is_wanted(url):
    return bool(ANIMAL_URL_REGEX.match(url))    # keep only animal pages


def is_disallowed(url):
    path = url[len(config.BASE_URL):]
    for disallowed in config.DISALLOWED_PATHS:
        if path.startswith(disallowed):         # do not crawl if URL is disallowed in robots.txt
            return True
    return False


def extract_links(html):
    """Return normalized, wanted URLs found in the HTML (duplicates removed, order kept)."""
    links = []
    seen = set()
    for href in HREF_REGEX.findall(html):
        url = normalize_url(href)                       # normalize URL
        if url and url not in seen and is_wanted(url):  # check if it is a duplicate in this HTML
            seen.add(url)
            links.append(url)
    return links





def save_frontier(frontier):
    tmp = config.FRONTIER_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for url in frontier:
            f.write(url + "\n")
    tmp.replace(config.FRONTIER_FILE)



def log_history(url, status, size, filename, note=""):
    if not config.HISTORY_FILE.exists():
        append_line(config.HISTORY_FILE, "timestamp\turl\tstatus\tbytes\tfile\tnote")
    timestamp = datetime.now().isoformat(timespec="seconds")
    append_line(config.HISTORY_FILE, f"{timestamp}\t{url}\t{status}\t{size}\t{filename}\t{note}")




def polite_sleep():
    time.sleep(config.SLEEP_BASE + random.uniform(0, config.SLEEP_JITTER))


def is_retryable(status):
    # network error
    if status is None:
        return True

    # 429 Too Many Requests
    if status == 429:
        return True

    # 5xx server-side error
    if status >= 500:
        return True

    # everything else, retrying will not help
    return False




def fetch(session, url):
    status = None
    note = ""

    for attempt in range(config.BACKOFF_TRIES + 1):
        response = None

        try:
            response = session.get(url, headers=config.HEADERS, timeout=(config.CONNECTION_TIMEOUT, config.READ_TIMEOUT))
            status = response.status_code
            note = ""

            if status == 200:
                return status, response.text, response.url, ""
            
        except requests.RequestException as e:
            status = None
            note  = type(e).__name__

        if not is_retryable(status):
            return status, "", url, "permanent error"
        
        if attempt == config.BACKOFF_TRIES:
            break

        wait = config.BACKOFF_BASE * config.BACKOFF_MULTIPLIER ** attempt
        if response is not None:
            # server answered, read returned servers wait
            retry_after = response.headers.get("Retry-After", "")
        else:
            # network error, no response
            retry_after = ""
        
        if retry_after.isdigit():
            wait = int(retry_after)     # server answered with length of wait time

        print(f"   ! {status or note} - waiting {wait} s (retry {attempt + 1}/{config.BACKOFF_TRIES})")
        time.sleep(wait)

    if note == "":
        note = "max retries reached"

    return status, "", url, note




def crawl(max_pages=0):

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    visited = set(load_lines(config.VISITED_FILE))
    frontier = deque(load_lines(config.FRONTIER_FILE))

    if not frontier and not visited:
        frontier.append(config.SEED_URL)    # first run
    queued = set(frontier)

    print(f"Frontier: {len(frontier)} URLs, visited: {len(visited)}")

    saved = 0
    url = None

    try:
        while frontier:
            url = frontier.popleft()
            queued.discard(url)
            if url in visited:
                continue

            if is_disallowed(url):
                print(f"   - skipped (robots.txt): {url}")
                log_history(url, "-", 0, "", "disallowed by robots.txt")
                visited.add(url)
                append_line(config.VISITED_FILE, url)
                save_frontier(frontier)
                continue

            status, html, final_url, note = fetch(session, url)

            normalized = normalize_url(final_url)
            if normalized is None:
                final_url = url
            else:
                final_url = normalized


            if final_url != url:
                note = f"{note} redirect -> {final_url}".strip()

            # save animal pages directly into the ZIP
            filename = ""
            match = ANIMAL_URL_REGEX.match(final_url)
            if status == 200 and match:
                slug = match.group(1).lower()
                save_raw_page(slug, html)
                filename = f"{slug}.html"
                saved += 1

            size = len(html.encode("utf-8"))
            log_history(url, status, size, filename, note)
            print(f"[{len(visited) + 1}] {status} {url} ({size} B), frontier: {len(frontier)}")

            # mark the requested URL as visited
            if url not in visited:
                visited.add(url)
                append_line(config.VISITED_FILE, url)

            # after a redirect, mark also the final URL, so it is not downloaded again
            if final_url != url and final_url not in visited:
                visited.add(final_url)
                append_line(config.VISITED_FILE, final_url)

            # new links, add them to the frontier
            if status == 200:
                for link in extract_links(html):
                    if link not in visited and link not in queued:
                        frontier.append(link)
                        queued.add(link)

            save_frontier(frontier)     # Checkpoint

            if max_pages and saved >= max_pages:
                print(f"Limit of {max_pages} pages reached.")
                break

            polite_sleep()

    except KeyboardInterrupt:
        # the URL being processed was not finished  so put back to the front
        if url and url not in visited and url not in queued:
            frontier.appendleft(url)
        save_frontier(frontier)
        print("\nInterrupted - state saved, run again to continue.")

    print(f"Done. Saved in this run: {saved}, remaining in frontier: {len(frontier)}")


def reset():
    for path in (config.FRONTIER_FILE, config.VISITED_FILE, config.HISTORY_FILE):
        if path.exists():
            path.unlink()
    print("Crawl state deleted - next run starts from the seed URL.")


if __name__ == "__main__":
    crawl()