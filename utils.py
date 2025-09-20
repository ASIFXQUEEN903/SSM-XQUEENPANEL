import os
import requests
import logging
import json

logger = logging.getLogger(__name__)

TEMPORA_API_KEY = os.getenv("TEMPORA_API_KEY", "TEMPORA_API_KEY_HERE")
TEMPORA_BASE = "https://api.temporasms.com/stubs/handler_api.php"

def call_tempora_api(action, extra_params=None):
    """
    Call TemporaSMS API and return JSON parsed response.
    """
    params = {"action": action, "api_key": TEMPORA_API_KEY}
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get(TEMPORA_BASE, params=params, timeout=15)
        r.raise_for_status()
        try:
            return json.loads(r.text)
        except Exception:
            return r.text
    except Exception as e:
        logger.exception(f"Tempora API request failed for action {action}")
        return None
