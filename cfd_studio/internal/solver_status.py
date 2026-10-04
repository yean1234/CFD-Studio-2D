"""Recognize completed logs only after the current solver and launcher exit."""
import math
import re


def current_log_finished(log, log_run_id, active_run_id, modified, launched, processes):
    if not active_run_id or log_run_id != active_run_id or processes:
        return False
    try:
        modified, launched = float(modified), float(launched)
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(v) for v in (modified, launched)) or launched <= 0 or modified < launched:
        return False
    return bool(re.search(r'(?:^|\n)End(?:\n|$)', log or ''))
