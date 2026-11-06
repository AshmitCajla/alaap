"""Make text sound right when spoken, and split streaming text into sentences.

Gnani's TTS reads digits in English ("Rs 200" -> "two hundred rupees"), which sounds robotic in a
Hinglish sentence. So before speaking we turn prices, times, counts and reference numbers into the
words a person would say: "do sau rupaye", "saade chhe baje", "ref chhe saat ek saat"."""

import re

HI = ("shunya ek do teen chaar paanch chhe saat aath nau das gyaarah baarah terah chaudah pandrah solah satrah "
      "athaarah unnees bees ikkees baaees teyees chaubees pachchees chhabbees sattaaees atthaaees untees tees "
      "iktees battees taintees chauntees paintees chhattees saintees adtees untaalees chaalees iktaalees bayaalees "
      "taintaalees chauvaalees paintaalees chhiyaalees saintaalees artaalees unchaas pachaas ikyaavan baavan tirpan "
      "chauvan pachpan chhappan sattaavan atthaavan unsath saath iksath baasath tirsath chausath painsath chhiyaasath "
      "sadsath adsath unhattar sattar ikhattar bahattar tihattar chauhattar pachhattar chhihattar sathattar "
      "athhattar unaasi assi ikyaasi bayaasi tiraasi chauraasi pachaasi chhiyaasi sattaasi athaasi navaasi nabbe "
      "ikyaanave baanave tiraanave chauraanave pachaanave chhiyaanave sattaanave atthaanave ninyaanave").split()
EN_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
           "seventeen eighteen nineteen").split()
EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

# Words that tell us a reply is Hindi/Hinglish rather than English.
HINDI_HINTS = re.compile(r"\b(hai|hain|ji|aap|aapka|aapki|kal|aaj|ka|ke|ki|main|nahi|haan|karoon|kar|baje|"
                         r"rupaye|theek|achha|bataiye|hoga|hogi|ho|tusi|tuhada|nu|da|di|hoon|raha|rahi|aur|kya|ya|se|par|mein|ko|"
                         r"chahiye|wala|wali|lagenge|lagega|karna|dijiye|kijiye|shaam|subah)\b", re.I)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def hindi_number(n: int) -> str:
    if n < 100:
        return HI[n]
    parts = []
    for size, word in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "hazaar"), (100, "sau")):
        if n >= size:
            parts.append(f"{hindi_number(n // size)} {word}")
            n %= size
    if n:
        parts.append(HI[n])
    return " ".join(parts)


