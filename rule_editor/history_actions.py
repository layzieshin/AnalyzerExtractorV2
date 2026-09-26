"""HistoryMixin: Dirty-Tracking, Auto-Save, Undo/Redo."""
from __future__ import annotations

import re
from datetime import datetime

_REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_ERROR = "Der Undo-Beleg fehlt oder ist ungueltig. Undo und Redo wurden nicht veraendert."
_ENTRY_ERROR = "Der Undo-Eintrag hat keine erwartete Revision. Es wurde nichts geschrieben."
_RELOAD_ERROR = "Die Aenderung ist gespeichert, die Ansicht konnte aber nicht neu geladen werden.\n{exc}"


def history_entry_from_receipt(receipt: object) -> dict | None:
    if not isinstance(receipt, dict):
        return None
    before = receipt.get("before")
    revision = receipt.get("after_revision")
    if not isinstance(before, dict) or not isinstance(revision, str) or _REVISION_RE.fullmatch(revision) is None:
        return None
    return {"snapshot": before, "expected_revision": revision}


def parse_history_entry(entry: object) -> tuple[dict, str] | None:
    if not isinstance(entry, dict):
        return None
    snapshot = entry.get("snapshot")
    revision = entry.get("expected_revision")
    if not isinstance(snapshot, dict) or not isinstance(revision, str) or _REVISION_RE.fullmatch(revision) is None:
        return None
    if set(entry) != {"snapshot", "expected_revision"}:
        return None
    return snapshot, revision


class HistoryMixin:
    def _install_dirty_watchers(self) -> None:
        for var in (
            self.var_new_assay_key,
            self.var_new_assay_name,
            self.var_lot_regex,
            self.var_excel_filename,
            self.var_sheet_template,
        ):
            var.trace_add("write", self._on_form_changed)
        for var in (
            self.var_field_key,
            self.var_field_regex,
            self.var_search_mode,
            self.var_search_after,
            self.var_search_line,
            self.var_field_excel_column,
            self.var_field_dedupe,
        ):
            var.trace_add("write", self._on_field_form_changed)
        self.var_search_mode_label.trace_add("write", self.on_search_mode_label_changed)

    def _on_form_changed(self, *_args: object) -> None:
        if self._suspend_dirty_tracking:
            return
        if self.current_draft_path:
            self._dirty = True

    def _on_field_form_changed(self, *_args: object) -> None:
        if self._suspend_dirty_tracking or self._field_form_loading:
            return
        self._field_form_dirty = True

    def _schedule_autosave(self) -> None:
        self.after(self._autosave_ms, self._autosave_tick)

    def _autosave_tick(self) -> None:
        try:
            if (
                self.var_autosave.get()
                and self._dirty
                and self.current_draft_path
                and not self._busy
                and not getattr(self, "_field_mutation_guard", False)
                and not getattr(self, "_dialog_guard", False)
            ):
                self._save_meta_to_draft(push_undo=False)
                ts = datetime.now().strftime("%H:%M:%S")
                self.var_last_autosave.set(ts)
                self._dirty = False
                self._log(f"[AUTOSAVE] Draft gespeichert um {ts}")
        except Exception as e:
            self._log(f"[AUTOSAVE-ERROR] {e}")
        finally:
            self._schedule_autosave()

    def _capture_draft_snapshot(self) -> dict | None:
        if not self.current_draft_path:
            return None
        try:
            return self._rules.load_draft(self.current_draft_path)
        except Exception:
            return None

    def _push_undo_snapshot(self) -> None:
        snap = self._capture_draft_snapshot()
        reader = getattr(getattr(self, "_rules", None), "draft_content_revision", None)
        revision = None
        if callable(reader) and self.current_draft_path:
            try:
                revision = reader(self.current_draft_path)
            except Exception:
                revision = None
        if not isinstance(snap, dict) or not isinstance(revision, str) or _REVISION_RE.fullmatch(revision) is None:
            return
        self._undo_stack.append({"snapshot": snap, "expected_revision": revision})
        if len(self._undo_stack) > 50:
            self._undo_stack = self._undo_stack[-50:]
        self._redo_stack.clear()

    def _apply_restored_widgets(self, snap: dict) -> None:
        self._suspend_dirty_tracking = True
        try:
            self._apply_data_to_widgets(snap)
        finally:
            self._suspend_dirty_tracking = False
        self._dirty = False
        self._field_form_dirty = False
        self._field_form_is_new = False
        self._selected_field_key = None
        updater = getattr(self, "_update_field_commit_button", None)
        if callable(updater):
            updater()

    def _restore_snapshot(self, snap: dict, *, expected_revision: str | None = None) -> None:
        if not self.current_draft_path:
            return
        if not isinstance(expected_revision, str) or _REVISION_RE.fullmatch(expected_revision) is None:
            raise RuntimeError(_ENTRY_ERROR)
        self._rules.restore_draft_snapshot(
            self.current_draft_path,
            snap,
            expected_revision=expected_revision,
            return_receipt=True,
        )
        self._apply_restored_widgets(snap)

    def _guarded_history_step(self, *, undo: bool) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        stack = self._undo_stack if undo else self._redo_stack
        other = self._redo_stack if undo else self._undo_stack
        empty_hint = "Undo-Stack ist leer." if undo else "Redo-Stack ist leer."
        done_hint = "Undo ausgeführt." if undo else "Redo ausgeführt."
        if not self._resolve_dirty_field_form():
            return
        if not stack:
            self._set_hint(empty_hint)
            return
        parsed = parse_history_entry(stack[-1])
        if parsed is None:
            from tkinter import messagebox

            messagebox.showerror("Fehler", _ENTRY_ERROR)
            return
        snap, expected_revision = parsed
        self._field_mutation_guard = True
        try:
            try:
                receipt = self._rules.restore_draft_snapshot(
                    self.current_draft_path,
                    snap,
                    expected_revision=expected_revision,
                    return_receipt=True,
                )
            except Exception as exc:
                from tkinter import messagebox

                messagebox.showerror("Fehler", str(exc))
                return
            opposite = history_entry_from_receipt(receipt)
            if opposite is None:
                from tkinter import messagebox

                messagebox.showerror("Fehler", _RECEIPT_ERROR)
                return
            stack.pop()
            other.append(opposite)
            try:
                self._apply_restored_widgets(snap)
            except Exception as exc:
                from tkinter import messagebox

                messagebox.showerror("Hinweis", _RELOAD_ERROR.format(exc=exc))
                return
            self._set_hint(done_hint)
        finally:
            self._field_mutation_guard = False

    def on_undo(self) -> None:
        self._guarded_history_step(undo=True)

    def on_redo(self) -> None:
        self._guarded_history_step(undo=False)
