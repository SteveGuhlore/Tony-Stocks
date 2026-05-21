"""Tests for dashboard theme module (no Streamlit UI automation)."""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import trading_bot.dashboard.theme as theme


class TestTonyThemeCss:
    def test_css_constant_defined(self) -> None:
        assert isinstance(theme._TONY_APP_CSS, str)
        assert len(theme._TONY_APP_CSS) > 100
        assert "<style>" in theme._TONY_APP_CSS
        assert ".tony-hero" in theme._TONY_APP_CSS

    def test_inject_tony_theme_references_css_constant(self) -> None:
        source = inspect.getsource(theme.inject_tony_theme)
        assert "_TONY_APP_CSS" in source


class TestStatGridHtml:
    def test_empty_grid_is_valid_html(self) -> None:
        html = theme.build_stat_grid_html([])
        assert html
        assert theme.html_has_balanced_divs(html)
        assert "tony-stat-grid" in html

    def test_stat_grid_balanced_and_non_empty(self) -> None:
        html = theme.build_stat_grid_html([
            ("Watched", "3", "blue", "Setups Tony saved"),
            ("Triggered", "1", "purple", None),
        ])
        assert theme.html_has_balanced_divs(html)
        assert "tony-stat-tile" in html
        assert "Watched" in html
        assert "<div" in html
        assert "motionless" not in html

    def test_render_html_uses_unsafe_markdown(self) -> None:
        mock_st = MagicMock()
        with patch.object(theme, "st", mock_st):
            theme.render_html('<motionless class="tony-section">Test</motionless>'.replace("motionless", "div"))
        mock_st.markdown.assert_called_once()
        args, kwargs = mock_st.markdown.call_args
        assert kwargs.get("unsafe_allow_html") is True
        assert "tony-section" in args[0]


class TestResultsGridZeroRows:
    def test_zero_summary_still_builds_grid(self) -> None:
        summary = {
            "watched_setups": 0,
            "triggered": 0,
            "target_hits": 0,
            "stop_hits": 0,
            "partial_moves": 0,
            "expired_no_trigger": 0,
            "still_active": 0,
        }
        items = [
            ("Watched", str(summary["watched_setups"]), "blue", "Setups Tony saved"),
            ("Triggered", str(summary["triggered"]), "purple", "Alerts that fired"),
        ]
        html = theme.build_stat_grid_html(items)
        assert theme.html_has_balanced_divs(html)
        assert "0" in html


class TestDashboardImportProtection:
    def test_theme_exports_tracking_position_renderer(self) -> None:
        assert callable(theme.render_tracking_position_card)
        assert callable(theme.render_tracking_preview_card)

    def test_app_imports_tracking_position_renderer(self) -> None:
        import inspect

        import trading_bot.dashboard.app as app_module

        source = inspect.getsource(app_module)
        assert "render_tracking_position_card" in source
        assert hasattr(app_module, "render_active_tracking")

    def test_app_module_imports_without_error(self) -> None:
        import trading_bot.dashboard.app as app_module

        assert app_module.render_active_tracking is not None


class TestHomePreviewCardHtml:
    def _pick_card(self) -> dict[str, str]:
        return {
            "symbol": "PLTR",
            "tony_rating": "On watch",
            "setup_type": "Breakout Watch",
            "risk_level": "Normal",
            "status": "Waiting for trigger",
            "status_tone": "warning",
            "why": "Tony sees strong volume and a clean breakout setup worth watching.",
            "home_summary": "Tony sees strong volume and a clean breakout setup worth watching.",
            "entry_trigger": "$25.50",
            "active_entry": "N/A",
            "price_label": "Current price",
            "current_price": "$25.10",
            "target": "$30.00",
            "stop": "$23.00",
        }

    def _tracking_card(self) -> dict[str, str]:
        return {
            "symbol": "SOFI",
            "entry_trigger": "$9.90",
            "research_pl_pct": "+5.00%",
            "tracked_from_price": "$10.00",
            "price_label": "Current price",
            "price_value": "$10.50",
            "current_price": "$10.50",
            "target": "$12.00",
            "stop": "$9.50",
            "time_active": "2h active",
            "tony_status": "Still active",
            "pl_tone": "positive",
            "status_tone": "positive",
            "home_summary": "Still active from $10.00.",
        }

    def test_pick_preview_html_balanced_and_enriched(self) -> None:
        html = theme.build_pick_preview_card_html(self._pick_card())
        assert theme.html_has_balanced_divs(html)
        assert "PLTR" in html
        assert "Risk:" in html
        assert "Entry trigger" in html
        assert "Active entry" in html
        assert "Current price" in html
        assert "Stop" in html
        assert "tony-metric-grid" in html
        assert "Confirms if" not in html

    def test_tracking_preview_html_balanced_and_enriched(self) -> None:
        html = theme.build_tracking_preview_card_html(self._tracking_card())
        assert theme.html_has_balanced_divs(html)
        assert "SOFI" in html
        assert "Entry trigger" in html
        assert "Tracked from" in html
        assert "Current price" in html
        assert "Result:" in html
        assert "2h active" in html

    def test_preview_render_uses_render_html(self) -> None:
        mock_st = MagicMock()
        with patch.object(theme, "st", mock_st):
            theme.render_pick_preview_card(self._pick_card())
        mock_st.markdown.assert_called_once()
        _, kwargs = mock_st.markdown.call_args
        assert kwargs.get("unsafe_allow_html") is True


