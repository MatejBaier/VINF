def not_ready(name):
    def handler():
        print(f"'{name}' is not implemented yet.")
    return handler


def crawl_test():
    from modules import crawler
    crawler.crawl(max_pages=5)


def crawl_full():
    from modules import crawler
    crawler.crawl()


def crawl_reset():
    from modules import crawler
    if input("Really delete crawl state? (y/n): ").strip().lower() == "y":
        crawler.reset()

def show_stats():
    from modules import stats
    stats.show()


def extract_all():
    from modules import extractor
    extractor.run()


def extract_show():
    from modules import extractor
    extractor.show_record()


def extract_missing():
    from modules import extractor
    extractor.show_missing()


def extract_tests():
    import unittest
    tests = unittest.defaultTestLoader.loadTestsFromName("tests.test_extractor")
    unittest.TextTestRunner(verbosity=2).run(tests)


def show_token_stats():
    from modules import token_stats
    token_stats.show()


def index_build():
    from modules import indexer
    indexer.build()


def index_stats():
    from modules import indexer
    indexer.show_stats()


def search_run():
    from modules import search
    search.run()


def search_compare():
    from modules import search
    search.compare()


def spark_animals_run():
    from modules import spark_animals
    spark_animals.run()


def spark_animals_compare():
    from modules import spark_animals
    spark_animals.compare()


def spark_wiki_sample():
    from modules import spark_wiki
    spark_wiki.run(full=False)


def spark_wiki_full():
    from modules import spark_wiki
    spark_wiki.run(full=True)


def spark_wiki_show():
    from modules import spark_wiki
    spark_wiki.show_record()


def spark_join_run():
    from modules import spark_join
    spark_join.run()


def spark_join_show():
    from modules import spark_join
    spark_join.show_record()


def lucene_build():
    from modules import lucene_indexer
    lucene_indexer.build()


def lucene_stats():
    from modules import lucene_indexer
    lucene_indexer.show_stats()


def lucene_search():
    from modules import lucene_search
    lucene_search.run()


def lucene_examples():
    from modules import lucene_search
    lucene_search.examples()


def lucene_compare():
    from modules import lucene_search
    lucene_search.compare()


MENU = [
    ("1", "Crawler - test run (5 pages)", crawl_test),
    ("2", "Crawler - full run / resume", crawl_full),
    ("3", "Crawler - RESET state", crawl_reset),
    ("4", "Crawler - statistics", show_stats),
    (None, "", None),
    ("5", "Extractor - parse HTMLs", extract_all),
    ("6", "Extractor - show record", extract_show),
    ("7", "Extractor - missing fields", extract_missing),
    ("8", "Extractor - unit tests", extract_tests),
    ("9", "Extractor - token statistics (tiktoken)", show_token_stats),
    (None, "", None),
    ("10", "Indexer - build index", index_build),
    ("11", "Indexer - statistics", index_stats),
    (None, "", None),
    ("12", "Search", search_run),
    ("13", "Search - compare scoring / idf methods", search_compare),
    (None, "", None),
    ("14", "Spark - extract animals", spark_animals_run),
    ("15", "Spark - compare with part 1 extractor", spark_animals_compare),
    ("16", "Spark - process wiki dump (sample)", spark_wiki_sample),
    ("17", "Spark - process wiki dump (full)", spark_wiki_full),
    ("18", "Spark - show wiki record", spark_wiki_show),
    ("19", "Spark - join animals with wiki", spark_join_run),
    ("20", "Spark - show joined record", spark_join_show),
    (None, "", None),
    ("21", "Lucene - build index", lucene_build),
    ("22", "Lucene - statistics", lucene_stats),
    ("23", "Lucene - search", lucene_search),
    ("24", "Lucene - query type examples", lucene_examples),
    ("25", "Lucene - compare old vs new index", lucene_compare),
]

HANDLERS = {}
for key, label, handler in MENU:
    if key is not None:
        HANDLERS[key] = handler


def print_menu():
    for key, label, _ in MENU:
        if key is None:
            print()                 # empty line between logical parts
        else:
            print(f"{key}) {label}")
    print("\n0) Exit")


def main():
    while True:
        print("\n==========================")
        print_menu()
        choice = input("\nChoose: ").strip()

        if choice == "0":
            break
        handler = HANDLERS.get(choice)
        if handler is None:
            print("Invalid choice.")
            continue

        print("==========================")

        try:
            handler()                       # run the selected action
        except KeyboardInterrupt:
            print("\nInterrupted, back to menu.")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")



if __name__ == "__main__":
    main()