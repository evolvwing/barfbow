#!/usr/bin/env python3
"""Interactive Shiny front end for barfbow."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import re
import tempfile
from dataclasses import dataclass
from math import atan2, ceil, cos, degrees, floor, radians, sin
from pathlib import Path
from urllib.parse import parse_qs

from shiny import App, Inputs, Outputs, Session, reactive, render, ui

import barfbow


APP_VERSION_DATE = "August 20, 2026"


@dataclass(frozen=True)
class PaletteState:
    rows: list[tuple[str, float, float, float]]
    chroma_ranges: list[tuple[str, float, int, int]]
    title: str
    luminance_cycles: float
    reverse_dot_fade: bool
    mode_label: str
    palette_name: str
    divergent: bool


PALETTE_ADJECTIVES: dict[str, tuple[str, ...]] = {
    "vivid": ("ardente", "brillante", "radiante", "vivace", "luminoso"),
    "muted": ("brumoso", "calme", "morbido", "sereno", "suave"),
    "dark": ("notturno", "oscuro", "profondo", "sombre", "vesperal"),
    "light": ("chiaro", "claro", "dorado", "solaire", "luminoso"),
    "warm": ("ambrato", "ardente", "dorato", "solare", "vermiglio"),
    "cool": ("azulado", "celeste", "glacial", "marino", "sereno"),
    "balanced": ("armonico", "gentile", "quieto", "sottile", "tranquilo"),
}

PALETTE_COMPANIONS = (
    "amalfi", "arles", "avignon", "coimbra", "cordoba", "firenze", "lisboa",
    "lucca", "matera", "menton", "napoli", "nimes", "porto", "ravenna",
    "sevilla", "siena", "toledo", "valencia", "verona", "vicenza",
    "adela", "celeste", "elio", "ines", "leon", "lucia", "maia", "mateo",
    "noemi", "renzo", "sofia", "teo",
)


README_PRESETS: dict[str, dict[str, object]] = {
    "default": {
        "label": "Chroma Rainbows · 100 colors",
        "divergent": False,
        "n": 100,
        "h_orbits": 2.5,
        "h1": 90,
        "h2": 270,
        "l_cycles": 3.5,
        "l1": 30,
        "l2": 85,
        "c1": 85,
        "delta_mode": "add",
        "delta_c": -30,
        "c_mode": "L",
        "c_interval": 12,
    },
    "categorical": {
        "label": "Categorical · 26 distinct colors",
        "divergent": False,
        "n": 26,
        "h_orbits": 3.6,
        "h1": 300,
        "h2": 120,
        "l_cycles": 2.4,
        "l1": 35,
        "l2": 85,
        "c1": 80,
        "delta_mode": "halve",
        "delta_c": -50,
        "c_mode": "L",
        "c_interval": 12,
    },
    "sequential": {
        "label": "Sequential - Blue-to-Yellow",
        "divergent": False,
        "n": 1000,
        "h_orbits": 0.5,
        "h1": 280,
        "h2": 100,
        "l_cycles": 0.5,
        "l1": 30,
        "l2": 85,
        "c1": 55,
        "delta_mode": "add",
        "delta_c": -30,
        "c_mode": "L",
        "c_interval": 12,
    },
    "divergent": {
        "label": "Divergent - Blue-Bright-Red",
        "divergent": True,
        "n": 301,
        "h_orbits": 0,
        "h1": 260,
        "h2": 30,
        "l_cycles": 1,
        "l1": 50,
        "l2": 98,
        "c1": 85,
        "delta_mode": "add",
        "delta_c": 0,
        "c_mode": "L",
        "c_interval": 12,
    },
    "divergent_dark": {
        "label": "Divergent - Blue-Dark-Red",
        "divergent": True,
        "n": 301,
        "h_orbits": 0,
        "h1": 260,
        "h2": 30,
        "l_cycles": 1,
        "l1": 90,
        "l2": 10,
        "c1": 85,
        "delta_mode": "add",
        "delta_c": 0,
        "c_mode": "L",
        "c_interval": 12,
    },
}


def parse_shared_parameters(search: str) -> dict[str, object]:
    """Parse and bound palette controls from a generated share-link query."""
    query = parse_qs(search.removeprefix("?"), keep_blank_values=False)
    values: dict[str, object] = {}

    numeric_specs = {
        "n": (2, 1000, True),
        "h_orbits": (-8, 8, False),
        "h1": (0, 359, False),
        "h2": (0, 359, False),
        "l_cycles": (0.1, 12, False),
        "l1": (0, 100, False),
        "l2": (0, 100, False),
        "c1": (0, 100, False),
        "delta_c": (-100, 100, False),
        "c_interval": (1, 1000, True),
    }
    for name, (lower, upper, integer) in numeric_specs.items():
        if name not in query:
            continue
        try:
            value = max(lower, min(upper, float(query[name][0])))
        except ValueError:
            continue
        values[name] = int(value) if integer else value

    if "n" in values and "c_interval" in values:
        values["c_interval"] = min(int(values["c_interval"]), int(values["n"]))

    if query.get("delta_mode", [""])[0] in {"add", "halve"}:
        values["delta_mode"] = query["delta_mode"][0]
    if query.get("c_mode", [""])[0] in {"L", "H", "k"}:
        values["c_mode"] = query["c_mode"][0]
    if "divergent" in query:
        values["divergent"] = query["divergent"][0].lower() in {"1", "true", "yes", "on"}
    palette_name = query.get("palette_name", [""])[0]
    if re.fullmatch(r"[a-z][a-z0-9_]{2,63}", palette_name):
        # Informational only: the authoritative name is regenerated from the
        # palette rows so a modified URL cannot relabel a different palette.
        values["palette_name"] = palette_name
    return values


def n_to_slider_position(n: int | float) -> int:
    """Map an actual color count to the two-speed N slider position."""
    n = max(2, min(1000, int(round(float(n)))))
    if n <= 100:
        return n
    return 100 + int(floor(((n - 100) / 10.0) + 0.5))


def slider_position_to_n(position: int | float) -> int:
    """Map the two-speed N slider position to its actual color count."""
    position = max(2, min(190, int(round(float(position)))))
    if position <= 100:
        return position
    return 100 + ((position - 100) * 10)


def h_orbits_to_slider_position(value: int | float) -> int:
    """Map hue orbits to a fine-centered, coarse-ended slider position."""
    value = max(-8.0, min(8.0, float(value)))
    if value < -3:
        return int(round(-30 + ((value + 3) * 2)))
    if value > 3:
        return int(round(30 + ((value - 3) * 2)))
    return int(round(value * 10))


def slider_position_to_h_orbits(position: int | float) -> float:
    """Map a hue-orbit slider position to its displayed orbit value."""
    position = max(-40, min(40, int(round(float(position)))))
    if position < -30:
        return -3 + ((position + 30) * 0.5)
    if position > 30:
        return 3 + ((position - 30) * 0.5)
    return position / 10.0


def generate_palette_name(rows: list[tuple[str, float, float, float]]) -> str:
    """Return a deterministic, feature-aware Romance-style palette slug."""
    if not rows:
        return "sereno_lisboa"

    average_lightness = sum(row[1] for row in rows) / len(rows)
    average_chroma = sum(row[2] for row in rows) / len(rows)
    hue_x = sum(max(1.0, row[2]) * cos(radians(row[3])) for row in rows)
    hue_y = sum(max(1.0, row[2]) * sin(radians(row[3])) for row in rows)
    average_hue = degrees(atan2(hue_y, hue_x)) % 360.0

    if average_chroma >= 65:
        family = "vivid"
    elif average_chroma <= 30:
        family = "muted"
    elif average_lightness >= 72:
        family = "light"
    elif average_lightness <= 42:
        family = "dark"
    elif average_hue >= 315 or average_hue < 125:
        family = "warm"
    elif 155 <= average_hue < 300:
        family = "cool"
    else:
        family = "balanced"

    fingerprint = "|".join(
        f"{color}:{lightness:.6g}:{chroma:.6g}:{hue:.6g}"
        for color, lightness, chroma, hue in rows
    ).encode("ascii")
    digest = hashlib.sha256(fingerprint).digest()
    adjectives = PALETTE_ADJECTIVES[family]
    adjective = adjectives[int.from_bytes(digest[:2], "big") % len(adjectives)]
    companion = PALETTE_COMPANIONS[int.from_bytes(digest[2:4], "big") % len(PALETTE_COMPANIONS)]
    return f"{adjective}_{companion}"


def r_palette_script(rows: list[tuple[str, float, float, float]], palette_name: str) -> str:
    """Return a sourceable R palette object with ggplot2 scale helpers."""
    colors = ", ".join(f'"{row[0]}"' for row in rows)
    return "\n".join(
        [
            f'# Generated by barfbow. Run source("{palette_name}.R") to load.',
            f"{palette_name} <- c({colors})",
            f"barfbow_palette <- {palette_name}",
            "",
            "scale_colour_barfbow <- function(...) {",
            "  ggplot2::scale_colour_manual(values = barfbow_palette, ...)",
            "}",
            "",
            "scale_fill_barfbow <- function(...) {",
            "  ggplot2::scale_fill_manual(values = barfbow_palette, ...)",
            "}",
            "",
        ]
    )


def chroma_block_count(
    n: int, h_orbits: float, l_cycles: float, c_mode: str, divergent: bool
) -> int:
    """Return the number of chroma blocks produced by the current controls."""
    n = max(2, int(n))
    if divergent:
        return 2
    if c_mode == "H":
        h_step = float(h_orbits) * (360.0 / n)
        return max(1, int(abs(h_step) * (n - 1) // 360.0) + 1)
    if c_mode == "L":
        half_period = max(1, int(round((n - 1) / (2.0 * max(0.0001, float(l_cycles))))))
        return max(1, ((n - 1) // (2 * half_period)) + 1)
    return max(1, ((n - 1) // int(c_mode)) + 1)


def delta_c_bounds(
    *, n: int, h_orbits: float, l_cycles: float, c1: float, c_mode: str, divergent: bool
) -> tuple[int, int]:
    """Integer deltaC limits that keep every later chroma strictly inside 0..100."""
    blocks = chroma_block_count(n, h_orbits, l_cycles, c_mode, divergent)
    if blocks <= 1:
        return -100, 100
    transitions = blocks - 1
    c1 = max(0.0, min(100.0, float(c1)))
    lower = ceil((-c1 / transitions) + 1e-9)
    upper = floor(((100.0 - c1) / transitions) - 1e-9)
    if lower > upper:
        return 0, 0
    return lower, upper


def make_palette_state(
    *,
    n: int,
    h_orbits: float,
    h1: float,
    h2: float,
    l1: float,
    l2: float,
    l_cycles: float,
    c1: float,
    delta_c: float | None,
    c_mode: str,
    divergent: bool,
) -> PaletteState:
    """Normalize app inputs and call the same palette builders as the CLI."""
    n = max(2, int(n))
    h_orbits = float(h_orbits)
    h1 = float(h1) % 360.0
    h2 = float(h2) % 360.0
    if not divergent:
        l1 = max(0.0, min(100.0, float(l1)))
        l2 = max(0.0, min(100.0, float(l2)))
    else:
        l1, l2 = float(l1), float(l2)
    l_cycles = 1.0 if divergent else max(0.0001, float(l_cycles))
    c1 = max(0.0, min(100.0, float(c1)))

    chroma_blocks = chroma_block_count(n, h_orbits, l_cycles, c_mode, divergent)

    if delta_c is None:
        c_values = tuple(max(0.0, min(100.0, c1 / (2**index))) for index in range(chroma_blocks))
    else:
        c_values = tuple(
            max(0.0, min(100.0, c1 + index * float(delta_c)))
            for index in range(chroma_blocks)
        )

    if divergent:
        split_index = int(ceil(n / 2.0))
        _, _, chroma_ranges, rows = barfbow.build_divergent_palette(
            n, h1, h2, l1, l2, c_values[0], c_values[1]
        )
        title = barfbow.divergent_palette_title(
            n, h1, h2, l1, l2, c_values[0], c_values[1], split_index
        )
        mode_label = "Divergent · 2 fixed hue families"
    else:
        _, _, chroma_ranges, rows = barfbow.build_palette(
            n, h_orbits, h1, l1, l2, l_cycles, c_values, c_mode
        )
        title = barfbow.palette_title(
            n, h_orbits, h1, l1, l2, l_cycles, c1, delta_c, c_mode
        )
        mode_label = f"Normal · C-mode {c_mode}"

    return PaletteState(
        rows, chroma_ranges, title, l_cycles, l1 > l2, mode_label,
        generate_palette_name(rows), divergent,
    )


def _swatches(colors: list[str]) -> str:
    return "".join(f'<span class="swatch" style="background:{color}" title="{color}"></span>' for color in colors)


def hue_slider_css(h1: float, h2: float) -> str:
    """Return reactive slider styling using gamut-fitted display colors."""
    colors = {
        "h1-control": barfbow.oklch_to_srgb_hex(62, 85, float(h1) % 360),
        "h2-control": barfbow.oklch_to_srgb_hex(62, 85, float(h2) % 360),
    }
    rules = []
    for control_id, color in colors.items():
        rules.append(
            f"""
            #{control_id} .irs--shiny .irs-bar {{
              background:{color}!important;
              border-color:{color}!important;
            }}
            #{control_id} .irs--shiny .irs-handle,
            #{control_id} .irs--shiny .irs-handle:hover,
            #{control_id} .irs--shiny .irs-handle.state_hover,
            #{control_id} .irs--shiny .irs-single {{
              background-color:{color}!important;
              border-color:{color}!important;
            }}
            """
        )
    return "\n".join(rules)


def preview_number_labels(color_count: int) -> list[int]:
    """Return at most 24 evenly spaced, human-friendly swatch labels."""
    candidates = (1, 5, 10, 25, 50, 100)
    minimum_step = max(1, ceil(color_count / 24))
    step = next((candidate for candidate in candidates if candidate >= minimum_step), 100)
    return [index for index in range(color_count) if (index + 1) % step == 0]


def _wheel_gradient(chroma: float) -> str:
    stops = []
    for hue in range(0, 361, 10):
        color = barfbow.oklch_to_srgb_hex(62.5, chroma, hue)
        stops.append(f"{color} {hue}deg")
    return ",".join(stops)


def _wheel_html(
    rows: list[tuple[str, float, float, float]],
    name: str,
    chroma: float,
    start: int,
    end: int,
    line_1: str | None = None,
    line_2: str | None = None,
    reverse: bool = False,
) -> str:
    wheel_rows = rows[start : end + 1]
    if len(wheel_rows) > 150:
        stride = ceil(len(wheel_rows) / 150)
        wheel_rows = wheel_rows[::stride]
        if wheel_rows[-1] != rows[end]:
            wheel_rows.append(rows[end])
    dots = []
    total = max(1, len(wheel_rows) - 1)
    for index, (_, lightness, _, hue) in enumerate(wheel_rows):
        radius = (100.0 - max(25.0, min(100.0, lightness))) / 75.0 * 88.0
        x = 110.0 + radius * sin(radians(hue))
        y = 110.0 - radius * cos(radians(hue))
        fade = index / total
        gray = round(51 + 204 * fade) if reverse else round(255 - 204 * fade)
        dots.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.35" fill="none" '
            f'stroke="rgb({gray},{gray},{gray})" stroke-width="1.25"/>'
        )
    label_1 = html.escape(line_1 or f"{name} = {barfbow.format_number(chroma)}%")
    label_2 = html.escape(line_2 or f"colors {start + 1}–{end + 1}")
    return f"""
      <div class="wheel-card">
        <div class="wheel-label"><strong>{label_1}</strong><span>{label_2}</span></div>
        <div class="wheel-disc" style="--wheel:{_wheel_gradient(chroma)}">
          <svg viewBox="0 0 220 220" aria-label="{label_1}, {label_2}">{''.join(dots)}</svg>
        </div>
      </div>
    """


def preview_html(state: PaletteState, color_names: dict[int, str]) -> str:
    rows = state.rows
    hexes = [row[0] for row in rows]
    simulations = [
        ("Original", hexes),
        ("Protanopia", [barfbow.simulate_cvd_hex(color, barfbow.M_PROT) for color in hexes]),
        ("Deuteranopia", [barfbow.simulate_cvd_hex(color, barfbow.M_DEUT) for color in hexes]),
        ("Tritanopia", [barfbow.simulate_cvd_hex(color, barfbow.M_TRIT) for color in hexes]),
        ("Monochrome", [barfbow.simulate_monochrome_hex(color) for color in hexes]),
    ]
    grid_style = f"grid-template-columns:repeat({len(rows)},minmax(1px,1fr))"
    swatch_rows = "".join(
        f'<div class="row-label">{label}</div><div class="swatch-row" style="{grid_style}">{_swatches(colors)}</div>'
        for label, colors in simulations
    )

    name_items = "".join(
        f'<span style="grid-column:{index + 1}" title="color {index + 1}">{html.escape(name)}</span>'
        for index, name in color_names.items()
    )
    number_indices = preview_number_labels(len(rows))
    number_items = "".join(
        f'<span style="grid-column:{index + 1}">{index + 1}</span>'
        for index in number_indices
    )
    number_grid_class = "number-grid number-grid-rotated" if len(number_indices) >= 15 else "number-grid"

    # Divergent palettes always contain two fixed chroma blocks, split at the
    # palette midpoint, even though their luminance cycle is fixed at one.
    show_chroma_progression = state.luminance_cycles > 1 or state.divergent
    ranges = barfbow.displayed_chroma_ranges(state.chroma_ranges) if show_chroma_progression else []
    wheels = [
        _wheel_html(
            rows,
            "full walk",
            state.chroma_ranges[0][1] if state.chroma_ranges else 0,
            0,
            len(rows) - 1,
            f"overview at {barfbow.format_number(state.chroma_ranges[0][1])}% chroma",
            f"{len(rows)} colors with {barfbow.format_number(state.luminance_cycles)} luminance cycles",
            state.reverse_dot_fade,
        )
    ]
    wheels.extend(_wheel_html(rows, *item, reverse=state.reverse_dot_fade) for item in ranges)
    hidden = max(0, len(state.chroma_ranges) - len(ranges)) if show_chroma_progression else 0
    hidden_note = f'<p class="hidden-note">{hidden} more chroma layers not shown</p>' if hidden else ""

    table_rows = "".join(
        f"<tr><td>{index}</td><td><i style='background:{color}'></i>{color}</td>"
        f"<td>{lightness:g}</td><td>{chroma:g}</td><td>{hue:g}</td></tr>"
        for index, (color, lightness, chroma, hue) in enumerate(rows, 1)
    )
    visible_title_lines = state.title.splitlines() if show_chroma_progression else state.title.splitlines()[:2]
    title_lines = "".join(f"<span>{html.escape(line)}</span>" for line in visible_title_lines)
    wheels_class = "wheels" if show_chroma_progression else "wheels single-wheel"
    return f"""
    <section class="preview-shell">
      <div class="palette-name" id="palette-name-value" data-palette-name="{state.palette_name}">
        <span>Palette</span><strong>{state.palette_name}</strong>
      </div>
      <header class="preview-header">
        <div class="preview-brand">
          <img src="barfbow_logo2.png" alt="Barfbow frog wizard logo">
          <p>evolvwing/barfbow</p>
        </div>
        <div class="preview-title">{title_lines}</div>
      </header>
      <div class="name-grid" style="{grid_style}">{name_items}</div>
      <div class="swatch-grid">{swatch_rows}</div>
      <div class="row-label"></div><div class="{number_grid_class}" style="{grid_style}">{number_items}</div>
      <div class="{wheels_class}">{''.join(wheels)}</div>
      {hidden_note}
      <details class="data-details"><summary>Palette data · {len(rows)} rows</summary>
        <div class="table-wrap"><table><thead><tr><th>#</th><th>Hex</th><th>L%</th><th>C%</th><th>h°</th></tr></thead>
        <tbody>{table_rows}</tbody></table></div>
      </details>
    </section>
    """


def control_label(title: str, explanation: str):
    """Build a compact label with a plain-language explanation."""
    return ui.TagList(
        ui.span(title, class_="control-title"),
        ui.span(explanation, class_="control-help"),
    )


APP_CSS = """
:root { --ink:#171717; --muted:#6d6a65; --paper:#f2f0eb; --panel:#fffefa; --accent:#ff4f87; }
* { box-sizing:border-box; }
body { margin:0; color:var(--ink); background:var(--paper); font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
.app-wrap { min-height:100vh; display:grid; grid-template-columns:310px minmax(0,1fr); }
.controls { height:100vh; overflow:auto; position:sticky; top:0; padding:24px 22px 36px; background:#181818; color:white; }
.brand { font-size:34px; font-weight:900; letter-spacing:-1.8px; margin:0; }
.tagline { color:#aaa; font-size:13px; margin:2px 0 0; }
.intro-copy { max-width:245px; margin:6px 0 20px; color:#8f8f8f; font-size:10px; font-style:italic; line-height:1.35; }
#preset-label { position:absolute!important; width:1px!important; height:1px!important; padding:0!important; margin:-1px!important; overflow:hidden!important; clip:rect(0,0,0,0)!important; white-space:nowrap!important; border:0!important; }
.controls h2 { color:#999; font-size:11px; letter-spacing:.14em; text-transform:uppercase; margin:24px 0 12px; }
.controls .form-label { font-size:12px; font-weight:650; margin-bottom:4px; }
.control-title { display:block; }
.control-help { display:block; max-width:255px; margin-top:2px; color:#9d9d9d; font-size:10px; font-weight:450; line-height:1.3; }
.controls .form-group { margin-bottom:17px; }
.controls .irs { margin-top:-5px; }
.controls .selectize-input, .controls select { color:#171717; }
.controls .form-check { margin:10px 0 18px; }
.parameter-control { transition:opacity .16s ease,filter .16s ease; }
.parameter-control.parameter-disabled { opacity:.34; filter:grayscale(1); cursor:not-allowed; }
.parameter-control.parameter-disabled .form-group { pointer-events:none; }
.controls:not(:has(#divergent:checked)) #h2-control {
  opacity:.34;
  filter:grayscale(1);
  cursor:not-allowed;
}
.controls:not(:has(#divergent:checked)) #h2-control .form-group {
  pointer-events:none;
}
.controls:has(#divergent:checked) #h2-control {
  opacity:1;
  filter:none;
  cursor:auto;
}
.controls:has(#divergent:checked) #h2-control .form-group {
  pointer-events:auto;
}
.controls:has(#divergent:checked) #c-mode-control,
.controls:has(#divergent:checked) #c-interval-control {
  display:none;
}
.download-row { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:25px; }
.download-row .btn { border:1px solid #555; color:white; background:#292929; font-size:12px; }
.download-row + .download-row { margin-top:8px; }
.copy-note { display:block; min-height:16px; margin-top:5px; color:#8fd7a6; font-size:10px; text-align:center; opacity:0; transition:opacity .16s ease; }
.copy-note.visible { opacity:1; }
.app-footer { margin:4px 0 2px; color:#858585; font-size:10px; line-height:1.45; }
.app-footer p { margin:0; }
.app-footer a { color:#b5b5b5; text-decoration:underline; text-underline-offset:2px; }
.app-footer a:hover { color:#fff; }
.sidebar-logo { display:block; width:220px; height:110px; margin:10px auto 0; object-fit:cover; object-position:center; }
.stage { min-width:0; padding:24px; }
.status-strip { display:flex; gap:9px; align-items:center; margin:0 0 12px; color:var(--muted); font-size:12px; }
.status-strip b { background:#171717; color:white; border-radius:99px; padding:5px 10px; font-weight:650; }
.preview-shell { background:var(--panel); border:1px solid #ddd9d0; border-radius:18px; padding:25px 24px 18px; box-shadow:0 16px 55px rgba(30,25,15,.08); overflow:hidden; }
.palette-name { display:flex; justify-content:center; align-items:baseline; gap:7px; margin:-5px 0 17px; color:#171717; }
.palette-name span { color:var(--muted); font-size:10px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
.palette-name strong { font:700 18px ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:-.04em; }
.preview-header { display:grid; grid-template-columns:minmax(140px,20%) 1fr; gap:25px; align-items:start; margin-bottom:47px; }
.preview-brand img { display:block; width:100%; max-width:210px; height:108px; object-fit:cover; object-position:center 58%; image-rendering:pixelated; mix-blend-mode:multiply; }
.preview-header p { margin:1px 0 0; color:#57534e; font-size:13px; font-weight:750; letter-spacing:.01em; }
.preview-title { display:flex; flex-direction:column; text-align:center; gap:4px; font-size:12px; }
.swatch-grid { display:grid; grid-template-columns:92px minmax(0,1fr); align-items:stretch; }
.row-label { font-size:11px; font-weight:750; display:flex; justify-content:flex-end; align-items:center; padding-right:10px; }
.swatch-row { display:grid; height:34px; overflow:hidden; }
.swatch { min-width:0; }
.name-grid, .number-grid { margin-left:92px; display:grid; height:34px; position:relative; }
.name-grid span { font:8px ui-monospace,SFMono-Regular,Menlo,monospace; white-space:nowrap; transform:rotate(-42deg); transform-origin:left bottom; align-self:end; }
.number-grid { height:18px; }
.number-grid span { width:max-content; justify-self:center; font:8px ui-monospace,SFMono-Regular,Menlo,monospace; text-align:center; color:#555; }
.number-grid.number-grid-rotated { height:43px; padding-top:4px; }
.number-grid-rotated span { align-self:start; justify-self:start; text-align:left; transform:rotate(58deg); transform-origin:left top; }
.wheels { display:grid; grid-template-columns:repeat(5,minmax(130px,1fr)); gap:10px; margin:24px 0 8px; }
.wheels.single-wheel { grid-template-columns:minmax(130px,210px); justify-content:center; }
.wheel-card { min-width:0; text-align:center; }
.wheel-card:first-child { position:relative; }
.wheel-card:first-child::after { content:""; position:absolute; top:39px; right:-6px; bottom:0; width:1px; background:#d2ccc1; }
.wheels.single-wheel .wheel-card:first-child::after { display:none; }
.wheel-label { height:39px; font-size:10px; display:flex; flex-direction:column; justify-content:end; }
.wheel-label span { color:var(--muted); }
.wheel-disc { width:min(100%,210px); aspect-ratio:1; margin:auto; border-radius:50%; position:relative; background:radial-gradient(circle,rgba(255,255,255,.98) 0%,rgba(255,255,255,.34) 38%,rgba(0,0,0,.52) 100%),conic-gradient(from 0deg,var(--wheel)); box-shadow:inset 0 0 0 1px #222; }
.wheel-disc svg { position:absolute; inset:0; width:100%; height:100%; }
.hidden-note { text-align:right; font-size:11px; color:var(--muted); }
.data-details { border-top:1px solid #e2ded5; margin-top:17px; padding-top:12px; font-size:12px; }
.data-details summary { cursor:pointer; font-weight:750; }
.table-wrap { max-height:320px; overflow:auto; margin-top:10px; }
table { width:100%; border-collapse:collapse; font:11px ui-monospace,SFMono-Regular,Menlo,monospace; }
th,td { padding:5px 8px; border-bottom:1px solid #eee9df; text-align:right; }
th { position:sticky; top:0; background:var(--panel); }
td i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:7px; vertical-align:-1px; }
@media (max-width:1000px) { .app-wrap{grid-template-columns:270px minmax(0,1fr)} .wheels{grid-template-columns:repeat(3,1fr)} }
@media (max-width:720px) { .app-wrap{display:block}.controls{height:auto;position:relative}.stage{padding:10px}.preview-shell{padding:18px 10px}.wheels{grid-template-columns:repeat(2,1fr)}.preview-header{grid-template-columns:1fr;margin-bottom:45px}.preview-title{text-align:left}.row-label{font-size:9px}.swatch-grid{grid-template-columns:72px minmax(0,1fr)}.name-grid,.number-grid{margin-left:72px} }
"""


DEPENDENT_CONTROL_JS = """
(() => {
  let savedLuminanceCycles = null;
  let savedDeltaC = null;

  function setSliderDisabled(wrapperId, inputId, disabled, disabledValue = null) {
    const wrapper = document.getElementById(wrapperId);
    const input = document.getElementById(inputId);
    if (!wrapper || !input) return;
    const wasDisabled = wrapper.classList.contains("parameter-disabled");
    const slider = window.jQuery ? window.jQuery(input).data("ionRangeSlider") : null;

    if (inputId === "l_cycles" && disabled !== wasDisabled) {
      if (disabled) {
        savedLuminanceCycles = slider ? slider.result.from : Number(input.value);
      }
      const nextValue = disabled ? disabledValue : savedLuminanceCycles;
      if (nextValue !== null) {
        if (slider) slider.update({ from: nextValue });
        input.value = String(nextValue);
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (!disabled) savedLuminanceCycles = null;
    }

    wrapper.classList.toggle("parameter-disabled", disabled);
    wrapper.setAttribute("aria-disabled", String(disabled));
    if (slider) slider.update({ disable: disabled });
    else input.disabled = disabled;
  }

  function syncDependentControls(divergent) {
    setSliderDisabled("h-orbits-control", "h_orbits", divergent);
    setSliderDisabled("l-cycles-control", "l_cycles", divergent, 1);
    setSliderDisabled("h2-control", "h2", !divergent);
    setSelectDisabled(
      "c-mode-control", "c_mode",
      divergent || chromaProgressionIsDisabled()
    );
    syncChromaInterval(document.getElementById("c_mode")?.value);
  }

  function setSelectDisabled(wrapperId, inputId, disabled) {
    const wrapper = document.getElementById(wrapperId);
    const input = document.getElementById(inputId);
    if (!wrapper || !input) return;
    wrapper.classList.toggle("parameter-disabled", disabled);
    wrapper.setAttribute("aria-disabled", String(disabled));
    if (input.selectize) {
      if (disabled) input.selectize.disable();
      else input.selectize.enable();
    } else {
      input.disabled = disabled;
    }
  }

  function chromaProgressionIsDisabled() {
    const divergent = Boolean(document.getElementById("divergent")?.checked);
    const input = document.getElementById("l_cycles");
    const slider = input && window.jQuery ? window.jQuery(input).data("ionRangeSlider") : null;
    const luminanceCycles = slider ? Number(slider.result.from) : Number(input?.value);
    return luminanceCycles <= 1 && !divergent;
  }

  function syncChromaInterval(cMode) {
    const divergent = Boolean(document.getElementById("divergent")?.checked);
    setSliderDisabled(
      "c-interval-control", "c_interval",
      chromaProgressionIsDisabled() || divergent || cMode !== "k"
    );
  }

  function syncChromaIntervalLimit(colorCount, requestedValue = null) {
    const input = document.getElementById("c_interval");
    if (!input) return;
    const slider = window.jQuery ? window.jQuery(input).data("ionRangeSlider") : null;
    const maximum = Math.max(1, Math.floor(Number(colorCount)));
    const previous = slider ? Number(slider.result.from) : Number(input.value);
    const requested = requestedValue === null ? previous : Number(requestedValue);
    const nextValue = Math.max(1, Math.min(maximum, Math.floor(requested)));
    if (slider) slider.update({ min: 1, max: maximum, from: nextValue });
    else input.max = String(maximum);
    if (previous !== nextValue) {
      input.value = String(nextValue);
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function syncDeltaControl(deltaMode) {
    const wrapper = document.getElementById("delta-c-control");
    const input = document.getElementById("delta_c");
    if (!wrapper || !input) return;
    const disabled = deltaMode !== "add";
    const wasDisabled = wrapper.classList.contains("parameter-disabled");
    const slider = window.jQuery ? window.jQuery(input).data("ionRangeSlider") : null;
    if (disabled !== wasDisabled) {
      if (disabled) savedDeltaC = slider ? slider.result.from : Number(input.value);
      const nextValue = disabled ? -50 : savedDeltaC;
      if (slider) {
        if (disabled) slider.update({ min: -100, max: 100, from: -50, disable: true });
        else slider.update({ from: nextValue, disable: false });
      }
      if (nextValue !== null) {
        input.value = String(nextValue);
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (!disabled) savedDeltaC = null;
    }
    wrapper.classList.toggle("parameter-disabled", disabled);
    wrapper.setAttribute("aria-disabled", String(disabled));
    if (slider) slider.update({ disable: disabled });
    else input.disabled = disabled;
  }

  function syncChromaProgressionSection(luminanceCycles) {
    const wrapper = document.getElementById("chroma-progression-controls");
    if (!wrapper) return;
    const divergent = Boolean(document.getElementById("divergent")?.checked);
    const disabled = luminanceCycles <= 1 && !divergent;
    wrapper.classList.toggle("parameter-disabled", disabled);
    wrapper.setAttribute("aria-disabled", String(disabled));

    for (const id of ["delta_c"]) {
      const input = document.getElementById(id);
      const slider = input && window.jQuery ? window.jQuery(input).data("ionRangeSlider") : null;
      if (slider) slider.update({ disable: disabled });
      else if (input) input.disabled = disabled;
    }
    for (const id of ["delta_mode"]) {
      const input = document.getElementById(id);
      if (!input) continue;
      if (input.selectize) {
        if (disabled) input.selectize.disable();
        else input.selectize.enable();
      } else {
        input.disabled = disabled;
      }
    }
    setSelectDisabled("c-mode-control", "c_mode", disabled || divergent);
    if (!disabled) {
      syncDeltaControl(document.getElementById("delta_mode").value);
    }
    syncChromaInterval(document.getElementById("c_mode").value);
  }

  function bindNumberOfColorsScale() {
    const numberOfColors = document.getElementById("n");
    if (!numberOfColors || numberOfColors.dataset.twoSpeedBound === "true") return;
    const slider = window.jQuery ? window.jQuery(numberOfColors).data("ionRangeSlider") : null;
    if (!slider) {
      window.setTimeout(bindNumberOfColorsScale, 50);
      return;
    }
    const sliderRoot = numberOfColors.closest(".form-group");
    const actualN = position => position <= 100 ? position : 100 + ((position - 100) * 10);
    const syncNumberLabels = () => {
      const maximum = sliderRoot?.querySelector(".irs-max");
      const current = sliderRoot?.querySelector(".irs-single");
      const currentText = actualN(Number(slider.result.from)).toLocaleString("en-US");
      if (maximum && maximum.textContent !== "1,000") maximum.textContent = "1,000";
      if (current && current.textContent !== currentText) current.textContent = currentText;
    };
    const labelObserver = new MutationObserver(syncNumberLabels);
    labelObserver.observe(sliderRoot, { childList: true, characterData: true, subtree: true });
    if (window.jQuery) {
      window.jQuery(numberOfColors).on("change.twoSpeedN input.twoSpeedN", syncNumberLabels);
    }
    numberOfColors.dataset.twoSpeedBound = "true";
    syncNumberLabels();
  }

  function bindHueOrbitScale() {
    const hueOrbits = document.getElementById("h_orbits");
    if (!hueOrbits || hueOrbits.dataset.twoSpeedBound === "true") return;
    const slider = window.jQuery ? window.jQuery(hueOrbits).data("ionRangeSlider") : null;
    if (!slider) {
      window.setTimeout(bindHueOrbitScale, 50);
      return;
    }
    const sliderRoot = hueOrbits.closest(".form-group");
    const actualOrbits = position => position < -30
      ? -3 + ((position + 30) * 0.5)
      : position > 30 ? 3 + ((position - 30) * 0.5) : position / 10;
    const signed = value => value > 0 ? `+${value}` : String(value);
    const syncHueOrbitLabels = () => {
      const minimum = sliderRoot?.querySelector(".irs-min");
      const maximum = sliderRoot?.querySelector(".irs-max");
      const current = sliderRoot?.querySelector(".irs-single");
      const currentText = signed(actualOrbits(Number(slider.result.from)));
      if (minimum && minimum.textContent !== "-8") minimum.textContent = "-8";
      if (maximum && maximum.textContent !== "+8") maximum.textContent = "+8";
      if (current && current.textContent !== currentText) current.textContent = currentText;
      sliderRoot?.querySelector(".irs-handle")?.setAttribute("aria-valuetext", currentText);
    };
    const labelObserver = new MutationObserver(syncHueOrbitLabels);
    labelObserver.observe(sliderRoot, { childList: true, characterData: true, subtree: true });
    if (window.jQuery) {
      window.jQuery(hueOrbits).on("change.twoSpeedHue input.twoSpeedHue", syncHueOrbitLabels);
    }
    hueOrbits.dataset.twoSpeedBound = "true";
    syncHueOrbitLabels();
  }

  let lastCModeAvailability = null;
  function enforceCModeAvailability() {
    const divergent = Boolean(document.getElementById("divergent")?.checked);
    const disabled = divergent || chromaProgressionIsDisabled();
    const select = document.getElementById("c_mode");
    const selectizeDisabled = Boolean(select?.selectize?.isDisabled);
    const wrapperDisabled = Boolean(
      document.getElementById("c-mode-control")?.classList.contains("parameter-disabled")
    );
    const state = `${disabled}:${selectizeDisabled}:${wrapperDisabled}`;
    if (state !== lastCModeAvailability && (selectizeDisabled !== disabled || wrapperDisabled !== disabled)) {
      setSelectDisabled("c-mode-control", "c_mode", disabled);
      syncChromaInterval(select?.value);
    }
    lastCModeAvailability = `${disabled}:${disabled}:${disabled}`;
  }

  function bindDependentControls() {
    bindNumberOfColorsScale();
    bindHueOrbitScale();
    const divergent = document.getElementById("divergent");
    if (!divergent || divergent.dataset.dependentControlsBound === "true") return;
    const sync = () => {
      syncDependentControls(divergent.checked);
      const luminanceCycles = document.getElementById("l_cycles");
      const slider = luminanceCycles && window.jQuery
        ? window.jQuery(luminanceCycles).data("ionRangeSlider") : null;
      const value = slider ? Number(slider.result.from) : Number(luminanceCycles?.value);
      if (Number.isFinite(value)) syncChromaProgressionSection(value);
    };
    divergent.addEventListener("change", sync);
    divergent.dataset.dependentControlsBound = "true";
    sync();

    const cMode = document.getElementById("c_mode");
    if (cMode && cMode.dataset.dependentControlsBound !== "true") {
      const syncCMode = () => syncChromaInterval(cMode.value);
      cMode.addEventListener("change", syncCMode);
      cMode.dataset.dependentControlsBound = "true";
      syncCMode();
    }

    const deltaMode = document.getElementById("delta_mode");
    if (deltaMode && deltaMode.dataset.dependentControlsBound !== "true") {
      const syncDeltaMode = () => syncDeltaControl(deltaMode.value);
      deltaMode.addEventListener("change", syncDeltaMode);
      deltaMode.dataset.dependentControlsBound = "true";
      syncDeltaMode();
    }

    const luminanceCycles = document.getElementById("l_cycles");
    if (luminanceCycles && luminanceCycles.dataset.chromaProgressionBound !== "true") {
      const syncLuminanceCycles = () => {
        const slider = window.jQuery ? window.jQuery(luminanceCycles).data("ionRangeSlider") : null;
        const value = slider ? Number(slider.result.from) : Number(luminanceCycles.value);
        if (Number.isFinite(value)) {
          syncDependentControls(Boolean(document.getElementById("divergent")?.checked));
          syncChromaProgressionSection(value);
        }
      };
      if (window.jQuery) window.jQuery(luminanceCycles).on("change.chromaProgression", syncLuminanceCycles);
      else luminanceCycles.addEventListener("change", syncLuminanceCycles);
      luminanceCycles.dataset.chromaProgressionBound = "true";
      window.setTimeout(syncLuminanceCycles, 50);
    }

  }

  function registerDependentControlHandler() {
    if (!window.Shiny?.addCustomMessageHandler) {
      window.setTimeout(registerDependentControlHandler, 50);
      return;
    }
    if (window.barfbowDependentControlHandlerBound) return;
    window.Shiny.addCustomMessageHandler("barfbow-dependent-controls", message => {
      const divergent = document.getElementById("divergent");
      if (divergent) divergent.checked = Boolean(message.divergent);
      syncChromaIntervalLimit(Number(message.color_count), Number(message.c_interval));
      syncDependentControls(Boolean(message.divergent));
      syncChromaProgressionSection(Number(message.luminance_cycles));
    });
    window.barfbowDependentControlHandlerBound = true;
    if (typeof window.Shiny.setInputValue === "function") {
      window.Shiny.setInputValue("dependent_controls_ready", Date.now(), { priority: "event" });
    }
    window.setTimeout(() => {
      const divergent = Boolean(document.getElementById("divergent")?.checked);
      const luminanceCycles = document.getElementById("l_cycles");
      const slider = luminanceCycles && window.jQuery
        ? window.jQuery(luminanceCycles).data("ionRangeSlider") : null;
      const value = slider ? Number(slider.result.from) : Number(luminanceCycles?.value);
      syncDependentControls(divergent);
      if (Number.isFinite(value)) syncChromaProgressionSection(value);
    }, 50);
  }
  registerDependentControlHandler();
  window.setInterval(enforceCModeAvailability, 200);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindDependentControls, { once: true });
  } else {
    bindDependentControls();
  }
})();
"""


SHARE_LINK_JS = """
(() => {
  const parameterIds = [
    "n", "h_orbits", "h1", "h2", "l_cycles", "l1", "l2", "c1",
    "delta_mode", "delta_c", "c_mode", "c_interval", "divergent"
  ];

  function currentValue(id) {
    const input = document.getElementById(id);
    if (!input) return null;
    if (input.type === "checkbox") return input.checked ? "1" : "0";
    const slider = window.jQuery ? window.jQuery(input).data("ionRangeSlider") : null;
    const rawValue = Number(slider ? slider.result.from : input.value);
    if (id === "n") {
      return String(rawValue <= 100 ? rawValue : 100 + ((rawValue - 100) * 10));
    }
    if (id === "h_orbits") {
      const actual = rawValue < -30
        ? -3 + ((rawValue + 30) * 0.5)
        : rawValue > 30 ? 3 + ((rawValue - 30) * 0.5) : rawValue / 10;
      return String(actual);
    }
    return String(slider ? slider.result.from : input.value);
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.select();
    document.execCommand("copy");
    fallback.remove();
  }

  function bindShareButton() {
    const button = document.getElementById("generate_link");
    const note = document.getElementById("copy-note");
    if (!button || button.dataset.shareBound === "true") return;
    button.dataset.shareBound = "true";
    button.addEventListener("click", async () => {
      const query = new URLSearchParams();
      for (const id of parameterIds) {
        const value = currentValue(id);
        if (value !== null) query.set(id, value);
      }
      const paletteName = document.getElementById("palette-name-value")?.dataset.paletteName;
      if (paletteName) query.set("palette_name", paletteName);
      const url = `${window.location.origin}${window.location.pathname}?${query.toString()}`;
      try {
        await copyText(url);
        if (note) {
          note.textContent = "Copied to clipboard";
          note.classList.add("visible");
          window.setTimeout(() => note.classList.remove("visible"), 2400);
        }
      } catch (error) {
        if (note) {
          note.textContent = "Could not copy link";
          note.classList.add("visible");
        }
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindShareButton, { once: true });
  } else {
    bindShareButton();
  }
})();
"""


app_ui = ui.page_fluid(
    ui.tags.style(APP_CSS),
    ui.tags.script(DEPENDENT_CONTROL_JS),
    ui.tags.script(SHARE_LINK_JS),
    ui.div(
        ui.tags.aside(
            ui.h1("barfbow", class_="brand"),
            ui.p("Live OKLCh palette laboratory", class_="tagline"),
            ui.p(
                "Hike up and down the color domes to generate color palettes. "
                "Check colorblind simulations to improve accessibility.",
                class_="intro-copy",
            ),
            ui.input_select(
                "preset",
                ui.span("Palette preset", class_="visually-hidden"),
                {"custom": "Choose a preset…"}
                | {key: str(preset["label"]) for key, preset in README_PRESETS.items()},
                selected="custom",
            ),
            ui.input_switch("divergent", "Divergent palette", False),
            ui.h2("Palette"),
            ui.input_slider("n", "Number of colors (N)", 2, 190, 100, step=1),
            ui.div(
            ui.input_slider(
                "h_orbits",
                control_label("Hue orbits", "How many full turns the palette makes around the color wheel."),
                -40, 40, 25, step=1,
            ),
                id="h-orbits-control",
                class_="parameter-control",
            ),
            ui.div(
                ui.input_slider(
                    "h1",
                    control_label("Initial hue (h1)", "Where the palette starts on the color wheel."),
                    0, 359, 90, step=1, post="°",
                ),
                id="h1-control",
                class_="parameter-control",
            ),
            ui.div(
                ui.input_slider(
                    "h2",
                    control_label("Second hue (h2)", "The color family used for the second half of a divergent palette."),
                    0, 359, 270, step=1, post="°",
                ),
                id="h2-control",
                class_="parameter-control",
            ),
            ui.h2("Luminance"),
            ui.div(
                ui.input_slider(
                    "l_cycles",
                    control_label(
                        "Luminance cycles",
                        "How often brightness rises from L1 to L2 and returns. "
                        "Use 0.5 for a sequential palette or 1 for a divergent palette.",
                    ),
                    0.1, 12, 3.5, step=0.1,
                ),
                id="l-cycles-control",
                class_="parameter-control",
            ),
            ui.input_slider(
                "l1",
                control_label("L1", "Brightness at the starting and ending edges of each luminance cycle."),
                0, 100, 30, step=1, post="%",
            ),
            ui.input_slider(
                "l2",
                control_label(
                    "L2",
                    "Center brightness of each luminance cycle "
                    "(or of the palette when divergent mode is on).",
                ),
                0, 100, 85, step=1, post="%",
            ),
            ui.div(
                ui.h2("Chroma"),
                ui.input_slider(
                    "c1",
                    control_label("Initial chroma (c1)", "How vivid the first chroma block is."),
                    0, 100, 85, step=1, post="%",
                ),
                ui.div(
                    ui.input_select(
                        "delta_mode",
                        control_label(
                            "Chroma progression",
                            "Choose how chroma changes at each new block defined by C-mode: "
                            "add deltaC or halve the previous block's chroma. In divergent mode, "
                            "the second half of the palette is the next chroma block.",
                        ),
                        {"add": "Add deltaC", "halve": "Halve each block"},
                        selected="add",
                    ),
                    ui.div(
                        ui.input_slider(
                            "delta_c",
                            control_label("deltaC", "How much vividness changes between chroma blocks."),
                            -28, 4, -28, step=1, post="%",
                        ),
                        id="delta-c-control",
                        class_="parameter-control",
                    ),
                    ui.div(
                        ui.input_select(
                            "c_mode",
                            control_label(
                                "C-mode",
                                "Choose when a new chroma block begins: L at each luminance cycle, "
                                "H at each hue orbit, or k after a fixed number of colors.",
                            ),
                            {"L": "L · luminance cycle", "H": "H · hue orbit", "k": "k · fixed color count"},
                            selected="L",
                        ),
                        id="c-mode-control",
                        class_="parameter-control",
                    ),
                    ui.div(
                        ui.input_slider("c_interval", "k colors per block", 1, 100, 12, step=1),
                        id="c-interval-control",
                        class_="parameter-control",
                    ),
                    id="chroma-progression-controls",
                    class_="parameter-control",
                ),
                id="chroma-controls",
                class_="control-section",
            ),
            ui.div(
                ui.download_button("download_csv", "Download CSV"),
                ui.download_button("download_png", "Download PNG"),
                class_="download-row",
            ),
            ui.div(
                ui.download_button("download_r", "Download R object"),
                ui.input_action_button("generate_link", "Generate link"),
                class_="download-row",
            ),
            ui.span("", id="copy-note", class_="copy-note", role="status", aria_live="polite"),
            ui.tags.img(
                src="barfbow_logo1.png",
                alt="Barfbow unicorn logo",
                class_="sidebar-logo",
            ),
            ui.tags.footer(
                ui.p(
                    "Designed by ",
                    ui.tags.a(
                        "Arnaud Martin",
                        href="https://www.dnacrobatics.com",
                        target="_blank",
                        rel="noopener noreferrer",
                    ),
                ),
                ui.p(
                    ui.tags.a(
                        "github.com/evolvwing",
                        href="https://github.com/evolvwing",
                        target="_blank",
                        rel="noopener noreferrer",
                    ),
                ),
                ui.p(f"Latest app version: {APP_VERSION_DATE}"),
                class_="app-footer",
            ),
            ui.output_ui("hue_slider_styles", inline=True, style="display:contents"),
            class_="controls",
        ),
        ui.tags.main(
            ui.div(ui.output_ui("status"), class_="status-strip"),
            ui.output_ui("preview"),
            class_="stage",
        ),
        class_="app-wrap",
    ),
)


NAME_PALETTE = barfbow.named_color_palette()


def server(input: Inputs, output: Outputs, session: Session):
    saved_delta_c = reactive.value(-28.0)
    shared_state_restored = reactive.value(False)
    previous_divergent = reactive.value(False)
    shared_divergent_transition_consumed = reactive.value(False)

    def update_control_values(values: dict[str, object]) -> None:
        """Apply a partial control mapping in dependency-safe order."""
        if "divergent" in values:
            ui.update_switch("divergent", value=bool(values["divergent"]), session=session)
        if "n" in values:
            ui.update_slider("n", value=n_to_slider_position(float(values["n"])), session=session)
        if "h_orbits" in values:
            ui.update_slider(
                "h_orbits",
                value=h_orbits_to_slider_position(float(values["h_orbits"])),
                session=session,
            )
        for name in ("h1", "h2", "l1", "l2", "c1"):
            if name in values:
                ui.update_slider(name, value=float(values[name]), session=session)
        if "delta_mode" in values:
            ui.update_select("delta_mode", selected=str(values["delta_mode"]), session=session)
        if "c_mode" in values:
            ui.update_select("c_mode", selected=str(values["c_mode"]), session=session)
        for name in ("c_interval", "delta_c", "l_cycles"):
            if name in values:
                ui.update_slider(name, value=float(values[name]), session=session)

    @reactive.effect
    def restore_shared_state():
        if shared_state_restored.get():
            return
        search = session.clientdata.url_search()
        shared_state_restored.set(True)
        values = parse_shared_parameters(search)
        if values:
            update_control_values(values)

    @reactive.effect
    async def sync_browser_dependent_controls():
        if input.dependent_controls_ready() is None:
            return
        await session.send_custom_message(
            "barfbow-dependent-controls",
            {
                "divergent": bool(input.divergent()),
                "luminance_cycles": float(input.l_cycles()),
                "color_count": slider_position_to_n(input.n()),
                "c_interval": int(input.c_interval()),
            },
        )

    @reactive.effect
    @reactive.event(input.preset)
    def apply_readme_preset():
        preset_name = str(input.preset())
        if preset_name == "custom":
            return
        preset = README_PRESETS[preset_name]
        update_control_values(preset)
        # A preset is an action, not persistent state. Returning to the prompt
        # lets the same preset be selected again after any manual adjustments.
        ui.update_select("preset", selected="custom", session=session)

    @reactive.effect
    def remember_delta_c():
        if input.delta_mode() == "add":
            saved_delta_c.set(float(input.delta_c()))

    @reactive.effect
    @reactive.event(input.n)
    def update_c_interval_limit():
        color_count = slider_position_to_n(input.n())
        with reactive.isolate():
            current = max(1, int(input.c_interval()))
        ui.update_slider(
            "c_interval",
            min=1,
            max=color_count,
            value=min(current, color_count),
            session=session,
        )

    @reactive.effect
    @reactive.event(input.divergent)
    def default_divergent_delta_c():
        current = bool(input.divergent())
        previous = bool(previous_divergent.get())
        previous_divergent.set(current)
        if not current or previous:
            return

        # Preserve a deltaC explicitly encoded in an initially divergent share
        # link. Later off→on switches use the divergent-mode default of zero.
        shared_values = parse_shared_parameters(session.clientdata.url_search())
        if (
            not shared_divergent_transition_consumed.get()
            and shared_values.get("divergent") is True
        ):
            shared_divergent_transition_consumed.set(True)
            if "delta_c" in shared_values:
                return

        if input.delta_mode() == "add":
            saved_delta_c.set(0.0)
            ui.update_slider("delta_c", value=0.0, session=session)

    @reactive.effect
    def update_delta_c_limits():
        if input.delta_mode() != "add":
            return
        c_mode = str(input.c_mode())
        if c_mode == "k":
            c_mode = str(max(1, int(input.c_interval())))
        lower, upper = delta_c_bounds(
            n=slider_position_to_n(input.n()),
            h_orbits=slider_position_to_h_orbits(input.h_orbits()),
            l_cycles=float(input.l_cycles()),
            c1=float(input.c1()),
            c_mode=c_mode,
            divergent=bool(input.divergent()),
        )
        value = max(lower, min(upper, float(saved_delta_c.get())))
        ui.update_slider("delta_c", min=lower, max=upper, value=value, session=session)

    @reactive.calc
    def palette_state() -> PaletteState:
        c_mode = str(input.c_mode())
        if c_mode == "k":
            c_mode = str(max(1, int(input.c_interval())))
        delta_c = None if input.delta_mode() == "halve" else float(input.delta_c())
        return make_palette_state(
            n=slider_position_to_n(input.n()), h_orbits=slider_position_to_h_orbits(input.h_orbits()), h1=float(input.h1()), h2=float(input.h2()),
            l1=float(input.l1()), l2=float(input.l2()), l_cycles=float(input.l_cycles()),
            c1=float(input.c1()), delta_c=delta_c, c_mode=c_mode, divergent=bool(input.divergent()),
        )

    @render.ui
    def status():
        state = palette_state()
        return ui.TagList(ui.tags.b(state.mode_label), ui.span(f"{len(state.rows)} display-ready sRGB colors"))

    @render.ui
    def hue_slider_styles():
        return ui.tags.style(hue_slider_css(float(input.h1()), float(input.h2())))

    @render.ui
    def preview():
        state = palette_state()
        stride = barfbow.swatch_label_stride(len(state.rows))
        names = {
            index: name
            for index in range(0, len(state.rows), stride)
            if (name := barfbow.closest_color_name(state.rows[index][0], NAME_PALETTE))
        }
        return ui.HTML(preview_html(state, names))

    @render.download_button(filename=lambda: f"{palette_state().palette_name}.csv", media_type="text/csv")
    def download_csv():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(("Hex", "L%", "C%", "h°"))
        writer.writerows(palette_state().rows)
        yield buffer.getvalue()

    @render.download_button(filename=lambda: f"{palette_state().palette_name}.png", media_type="image/png")
    def download_png():
        state = palette_state()
        with tempfile.TemporaryDirectory(prefix="barfbow-shiny-") as temp_dir:
            output_path = Path(temp_dir) / "barfbow_palette.png"
            barfbow.show_swatch_grid(
                state.rows, state.chroma_ranges, state.title, state.luminance_cycles,
                reverse_dot_fade=state.reverse_dot_fade, save_png=True,
                png_path=str(output_path), show=False, palette_name=state.palette_name,
            )
            yield output_path.read_bytes()

    @render.download_button(filename=lambda: f"{palette_state().palette_name}.R", media_type="text/plain")
    def download_r():
        state = palette_state()
        yield r_palette_script(state.rows, state.palette_name)


app = App(app_ui, server, static_assets=Path(__file__).with_name("docs"))
