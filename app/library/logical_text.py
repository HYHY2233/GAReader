"""Versioned NFC text; positions count Unicode code points, never UTF-16 units."""
import hashlib
import re
import unicodedata

NORMALIZATION = 'nfc-whitespace-v1'
WHITESPACE = '\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def normalize(text):
    return re.sub('['+WHITESPACE+']+', ' ', unicodedata.normalize('NFC', text)).strip(' ')


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalized_map(text):
    """Return normalized text and [raw start, raw end) for every code point."""
    clusters = []
    for index, char in enumerate(text):
        joins = clusters and unicodedata.normalize('NFC',clusters[-1][1]+char)!=unicodedata.normalize('NFC',clusters[-1][1])+unicodedata.normalize('NFC',char)
        if clusters and (unicodedata.combining(char) or joins):
            clusters[-1][1] += char
            clusters[-1][2] = index + 1
        else:
            clusters.append([index, char, index + 1])
    output, mapping = [], []
    for start, cluster, end in clusters:
        for char in unicodedata.normalize('NFC', cluster):
            if char in WHITESPACE:
                if not output:
                    continue
                if output[-1] == ' ':
                    mapping[-1][1] = end
                    continue
                char = ' '
            output.append(char)
            mapping.append([start, end])
    if output and output[-1] == ' ':
        output.pop(); mapping.pop()
    return ''.join(output), mapping


def occurrences(text, quote):
    if not quote:
        return []
    found, start = [], 0
    while len(found) < 100:
        pos = text.find(quote, start)
        if pos < 0:
            break
        found.append(pos)
        start = pos + 1
    return found


def resolve_quote(text, quote, prefix='', suffix='', start=None, end=None):
    if type(start) is int and type(end) is int and 0 <= start < end <= len(text):
        if text[start:end] == quote:
            return start, end
    candidates = [p for p in occurrences(text, quote)
                  if (not prefix or text[:p].endswith(prefix))
                  and (not suffix or text[p+len(quote):].startswith(suffix))]
    if len(candidates) != 1:
        return None
    return candidates[0], candidates[0]+len(quote)
