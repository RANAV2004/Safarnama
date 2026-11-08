# reads pasted flight, train or bus details such as an airline email, an IRCTC e-ticket or a redBus ticket
import re
from datetime import date, datetime, time, timedelta

AIRPORTS = {
    "BOM": "Mumbai",
    "DEL": "Delhi",
    "BLR": "Bengaluru",
    "IDR": "Indore",
    "GOI": "Goa",
    "GOX": "Goa",
    "JAI": "Jaipur",
    "UDR": "Udaipur",
    "MYQ": "Mysuru",
    "HYD": "Hyderabad",
    "MAA": "Chennai",
    "CCU": "Kolkata",
    "PNQ": "Pune",
    "AMD": "Ahmedabad",
    "COK": "Kochi",
}
AIRLINES = {
    "6E": "IndiGo",
    "AI": "Air India",
    "IX": "Air India Express",
    "QP": "Akasa Air",
    "SG": "SpiceJet",
    "UK": "Vistara",
    "I5": "AirAsia India",
    "9I": "Alliance Air",
    "S5": "Star Air",
}
CITY_NAMES = {
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "indore": "Indore",
    "goa": "Goa",
    "dabolim": "Goa",
    "mopa": "Goa",
    "jaipur": "Jaipur",
    "udaipur": "Udaipur",
    "mysuru": "Mysuru",
    "mysore": "Mysuru",
    "csmt": "Mumbai",
    "mumbai cst": "Mumbai",
    "ltt": "Mumbai",
    "lokmanya tilak": "Mumbai",
    "madgaon": "Goa",
    "margao": "Goa",
    "thivim": "Goa",
    "karmali": "Goa",
    "vasco da gama": "Goa",
    "hazrat nizamuddin": "Delhi",
    "ksr bengaluru": "Bengaluru",
    "yesvantpur": "Bengaluru",
    "udaipur city": "Udaipur",
}
MONTHS = {
    m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)
}
STATIONS = {
    "CSMT": "Mumbai",
    "BCT": "Mumbai",
    "LTT": "Mumbai",
    "DR": "Mumbai",
    "MAO": "Goa",
    "THVM": "Goa",
    "KRMI": "Goa",
    "VSG": "Goa",
    "NDLS": "Delhi",
    "NZM": "Delhi",
    "DLI": "Delhi",
    "DEE": "Delhi",
    "JP": "Jaipur",
    "UDZ": "Udaipur",
    "SBC": "Bengaluru",
    "YPR": "Bengaluru",
    "MYS": "Mysuru",
    "INDB": "Indore",
    "ADI": "Ahmedabad",
    "BRC": "Vadodara",
    "PUNE": "Pune",
    "MAS": "Chennai",
    "HWH": "Kolkata",
    "SC": "Hyderabad",
}
NOISE = re.compile(
    r"booked on|booking date|booking time|transaction|printed on|issued on|generated on|date of booking|payment", re.I
)
DEP_LABEL = re.compile(r"\b(?:departure(?:\s*time)?|dep(?:arts?|t)?\b\.?|scheduled departure|start(?:s|ing)? at)", re.I)
ARR_LABEL = re.compile(
    r"\b(?:arrival(?:\s*time)?|arr(?:ives?)?\b\.?|scheduled arrival|reach(?:es|ing)?(?: at)?|drop(?:ping)? time)", re.I
)
JOURNEY_DATE = re.compile(r"\b(?:date of journey|journey date|travel date|doj|date)\b", re.I)
TRAIN_NAME = re.compile(
    r"\btrain\s*(?:no\.?|number)?\s*/\s*name\s*[:.]?\s*\d{5}\s*/\s*([A-Za-z][A-Za-z .]{2,40}?)(?:\s{2,}|\n|\s+(?:class|from|to|quota)\b|$)",
    re.I,
)
TRAIN_NAME_ALONE = re.compile(r"\btrain name\s*[:.]\s*([A-Za-z][A-Za-z .]{2,40}?)(?:\s{2,}|\n|$)", re.I)
OPERATOR = re.compile(
    r"\b(?:travels|operator|bus operator|operated by|travel agency)\s*[:\-]\s*([A-Za-z0-9&.' ]{3,40}?)(?:\s{2,}|\n|$)",
    re.I,
)
FARE = re.compile(
    r"\b(?:total fare|total amount|amount paid|grand total|total)\b[^\d\n]{0,30}([\d,]{2,9})(?:\.\d{1,2})?", re.I
)
FLIGHT_NO = re.compile(r"\b(6E|AI|IX|QP|SG|UK|I5|9I|S5|[A-Z]\d|\d[A-Z]|[A-Z]{2})[\s-]?(\d{2,4})\b")
TRAIN_NO = re.compile(r"\b(?:train|trn)\s*(?:no\.?|number|#)?(?:\s*/\s*name)?\s*[:.]?\s*(\d{5})\b", re.IGNORECASE)
CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(am|pm|hrs)?\b", re.IGNORECASE)
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+([A-Za-z]{3,9})\b(?:[\s,-]+(\d{4})\b)?", re.IGNORECASE)
MONTH_DAY = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4})\b)?", re.IGNORECASE)
NUMERIC = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b")
NEXT_DAY = re.compile(r"\+\s?1\b|next day|\(\+1\)", re.IGNORECASE)


class FlightParseError(ValueError):
    pass


def month(word: str) -> int | None:
    return MONTHS.get(word[:3].lower())


