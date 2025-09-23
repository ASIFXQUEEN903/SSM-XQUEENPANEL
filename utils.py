import os
import requests
import logging
import json

logger = logging.getLogger(__name__)

TEMPORA_API_KEY = os.getenv("TEMPORA_API_KEY", "TEMPORA_API_KEY_HERE")
TEMPORA_BASE = "https://api.temporasms.com/stubs/handler_api.php"

def call_tempora_api(action, extra_params=None):
    """
    Generic function to call Tempora API
    Supports: getBalance, getNumber, getStatus, setStatus, getPrices, getOperators, getCountries
    """
    params = {"action": action, "api_key": TEMPORA_API_KEY}
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get(TEMPORA_BASE, params=params, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.exception(f"Tempora API request failed: {action}")
        return None

def get_prices(country, operator):
    """
    Get prices for a specific country and operator
    Returns dict: service -> price
    """
    resp = call_tempora_api("getPrices", {"country": country, "operator": operator})
    if resp:
        try:
            data = json.loads(resp)
            # convert to simple {service: price} dict
            result = {}
            if country in data:
                for service, val in data[country].items():
                    price = list(val.keys())[0] if val else "N/A"
                    result[service] = price
            return result
        except Exception:
            logger.warning("Failed to parse getPrices response")
            return {}
    return {}

def get_operators():
    """
    Returns all operators available
    """
    resp = call_tempora_api("getOperators")
    if resp:
        try:
            return json.loads(resp)
        except Exception:
            logger.warning("Failed to parse getOperators response")
            return {}
    return {}

def get_countries():
    """
    Returns all countries available
    """
    resp = call_tempora_api("getCountries", {"operator": 1})
    if resp:
        try:
            return json.loads(resp)
        except Exception:
            logger.warning("Failed to parse getCountries response")
            return {}
    return {}