class TestTraceResultsTable:
    def _card(self, outcome: str = "target_hit", **kwargs: object) -> dict[str, str]:
        base = {
            "symbol": "OXY",
            "setup_type": "Breakout Watch",
            "status": "Target reached",
            "entry_trigger": "$48.00",
            "exit_price": "$52.00",
            "exit_price_label": "Target Hit",
            "target": "$52.00",
            "stop": "$45.00",
            "research_pl_pct": "+8.33%",
            "risk_reward": "1.6x",
            "trigger_date": "May 19, 10:30 AM",
            "reason": "Tony saw strong volume.",
            "outcome_label": outcome,
        }
        base.update(kwargs)
        return base  # type: ignore[return-value]

    def test_dark_css_present(self) -> None:
        assert "#080d1c" in theme._TONY_APP_CSS
        assert ".trace-results-table" in theme._TONY_APP_CSS
        assert ".trace-page-header" in theme._TONY_APP_CSS

    def test_results_table_html_balanced_and_non_empty(self) -> None:
        html = theme.build_results_table_html([self._card()])
        assert theme.html_has_balanced_divs(html)
        assert "OXY" in html
        assert "trace-results-table" in html
        assert "trace-table-header" in html

    def test_results_table_empty_state(self) -> None:
        html = theme.build_results_table_html([])
        assert theme.html_has_balanced_divs(html)
        assert "trace-empty-state" in html
        assert "trace-disclaimer" in html

    def test_results_table_target_hit_pill_green(self) -> None:
        html = theme.build_results_table_html([self._card("target_hit")])
        assert "trace-pill-green" in html

    def test_results_table_stop_hit_pill_red(self) -> None:
        html = theme.build_results_table_html([self._card("stop_hit")])
        assert "trace-pill-red" in html

    def test_results_table_active_pill_blue(self) -> None:
        html = theme.build_results_table_html([self._card("tracking")])
        assert "trace-pill-blue" in html

    def test_results_table_pl_positive_class(self) -> None:
        html = theme.build_results_table_html([self._card()])
        assert "trace-pl-positive" in html

    def test_results_table_pl_negative_class(self) -> None:
        html = theme.build_results_table_html([self._card("stop_hit", research_pl_pct="-5.00%")])
        assert "trace-pl-negative" in html

    def test_results_table_target_exit_gets_price_hit_class(self) -> None:
        html = theme.build_results_table_html([self._card(exit_price_label="Target Hit")])
        assert "trace-price-hit" in html

    def test_results_table_stop_exit_gets_price_stop_class(self) -> None:
        html = theme.build_results_table_html([self._card("stop_hit", exit_price_label="Stop Hit")])
        assert "trace-price-stop" in html

    def test_render_results_table_calls_markdown_unsafe(self) -> None:
        mock_st = MagicMock()
        with patch.object(theme, "st", mock_st):
            theme.render_results_table([self._card()])
        mock_st.markdown.assert_called_once()
        _, kwargs = mock_st.markdown.call_args
        assert kwargs.get("unsafe_allow_html") is True

    def test_disclaimer_present_in_table(self) -> None:
        html = theme.build_results_table_html([self._card()])
        assert "trace-disclaimer" in html
        assert "Research outcomes only" in html
