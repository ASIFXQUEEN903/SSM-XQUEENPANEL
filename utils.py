import os, requests, logging
logger = logging.getLogger(__name__)

TEMPORA_API_KEY = os.getenv("TEMPORA_API_KEY", "TEMPORA_API_KEY_HERE")
TEMPORA_BASE = "https://api.undefined/stubs/handler_api.php"

def call_tempora_api(action, extra_params=None):
    params = {"action": action, "api_key": TEMPORA_API_KEY}
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get(TEMPORA_BASE, params=params, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.exception("Tempora API request failed")
        return None
