"""Spotify's Control Room operator panel (P2 of
docs/planning/control-room-panel-registry-plan-2026-09-04.md).

Replaces the old hardcoded CR "SPOTIFY" panel, which reached into this
controller via vj_api.get_subsystem('spotify') + getattr duck-typing.
_operator_panel_content()/_operator_panel_action() read/act through the
same snapshot()/begin_auth_async()/logout() every other integration
already uses. Same construction pattern as test_snapshots_features.py
(a real SpotifyController via __init__, mock_app fixture from conftest).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController  # noqa: E402
from tests.conftest import MockApp  # noqa: E402

from unicornviz.operator_panels import OperatorPanel, PanelContent  # noqa: E402


def _controller(mock_app: MockApp) -> SpotifyController:
    with patch('sys.platform', 'linux'):
        return SpotifyController(mock_app, {})


def test_registration_call_registers_an_operator_panel(mock_app: MockApp) -> None:
    # __init__ already ran the real registration code (mock_app.vj_api is a
    # MagicMock, so register_operator_panel just records the call).
    controller = _controller(mock_app)
    call = mock_app.vj_api.register_operator_panel.call_args
    assert call is not None
    panel = call.args[0]
    assert isinstance(panel, OperatorPanel)
    assert panel.name == 'spotify' and panel.title == 'Spotify' and panel.page == 'sources'
    assert panel.content == controller._operator_panel_content
    assert panel.on_action == controller._operator_panel_action
    assert panel.tooltips == {
        'auth': 'Start Spotify login (opens the auth flow)',
        'logout': 'Disconnect the Spotify account',
    }


def test_content_reflects_no_playback(mock_app: MockApp) -> None:
    controller = _controller(mock_app)
    content = controller._operator_panel_content()
    assert isinstance(content, PanelContent)
    assert content.status == 'STOPPED'
    by_label = {row.label: row.value for row in content.rows}
    assert by_label['Track'] == '- - -'
    auth_button = next(b for b in content.buttons if b.action == 'auth')
    assert auth_button.active is False


def test_content_reflects_playing_track_with_web_auth(mock_app: MockApp) -> None:
    controller = _controller(mock_app)
    controller._available = True
    controller._is_playing = True
    controller._status = 'playing'
    controller._title = 'Strobe'
    controller._artist = 'Deadmau5'
    controller._duration_s = 180.0
    controller._position_s = 90.0
    controller._web_enabled = True
    controller._auth_status = 'ok'

    content = controller._operator_panel_content()
    assert content.status == 'PLAYING'
    by_label = {row.label: row.value for row in content.rows}
    assert by_label['Track'] == 'Deadmau5 - Strobe'
    assert by_label['Auth'] == 'OK'
    auth_row = next(r for r in content.rows if r.label == 'Auth')
    assert auth_row.emphasis == 'success'
    meter = next(m for m in content.meters if m.label == 'Progress')
    assert meter.value == 0.5 and meter.text == '01:30/03:00'
    auth_button = next(b for b in content.buttons if b.action == 'auth')
    assert auth_button.active is True


def test_content_progress_is_zero_with_no_duration(mock_app: MockApp) -> None:
    controller = _controller(mock_app)
    content = controller._operator_panel_content()
    meter = next(m for m in content.meters if m.label == 'Progress')
    assert meter.value == 0.0 and meter.text == '00:00/00:00'


# --------------------------------------------------------------------------- #
# _operator_panel_action -- routes to the real auth methods
# --------------------------------------------------------------------------- #

def test_action_auth_calls_begin_auth_async(mock_app: MockApp) -> None:
    controller = _controller(mock_app)
    controller.begin_auth_async = lambda: 'Spotify auth started'
    assert controller._operator_panel_action('auth', None) == 'Spotify auth started'


def test_action_logout_calls_logout(mock_app: MockApp) -> None:
    controller = _controller(mock_app)
    controller.logout = lambda: 'Spotify logged out'
    assert controller._operator_panel_action('logout', None) == 'Spotify logged out'


def test_action_unknown_returns_none(mock_app: MockApp) -> None:
    controller = _controller(mock_app)
    assert controller._operator_panel_action('bogus', None) is None


def test_shutdown_unregisters_the_operator_panel(mock_app: MockApp) -> None:
    """operator_panels.py "Lifecycle": a mid-session shutdown must not leave
    a dead panel (error box) behind in the Control Room."""
    controller = _controller(mock_app)
    controller.shutdown()
    mock_app.vj_api.unregister_operator_panel.assert_called_once_with('spotify')