def english_number(n: int) -> str:
    if n < 20:
        return EN_ONES[n]
    if n < 100:
        return EN_TENS[n // 10] + ("" if n % 10 == 0 else "-" + EN_ONES[n % 10])
    for size, word in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            rest = n % size
            return f"{english_number(n // size)} {word}" + (f" {english_number(rest)}" if rest else "")
    return str(n)


def is_hindi(text: str) -> bool:
    return bool(DEVANAGARI.search(text)) or len(HINDI_HINTS.findall(text)) >= 2


def _hindi_time(h: int, m: int) -> str:
    h12 = h % 12 or 12
    nxt = h12 % 12 + 1
    if m == 0:
        return f"{HI[h12]} baje"
    if m == 30:
        return {1: "dedh baje", 2: "dhaai baje"}.get(h12, f"saade {HI[h12]} baje")
    if m == 15:
        return f"sava {HI[h12]} baje"
    if m == 45:
        return {1: "paune ek baje" if h12 == 12 else "paune do baje"}.get(nxt if nxt == 2 else -1, f"paune {HI[nxt]} baje")
    return f"{HI[h12]} bajkar {hindi_number(m)} minute"


def _english_time(h: int, m: int) -> str:
    h12 = h % 12 or 12
    ampm = "a m" if h < 12 else "p m"
    return f"{english_number(h12)}{'' if m == 0 else ' ' + ('oh ' if m < 10 else '') + english_number(m)} {ampm}"


def _digits(s: str, hindi: bool) -> str:
    return " ".join(HI[int(d)] if hindi else EN_ONES[int(d)] for d in s)


class _M:
    """A stand-in regex match for reusing time_sub on range parts."""
    def __init__(self, h, m):
        self.g = (None, h, m, None)

    def group(self, i):
        return self.g[i]


def for_speech(text: str) -> str:
    """Rewrite numbers so TTS says them like a person in the same language."""
    hindi = is_hindi(text)
    num = hindi_number if hindi else english_number

    text = re.sub(r"[*#_`~>|]+", " ", text)
    text = re.sub(r"\(([^)]*)\)", r", \1,", text)  # brackets become a small pause
    # Times: 18:30, 6:30 PM
    def time_sub(m):
        h, mi = int(m.group(1)), int(m.group(2))
        if (m.group(3) or "").lower().startswith("p") and h < 12:
            h += 12
        return _hindi_time(h, mi) if hindi else _english_time(h, mi)
    # Ranges: 17:00-19:00 -> "paanch se saat baje"
    def range_sub(m):
        a, b = time_sub(_M(m.group(1), m.group(2))), time_sub(_M(m.group(3), m.group(4)))
        return f"{a.removesuffix(' baje')} se {b}" if hindi else f"{a} to {b}"
    text = re.sub(r"\b(\d{1,2}):(\d{2})\s*(?:-|to|se)\s*(\d{1,2}):(\d{2})(?:\s*baje\b)?", range_sub, text)
    text = re.sub(r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm|a\.m\.|p\.m\.)(?![a-z]))?(?:\s*baje\b)?", time_sub, text, flags=re.I)
    # Money: Rs 200, Rs. 1,200, ₹200, INR 200
    def money(m):
        n = int(m.group(1).replace(",", ""))
        return f"{num(n)} rupaye" if hindi else f"{num(n)} rupees"
    text = re.sub(r"(?:₹|\bRs\.?|\bINR)\s*(\d[\d,]*\d|\d)(?:\s*(?:rupaye|rupees)\b)?", money, text, flags=re.I)
    text = re.sub(r"\b(\d[\d,]*\d|\d)\s*(?:rupaye|rupees)\b", money, text, flags=re.I)
    # Phone numbers and refs: read digit by digit
    text = re.sub(r"\b(\d{4,})\b", lambda m: _digits(m.group(1), hindi), text)
    # Other numbers
    text = re.sub(r"\b(\d{1,3})\b", lambda m: num(int(m.group(1))), text)
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


ABBREV = re.compile(r"(?:\b(?:rs|dr|mr|mrs|ms|no|st|sr|jr|approx|etc)|\d)\.$", re.I)


class SentenceSplitter:
    """Feed streaming text; get back complete sentences as soon as they end."""

    def __init__(self, min_chars: int = 12):
        self.buf = ""
        self.min_chars = min_chars

    def _next_end(self, start: int = 0) -> int | None:
        """Index just after the next sentence end that is followed by whitespace, or None."""
        for m in re.finditer(r"[.!?।]+(?=\s)", self.buf[start:]):
            end = start + m.end()
            if m.group().startswith(".") and ABBREV.search(self.buf[: start + m.start() + 1]):
                continue  # "Rs." or "6." is not the end of a sentence
            return end
        return None

    def feed(self, text: str) -> list[str]:
        self.buf += text
        out = []
        while (end := self._next_end()) is not None:
            if end < self.min_chars:  # a tiny opener like "Ji." sounds better joined to what follows
                nxt = self._next_end(end)
                if nxt is None:
                    break
                end = nxt
            out.append(self.buf[:end].strip())
            self.buf = self.buf[end:].lstrip()
        return out

    def flush(self) -> list[str]:
        rest, self.buf = self.buf.strip(), ""
        return [rest] if rest else []
