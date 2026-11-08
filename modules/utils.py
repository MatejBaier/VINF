import zipfile
import config

def load_lines(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def append_line(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")



def save_raw_page(slug, html):
    # Saves one HTML page directly into the ZIP (skips it if it is already there)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{slug}.html"

    with zipfile.ZipFile(config.RAW_ZIP, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        if name in archive.namelist():
            return
        archive.writestr(name, html)


def iter_raw_pages():
    # Returns (slug, html) for every page in the ZIP 
    with zipfile.ZipFile(config.RAW_ZIP) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".html"):
                continue
            slug = name[:-len(".html")]
            html = archive.read(name).decode("utf-8")
            yield slug, html
 
 
def read_raw_page(slug):
    # Returns HTML of slug from ZIP
    with zipfile.ZipFile(config.RAW_ZIP) as archive:
        return archive.read(f"{slug}.html").decode("utf-8")