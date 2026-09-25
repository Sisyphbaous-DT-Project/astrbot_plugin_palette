"""ChatUI 外框去除重复叠色的回归约束。"""

from __future__ import annotations

import unittest

from palette.chat_theme import build_chat_theme_css
from palette.theme import build_theme_css


class ChatFrameTest(unittest.TestCase):
    def test_common_surface_and_transparent_layout_containers(self) -> None:
        css = build_chat_theme_css()
        self.assertIn(
            ":has(> .v-application__wrap > .top-header.chat-mode-header)", css
        )
        self.assertEqual(css.count("--astrbot-palette-surface-opacity"), 1)
        for selector in (
            ".v-main > .page-wrapper",
            ".chat-ui .chat-main",
            ".chat-ui .messages-panel",
            ".chat-ui .message-list-root",
            ".chat-ui .composer-shell",
            ".chat-ui .project-composer-shell",
        ):
            self.assertIn(selector, css)
        self.assertIn(
            ".chat-sidebar:not(.v-navigation-drawer--temporary)", css
        )

    def test_generic_button_tints_exclude_chat(self) -> None:
        css = build_theme_css({"surface_opacity": 0.4})
        self.assertIn(
            ".v-app-bar:not(.chat-mode-header) .v-btn--icon:not(.bg-primary)",
            css,
        )
        self.assertIn(
            ".v-navigation-drawer:not(.chat-sidebar) .v-btn:not(.bg-primary)",
            css,
        )
        self.assertNotIn(
            "#app .v-navigation-drawer .v-btn:not(.bg-primary)", css
        )
        self.assertNotIn("#app .v-app-bar .v-btn--icon:not(.bg-primary)", css)

    def test_interaction_feedback_does_not_depend_on_glass(self) -> None:
        css = build_chat_theme_css()
        for state in (
            ":hover",
            ":focus-visible",
            ".sidebar-workspace-btn--active",
            ".workspace-files-trigger--active",
            '[aria-expanded="true"]',
        ):
            self.assertIn(state, css)
        self.assertIn("rgba(var(--v-theme-on-surface), 0.08)", css)
        for blur in (0, 14, 40):
            self.assertIn(css, build_theme_css({"stats_card_blur": blur}))

    def test_content_and_native_geometry_are_not_overridden(self) -> None:
        css = build_chat_theme_css()
        for forbidden in (
            ".input-container",
            ".message-bubble",
            ".chat-textarea",
            ".tool-call",
            "position:",
            "height:",
            "width:",
            "padding:",
            "filter:",
            "pointer-events:",
            "outline:",
        ):
            self.assertNotIn(forbidden, css)


if __name__ == "__main__":
    unittest.main()
