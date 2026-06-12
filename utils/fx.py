"""FX rates to FJD — configurable defaults, optional live fetch."""
import json
import os
import datetime
from config import SUPPORTED_CURRENCIES

_DEFAULT_RATES = {
    "FJD": 1.0,
    "AUD": 1.54,
    "NZD": 1.41,
    "USD": 2.28,
    "GBP": 2.88,
}

_CACHE_FILE = "fx_rates_cache.json"
_CACHE_MAX_AGE_DAYS = 7


def _load_cache() -> dict | None:
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        updated = datetime.date.fromisoformat(data.get("updated", "2000-01-01"))
        if (datetime.date.today() - updated).days > _CACHE_MAX_AGE_DAYS:
            return None
        return data.get("rates")
    except Exception:
        return None


def _save_cache(rates: dict):
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"updated": datetime.date.today().isoformat(), "rates": rates}, f)
    except Exception:
        pass


def _fetch_live_rates() -> dict | None:
    """Best-effort fetch from a free API (USD base → derive FJD cross-rates)."""
    try:
        import urllib.request
        url = "https://api.exchangerate.host/latest?base=USD&symbols=FJD,AUD,NZD,GBP"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        rates_usd = data.get("rates", {})
        fjd_per_usd = rates_usd.get("FJD")
        if not fjd_per_usd:
            return None
        out = {"FJD": 1.0, "USD": float(fjd_per_usd)}
        for code in ("AUD", "NZD", "GBP"):
            if code in rates_usd and rates_usd[code]:
                out[code] = float(fjd_per_usd) / float(rates_usd[code])
        return out
    except Exception:
        return None


def get_fx_rates() -> dict[str, float]:
    cached = _load_cache()
    if cached:
        return cached
    live = _fetch_live_rates()
    if live:
        _save_cache(live)
        return live
    return dict(_DEFAULT_RATES)


def convert_to_fjd(amount: float, currency: str) -> tuple[float, float]:
    rates = get_fx_rates()
    rate = rates.get(currency, 1.0)
    return round(amount * rate, 2), rate