def find_dates(text: str, today: date) -> list[date]:
    found: list[tuple[int, date]] = []
    for m in NUMERIC.finditer(text):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                y = int(m.group(6))
                d = date(y + 2000 if y < 100 else y, int(m.group(5)), int(m.group(4)))
        except ValueError:
            continue
        found.append((m.start(), d))
    for pattern, day_first in ((DAY_MONTH, True), (MONTH_DAY, False)):
        for m in pattern.finditer(text):
            dd, mon = (m.group(1), m.group(2)) if day_first else (m.group(2), m.group(1))
            mm = month(mon)
            if not mm:
                continue
            year = int(m.group(3)) if m.group(3) else today.year
            try:
                d = date(year, mm, int(dd))
            except ValueError:
                continue
            if not m.group(3) and d < today:
                d = d.replace(year=today.year + 1)
            found.append((m.start(), d))
    return [d for _, d in sorted(found)]


def find_times(text: str) -> list[time]:
    out = []
    for m in CLOCK.finditer(text):
        h, mins, suffix = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        if suffix == "pm" and h < 12:
            h += 12
        if suffix == "am" and h == 12:
            h = 0
        out.append(time(h, mins))
    return out


def find_places(text: str) -> list[str]:
    hits: list[tuple[int, str]] = []
    for code, city in AIRPORTS.items():
        for m in re.finditer(rf"\b{code}\b", text):
            hits.append((m.start(), city))
    for code, city in STATIONS.items():
        for m in re.finditer(rf"\({code}\)", text):
            hits.append((m.start(), city))
    low = text.lower()
    for name, city in CITY_NAMES.items():
        for m in re.finditer(rf"\b{re.escape(name)}\b", low):
            hits.append((m.start(), city))
    out: list[str] = []
    for _, city in sorted(hits):
        if not out or out[-1] != city:
            out.append(city)
    return out


def labelled(text: str, label: re.Pattern, today: date) -> tuple[time | None, date | None]:
    for m in label.finditer(text):
        after = text[m.end() : m.end() + 45].split("\n")[0]
        stop = [x.start() for x in (DEP_LABEL.search(after), ARR_LABEL.search(after)) if x]
        after = after[: min(stop)] if stop else after
        times = find_times(after)
        if times:
            dates = find_dates(after, today)
            return times[0], dates[0] if dates else None
    return None, None


WORDS = {
    "exp": "Express",
    "expr": "Express",
    "sf": "Superfast",
    "spl": "Special",
    "janshatabdi": "Jan Shatabdi",
    "and": "and",
    "of": "of",
}


def clean_name(name: str) -> str:
    return " ".join(WORDS.get(w.lower(), w.capitalize()) for w in name.strip(" .").split())


def parse(text: str, today: date | None = None, mode: str | None = None) -> dict:
    today = today or date.today()
    text = text.strip()[:2000]
    if not text:
        raise FlightParseError("paste your booking details first")
    text = "\n".join(line for line in text.splitlines() if not NOISE.search(line))
    provider, number = "", ""
    train = TRAIN_NO.search(text)
    if mode is None:
        if train:
            mode = "train"
        elif re.search(r"\bbus\b|redbus|volvo|sleeper|seater|travels\b|boarding point", text, re.IGNORECASE):
            mode = "bus"
        else:
            mode = "flight"
    if mode == "train":
        number = train.group(1) if train else ""
        name = TRAIN_NAME.search(text) or TRAIN_NAME_ALONE.search(text)
        provider = clean_name(name.group(1)) if name else "Indian Railways"
    elif mode == "bus":
        op = OPERATOR.search(text)
        provider = clean_name(op.group(1)) if op else "Bus"
    else:
        for m in FLIGHT_NO.finditer(text):
            code = m.group(1).upper()
            if code in AIRPORTS or not re.search(r"[A-Z]", code):
                continue
            provider, number = AIRLINES.get(code, code), f"{code} {m.group(2)}"
            break
    times = find_times(text)
    dates = find_dates(text, today)
    places = find_places(text)
    dep_time, dep_date = labelled(text, DEP_LABEL, today)
    arr_time, arr_date = labelled(text, ARR_LABEL, today)
    jd = next((find_dates(text[m.end() : m.end() + 30], today) for m in JOURNEY_DATE.finditer(text)), [])
    journey = (jd or [None])[0]
    if dep_time and arr_time:
        times = [dep_time, arr_time]
    if len(times) < 2:
        raise FlightParseError("I need both the departure and arrival times, for example 06:10 and 07:25")
    first_day = dep_date or journey or (dates[0] if dates else None)
    if not first_day:
        raise FlightParseError("I could not find the travel date, add it like 12 Dec 2026")
    later = [d for d in dates if d > first_day]
    depart = datetime.combine(first_day, times[0])
    arrive_day = arr_date if arr_date and arr_date >= first_day else (later[0] if later and not arr_time else first_day)
    if arr_date is None and len(dates) > 1 and dates[1] >= first_day and not dep_time:
        arrive_day = dates[1]
    arrive = datetime.combine(arrive_day, times[1])
    if arrive <= depart or NEXT_DAY.search(text):
        if arrive <= depart or arrive.date() == depart.date():
            arrive += timedelta(days=1)
    if arrive - depart > timedelta(days=3):
        raise FlightParseError("the arrival is more than three days after departure, check the times")
    fare = FARE.search(text)
    return {
        "mode": mode,
        "provider": provider or {"flight": "Flight", "train": "Indian Railways", "bus": "Bus"}[mode],
        "number": number,
        "price_inr": int(fare.group(1).replace(",", "")) if fare else 0,
        "from_city": places[0] if places else None,
        "to_city": places[1] if len(places) > 1 else None,
        "depart_at": depart.isoformat(timespec="minutes"),
        "arrive_at": arrive.isoformat(timespec="minutes"),
    }
