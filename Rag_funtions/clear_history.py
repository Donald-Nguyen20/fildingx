from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton


def clear_popup_history(popup, *, ask_confirm: bool = False) -> None:
    """Clear chat UI + sources UI + common in-memory buffers if present."""

    if ask_confirm:
        ok = QMessageBox.question(
            popup,
            "Clear history",
            "Clear chat history and sources?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

    # UI
    if hasattr(popup, "chat_display") and popup.chat_display is not None:
        popup.chat_display.clear()
    if hasattr(popup, "sources_list") and popup.sources_list is not None:
        popup.sources_list.clear()

    # Optional in-memory buffers (only if you use them)
    for attr in ("conversation_history", "messages", "history", "chat_history"):
        buf = getattr(popup, attr, None)
        if isinstance(buf, list):
            buf.clear()

    # Put cursor back to input for fast typing
    if hasattr(popup, "input_line") and popup.input_line is not None:
        popup.input_line.setFocus(Qt.ActiveWindowFocusReason)


def install_clear_history_button(
    popup,
    top_bar_layout,
    *,
    insert_at: int = 1,
    text: str = "Clear chat history",
    tooltip: str = "Clear chat history",
    confirm: bool = False,
):
    """Add a Clear button next to the Chat label."""
    btn = QPushButton(text)
    btn.setToolTip(tooltip)

    # Avoid Enter/Return triggering the button unexpectedly when focus drifts.
    btn.setAutoDefault(False)
    btn.setDefault(False)

    btn.clicked.connect(lambda: clear_popup_history(popup, ask_confirm=confirm))

    # Insert right after the "💬 Chat:" label
    top_bar_layout.insertWidget(insert_at, btn)
    return btn
