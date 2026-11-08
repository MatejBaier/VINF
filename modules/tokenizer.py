import re
import unicodedata

import config





TOKEN_REGEX = re.compile(r"[a-z0-9]+")  # words and numbers, bed-bug -> bed, bug

# common English words without meaning for search
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and", "any",
    "are", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "however", "if", "in", "into", "is", "it", "its",
    "itself", "just", "may", "me", "might", "more", "most", "much", "must", "my", "myself", "no",
    "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "will", "with", "would",
    "you", "your", "yours", "yourself", "yourselves",
}





def normalize(text):
    text = text.lower()     # put all text into lower case

    # remove accents: Côte -> Cote
    text = unicodedata.normalize("NFKD", text)  # splits letters with accent to base letter and its accent separately
    letters = []
    for char in text:
        if not unicodedata.combining(char):
            letters.append(char)

    return "".join(letters)     # return text instead of array


def tokenize(text):
    # duplicates are kept, they are needed for tf
    if not text:
        return []

    tokens = []
    for token in TOKEN_REGEX.findall(normalize(text)):
        if len(token) < config.MIN_TOKEN_LENGTH:
            continue
        if token in STOP_WORDS:
            continue
        tokens.append(token)

    return tokens