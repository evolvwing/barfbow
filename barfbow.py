#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
barfbow — OKLCh palette generator with BVM simulations.

Update vs v2-7
--------------
• Palette generation now happens directly in OKLCh color space.
• Chroma is controlled by --c1 and --deltaC. The chroma value advances to the
  next block after each full lightness cycle.
"""

from typing import List, Tuple
import argparse
import csv
import sys
from math import cos, radians, sin
from pathlib import Path


COLOR_NAMES_PATH = Path(__file__).with_name("color_names_meodai.csv")
PNG_BACKGROUND = "#F2F2F2"
DEFAULT_COMMAND = (
    "python3 barfbow.py --N 100 --H-orbits 2.5 --h1 90 "
    "--L1 30 --L2 85 --L-cycles 3.5 --c1 85 --deltaC -30 --C-mode L"
)

# -----------------------------
# Color conversions
# -----------------------------
def oklch_to_srgb_hex(lightness: float, chroma: float, hue_degrees: float) -> str:
    L = max(0.0, min(100.0, lightness)) / 100.0
    chroma = chroma_to_oklch_chroma(chroma)
    chroma = fit_oklch_chroma_to_srgb(L, chroma, hue_degrees)
    r_linear, g_linear, b_linear = oklch_to_linear_srgb(L, chroma, hue_degrees)
    r, g, b = [int(round(linear_to_srgb_channel(channel) * 255)) for channel in (r_linear, g_linear, b_linear)]
    return "#{:02X}{:02X}{:02X}".format(r, g, b)

def oklch_to_linear_srgb(L: float, chroma: float, hue_degrees: float) -> Tuple[float, float, float]:
    a = chroma * cos(radians(hue_degrees))
    b = chroma * sin(radians(hue_degrees))

    l_prime = L + 0.3963377774 * a + 0.2158037573 * b
    m_prime = L - 0.1055613458 * a - 0.0638541728 * b
    s_prime = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_prime ** 3
    m = m_prime ** 3
    s = s_prime ** 3

    r_linear = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g_linear = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_linear = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return r_linear, g_linear, b_linear

def fit_oklch_chroma_to_srgb(L: float, chroma: float, hue_degrees: float) -> float:
    if is_linear_srgb_in_gamut(oklch_to_linear_srgb(L, chroma, hue_degrees)):
        return chroma

    low = 0.0
    high = chroma
    for _ in range(24):
        mid = (low + high) / 2.0
        if is_linear_srgb_in_gamut(oklch_to_linear_srgb(L, mid, hue_degrees)):
            low = mid
        else:
            high = mid
    return low

def is_linear_srgb_in_gamut(rgb: Tuple[float, float, float]) -> bool:
    return all(-0.000001 <= channel <= 1.000001 for channel in rgb)

def chroma_to_oklch_chroma(chroma: float) -> float:
    return max(0.0, min(100.0, chroma)) * 0.0032

# -----------------------------
# CVD simulation matrices
# -----------------------------
M_PROT = ((0.152286, 1.052583, -0.204868),
          (0.114503, 0.786281, 0.099216),
          (-0.003882, -0.048116, 1.051998))
M_DEUT = ((0.367322, 0.860646, -0.227968),
          (0.280085, 0.672501, 0.047413),
          (-0.011820, 0.042940, 0.968881))
M_TRIT = ((1.255528, -0.076749, -0.178779),
          (-0.078411, 0.930809, 0.147602),
          (0.004733, 0.691367, 0.303900))

def hex_to_srgb01(hx: str) -> Tuple[float, float, float]:
    return (int(hx[1:3], 16) / 255.0,
            int(hx[3:5], 16) / 255.0,
            int(hx[5:7], 16) / 255.0)

def srgb_to_linear_channel(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

def linear_to_srgb_channel(channel: float) -> float:
    channel = max(0.0, min(1.0, channel))
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * (channel ** (1 / 2.4)) - 0.055

def simulate_cvd_hex(hx: str, M: Tuple[Tuple[float, float, float], ...]) -> str:
    rgb = hex_to_srgb01(hx)
    lin = tuple(srgb_to_linear_channel(channel) for channel in rgb)
    out_lin = tuple(sum(row[index] * lin[index] for index in range(3)) for row in M)
    out = tuple(linear_to_srgb_channel(channel) for channel in out_lin)
    r, g, b = (int(round(out[0] * 255)),
               int(round(out[1] * 255)),
               int(round(out[2] * 255)))
    return "#{:02X}{:02X}{:02X}".format(r, g, b)

def simulate_monochrome_hex(hx: str) -> str:
    rgb = hex_to_srgb01(hx)
    linear = tuple(srgb_to_linear_channel(channel) for channel in rgb)
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    gray = int(round(linear_to_srgb_channel(luminance) * 255))
    return "#{:02X}{:02X}{:02X}".format(gray, gray, gray)

def linear_srgb_to_oklab(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    r, g, b = rgb
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_prime = l ** (1.0 / 3.0)
    m_prime = m ** (1.0 / 3.0)
    s_prime = s ** (1.0 / 3.0)

    return (
        0.2104542553 * l_prime + 0.7936177850 * m_prime - 0.0040720468 * s_prime,
        1.9779984951 * l_prime - 2.4285922050 * m_prime + 0.4505937099 * s_prime,
        0.0259040371 * l_prime + 0.7827717662 * m_prime - 0.8086757660 * s_prime,
    )

def hex_to_oklab(hx: str) -> Tuple[float, float, float]:
    return linear_srgb_to_oklab(tuple(srgb_to_linear_channel(channel) for channel in hex_to_srgb01(hx)))

def named_color_palette(color_names_path: Path = COLOR_NAMES_PATH) -> List[Tuple[str, Tuple[float, float, float]]]:
    if not color_names_path.exists():
        return []

    palette = []
    with color_names_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or "").strip()
            hx = (row.get("hex") or "").strip()
            if not name or len(hx) != 7 or not hx.startswith("#"):
                continue
            try:
                palette.append((name, hex_to_oklab(hx)))
            except ValueError:
                continue
    return palette

def closest_color_name(hex_color: str, palette: List[Tuple[str, Tuple[float, float, float]]] | None = None) -> str | None:
    if palette is None:
        palette = named_color_palette()
    if not palette:
        return None

    target = hex_to_oklab(hex_color)
    best_name = None
    best_distance = float("inf")
    for name, candidate in palette:
            distance = sum((target[index] - candidate[index]) ** 2 for index in range(3))
            if distance < best_distance:
                best_distance = distance
                best_name = name
    return best_name

def swatch_label_stride(color_count: int) -> int:
    if color_count <= 45:
        return 1
    return max(2, (color_count + 44) // 45)

def swatch_number_step(color_count: int) -> int:
    if color_count <= 30:
        return 1
    if color_count <= 120:
        return 5
    if color_count <= 1000:
        return 10
    return 100

def swatch_number_labels(color_count: int) -> List[int]:
    step = swatch_number_step(color_count)
    return [index for index in range(color_count) if (index + 1) % step == 0]

def swatch_color_names(hex_list: List[str]) -> dict[int, str]:
    stride = swatch_label_stride(len(hex_list))
    label_indices = range(0, len(hex_list), stride)
    palette = named_color_palette()
    return {
        index: name
        for index in label_indices
        if (name := closest_color_name(hex_list[index], palette))
    }

# -----------------------------
# Palette construction
# -----------------------------
def build_palette(N: int, H_orbits: float, h1: float, L1: float, L2: float, L_cycles: float,
                  C_values: Tuple[float, ...], C_mode: str):
    H = max(1, int(round((N - 1) / (2.0 * L_cycles))))
    half_period = H
    full_period = 2 * H
    h_step = H_orbits * (360.0 / N)
    def h_i(i: int) -> float:
        return (h1 + h_step * i) % 360.0
    def L_i(i: int) -> float:
        t = (i % full_period) / float(full_period)
        tri = 1.0 - 2.0 * abs(t - 0.5)
        return L1 + tri * (L2 - L1)
    def C_i(i: int) -> float:
        return chroma_at_index(i, N, h_step, full_period, C_values, C_mode)
    rows = []
    for i in range(N):
        L = round(L_i(i), 2)
        C = round(C_i(i), 2)
        h = round(h_i(i), 2)
        hex_code = oklch_to_srgb_hex(L, C, h)
        rows.append((hex_code, L, C, h))
    chroma_ranges = chroma_plan(N, h_step, full_period, C_values, C_mode)
    return H, half_period, chroma_ranges, rows

def chroma_at_index(index: int, N: int, h_step: float, full_period: int, C_values: Tuple[float, ...], C_mode: str) -> float:
    if C_mode == "H":
        block_index = min(int(abs(h_step * index) // 360.0), len(C_values) - 1)
    elif C_mode == "L":
        block_index = min(index // full_period, len(C_values) - 1)
    else:
        block_index = min(index // int(C_mode), len(C_values) - 1)
    return C_values[block_index]

def chroma_plan(N: int, h_step: float, full_period: int, C_values: Tuple[float, ...], C_mode: str) -> List[Tuple[str, float, int, int]]:
    ranges = []
    current_name = ""
    current_chroma = 0.0
    start = 0
    previous_block_index = -1
    for index in range(N):
        if C_mode == "H":
            block_index = min(int(abs(h_step * index) // 360.0), len(C_values) - 1)
        elif C_mode == "L":
            block_index = min(index // full_period, len(C_values) - 1)
        else:
            block_index = min(index // int(C_mode), len(C_values) - 1)
        if block_index != previous_block_index:
            if index > 0:
                ranges.append((current_name, current_chroma, start, index - 1))
            current_name = f"c{block_index + 1}"
            current_chroma = C_values[block_index]
            start = index
            previous_block_index = block_index
    if N > 0:
        ranges.append((current_name, current_chroma, start, N - 1))
    return ranges

# -----------------------------
# Visualization
# -----------------------------
WHEEL_MIN_LIGHTNESS = 10.0

def oklch_wheel_xy(lightness: float, hue: float, radius: float) -> Tuple[float, float]:
    clamped_lightness = max(WHEEL_MIN_LIGHTNESS, min(100.0, lightness))
    radial_position = (100.0 - clamped_lightness) / (100.0 - WHEEL_MIN_LIGHTNESS) * radius
    return radial_position * sin(radians(hue)), radial_position * cos(radians(hue))

WHEEL_X_MAX = 4.0

def wheel_x(position: float) -> float:
    return position * WHEEL_X_MAX

def wheel_layout(count: int) -> List[Tuple[float, float]]:
    if count == 1:
        return [(wheel_x(0.5), 0.5)]
    if count == 2:
        return [(wheel_x(0.25), 0.5), (wheel_x(0.75), 0.5)]
    if count == 3:
        return [(wheel_x(0.16), 0.5), (wheel_x(0.5), 0.5), (wheel_x(0.84), 0.5)]
    if count == 5:
        return [(wheel_x(0.09), 0.5), (wheel_x(0.295), 0.5), (wheel_x(0.5), 0.5), (wheel_x(0.705), 0.5), (wheel_x(0.91), 0.5)]
    return [(wheel_x(0.12), 0.5), (wheel_x(0.37), 0.5), (wheel_x(0.63), 0.5), (wheel_x(0.88), 0.5)]

def displayed_chroma_ranges(chroma_ranges: List[Tuple[str, float, int, int]]) -> List[Tuple[str, float, int, int]]:
    if len(chroma_ranges) <= 4:
        return chroma_ranges
    return chroma_ranges[:4]

def draw_oklch_wheel(ax, plt, rows: List[Tuple[str, float, float, float]], chroma_name: str,
                     chroma: float, start: int, end: int, center: Tuple[float, float],
                     radius: float, label_line_1: str | None = None,
                     label_line_2: str | None = None) -> None:
    from matplotlib.patches import Circle, Wedge

    radial_steps = 20
    hue_steps = 50
    cx, cy = center
    for radial_index in range(radial_steps):
        inner = radius * radial_index / radial_steps
        outer = radius * (radial_index + 1) / radial_steps
        lightness = 100.0 - (radial_index + 0.5) * (100.0 - WHEEL_MIN_LIGHTNESS) / radial_steps
        for hue_index in range(hue_steps):
            h_start = hue_index * 360.0 / hue_steps
            h_end = (hue_index + 1) * 360.0 / hue_steps
            hue = (h_start + h_end) / 2.0
            color = oklch_to_srgb_hex(lightness, chroma, hue)
            wedge = Wedge(
                (cx, cy), outer, 90.0 - h_end, 90.0 - h_start,
                width=outer - inner, facecolor=color, edgecolor=color, linewidth=0
            )
            ax.add_patch(wedge)

    path_points = []
    for _, lightness, _, hue in rows[start:end + 1]:
        x_offset, y_offset = oklch_wheel_xy(lightness, hue, radius)
        path_points.append((cx + x_offset, cy + y_offset))
    if path_points:
        x_values, y_values = zip(*path_points)
        if len(path_points) == 1:
            dot_colors = ["#FFFFFF"]
        else:
            dot_colors = [
                "#{0:02X}{0:02X}{0:02X}".format(round(255 - 178.5 * index / (len(path_points) - 1)))
                for index in range(len(path_points))
            ]
        ax.scatter(x_values, y_values, s=12, facecolors="none", edgecolors=dot_colors,
                   linewidths=0.8, zorder=4)

    ax.add_patch(Circle((cx, cy), radius, facecolor="none", edgecolor="#202020", linewidth=0.8))
    label_1 = label_line_1 if label_line_1 is not None else f"{chroma_name} = {format_number(chroma)}%"
    label_2 = label_line_2 if label_line_2 is not None else f"colors {start + 1}–{end + 1}"
    ax.text(cx, cy + radius + 0.052, label_1,
            ha="center", va="bottom", fontsize=10, weight="bold")
    ax.text(cx, cy + radius + 0.015, label_2,
            ha="center", va="bottom", fontsize=10)

def draw_oklch_walk_maps(ax, plt, rows: List[Tuple[str, float, float, float]],
                         chroma_ranges: List[Tuple[str, float, int, int]],
                         L_cycles: float) -> None:
    ax.set_xlim(0, WHEEL_X_MAX); ax.set_ylim(-0.04, 1.08); ax.set_aspect("equal"); ax.axis("off")
    visible_ranges = displayed_chroma_ranges(chroma_ranges)
    hidden_count = max(0, len(chroma_ranges) - 4)
    positions = wheel_layout(5)
    radius = 0.34
    full_walk_chroma = chroma_ranges[0][1] if chroma_ranges else 0.0
    draw_oklch_wheel(
        ax, plt, rows, "full walk", full_walk_chroma, 0, len(rows) - 1,
        center=positions[0], radius=radius,
        label_line_1=f"overview at {format_number(full_walk_chroma)}% chroma",
        label_line_2=f"{len(rows)} colors with {format_number(L_cycles)} luminance cycles",
    )
    for visible_range, center in zip(visible_ranges, positions[1:]):
        draw_oklch_wheel(ax, plt, rows, *visible_range, center=center, radius=radius)
    if hidden_count:
        cx, cy = positions[4]
        ax.text(cx, cy - radius - 0.08, f"{hidden_count} chroma layers not shown...", ha="center", va="top",
                fontsize=11, weight="bold", color="#333333")

def show_swatch_grid(rows: List[Tuple[str, float, float, float]], chroma_ranges: List[Tuple[str, float, int, int]],
                     title: str, L_cycles: float, save_png: bool = False,
                     png_path: str = "palette_grid.png", show: bool = True, block: bool = False) -> None:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as error:
        raise SystemExit("Matplotlib is required for previews and PNG export. Install it with: pip install -r requirements.txt") from error

    plt.rcParams["font.family"] = "Microsoft Sans Serif"

    hex_list = [hx for (hx, _, _, _) in rows]
    prot = [simulate_cvd_hex(hx, M_PROT) for hx in hex_list]
    deut = [simulate_cvd_hex(hx, M_DEUT) for hx in hex_list]
    trit = [simulate_cvd_hex(hx, M_TRIT) for hx in hex_list]
    mono = [simulate_monochrome_hex(hx) for hx in hex_list]
    swatch_rows = [("Original", hex_list), ("Protanopia", prot), ("Deuteranopia", deut), ("Tritanopia", trit), ("Monochrome", mono)]
    fig = plt.figure(figsize=(18, 7.65), facecolor=PNG_BACKGROUND)
    ax = fig.add_axes([0.06, 0.51, 0.9, 0.32])
    ax.set_facecolor(PNG_BACKGROUND)
    ax.set_xlim(0, len(hex_list)); ax.set_ylim(-0.45, len(swatch_rows) + 1.25); ax.axis("off")
    for r, (label, colors_row) in enumerate(swatch_rows[::-1]):
        y = r
        ax.text(-0.4, y + 0.5, label, ha="right", va="center", fontsize=10, weight="bold")
        for i, hx in enumerate(colors_row):
            ax.add_patch(plt.Rectangle((i, y), 1, 1, color=hx, linewidth=0))
    for index, color_name in swatch_color_names(hex_list).items():
        ax.text(index + 0.5, len(swatch_rows) + 0.08, color_name, ha="left", va="bottom",
                rotation=45, rotation_mode="anchor", fontsize=7, fontfamily="DejaVu Sans Mono")
    for index in swatch_number_labels(len(hex_list)):
        ax.text(index + 0.5, -0.25, str(index + 1), ha="center", va="center",
                fontsize=7, fontfamily="DejaVu Sans Mono")
    wheel_ax = fig.add_axes([0.02, 0.015, 0.96, 0.49])
    wheel_ax.set_facecolor(PNG_BACKGROUND)
    wheel_ax.set_zorder(2)
    draw_oklch_walk_maps(wheel_ax, plt, rows, chroma_ranges, L_cycles)
    title_lines = title.splitlines()
    title_y = [0.975, 0.948, 0.921]
    fig.text(0.18, title_y[0], "barfbow", ha="center", va="top", fontsize=28, weight="bold", fontfamily="Oswald")
    fig.text(0.18, title_y[2], "GitHub: evolvwing/barfbow", ha="center", va="top", fontsize=12)
    for line, y in zip(title_lines, title_y):
        fig.text(0.68, y, line, ha="center", va="top", fontsize=12)
    if save_png:
        plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    if show:
        plt.show(block=block)
    else:
        plt.close()

def format_table(rows: List[Tuple[str, float, float, float]]) -> str:
    headers = ("Hex", "L%", "C%", "h°")
    records = [dict(zip(headers, row)) for row in rows]
    widths = {header: len(header) for header in headers}
    for record in records:
        for header in headers:
            widths[header] = max(widths[header], len(str(record[header])))

    lines = [" ".join(header.rjust(widths[header]) for header in headers)]
    for record in records:
        lines.append(" ".join(str(record[header]).rjust(widths[header]) for header in headers))
    return "\n".join(lines)

def write_csv(csv_path: str, rows: List[Tuple[str, float, float, float]]) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("Hex", "L%", "C%", "h°"))
        writer.writerows(rows)

def chroma_label(C_values: Tuple[float, ...]) -> str:
    return ", ".join(f"c{index}={value:g}" for index, value in enumerate(C_values, start=1))

def format_number(value: float) -> str:
    return f"{value:g}"

def hue_orbit_phrase(H_orbits: float) -> str:
    if H_orbits < 0:
        return f"{format_number(abs(H_orbits))} counter-clockwise orbits"
    if H_orbits > 0:
        return f"{format_number(H_orbits)} clockwise orbits"
    return "0 orbits"

def C_mode_interval_label(C_mode: str) -> str:
    if C_mode == "H":
        return "full hue orbit"
    if C_mode == "L":
        return "full luminance cycle"
    return f"{C_mode} colors"

def C_mode_interval_size(N: int, H_orbits: float, L_cycles: float, C_mode: str) -> str:
    if C_mode == "H":
        if H_orbits == 0:
            return "∞"
        return format_number(N / abs(H_orbits))
    if C_mode != "L":
        return C_mode

    H = max(1, int(round((N - 1) / (2.0 * L_cycles))))
    return format_number(2 * H)

def chroma_title_phrase(N: int, H_orbits: float, L_cycles: float, c1: float, deltaC: float | None, C_mode: str) -> str:
    interval = C_mode_interval_label(C_mode)
    interval_size = C_mode_interval_size(N, H_orbits, L_cycles, C_mode)
    if deltaC is None:
        return f"Initial Chroma : {format_number(c1)}% with halving every {interval} (every {interval_size} colors)"

    direction = "increments" if deltaC > 0 else "decrements"
    amount = abs(deltaC)
    return f"Initial Chroma : {format_number(c1)}% with {direction} of {format_number(amount)}% every {interval} (every {interval_size} colors)"

def palette_title(N: int, H_orbits: float, h1: float, L1: float, L2: float, L_cycles: float,
                  c1: float, deltaC: float | None, C_mode: str) -> str:
    return "\n".join((
        f"N = {N} colors with initial Hue (h1) = {format_number(h1)}° and {hue_orbit_phrase(H_orbits)} around the 360° Hue wheel",
        f"Luminance : {format_number(L1)}% to {format_number(L2)}% with {format_number(L_cycles)} cycles",
        chroma_title_phrase(N, H_orbits, L_cycles, c1, deltaC, C_mode),
    ))

def normalized_C_mode(value: str) -> str:
    normalized = value.strip()
    aliases = {
        "L": "L",
        "l": "L",
        "L-cycle": "L",
        "l-cycle": "L",
        "H": "H",
        "h": "H",
        "H-orbit": "H",
        "h-orbit": "H",
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        k = int(abs(float(normalized)))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected C-mode L, H, or a positive integer k.") from error
    return str(max(1, k))

def deltaC_value(value: str) -> float | None:
    if value.lower() in ("none", "halve", "halving"):
        return None
    try:
        return float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected a number, or 'none' to halve chroma each block.") from error

# -----------------------------
# Main
# -----------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an OKLCh palette, CSV table, and PNG preview with color-vision simulations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Chroma blocks:\n"
            "  With --deltaC, blocks use c(n) = c1 + (n - 1) * deltaC, clamped to 0..100.\n"
            "  Use --deltaC none to halve each new block instead: c1, c1/2, c1/4...\n\n"
            "Chroma scale:\n"
            "  barfbow C% is a 0..100 design scale: OKLCh C = C% * 0.0032.\n"
            "  C% 100 requests OKLCh C 0.320, or 80% of an OKLCh C 0.4 reference.\n"
            "  Out-of-sRGB colors are rendered with the highest fitting chroma for their L/h.\n\n"
            "C-mode:\n"
            "  L  L-cycle  change chroma after each full luminance cycle (default)\n"
            "  H  H-orbit  change chroma after each full hue orbit\n"
            "  k           change chroma every k colors; k is floored and made positive\n\n"
            "Examples:\n"
            "  python3 barfbow.py --N 200 --H-orbits 2 --c1 100 --save-png\n"
            "  python3 barfbow.py --N 80 --L-cycles 1.5 --C-mode H --deltaC -20\n"
            "  python3 barfbow.py --N 80 --C-mode 12 --deltaC -20"
        ),
    )
    parser.add_argument("--N", type=int, default=100,
                        help="Number of colors to generate. Values below 2 are raised to 2.")
    parser.add_argument("--H-orbits", dest="H_orbits", type=float, default=2.5,
                        help="Hue rotations across the palette; negative values reverse direction.")
    parser.add_argument("--h1", type=float, default=90.0,
                        help="Initial OKLCh hue angle in degrees. Wrapped into 0..360.")
    parser.add_argument("--L1", type=float, default=30.0,
                        help="First OKLCh luminance endpoint, as a percentage.")
    parser.add_argument("--L2", type=float, default=85.0,
                        help="Second OKLCh luminance endpoint, as a percentage.")
    parser.add_argument("--L-cycles", dest="L_cycles", type=float, default=3.5,
                        help="Number of luminance cycles from L1 to L2 and back across the palette.")
    parser.add_argument("--c1", type=float, default=85.0,
                        help="Initial OKLCh chroma percentage. Clamped to 0..100.")
    parser.add_argument("--deltaC", type=deltaC_value, default=-30.0,
                        help="Additive chroma step between blocks; use 'none' for halving instead.")
    parser.add_argument("--C-mode", type=normalized_C_mode, default="L",
                        metavar="{L,H,k}",
                        help="Chroma progression mode. Use L, H, or a positive integer k.")
    parser.add_argument("--save-csv", action="store_true",
                        help="Write the generated Hex/L/C/h table to CSV.")
    parser.add_argument("--csv-path", type=str, default="palette_OKLCh.csv",
                        help="CSV output path used with --save-csv.")
    parser.add_argument("--save-png", action="store_true",
                        help="Save the swatch grid, simulations, monochrome row, and OKLCh wheels as PNG.")
    parser.add_argument("--png-path", type=str, default="palette_OKLCh_grid.png",
                        help="PNG output path used with --save-png.")
    parser.add_argument("--no-block", dest="block", action="store_false",
                        help="Do not block while the Matplotlib preview window is open.")
    parser.set_defaults(block=True)
    return parser

def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        print("No arguments supplied. Equivalent full command:")
        print(DEFAULT_COMMAND)
        print()
    args = parser.parse_args()

    N = max(2, int(args.N))
    H_orbits = float(args.H_orbits)
    h1 = float(args.h1) % 360.0
    L1 = max(0.0, min(100.0, float(args.L1)))
    L2 = max(0.0, min(100.0, float(args.L2)))
    L_cycles = max(0.0001, float(args.L_cycles))
    H = max(1, int(round((N - 1) / (2.0 * L_cycles))))
    full_period = 2 * H
    if args.C_mode == "H":
        h_step_for_blocks = H_orbits * (360.0 / N)
        chroma_blocks = max(1, int(abs(h_step_for_blocks) * (N - 1) // 360.0) + 1)
    elif args.C_mode == "L":
        chroma_blocks = max(1, ((N - 1) // full_period) + 1)
    else:
        chroma_blocks = max(1, ((N - 1) // int(args.C_mode)) + 1)
    c1 = max(0.0, min(100.0, float(args.c1)))
    if args.deltaC is None:
        C_values = tuple(max(0.0, min(100.0, c1 / (2 ** index))) for index in range(chroma_blocks))
    else:
        deltaC = float(args.deltaC)
        C_values = tuple(max(0.0, min(100.0, c1 + index * deltaC)) for index in range(chroma_blocks))

    H, half_period, chroma_ranges, rows = build_palette(
        N=N, H_orbits=H_orbits, h1=h1, L1=L1, L2=L2, L_cycles=L_cycles,
        C_values=C_values, C_mode=args.C_mode
    )

    print(f"\nH = {H}  (half period = H = {half_period} steps)")
    joined = ", ".join(f"{name}={value:g} [{start}..{end}]" for name, value, start, end in chroma_ranges)
    if args.C_mode == "H":
        print(f"C-mode H (H-orbit): chroma blocks shift after each full hue orbit: {joined}")
    elif args.C_mode == "L":
        print(f"C-mode L (L-cycle): chroma blocks shift after each full lightness cycle: {joined}")
    else:
        print(f"C-mode {args.C_mode}: chroma blocks shift every {args.C_mode} colors: {joined}")
    print()
    print(format_table(rows))

    if args.save_csv:
        write_csv(args.csv_path, rows)
        print(f"\nSaved CSV to: {args.csv_path}")

    title = palette_title(N, H_orbits, h1, L1, L2, L_cycles, c1, args.deltaC, args.C_mode)
    show_swatch_grid(rows, chroma_ranges, title=title, L_cycles=L_cycles,
                     save_png=args.save_png, png_path=args.png_path,
                     show=True, block=args.block)

if __name__ == "__main__":
    main()
