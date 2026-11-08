import zipfile
from collections import Counter

import config


def human_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def show_crawl_stats():

    if not config.HISTORY_FILE.exists():
        print("history.tsv not found - run the crawler first")
        return

    with open(config.HISTORY_FILE, encoding="utf-8") as f:
        lines = f.read().splitlines()[1:]       # skip header

    status_counts = Counter()
    for line in lines:
        status = line.split("\t")[2]
        status_counts[status] += 1

    first_timestamp = lines[0].split("\t")[0]
    last_timestamp = lines[-1].split("\t")[0]

    print("\nCrawl")
    print(f" Requests total: {len(lines)}")
    print(f" Started: {first_timestamp}")
    print(f" Finished: {last_timestamp}")
    for status, count in sorted(status_counts.items()):
        label = f"HTTP {status}:"
        print(f" {label:<17}{count}")


def show_page_stats():
    # statistics of the animal pages saved in the ZIP
    if not config.RAW_ZIP.exists():
        print("ZIP with pages not found - run the crawler first")
        return

    with zipfile.ZipFile(config.RAW_ZIP) as archive:
        sizes = [info.file_size for info in archive.infolist()]

    total_size = sum(sizes)
    zip_size = config.RAW_ZIP.stat().st_size

    print("\nDownloaded animal pages")
    print(f" Pages: {len(sizes)}")
    print(f" Size uncompressed: {human_size(total_size)}")
    print(f" Size on disk (ZIP): {human_size(zip_size)}")
    print(f" Average page size: {human_size(total_size / len(sizes))}")


def show():
    show_crawl_stats()
    show_page_stats()