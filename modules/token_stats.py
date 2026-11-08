import json

import config
from modules.indexer import LIST_FIELDS, TEXT_FIELDS
from modules.tokenizer import tokenize





def record_plain_text(record):
    # all text of one animal without boosts
    parts = []

    for field in TEXT_FIELDS:
        if record[field]:
            parts.append(record[field])

    for field in LIST_FIELDS:
        for value in record[field]:
            parts.append(value)

    for section in record["article"]:
        if section["heading"]:
            parts.append(section["heading"])
        parts.append(section["text"])

    return " ".join(parts)


def load_texts():
    # (name, text) of every animal
    texts = []
    with open(config.EXTRACTED_FILE, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)

            name = record["name"]
            if not name:
                name = record["id"]
            texts.append((name, record_plain_text(record)))
    return texts


def load_encoding():
    try:
        import tiktoken
    except ImportError:
        print("tiktoken is not installed - run: pip install tiktoken")
        return None

    try:
        return tiktoken.get_encoding(config.TIKTOKEN_ENCODING)      # first run downloads the encoding from the internet
    except Exception as e:
        print(f"tiktoken encoding '{config.TIKTOKEN_ENCODING}' could not be loaded: {type(e).__name__}: {e}")
        return None





def show():
    if not config.EXTRACTED_FILE.exists():
        print("extracted.jsonl not found - run the extractor first")
        return

    encoding = load_encoding()
    if encoding is None:
        return

    print("Counting tokens...")
    texts = load_texts()

    only_texts = []
    for name, text in texts:
        only_texts.append(text)

    # encode_ordinary = special tokens like <|endoftext|> are taken as normal text
    encoded = encoding.encode_ordinary_batch(only_texts)

    characters = 0
    words = 0
    own_tokens = 0
    tiktoken_counts = []

    for i, (name, text) in enumerate(texts):
        characters += len(text)
        words += len(text.split())
        own_tokens += len(tokenize(text))
        tiktoken_counts.append((len(encoded[i]), name))

    tiktoken_total = 0
    for count, name in tiktoken_counts:
        tiktoken_total += count

    largest_count, largest_name = max(tiktoken_counts)
    smallest_count, smallest_name = min(tiktoken_counts)

    print("\nTokens of extracted text")
    print(f" Documents: {len(texts)}")
    print(f" Characters: {characters}")
    print(f" Words (split by spaces): {words}")
    print(f" Own tokenizer (without stop words): {own_tokens}")
    print(f" tiktoken ({config.TIKTOKEN_ENCODING}): {tiktoken_total}")

    print(f"\n Average tiktoken tokens per document: {tiktoken_total / len(texts):.1f}")
    print(f" Characters per tiktoken token: {characters / tiktoken_total:.2f}")
    print(f" tiktoken tokens per word: {tiktoken_total / words:.2f}")
    print(f" Largest document: {largest_name} ({largest_count} tokens)")
    print(f" Smallest document: {smallest_name} ({smallest_count} tokens)")