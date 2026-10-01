import re

SUFFIXES = [
    " city and borough", " CDP", " city", " town", " village", " borough",
    " comunidad", " urbana", " (balance)", " municipality", " government",
    " County", " county", " City", " Princeton", " corporation", " township",
    " plantation"
]

def strip_suffix(name):
    for suffix in sorted(SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name

REPLACEMENTS = [(r"\bSAINT\b", "ST"), (r"\bFORT\b", "FT"), (r"\bMOUNT\b", "MT")]

def normalize_place_name(name):
    name = name.upper().replace(".", "").replace("'", "").replace("-", " ")
    for pattern, repl in REPLACEMENTS:
        name = re.sub(pattern, repl, name)
    return "".join(name.split())

ALIASES = {
    ("PECOS", "TX"): "TOWNOFPECOS",
    ("BOISE", "ID"): "BOISECITY",
}