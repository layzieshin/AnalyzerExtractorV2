from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import format_timestamp
from interfaces.tk.widgets.common import Card, EmptyState, SectionHeader, create_scrollable_tree
from src.application.api import ReportPdfPage, ValidationQueueItem


PdfPreviewRequest = tuple[int, str, int, int, float]


class ValidationView(ttk.Frame):
    """Primary work queue for human first validation of assay runs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], None],
        on_save: Callable[[], None],
        on_open_pdf: Callable[[], None],
        on_preview: Callable[[PdfPreviewRequest], None] | None = None,
        on_reanalyze: Callable[[], None] | None = None,
        on_choose: Callable[[str], None] | None = None,
        on_edit_rules: Callable[[], None] | None = None,
        on_add_device: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_refresh = on_refresh
        self._on_save = on_save
        self._on_open_pdf = on_open_pdf
        self._on_preview = on_preview
        self._on_reanalyze = on_reanalyze
        self._on_choose = on_choose
        self._on_edit_rules = on_edit_rules
        self._on_add_device = on_add_device
        self._device_report_context = None
        self._device_labels = {}
        self._reanalysis_busy = False
        self._items: dict[str, ValidationQueueItem] = {}
        self._default_operator_initials = ""
        self._pdf_generation = 0
        self._pdf_identity: tuple[str, int] | None = None
        self._pdf_page_index = 0
        self._pdf_page_count = 0
        self._pdf_zoom = 1.0
        self._pdf_photo: tk.PhotoImage | None = None
        self._pdf_width = 0
        self._pdf_active = True
        self._build()

    def _build(self) -> None:
        card = Card(self)
        card.pack(fill="both", expand=True)
        body = card.body
        SectionHeader(
            body,
            "Validierung",
            subtitle="Offene Assay-Messungen fachlich pruefen und mit Initialen freigeben.",
            action_text="Aktualisieren",
            on_action=self._on_refresh,
        ).pack(fill="x", pady=(0, 8))

        self._split = ttk.Panedwindow(body, orient="horizontal")
        self._split.pack(fill="both", expand=True)
        self._pdf_panel = ttk.Frame(self._split, style="CardInner.TFrame")
        workflow = ttk.Frame(self._split, style="CardInner.TFrame", padding=(12, 0, 0, 0))
        workflow.columnconfigure(0, weight=1)
        workflow.rowconfigure(0, weight=1, minsize=48)
        workflow.rowconfigure(3, weight=2, minsize=48)
        self._split.add(self._pdf_panel, weight=1)
        self._split.add(workflow, weight=1)
        self._split.bind("<Configure>", self._on_split_configure)
        self._build_pdf_panel()

        list_frame, self._tree = create_scrollable_tree(
            workflow,
            ("report", "assay", "lot", "device", "time", "status"),
            ("Bericht", "Assay", "Charge/Lot", "Geraet", "Zeit", "Status"),
            height=4,
        )
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._tree.configure(selectmode="extended")
        self._tree.column("assay", width=260, minwidth=200, stretch=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._empty = EmptyState(workflow, "Keine offenen Validierungen.")
        self._empty.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self._empty.grid_remove()

        self._lbl_context = ttk.Label(workflow, text="Keine Messung ausgewaehlt.", style="Muted.TLabel", wraplength=460)
        self._lbl_context.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        workflow.bind("<Configure>", lambda event: self._lbl_context.configure(wraplength=max(180, event.width - 20)))
        fields_frame, self._fields = create_scrollable_tree(
            workflow,
            ("field", "old", "new"),
            ("Feld / Nachweis", "Gewaehlte Werte", "Neue Werte"),
            height=4,
        )
        fields_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        self._fields.tag_configure("changed", background="#fff3cd")
        self._fields.tag_configure("metadata", foreground="#526171")

        analysis_actions = ttk.Frame(workflow, style="CardInner.TFrame")
        analysis_actions.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        self._btn_reanalyze = ttk.Button(analysis_actions, text="Erneut analysieren", command=lambda: self._on_reanalyze and self._on_reanalyze())
        self._btn_reanalyze.pack(side="left")
        self._btn_edit_rules = ttk.Button(analysis_actions, text="Regelwerk bearbeiten", command=lambda: self._on_edit_rules and self._on_edit_rules())
        self._btn_edit_rules.pack(side="left", padx=(8, 0))
        choices = ttk.Frame(workflow, style="CardInner.TFrame")
        choices.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self._btn_keep_old = ttk.Button(choices, text="Alte Werte behalten", command=lambda: self._on_choose and self._on_choose("keep_old"))
        self._btn_keep_old.pack(side="left")
        self._btn_accept_new = ttk.Button(choices, text="Neue Werte übernehmen", command=lambda: self._on_choose and self._on_choose("accept_new"))
        self._btn_accept_new.pack(side="left", padx=(8, 0))

        form = ttk.Frame(workflow, style="CardInner.TFrame")
        form.grid(row=6, column=0, sticky="ew")
        ttk.Label(form, text="Gerät dieses Berichts").grid(row=0, column=0, sticky="w")
        self._var_report_device = tk.StringVar()
        self._report_device_combo = ttk.Combobox(form, textvariable=self._var_report_device, state="readonly")
        self._report_device_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._device_add_button = ttk.Button(form, text="Gerät hier anlegen", command=lambda: self._on_add_device and self._on_add_device())
        self._device_add_button.grid(row=0, column=2, padx=(8, 0))
        self._var_device_confirmed = tk.BooleanVar(value=False)
        self._device_confirmation = ttk.Checkbutton(form, text="Gerät für diesen Quellbericht bestätigen", variable=self._var_device_confirmed)
        self._device_confirmation.grid(row=1, column=1, sticky="w", pady=(4, 0))
        self._var_device_reason = tk.StringVar()
        self._device_reason_label = ttk.Label(form, text="Grund der Gerätekorrektur")
        self._device_reason_entry = ttk.Entry(form, textvariable=self._var_device_reason)
        self._device_reason_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._device_reason_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
        self._device_reason_label.grid_remove()
        self._device_reason_entry.grid_remove()
        self._lbl_device_impact = ttk.Label(form, text="", wraplength=460, style="Muted.TLabel")
        self._lbl_device_impact.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._report_device_combo.bind("<<ComboboxSelected>>", self._device_selection_changed)
        ttk.Label(form, text="Initialen").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._var_initials = tk.StringVar()
        ttk.Entry(form, textvariable=self._var_initials, width=16).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        ttk.Label(form, text="Kommentar (optional)").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self._var_comment = tk.StringVar()
        ttk.Entry(form, textvariable=self._var_comment).grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        form.columnconfigure(1, weight=1)
        actions = ttk.Frame(workflow, style="CardInner.TFrame")
        actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self._btn_save = ttk.Button(actions, text="Validierung speichern", style="Primary.TButton", command=self._on_save)
        self._btn_save.pack(side="left")
        self._btn_open_pdf = ttk.Button(actions, text="PDF extern oeffnen", command=self._on_open_pdf)
        self._btn_open_pdf.pack(side="left", padx=(8, 0))
        self._btn_save.configure(state="disabled")
        self._btn_open_pdf.configure(state="disabled")
        for button in (self._btn_reanalyze, self._btn_keep_old, self._btn_accept_new, self._btn_edit_rules):
            button.configure(state="disabled")

    def _build_pdf_panel(self) -> None:
        panel = self._pdf_panel
        ttk.Label(panel, text="Original-PDF", style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 6))
        navigation = ttk.Frame(panel, style="CardInner.TFrame")
        navigation.pack(fill="x")
        self._btn_pdf_previous = ttk.Button(navigation, text="Zurueck", command=lambda: self._change_pdf_page(-1))
        self._btn_pdf_previous.pack(side="left")
        self._lbl_pdf_page = ttk.Label(navigation, text="Seite - / -")
        self._lbl_pdf_page.pack(side="left", padx=8)
        self._btn_pdf_next = ttk.Button(navigation, text="Weiter", command=lambda: self._change_pdf_page(1))
        self._btn_pdf_next.pack(side="left")
        zoom = ttk.Frame(panel, style="CardInner.TFrame")
        zoom.pack(fill="x", pady=(6, 4))
        self._btn_pdf_zoom_out = ttk.Button(zoom, text="-", width=3, command=lambda: self._set_pdf_zoom(self._pdf_zoom - 0.25))
        self._btn_pdf_zoom_out.pack(side="left")
        self._lbl_pdf_zoom = ttk.Label(zoom, text="100 %", width=7, anchor="center")
        self._lbl_pdf_zoom.pack(side="left")
        self._btn_pdf_zoom_in = ttk.Button(zoom, text="+", width=3, command=lambda: self._set_pdf_zoom(self._pdf_zoom + 0.25))
        self._btn_pdf_zoom_in.pack(side="left")
        self._btn_pdf_fit = ttk.Button(zoom, text="Breite anpassen", command=self._fit_pdf_width)
        self._btn_pdf_fit.pack(side="left", padx=(8, 0))
        self._lbl_pdf_status = ttk.Label(panel, text="Keine Messung ausgewaehlt.", style="Muted.TLabel", wraplength=450)
        self._lbl_pdf_status.pack(anchor="w", fill="x", pady=(0, 6))
        viewport = ttk.Frame(panel, style="CardInner.TFrame")
        viewport.pack(fill="both", expand=True)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)
        self._pdf_canvas = tk.Canvas(viewport, background="#d8dde3", highlightthickness=0, width=400, height=400)
        vertical = ttk.Scrollbar(viewport, orient="vertical", command=self._pdf_canvas.yview)
        horizontal = ttk.Scrollbar(viewport, orient="horizontal", command=self._pdf_canvas.xview)
        self._pdf_canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._pdf_canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        panel.bind("<Configure>", lambda event: self._lbl_pdf_status.configure(wraplength=max(180, event.width - 12)))
        self._update_pdf_controls()

    def _on_split_configure(self, event: tk.Event) -> None:
        if event.width > 1:
            self._split.sashpos(0, event.width // 2)

    def pdf_request(self) -> PdfPreviewRequest | None:
        if self._pdf_identity is None or not self._pdf_active:
            return None
        report_id, run_id = self._pdf_identity
        return self._pdf_generation, report_id, run_id, self._pdf_page_index, self._pdf_zoom

    def _clear_pdf_image(self) -> None:
        self._pdf_canvas.delete("all")
        self._pdf_canvas.configure(scrollregion=(0, 0, 0, 0))
        self._pdf_photo = None

    def _request_pdf_page(self) -> None:
        self._pdf_generation += 1
        self._clear_pdf_image()
        request = self.pdf_request()
        if request is not None:
            self._lbl_pdf_status.configure(text="PDF wird geladen …")
            if self._on_preview is not None:
                self._on_preview(request)
        self._update_pdf_controls()

    def _update_pdf_controls(self) -> None:
        selected = self._pdf_identity is not None and self._pdf_active
        known_page = selected and 0 <= self._pdf_page_index < self._pdf_page_count
        self._lbl_pdf_page.configure(text=f"Seite {self._pdf_page_index + 1} / {self._pdf_page_count}" if self._pdf_page_count else "Seite - / -")
        self._lbl_pdf_zoom.configure(text=f"{self._pdf_zoom:.0%}")
        self._btn_pdf_previous.configure(state="normal" if known_page and self._pdf_page_index > 0 else "disabled")
        self._btn_pdf_next.configure(state="normal" if known_page and self._pdf_page_index + 1 < self._pdf_page_count else "disabled")
        self._btn_pdf_zoom_out.configure(state="normal" if selected and self._pdf_zoom > 0.25 else "disabled")
        self._btn_pdf_zoom_in.configure(state="normal" if selected and self._pdf_zoom < 3.0 else "disabled")
        self._btn_pdf_fit.configure(state="normal" if selected and self._pdf_photo is not None else "disabled")

    def _change_pdf_page(self, delta: int) -> None:
        target = self._pdf_page_index + delta
        if self._pdf_identity is not None and 0 <= target < self._pdf_page_count:
            self._pdf_page_index = target
            self._request_pdf_page()

    def _set_pdf_zoom(self, zoom: float, *, automatic: bool = False) -> None:
        if not math.isfinite(zoom) or zoom <= 0:
            return
        target = min(3.0, zoom if automatic else max(0.25, zoom))
        if self._pdf_identity is not None and not math.isclose(target, self._pdf_zoom, rel_tol=1e-9, abs_tol=0.0):
            self._pdf_zoom = target
            self._request_pdf_page()

    def _fit_pdf_width(self) -> None:
        if self._pdf_width > 0 and self._pdf_photo is not None:
            # Reserve the canvas padding plus two pixels for outward raster rounding.
            width = max(1, self._pdf_canvas.winfo_width() - 18)
            self._set_pdf_zoom(self._pdf_zoom * width / self._pdf_width, automatic=True)

    def render_pdf_page(self, request: PdfPreviewRequest, page: ReportPdfPage) -> None:
        if request != self.pdf_request():
            return
        if page.report_id != request[1] or page.page_index != request[3]:
            self.render_pdf_error(request, "Die PDF-Vorschau passt nicht zur gewaehlten Messung. Bitte aktualisieren.")
            return
        try:
            photo = tk.PhotoImage(master=self, data=page.image_data, format="PPM")
        except tk.TclError:
            self.render_pdf_error(request, "Die PDF-Seite konnte nicht angezeigt werden.")
            return
        self._clear_pdf_image()
        self._pdf_photo = photo
        self._pdf_width = page.width
        self._pdf_page_count = page.page_count
        self._pdf_zoom = page.zoom
        self._pdf_canvas.create_image(8, 8, anchor="nw", image=photo)
        self._pdf_canvas.configure(scrollregion=(0, 0, page.width + 16, page.height + 16))
        self._pdf_canvas.xview_moveto(0)
        self._pdf_canvas.yview_moveto(0)
        item = self.selected_item()
        self._lbl_pdf_status.configure(text=item.file_name if item is not None else "Original-PDF")
        self._update_pdf_controls()

    def render_pdf_error(self, request: PdfPreviewRequest, message: str) -> None:
        if request != self.pdf_request():
            return
        self._clear_pdf_image()
        # Keep the last successful page bounds so Previous can recover from a
        # later-page timeout. Unknown documents remain at page zero with no nav.
        if self._pdf_page_count <= 0:
            self._pdf_page_index = 0
        self._lbl_pdf_status.configure(text=message)
        self._update_pdf_controls()

    def suspend_pdf_preview(self) -> None:
        self._pdf_active = False
        self._pdf_generation += 1
        self._clear_pdf_image()
        self._update_pdf_controls()

    def resume_pdf_preview(self) -> None:
        self._pdf_active = True
        self._request_pdf_page()

    def set_default_operator_initials(self, initials: str) -> None:
        self._default_operator_initials = str(initials or "").strip()
        if not str(self._var_initials.get() or "").strip():
            self._var_initials.set(self._default_operator_initials)

    def selected_item(self) -> ValidationQueueItem | None:
        selection = self._tree.selection()
        focused = self._tree.focus()
        target = focused if focused in selection else (selection[0] if selection else "")
        return self._items.get(str(target))

    def selected_items(self) -> tuple[ValidationQueueItem, ...]:
        selected = set(self._tree.selection())
        return tuple(self._items[str(key)] for key in self._tree.get_children() if key in selected)

    def set_reanalysis_busy(self, busy: bool) -> None:
        self._reanalysis_busy = busy
        self._render_item(self.selected_item())

    def validation_initials(self) -> str:
        return self._var_initials.get()

    def validation_comment(self) -> str:
        return self._var_comment.get()

    def validation_device(self) -> str:
        return self._device_labels.get(self._var_report_device.get(), "")

    def validation_device_confirmed(self) -> bool:
        return bool(self._var_device_confirmed.get())

    def validation_device_reason(self) -> str:
        return self._var_device_reason.get().strip()

    def select_report_device(self, device_id: str) -> None:
        self._var_report_device.set(next((label for label, key in self._device_labels.items() if key == device_id), ""))
        self._device_selection_changed()

    def _device_selection_changed(self, _event=None) -> None:
        self._var_device_confirmed.set(False)
        item = self.selected_item()
        correction = bool(item and item.device_assignment_id and self.validation_device() != item.device_id)
        self._device_reason_label.grid() if correction else self._device_reason_label.grid_remove()
        self._device_reason_entry.grid() if correction else self._device_reason_entry.grid_remove()
        self._device_confirmation.configure(text="Neues Berichtgerät bestätigen" if correction else
            "Gerät dieses Berichts bereits bestätigt" if item and item.device_assignment_id else "Gerät für diesen Quellbericht bestätigen")
        self._render_device_impact(item)

    def clear_comment(self) -> None:
        self._var_comment.set("")

    def select_run(self, run_id: int) -> None:
        key = str(run_id)
        if key in self._items:
            self._tree.selection_set(key)
            self._tree.focus(key)
            self._tree.see(key)
            self._render_item(self._items[key])

    def _render_device_impact(self, item) -> None:
        if item is None:
            self._lbl_device_impact.configure(text="")
            return
        old = next((name for key, name in item.device_options if key == item.device_id), "noch nicht bestätigt")
        new = self._var_report_device.get() or "bitte wählen"
        changed = bool(item.device_assignment_id and self.validation_device() != item.device_id)
        self._lbl_device_impact.configure(text="\n".join((f"Bisher: {old} → Auswahl: {new}", *item.device_impact)))
        self._btn_save.configure(text="Gerät ändern und diese Messung erneut freigeben" if changed else "Korrektur speichern" if item.validation_current else "Erneut validieren" if item.revalidation_required else "Validierung speichern")

    def render_cases(self, items: Sequence[ValidationQueueItem]) -> None:
        selected = self.selected_item()
        previous_selection = tuple(self._tree.selection())
        previous_run_id = selected.run_id if selected is not None else None
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._items = {str(item.run_id): item for item in items}
        if not items:
            self._empty.grid()
            self._render_item(None)
            return
        self._empty.grid_remove()
        for item in items:
            status = "Historie unklar" if item.validation_ambiguous else "Duplikat / Gerät klären" if item.candidate_id else "Erneut bestätigen" if item.revalidation_required else "Bestätigt · Korrektur möglich" if item.validation_current else ("Vergleich offen" if item.comparison else ("Nacharbeit" if item.missing_fields or item.revision_error else "Offen"))
            device_name = next((name for key, name in item.device_options if key == item.device_id), item.device_id or "ungeklärt")
            self._tree.insert(
                "",
                "end",
                iid=str(item.run_id),
                values=(item.file_name or "-", item.assay_name or "Assayname fehlt", item.lot_id or "-", device_name, format_timestamp(item.created_at), status),
            )
        target = str(previous_run_id) if previous_run_id is not None and self._tree.exists(str(previous_run_id)) else str(items[0].run_id)
        retained = tuple(key for key in previous_selection if key in self._items)
        self._tree.selection_set(retained or (target,))
        self._tree.focus(target)
        self._render_item(self._items[target], refresh_pdf=True)

    def _on_select(self, _event: object) -> None:
        self._render_item(self.selected_item())

    def _render_item(self, item: ValidationQueueItem | None, *, refresh_pdf: bool = False) -> None:
        identity = (item.report_id, item.run_id) if item is not None else None
        changed = identity != self._pdf_identity
        if changed:
            self._pdf_identity = identity
            self._pdf_zoom = 1.0
        if changed or refresh_pdf:
            # Refresh rediscovers the source from page one: the same report may
            # now resolve to a shorter PDF, so an old page index is not reusable.
            self._pdf_page_index = 0
            self._pdf_page_count = 0
            self._pdf_width = 0
            self._request_pdf_page()
        for row in self._fields.get_children():
            self._fields.delete(row)
        if item is None:
            self._device_report_context = None
            self._report_device_combo.configure(values=(), state="disabled")
            self._var_report_device.set("")
            self._var_device_confirmed.set(False)
            self._device_confirmation.configure(state="disabled", text="Gerät für diesen Quellbericht bestätigen")
            self._device_add_button.configure(state="disabled")
            self._device_reason_label.grid_remove()
            self._device_reason_entry.grid_remove()
            self._render_device_impact(None)
            self._lbl_context.configure(text="Keine Messung ausgewaehlt.")
            self._btn_save.configure(state="disabled")
            self._btn_open_pdf.configure(state="disabled")
            for button in (self._btn_reanalyze, self._btn_keep_old, self._btn_accept_new, self._btn_edit_rules):
                button.configure(state="disabled")
            self._lbl_pdf_status.configure(text="Keine offenen Validierungen." if not self._items else "Keine Messung ausgewaehlt.")
            return
        device_context = (item.report_id, item.device_assignment_id, item.device_options)
        self._device_confirmation.configure(state="normal")
        self._device_add_button.configure(state="normal")
        if self._device_report_context != device_context:
            self._device_report_context = device_context
            counts = {}
            for key, name in item.device_options:
                counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
            self._device_labels = {(name if counts[name.casefold()] == 1 else name + " · " + key[-6:]): key for key, name in item.device_options}
            self._report_device_combo.configure(values=tuple(self._device_labels), state="readonly")
            chosen = item.device_id if item.device_assignment_id else item.suggested_device_id
            self._var_report_device.set(next((label for label, key in self._device_labels.items() if key == chosen), ""))
            self._var_device_confirmed.set(bool(item.device_assignment_id))
            self._device_confirmation.configure(text="Gerät dieses Berichts bereits bestätigt" if item.device_assignment_id else "Gerät für diesen Quellbericht bestätigen")
            self._var_device_reason.set("")
            self._device_reason_label.grid_remove()
            self._device_reason_entry.grid_remove()
        self._render_device_impact(item)
        status = "Validierungshistorie ist nicht eindeutig; bitte in Ergebnisse klaeren." if item.validation_ambiguous else "Nach Gerätekorrektur erneut fachlich bestätigen." if item.revalidation_required else "Bereits validiert; Korrektur möglich." if item.validation_current else "Quellkandidat: Gerät klären; ein eigener Messlauf entsteht nur bei belegbar anderem Gerät." if item.candidate_id else f"Revision {item.revision_id}: bereit zur Erstvalidierung."
        comparison = item.comparison
        if comparison:
            status = "Vergleich offen. Alte oder neue Werte auswaehlen, danach separat validieren."
            if comparison.error:
                status += " Nacharbeit: " + comparison.error
        elif item.revision_error or item.missing_fields:
            status = "Nacharbeit erforderlich: " + (item.revision_error or ", ".join(item.missing_fields))
        self._lbl_context.configure(
            text=(
                f"Bericht: {item.file_name or '-'} | Assay: {item.assay_name or 'Assayname fehlt'} | "
                f"Charge/Lot: {item.lot_id or '-'} | Gerät: {next((name for key, name in item.device_options if key == item.device_id), 'ungeklärt')} | {status}"
            )
        )
        self._fields.heading("old", text="Alte Werte" if comparison else "Gewaehlte Werte")
        if comparison:
            for field in comparison.fields:
                self._fields.insert("", "end", values=(field.field_key, field.old_value or "(leer)", field.new_value or "(leer)"), tags=("changed",) if field.changed else ())
            for field in comparison.metadata:
                self._fields.insert("", "end", values=("Nachweis: " + field.field_key, field.old_value or "-", field.new_value or "-"), tags=("metadata",))
        else:
            for field in item.fields:
                self._fields.insert("", "end", values=(field.field_key, field.value if field.value != "" else "(leer)", ""))
        for event in item.reanalysis_history:
            self._fields.insert("", "end", values=("Historie: " + event.field_key, event.value, ""), tags=("metadata",))
        available = not item.validation_ambiguous and not item.revision_error and not self._reanalysis_busy
        self._btn_save.configure(state="normal" if available and not comparison and not item.missing_fields else "disabled")
        self._btn_reanalyze.configure(state="normal" if available and not item.candidate_id and not item.validation_current else "disabled")
        self._btn_keep_old.configure(state="normal" if available and comparison and comparison.can_keep_old else "disabled")
        self._btn_accept_new.configure(state="normal" if available and comparison and comparison.can_accept_new else "disabled")
        self._btn_edit_rules.configure(state="normal" if not self._reanalysis_busy else "disabled")
        self._btn_open_pdf.configure(state="normal")
