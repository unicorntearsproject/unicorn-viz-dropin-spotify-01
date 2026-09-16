"""Config-editor rows (rc.8): polling cadences on the Performance tab."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location('spotify_under_test_ce', _ROOT / 'spotify_controller.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load()


def _ctrl():
    c = object.__new__(_mod.SpotifyController)
    c._poll_interval_s = 0.75
    c._web_poll_interval_s = 3.0
    c._web_poll_fallback_s = 60.0
    c._http_timeout_s = 2.0
    return c


def test_rows_and_clamped_setters() -> None:
    c = _ctrl()
    rows = {r['name']: r for r in c.config_editor_settings()}
    assert list(rows) == ['poll_interval_s', 'web_poll_interval_s', 'web_poll_fallback_s', 'http_timeout_s']
    assert rows['web_poll_interval_s']['display'] == '3.00 s'
    assert all(r['hint'] and r['label'] for r in rows.values())
    c.set_config_setting('poll_interval_s', 0.01)
    assert c._poll_interval_s == 0.15
    c.set_config_setting('web_poll_fallback_s', 120.0)
    assert c._web_poll_fallback_s == 120.0
    c.set_config_setting('http_timeout_s', 99.0)
    assert c._http_timeout_s == 10.0
    c.set_config_setting('unknown', 1.0)  # ignored
