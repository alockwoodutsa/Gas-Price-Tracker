"""Tkinter desktop interface for historical U.S. fuel prices."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from bisect import bisect_left
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .config import load_eia_api_key
from .providers import EIAProvider, FREDProvider, Facet, PricePoint, ProviderError
from .storage import PriceStore


INK = "#192b28"
MUTED = "#6a7772"
PAPER = "#f4f6f2"
WHITE = "#ffffff"
GREEN = "#16745b"
ORANGE = "#d4773d"
GRID = "#e5e9e4"
HISTORICAL_EVENTS = (
    ("1990-08-02", "Gulf War"),
    ("2003-03-20", "Iraq invasion begins"),
    ("2005-08-29", "Hurricane Katrina"),
    ("2008-07-11", "Oil-price peak"),
    ("2020-03-11", "COVID-19 pandemic"),
    ("2022-02-24", "Ukraine invasion"),
    ("2026-02-28", "Iran war begins"),
)


def default_database_path() -> Path:
    app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / ".local" / "share"
    return base / "GasPriceTracker" / "prices.db"


class GasPriceApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Fuel Price Ledger")
        self.root.geometry("1020x720")
        self.root.minsize(780, 600)
        self.root.configure(bg=PAPER)

        self.store = PriceStore(default_database_path())
        self.eia = EIAProvider()
        self.fred = FREDProvider()
        self.source = tk.StringVar(value="EIA")
        self.fuel = tk.StringVar(value="Regular gasoline")
        self.region = tk.StringVar(value="U.S. average (NUS)")
        self.api_key = tk.StringVar(value=load_eia_api_key())
        self.show_events = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Choose a source and refresh to load price history.")
        self.region_ids = {"U.S. average (NUS)": "NUS"}
        self.busy = False
        self.hover_index: int | None = None
        self.hover_items: tuple[int, int] | None = None

        self._build()
        self._draw_history()

    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=PAPER, padx=28, pady=24)
        outer.pack(fill="both", expand=True)

        heading = tk.Frame(outer, bg=PAPER)
        heading.pack(fill="x", pady=(0, 20))
        tk.Label(heading, text="FUEL PRICE LEDGER", bg=PAPER, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        title_row = tk.Frame(heading, bg=PAPER)
        title_row.pack(fill="x", pady=(5, 0))
        tk.Label(title_row, text="Prices, week by week.", bg=PAPER, fg=INK, font=("Segoe UI", 25, "bold")).pack(side="left")
        self.refresh_button = tk.Button(
            title_row,
            text="Refresh history",
            command=self.refresh,
            bg=GREEN,
            fg=WHITE,
            activebackground="#105b47",
            activeforeground=WHITE,
            relief="flat",
            padx=18,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.refresh_button.pack(side="right", padx=(12, 0))

        controls = tk.Frame(outer, bg=WHITE, padx=16, pady=14, highlightbackground=GRID, highlightthickness=1)
        controls.pack(fill="x", pady=(0, 18))
        self._field(controls, "DATA SOURCE", self._source_control(controls), 0)
        self._field(controls, "FUEL", self._fuel_control(controls), 1)
        self._field(controls, "REGION", self._region_control(controls), 2)
        self.key_entry = tk.Entry(
            controls,
            textvariable=self.api_key,
            show="*",
            relief="solid",
            bd=1,
            font=("Segoe UI", 10),
            highlightthickness=0,
        )
        self._field(controls, "EIA API KEY", self.key_entry, 3)

        stats = tk.Frame(outer, bg=PAPER)
        stats.pack(fill="x", pady=(0, 16))
        self.current_value = self._stat(stats, "LATEST PRICE", "--")
        self.change_value = self._stat(stats, "CHANGE IN VIEW", "--")
        self.points_value = self._stat(stats, "OBSERVATIONS", "0")

        chart_frame = tk.Frame(outer, bg=WHITE, highlightbackground=GRID, highlightthickness=1)
        chart_frame.pack(fill="both", expand=True)
        chart_header = tk.Frame(chart_frame, bg=WHITE, padx=18, pady=14)
        chart_header.pack(fill="x")
        tk.Label(chart_header, text="Weekly average · USD per gallon", bg=WHITE, fg=INK, font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Checkbutton(
            chart_header,
            text="Historical events",
            variable=self.show_events,
            command=self._draw_history,
        ).pack(side="right", padx=(12, 0))
        self.range_label = tk.Label(chart_header, text="HISTORY", bg=WHITE, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.range_label.pack(side="right")
        self.canvas = tk.Canvas(chart_frame, bg=WHITE, height=330, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self._draw_history())
        self.canvas.bind("<Motion>", self._show_history_hover)
        self.canvas.bind("<Leave>", lambda _event: self._hide_history_hover())

        self.status_label = tk.Label(outer, textvariable=self.status, bg=PAPER, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.status_label.pack(fill="x", pady=(12, 0))

    def _field(self, parent: tk.Widget, label: str, control: tk.Widget, column: int) -> None:
        padding = (0, 12) if column < 3 else (0, 0)
        tk.Label(parent, text=label, bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(
            row=0, column=column, sticky="w", padx=padding, pady=(0, 6)
        )
        control.grid(row=1, column=column, sticky="ew", padx=padding, ipady=5)
        parent.grid_columnconfigure(column, weight=1)

    def _combo(self, parent: tk.Widget, values: tuple[str, ...], variable: tk.StringVar) -> ttk.Combobox:
        return ttk.Combobox(parent, values=values, textvariable=variable, state="readonly", font=("Segoe UI", 10), width=19)

    def _source_control(self, parent: tk.Widget) -> ttk.Combobox:
        control = self._combo(parent, ("EIA", "FRED"), self.source)
        control.bind("<<ComboboxSelected>>", self._source_changed)
        return control

    def _fuel_control(self, parent: tk.Widget) -> ttk.Combobox:
        control = self._combo(parent, tuple(self.eia.PRODUCTS), self.fuel)
        control.bind("<<ComboboxSelected>>", lambda _event: self._draw_history())
        return control

    def _region_control(self, parent: tk.Widget) -> ttk.Combobox:
        control = self._combo(parent, tuple(self.region_ids), self.region)
        control.bind("<<ComboboxSelected>>", lambda _event: self._draw_history())
        self.region_control = control
        return control

    def _stat(self, parent: tk.Widget, label: str, value: str) -> tk.Label:
        cell = tk.Frame(parent, bg=WHITE, padx=16, pady=12, highlightbackground=GRID, highlightthickness=1)
        cell.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(cell, text=label, bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        result = tk.Label(cell, text=value, bg=WHITE, fg=INK, font=("Segoe UI", 19, "bold"))
        result.pack(anchor="w", pady=(4, 0))
        return result

    def _source_changed(self, _event: tk.Event) -> None:
        is_eia = self.source.get() == "EIA"
        self.key_entry.configure(state="normal" if is_eia else "disabled")
        self.region_control.configure(state="readonly" if is_eia else "disabled")
        self.fuel.set("Regular gasoline" if not is_eia else self.fuel.get())
        self._draw_history()

    def _selection(self) -> tuple[str, str, str]:
        if self.source.get() == "FRED":
            return "FRED", "EPMR", "NUS"
        return "EIA", self.eia.PRODUCTS[self.fuel.get()], self.region_ids.get(self.region.get(), "NUS")

    def _draw_history(self) -> None:
        source, product, region = self._selection()
        points = self.store.history(source, product, region)
        self.chart_points = points
        self.points_value.configure(text=f"{len(points):,}")
        self.canvas.delete("all")
        self.hover_index = None
        self.hover_items = None
        if not points:
            self.current_value.configure(text="--")
            self.change_value.configure(text="--")
            self.range_label.configure(text="NO HISTORY YET")
            self.canvas.create_text(
                max(self.canvas.winfo_width() // 2, 200),
                max(self.canvas.winfo_height() // 2, 120),
                text="Refresh history to collect weekly prices",
                fill=MUTED,
                font=("Segoe UI", 12),
            )
            return

        latest = points[-1]
        self.current_value.configure(text=f"${latest.price:.3f}")
        delta = latest.price - points[0].price
        self.change_value.configure(text=f"{delta:+.3f}")
        self.range_label.configure(text=f"{points[0].period}  —  {latest.period}")
        self._plot(points)

    def _show_history_hover(self, event: tk.Event) -> None:
        points = self.chart_points
        if not points:
            return

        width = max(self.canvas.winfo_width(), 400)
        height = max(self.canvas.winfo_height(), 240)
        left, right, top, bottom = 62, width - 22, 18, height - 42
        if not left <= event.x <= right or not top <= event.y <= bottom:
            self._hide_history_hover()
            return

        fraction = (event.x - left) / (right - left)
        index = round(fraction * max(len(points) - 1, 0))
        if index == self.hover_index:
            return

        point = points[index]
        tooltip_width, tooltip_height = 156, 42
        tooltip_x = min(event.x + 12, width - tooltip_width - 4)
        tooltip_y = max(event.y - tooltip_height - 10, 4)
        if self.hover_items is None:
            rectangle = self.canvas.create_rectangle(
                tooltip_x,
                tooltip_y,
                tooltip_x + tooltip_width,
                tooltip_y + tooltip_height,
                fill=INK,
                outline=INK,
                tags="hover",
            )
            text = self.canvas.create_text(
                tooltip_x + 9,
                tooltip_y + 7,
                text="",
                anchor="nw",
                fill=WHITE,
                font=("Segoe UI", 9, "bold"),
                tags="hover",
            )
            self.hover_items = (rectangle, text)

        rectangle, text = self.hover_items
        self.canvas.coords(
            rectangle,
            tooltip_x,
            tooltip_y,
            tooltip_x + tooltip_width,
            tooltip_y + tooltip_height,
        )
        self.canvas.coords(text, tooltip_x + 9, tooltip_y + 7)
        self.canvas.itemconfigure(text, text=f"{point.period}\n${point.price:.3f} per gallon")
        self.canvas.itemconfigure(rectangle, state="normal")
        self.canvas.itemconfigure(text, state="normal")
        self.hover_index = index

    def _hide_history_hover(self) -> None:
        if self.hover_items is None or self.hover_index is None:
            return
        for item in self.hover_items:
            self.canvas.itemconfigure(item, state="hidden")
        self.hover_index = None

    def _plot(self, points: list[PricePoint]) -> None:
        width = max(self.canvas.winfo_width(), 400)
        height = max(self.canvas.winfo_height(), 240)
        left, right, top, bottom = 62, width - 22, 18, height - 42
        values = [point.price for point in points]
        low, high = min(values), max(values)
        spread = high - low or 0.1
        low -= spread * 0.12
        high += spread * 0.12

        plot_indexes = list(range(len(points)))
        if len(points) > right - left:
            bucket_count = max((right - left) // 2, 1)
            bucket_size = (len(points) + bucket_count - 1) // bucket_count
            plot_indexes = {0, len(points) - 1}
            for start in range(0, len(points), bucket_size):
                end = min(start + bucket_size, len(points))
                bucket_indexes = range(start, end)
                plot_indexes.update(
                    (
                        min(bucket_indexes, key=lambda index: values[index]),
                        max(bucket_indexes, key=lambda index: values[index]),
                    )
                )
            plot_indexes = sorted(plot_indexes)

        for tick in range(5):
            fraction = tick / 4
            y = bottom - fraction * (bottom - top)
            value = low + fraction * (high - low)
            self.canvas.create_line(left, y, right, y, fill=GRID)
            self.canvas.create_text(left - 10, y, text=f"${value:.2f}", anchor="e", fill=MUTED, font=("Segoe UI", 8))

        coords = []
        last_index = max(len(points) - 1, 1)
        for index in plot_indexes:
            point = points[index]
            x = left + index / last_index * (right - left)
            y = bottom - (point.price - low) / (high - low) * (bottom - top)
            coords.extend((x, y))
        if len(coords) >= 4:
            self.canvas.create_line(*coords, fill=GREEN, width=3)
        self._draw_event_markers(points, left, right, top, bottom)
        self.canvas.create_oval(coords[-2] - 4, coords[-1] - 4, coords[-2] + 4, coords[-1] + 4, fill=ORANGE, outline=WHITE, width=2)
        self.canvas.create_text(left, bottom + 18, text=points[0].period, anchor="w", fill=MUTED, font=("Segoe UI", 8))
        self.canvas.create_text(right, bottom + 18, text=points[-1].period, anchor="e", fill=MUTED, font=("Segoe UI", 8))

    def _draw_event_markers(self, points: list[PricePoint], left: int, right: int, top: int, bottom: int) -> None:
        if not self.show_events.get():
            return

        try:
            point_dates = [datetime.strptime(point.period, "%Y-%m-%d").date() for point in points]
        except ValueError:
            return

        first_date, last_date = point_dates[0], point_dates[-1]
        last_index = max(len(points) - 1, 1)
        for event_number, (date_text, label) in enumerate(HISTORICAL_EVENTS):
            event_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            if not first_date <= event_date <= last_date:
                continue

            index = bisect_left(point_dates, event_date)
            if index and (index == len(point_dates) or event_date - point_dates[index - 1] < point_dates[index] - event_date):
                index -= 1
            x = left + index / last_index * (right - left)
            self.canvas.create_line(x, top, x, bottom, fill=ORANGE, dash=(5, 4), width=1, tags="event")
            anchor = "nw" if x < (left + right) / 2 else "ne"
            label_x = x + 4 if anchor == "nw" else x - 4
            label_y = top + 4 + (event_number % 2) * 18
            self.canvas.create_text(
                label_x,
                label_y,
                text=f"{event_date.year} {label}",
                anchor=anchor,
                fill=ORANGE,
                font=("Segoe UI", 8, "bold"),
                tags="event",
            )

    def refresh(self) -> None:
        if self.busy:
            return
        source, product, region = self._selection()
        key = self.api_key.get().strip()
        if source == "EIA" and not key:
            messagebox.showinfo("EIA API key needed", "Register for a free key at eia.gov/opendata, then enter it here or set EIA_API_KEY.")
            return

        self.busy = True
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.status.set(f"Fetching weekly history from {source}...")
        threading.Thread(target=self._fetch, args=(source, product, region, key), daemon=True).start()

    def _fetch(self, source: str, product: str, region: str, key: str) -> None:
        try:
            regions: list[Facet] = []
            if source == "EIA":
                regions = self.eia.list_regions(key)
                points = self.eia.fetch_history(api_key=key, product=product, region=region)
            else:
                points = self.fred.fetch_history()
            self.store.save(points)
            self.root.after(0, self._fetch_finished, source, points, regions, None)
        except ProviderError as error:
            self.root.after(0, self._fetch_finished, source, [], [], str(error))
        except Exception as error:
            self.root.after(0, self._fetch_finished, source, [], [], f"Unexpected error: {error}")

    def _fetch_finished(self, source: str, points: list[PricePoint], regions: list[Facet], error: str | None) -> None:
        self.busy = False
        self.refresh_button.configure(state="normal", text="Refresh history")
        if error:
            self.status.set(error)
            return
        if source == "EIA" and regions:
            self.region_ids = {f"{facet.label} ({facet.id})": facet.id for facet in regions}
            self.region.set(next((label for label, value in self.region_ids.items() if value == "NUS"), self.region.get()))
            self.region_control.configure(values=tuple(self.region_ids))
        self.status.set(f"Updated {len(points):,} weekly observations at {datetime.now():%H:%M}.")
        self._draw_history()


def main() -> None:
    root = tk.Tk()
    GasPriceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()