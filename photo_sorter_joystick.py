import os
import json
import http.client
import queue
import re
import shutil
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pygame
from PIL import Image, UnidentifiedImageError

try:
    import rawpy
    import numpy as np
except Exception:
    rawpy = None
    np = None

# ---------------------------
# Konfigurasi awal
# ---------------------------
APP_VERSION = os.environ.get("PHOTOSORTER_VERSION", "0.3.0-beta").removeprefix("v")
APP_VERSION_LABEL = APP_VERSION
UPDATE_REPOSITORY = "PaleSalome/PhotoSorter"
GITHUB_RELEASES_API = (
    f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases?per_page=30"
)
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
RAW_EXTENSIONS = {
    ".raw",
    ".dng",
    ".nef",
    ".cr2",
    ".cr3",
    ".arw",
    ".raf",
    ".orf",
    ".rw2",
    ".pef",
    ".sr2",
    ".mrw",
    ".3fr",
    ".kdc",
    ".mos",
}

# Default mapping tombol untuk controller Xbox-like:
# A = diterima, B = ditolak, X = lewati
ACCEPT_BUTTON = 0
REJECT_BUTTON = 1
SKIP_BUTTON = 2
RESET_VIEW_BUTTON = 3
ZOOM_OUT_BUTTON = 4
ZOOM_IN_BUTTON = 5
DEFAULT_JOYSTICK_MAPPING = {
    "accept": ACCEPT_BUTTON,
    "reject": REJECT_BUTTON,
    "skip": SKIP_BUTTON,
    "reset": RESET_VIEW_BUTTON,
    "zoom_out": ZOOM_OUT_BUTTON,
    "zoom_in": ZOOM_IN_BUTTON,
}
JOYSTICK_ACTIONS = (
    ("accept", "Terima foto", True),
    ("reject", "Tolak foto", True),
    ("skip", "Lewati foto", True),
    ("zoom_out", "Zoom out", False),
    ("zoom_in", "Zoom in", False),
    ("reset", "Reset tampilan", False),
    ("pan_left", "Geser ke kiri", False),
    ("pan_right", "Geser ke kanan", False),
    ("pan_up", "Geser ke atas", False),
    ("pan_down", "Geser ke bawah", False),
)
KEYBOARD_ACTIONS = (
    ("accept", "Terima foto", True),
    ("reject", "Tolak foto", True),
    ("skip", "Lewati foto", True),
    ("zoom_out", "Zoom out", False),
    ("zoom_in", "Zoom in", False),
    ("reset", "Reset tampilan", False),
    ("pan_left", "Geser ke kiri", False),
    ("pan_right", "Geser ke kanan", False),
    ("pan_up", "Geser ke atas", False),
    ("pan_down", "Geser ke bawah", False),
)
DEFAULT_KEYBOARD_MAPPING = {
    "accept": pygame.K_a,
    "reject": pygame.K_d,
    "skip": pygame.K_s,
    "zoom_out": pygame.K_MINUS,
    "zoom_in": pygame.K_EQUALS,
    "reset": pygame.K_r,
    "pan_left": pygame.K_LEFT,
    "pan_right": pygame.K_RIGHT,
    "pan_up": pygame.K_UP,
    "pan_down": pygame.K_DOWN,
}
ZOOM_MIN = 1.0
ZOOM_MAX = 8.0
ZOOM_STEP = 1.25
PAN_SPEED = 700
VIEWPORT = pygame.Rect(40, 100, 920, 660)
GALLERY_RECT = pygame.Rect(980, 100, 380, 660)
LAYOUT_DIVIDER_RECT = pygame.Rect(960, 100, 20, 660)
MENU_BUTTON_RECT = pygame.Rect(1110, 24, 230, 48)
GALLERY_TOGGLE_RECT = pygame.Rect(870, 24, 220, 48)
PHOTO_TRANSITION_MS = 240
GALLERY_ROW_HEIGHT = 60
THUMBNAIL_SIZE = (68, 42)
THUMBNAIL_CACHE_LIMIT = 128
THEME_PALETTES = {
    "dark": {
        "background": (38, 40, 45),
        "panel": (49, 51, 56),
        "text": (245, 237, 220),
        "muted": (196, 179, 155),
        "border": (184, 135, 95),
        "accent": (222, 145, 94),
        "accepted": (137, 183, 132),
        "rejected": (211, 125, 111),
        "error": (237, 141, 119),
        "paper_line": (52, 55, 60),
        "shadow": (25, 27, 31),
    },
    "light": {
        "background": (246, 238, 219),
        "panel": (255, 249, 235),
        "text": (69, 54, 43),
        "muted": (133, 108, 86),
        "border": (141, 92, 65),
        "accent": (202, 112, 79),
        "accepted": (74, 128, 88),
        "rejected": (177, 80, 68),
        "error": (174, 63, 63),
        "paper_line": (233, 220, 194),
        "shadow": (220, 204, 175),
    },
}

_VERSION_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?$"
)


def _version_key(version: str):
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        return None
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return major, minor, patch, 1, ()

    identifiers = []
    for identifier in prerelease.split("."):
        if not identifier:
            return None
        if identifier.isdigit():
            if len(identifier) > 1 and identifier.startswith("0"):
                return None
            identifiers.append((0, int(identifier)))
        else:
            identifiers.append((1, identifier.lower()))
    return major, minor, patch, 0, tuple(identifiers)


def _check_for_update():
    current_version = _version_key(APP_VERSION)
    if current_version is None:
        raise ValueError(f"Versi aplikasi tidak valid: {APP_VERSION}")

    request = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PhotoSorter-UpdateChecker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read(1_048_577)
    if len(payload) > 1_048_576:
        raise ValueError("Respons informasi update terlalu besar.")

    releases = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError("Format informasi rilis dari GitHub tidak valid.")

    candidates = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        if release.get("draft") is True:
            continue
        tag_name = release.get("tag_name")
        release_url = release.get("html_url")
        version_key = _version_key(tag_name) if isinstance(tag_name, str) else None
        parsed_url = (
            urllib.parse.urlparse(release_url)
            if isinstance(release_url, str)
            else None
        )
        if (
            version_key is None
            or parsed_url is None
            or parsed_url.scheme != "https"
            or parsed_url.netloc.lower() != "github.com"
            or not parsed_url.path.startswith(
                f"/{UPDATE_REPOSITORY}/releases/"
            )
        ):
            continue
        candidates.append((version_key, tag_name, release_url))

    if not candidates:
        raise ValueError("Belum ada rilis Photo Sorter yang valid di GitHub.")
    latest = max(candidates, key=lambda candidate: candidate[0])
    if latest[0] <= current_version:
        return None
    return {"version": latest[1], "url": latest[2]}


def _joystick_config_path():
    app_data = Path(os.environ.get("APPDATA", Path.home()))
    return app_data / "PhotoSorter" / "joystick_mappings.json"


def _load_joystick_mappings():
    config_path = _joystick_config_path()
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as config_file:
        mappings = json.load(config_file)
    if not isinstance(mappings, dict):
        raise ValueError(f"Format konfigurasi joystick tidak valid: {config_path}")
    return mappings


def _save_joystick_mapping(guid: str, mapping: dict):
    mappings = _load_joystick_mappings()
    mappings[guid] = mapping
    config_path = _joystick_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as config_file:
        json.dump(mappings, config_file, indent=2)


def _load_theme():
    theme = _load_joystick_mappings().get("_theme", "dark")
    if theme not in THEME_PALETTES:
        raise ValueError("Pengaturan tema tidak valid.")
    return theme


def _save_theme(theme: str):
    if theme not in THEME_PALETTES:
        raise ValueError(f"Tema tidak dikenal: {theme}")
    mappings = _load_joystick_mappings()
    mappings["_theme"] = theme
    config_path = _joystick_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as config_file:
        json.dump(mappings, config_file, indent=2)


def _load_layout_settings():
    settings = _load_joystick_mappings().get("_layout", {})
    if not isinstance(settings, dict):
        raise ValueError("Pengaturan tata letak tidak valid.")
    ratio = settings.get("gallery_ratio", 0.28)
    if not isinstance(ratio, (int, float)) or not 0.18 <= ratio <= 0.48:
        ratio = 0.28
    width = settings.get("window_width", 1400)
    height = settings.get("window_height", 900)
    if not isinstance(width, int) or not 640 <= width <= 2400:
        width = 1400
    if not isinstance(height, int) or not 480 <= height <= 1600:
        height = 900
    return {
        "gallery_ratio": float(ratio),
        "gallery_visible": settings.get("gallery_visible", True) is not False,
        "window_width": width,
        "window_height": height,
    }


def _fit_window_size(window_size, desktop_size):
    desktop_width, desktop_height = desktop_size
    available_width = max(1, desktop_width - min(64, max(16, desktop_width // 20)))
    available_height = max(1, desktop_height - min(96, max(32, desktop_height // 10)))
    minimum_width = min(640, available_width)
    minimum_height = min(480, available_height)
    width = max(minimum_width, min(window_size[0], available_width))
    height = max(minimum_height, min(window_size[1], available_height))
    return width, height


def _save_layout_settings(settings: dict):
    mappings = _load_joystick_mappings()
    mappings["_layout"] = settings
    config_path = _joystick_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as config_file:
        json.dump(mappings, config_file, indent=2)


def _update_layout(width: int, height: int, gallery_ratio: float, gallery_visible: bool):
    global VIEWPORT, GALLERY_RECT, LAYOUT_DIVIDER_RECT
    global MENU_BUTTON_RECT, GALLERY_TOGGLE_RECT

    margin = max(16, min(48, width // 35))
    top = max(68, min(110, height // 8))
    bottom = max(110, min(150, height // 6))
    content_height = max(160, height - top - bottom)
    content_width = max(1, width - margin * 2)
    gap = max(8, min(24, width // 70))
    button_width = max(150, min(230, (width - margin * 3 - 10) // 2))
    if gallery_visible:
        min_viewport_width = min(420, max(220, content_width // 2))
        max_gallery_width = max(100, content_width - min_viewport_width - gap)
        min_gallery_width = min(240, max_gallery_width)
        gallery_width = max(
            min_gallery_width,
            min(
                max_gallery_width,
                min(480, int(content_width * gallery_ratio)),
            ),
        )
        viewport_width = content_width - gallery_width - gap
        gallery_x = margin + viewport_width + gap
        VIEWPORT = pygame.Rect(margin, top, viewport_width, content_height)
        LAYOUT_DIVIDER_RECT = pygame.Rect(
            margin + viewport_width,
            top,
            gap,
            content_height,
        )
        GALLERY_RECT = pygame.Rect(
            gallery_x,
            top,
            width - margin - gallery_x,
            content_height,
        )
    else:
        VIEWPORT = pygame.Rect(margin, top, content_width, content_height)
        LAYOUT_DIVIDER_RECT = pygame.Rect(0, 0, 0, 0)
        GALLERY_RECT = pygame.Rect(0, 0, 0, 0)

    button_y = max(14, (top - 46) // 2)
    MENU_BUTTON_RECT = pygame.Rect(
        width - margin - button_width,
        button_y,
        button_width,
        46,
    )
    GALLERY_TOGGLE_RECT = pygame.Rect(
        MENU_BUTTON_RECT.x - button_width - 10,
        button_y,
        button_width,
        46,
    )
    return VIEWPORT, GALLERY_RECT


def _blend_color(start: tuple[int, int, int], end: tuple[int, int, int], amount: float):
    return tuple(
        round(start_channel + (end_channel - start_channel) * amount)
        for start_channel, end_channel in zip(start, end)
    )


def _tk_color(color: tuple[int, int, int]):
    return "#" + "".join(f"{channel:02x}" for channel in color)


def _draw_sketch_panel(
    screen: pygame.Surface,
    rect: pygame.Rect,
    fill,
    outline,
    width: int = 2,
):
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    corners = (
        (left + 3, top + 1),
        (right - 4, top + 2),
        (right - 1, top + 4),
        (right - 2, bottom - 4),
        (right - 5, bottom - 1),
        (left + 4, bottom - 2),
        (left + 1, bottom - 5),
        (left + 2, top + 4),
    )
    if fill is not None:
        pygame.draw.polygon(screen, fill, corners)
    if outline is None or width <= 0:
        return

    pygame.draw.lines(screen, outline, True, corners, width)
    inner_corners = tuple(
        (x + (1 if x < rect.centerx else -1), y + (1 if y < rect.centery else -1))
        for x, y in corners
    )
    pygame.draw.lines(screen, outline, True, inner_corners, 1)


def _joystick_binding_key(binding):
    if isinstance(binding, int):
        return ("button", binding)
    if not isinstance(binding, dict):
        return None
    binding_type = binding.get("type")
    index = binding.get("index")
    direction = binding.get("direction")
    if (
        binding_type == "axis"
        and isinstance(index, int)
        and index >= 0
        and direction in (-1, 1)
    ):
        return ("axis", index, direction)
    if (
        binding_type == "hat"
        and isinstance(index, int)
        and index >= 0
        and isinstance(direction, list)
        and len(direction) == 2
        and all(value in (-1, 0, 1) for value in direction)
        and direction != [0, 0]
    ):
        return ("hat", index, direction[0], direction[1])
    return None


def _validate_joystick_mapping(mapping: dict, joystick):
    required_actions = {
        action for action, _, required in JOYSTICK_ACTIONS if required
    }
    configured = {
        action: mapping.get(action)
        for action, _, _ in JOYSTICK_ACTIONS
    }
    binding_keys = []
    for action, binding in configured.items():
        if binding is None:
            if action in required_actions:
                raise ValueError(f"Tombol joystick untuk {action} belum diatur.")
            continue
        binding_key = _joystick_binding_key(binding)
        if binding_key is None:
            raise ValueError(f"Mapping joystick untuk {action} tidak valid.")
        binding_type = binding_key[0]
        index = binding_key[1]
        if binding_type == "button" and (
            index < 0 or index >= joystick.get_numbuttons()
        ):
            raise ValueError(f"Nomor tombol joystick untuk {action} tidak tersedia.")
        if binding_type == "axis" and index >= joystick.get_numaxes():
            raise ValueError(f"Sumbu joystick untuk {action} tidak tersedia.")
        if binding_type == "hat" and index >= joystick.get_numhats():
            raise ValueError(f"D-pad joystick untuk {action} tidak tersedia.")
        binding_keys.append(binding_key)
    if len(binding_keys) != len(set(binding_keys)):
        raise ValueError("Satu input joystick dipetakan ke lebih dari satu fungsi.")
    return configured


def _load_keyboard_mapping():
    mappings = _load_joystick_mappings()
    stored_mapping = mappings.get("_keyboard")
    if stored_mapping is None:
        return dict(DEFAULT_KEYBOARD_MAPPING)
    if not isinstance(stored_mapping, dict):
        raise ValueError("Format pengaturan tombol keyboard tidak valid.")

    required_actions = {
        action for action, _, required in KEYBOARD_ACTIONS if required
    }
    configured_mapping = {
        action: stored_mapping.get(action)
        for action, _, _ in KEYBOARD_ACTIONS
    }
    assigned_keys = [key for key in configured_mapping.values() if key is not None]
    if (
        any(
            not isinstance(configured_mapping[action], int)
            for action in required_actions
        )
        or any(
            key is not None and not isinstance(key, int)
            for key in configured_mapping.values()
        )
        or len(assigned_keys) != len(set(assigned_keys))
        or pygame.K_ESCAPE in assigned_keys
    ):
        raise ValueError(
            "Pengaturan tombol keyboard tidak valid. Atur ulang dari menu awal."
        )
    return configured_mapping


def _save_keyboard_mapping(mapping: dict):
    mappings = _load_joystick_mappings()
    mappings["_keyboard"] = mapping
    config_path = _joystick_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as config_file:
        json.dump(mappings, config_file, indent=2)


def _format_keyboard_binding(key):
    if key is None:
        return "Tidak diatur"
    if key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
        return "Shift kiri" if key == pygame.K_LSHIFT else "Shift kanan"
    if key in (pygame.K_LCTRL, pygame.K_RCTRL):
        return "Ctrl kiri" if key == pygame.K_LCTRL else "Ctrl kanan"
    if key in (pygame.K_LALT, pygame.K_RALT):
        return "Alt kiri" if key == pygame.K_LALT else "Alt kanan"
    name = pygame.key.name(key)
    return name.replace("left ", "kiri ").replace("right ", "kanan ").title()


def _keyboard_key_from_tk_keysym(keysym: str):
    aliases = {
        "shift_l": pygame.K_LSHIFT,
        "shift_r": pygame.K_RSHIFT,
        "control_l": pygame.K_LCTRL,
        "control_r": pygame.K_RCTRL,
        "alt_l": pygame.K_LALT,
        "alt_r": pygame.K_RALT,
        "meta_l": pygame.K_LGUI,
        "meta_r": pygame.K_RGUI,
        "super_l": pygame.K_LSUPER,
        "super_r": pygame.K_RSUPER,
        "caps_lock": pygame.K_CAPSLOCK,
        "num_lock": pygame.K_NUMLOCK,
        "scroll_lock": pygame.K_SCROLLLOCK,
        "print": pygame.K_PRINTSCREEN,
        "pause": pygame.K_PAUSE,
        "prior": pygame.K_PAGEUP,
        "page_up": pygame.K_PAGEUP,
        "next": pygame.K_PAGEDOWN,
        "page_down": pygame.K_PAGEDOWN,
        "kp_enter": pygame.K_KP_ENTER,
        "kp_add": pygame.K_KP_PLUS,
        "kp_subtract": pygame.K_KP_MINUS,
        "kp_multiply": pygame.K_KP_MULTIPLY,
        "kp_divide": pygame.K_KP_DIVIDE,
        "kp_decimal": pygame.K_KP_PERIOD,
    }
    aliases.update(
        {
            f"kp_{number}": getattr(pygame, f"K_KP{number}")
            for number in range(10)
        }
    )
    key_name = keysym.lower()
    if key_name in aliases:
        return aliases[key_name]
    return pygame.key.key_code(key_name)


def _format_joystick_binding(binding):
    if binding is None:
        return "Tidak diatur"
    if isinstance(binding, int):
        return f"Tombol {binding + 1}"
    if binding.get("type") == "axis":
        direction = "+" if binding["direction"] > 0 else "-"
        return f"Trigger / sumbu {binding['index'] + 1} ({direction})"
    if binding.get("type") == "hat":
        x, y = binding["direction"]
        directions = []
        if y > 0:
            directions.append("Atas")
        elif y < 0:
            directions.append("Bawah")
        if x < 0:
            directions.append("Kiri")
        elif x > 0:
            directions.append("Kanan")
        return f"D-pad {'+'.join(directions)}"
    return "Input tidak dikenal"


def _show_mapping_dialog(
    parent,
    title,
    description,
    actions,
    mapping,
    formatter,
    on_save,
    capture_callback=None,
    bind_keyboard=True,
    on_open=None,
    on_close=None,
):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    palette = THEME_PALETTES[_load_theme()]
    colors = {key: _tk_color(value) for key, value in palette.items()}
    dialog.configure(background=colors["background"])
    dialog.grab_set()

    style = ttk.Style(dialog)
    style.configure("Mapping.TFrame", background=colors["background"])
    style.configure(
        "MappingCard.TFrame",
        background=colors["panel"],
        bordercolor=colors["border"],
        borderwidth=2,
        relief="ridge",
    )
    style.configure(
        "MappingTitle.TLabel",
        background=colors["background"],
        foreground=colors["text"],
        font=("Segoe Print", 18, "bold"),
    )
    style.configure(
        "MappingSubtitle.TLabel",
        background=colors["background"],
        foreground=colors["muted"],
        font=("Segoe Print", 9),
    )
    style.configure(
        "MappingCard.TLabel",
        background=colors["panel"],
        foreground=colors["text"],
        font=("Segoe Print", 10),
    )
    style.configure(
        "MappingValue.TLabel",
        background=colors["panel"],
        foreground=colors["accent"],
        bordercolor=colors["border"],
        borderwidth=1,
        relief="ridge",
        padding=(9, 5),
        font=("Segoe Print", 9, "bold"),
    )
    style.configure(
        "Mapping.TButton",
        background=colors["panel"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        borderwidth=2,
        relief="ridge",
        padding=(9, 6),
        font=("Segoe Print", 9),
    )
    style.map(
        "Mapping.TButton",
        background=[("active", colors["shadow"])],
        relief=[("pressed", "sunken")],
    )
    style.configure(
        "MappingPrimary.TButton",
        background=colors["accent"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        borderwidth=2,
        relief="ridge",
        padding=(15, 7),
        font=("Segoe Print", 9, "bold"),
    )
    style.map(
        "MappingPrimary.TButton",
        background=[("active", colors["accent"])],
        relief=[("pressed", "sunken")],
    )

    container = ttk.Frame(dialog, style="Mapping.TFrame", padding=22)
    container.pack(fill="both", expand=True)
    ttk.Label(container, text=title, style="MappingTitle.TLabel").pack(anchor="w")
    ttk.Label(
        container,
        text=description,
        style="MappingSubtitle.TLabel",
        wraplength=560,
    ).pack(anchor="w", pady=(4, 14))

    status = tk.StringVar(value="Pilih Atur untuk mengganti input pada fungsi.")
    rows = {}
    capture_action = {"name": None}

    def refresh_rows():
        for action, _, _ in actions:
            rows[action].configure(text=formatter(mapping.get(action)))

    for action, label, required in actions:
        card = ttk.Frame(container, style="MappingCard.TFrame", padding=(12, 8))
        card.pack(fill="x", pady=3)
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=label, style="MappingCard.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        if required:
            ttk.Label(
                card,
                text="WAJIB",
                style="MappingSubtitle.TLabel",
            ).grid(row=0, column=1, padx=(8, 10))
        value_label = ttk.Label(
            card,
            text=formatter(mapping.get(action)),
            style="MappingValue.TLabel",
            width=24,
            anchor="center",
        )
        value_label.grid(row=0, column=2, padx=8)
        rows[action] = value_label
        ttk.Button(
            card,
            text="Atur",
            style="Mapping.TButton",
            command=lambda name=action: begin_capture(name),
        ).grid(row=0, column=3, padx=(4, 0))
        if not required:
            ttk.Button(
                card,
                text="Nonaktif",
                style="Mapping.TButton",
                command=lambda name=action: clear_binding(name),
            ).grid(row=0, column=4, padx=(4, 0))

    ttk.Label(
        container,
        textvariable=status,
        style="MappingSubtitle.TLabel",
        wraplength=560,
    ).pack(anchor="w", pady=(12, 10))

    footer = ttk.Frame(container, style="Mapping.TFrame")
    footer.pack(fill="x", pady=(4, 0))
    ttk.Button(
        footer,
        text="Batal",
        style="Mapping.TButton",
        command=lambda: close_dialog(),
    ).pack(side="right", padx=(8, 0))
    ttk.Button(
        footer,
        text="Simpan pengaturan",
        style="MappingPrimary.TButton",
        command=lambda: save_mapping(),
    ).pack(side="right")

    def begin_capture(action):
        capture_action["name"] = action
        status.set(f"Menunggu input untuk: {dict((key, label) for key, label, _ in actions)[action]}")
        if capture_callback is not None:
            capture_callback(action, status, mapping, refresh_rows)
        else:
            dialog.focus_force()

    def capture_keyboard(event):
        if not bind_keyboard:
            return None
        action = capture_action["name"]
        if action is None:
            return "break"
        if event.keysym == "Escape":
            status.set("Esc digunakan untuk membatalkan pengaturan.")
            return "break"
        try:
            key = _keyboard_key_from_tk_keysym(event.keysym)
        except (ValueError, KeyError):
            status.set(f"Tombol '{event.keysym}' tidak didukung. Coba tombol lain.")
            return "break"
        if key == pygame.K_ESCAPE:
            status.set("Esc disimpan untuk keluar dari layar sortir.")
            return "break"
        if key in {
            assigned
            for other_action, assigned in mapping.items()
            if other_action != action and assigned is not None
        }:
            status.set("Tombol itu sudah dipakai fungsi lain. Pilih tombol berbeda.")
            return "break"
        mapping[action] = key
        capture_action["name"] = None
        refresh_rows()
        status.set(f"{dict((key, label) for key, label, _ in actions)[action]}: {_format_keyboard_binding(key)}")
        return "break"

    def clear_binding(action):
        mapping[action] = None
        refresh_rows()
        status.set(f"{dict((key, label) for key, label, _ in actions)[action]} dinonaktifkan.")

    def save_mapping():
        required_actions = {
            action for action, _, required in actions if required
        }
        missing = [
            label
            for action, label, _ in actions
            if action in required_actions and mapping.get(action) is None
        ]
        if missing:
            status.set("Atur fungsi wajib terlebih dahulu: " + ", ".join(missing))
            return
        try:
            on_save(mapping)
        except (OSError, ValueError, TypeError) as exc:
            status.set(f"Gagal menyimpan: {exc}")
            return
        close_dialog()
        messagebox.showinfo(
            "Pengaturan tersimpan",
            "Input untuk semua fungsi berhasil diperbarui.",
            parent=parent,
        )

    def close_dialog():
        if on_close is not None:
            on_close()
        dialog.destroy()

    if bind_keyboard:
        dialog.bind_all("<KeyPress>", capture_keyboard)
    dialog.protocol("WM_DELETE_WINDOW", close_dialog)
    if on_open is not None:
        on_open(dialog, status, mapping, refresh_rows)
    dialog.wait_window()
    if bind_keyboard:
        dialog.unbind_all("<KeyPress>")


def _capture_keyboard_mapping(parent):
    pygame.init()
    mapping = _load_keyboard_mapping()
    _show_mapping_dialog(
        parent,
        "Pengaturan Keyboard",
        "Pilih Atur lalu tekan tombol yang ingin digunakan. Tombol terpilih langsung terlihat di daftar.",
        KEYBOARD_ACTIONS,
        mapping,
        _format_keyboard_binding,
        _save_keyboard_mapping,
    )


def configure_keyboard(parent):
    try:
        _capture_keyboard_mapping(parent)
    except Exception as exc:
        pygame.quit()
        messagebox.showerror(
            "Pengaturan keyboard - Error",
            str(exc),
            parent=parent,
        )


def _capture_joystick_mapping(parent, device_index: int, guid: str, name: str, mapping):
    pygame.init()
    pygame.joystick.init()
    joystick = pygame.joystick.Joystick(device_index)
    joystick.init()
    mapping = dict(mapping)
    capture = {"action": None}
    action_labels = {
        action: label for action, label, _ in JOYSTICK_ACTIONS
    }
    previous_buttons = [
        bool(joystick.get_button(index))
        for index in range(joystick.get_numbuttons())
    ]
    previous_axes = [
        joystick.get_axis(index) for index in range(joystick.get_numaxes())
    ]
    previous_hats = [
        joystick.get_hat(index)         for index in range(joystick.get_numhats())
    ]
    poll_state = {
        "dialog": None,
        "after_id": None,
        "status": None,
        "refresh_rows": None,
    }

    def begin_capture(action, status, current_mapping, refresh_rows):
        pygame.event.pump()
        previous_buttons[:] = [
            bool(joystick.get_button(index))
            for index in range(joystick.get_numbuttons())
        ]
        previous_axes[:] = [
            joystick.get_axis(index) for index in range(joystick.get_numaxes())
        ]
        previous_hats[:] = [
            joystick.get_hat(index) for index in range(joystick.get_numhats())
        ]
        capture["action"] = action
        status.set(f"Menunggu input joystick untuk: {action_labels[action]}")

    def on_save(updated_mapping):
        _validate_joystick_mapping(updated_mapping, joystick)
        _save_joystick_mapping(guid, updated_mapping)

    def poll_input():
        dialog = poll_state["dialog"]
        status = poll_state["status"]
        refresh_rows = poll_state["refresh_rows"]
        if dialog is None or not dialog.winfo_exists():
            return
        try:
            pygame.event.pump()
            action = capture["action"]
            if action is not None:
                new_binding = None
                for index in range(joystick.get_numbuttons()):
                    pressed = bool(joystick.get_button(index))
                    if pressed and not previous_buttons[index]:
                        new_binding = index
                        break
                    previous_buttons[index] = pressed

                if new_binding is None:
                    for index in range(joystick.get_numaxes()):
                        value = joystick.get_axis(index)
                        previous_value = previous_axes[index]
                        if abs(value) >= 0.65 and abs(previous_value) < 0.45:
                            new_binding = {
                                "type": "axis",
                                "index": index,
                                "direction": 1 if value > 0 else -1,
                            }
                            break
                        previous_axes[index] = value

                if new_binding is None:
                    for index in range(joystick.get_numhats()):
                        value = joystick.get_hat(index)
                        if value != (0, 0) and previous_hats[index] == (0, 0):
                            new_binding = {
                                "type": "hat",
                                "index": index,
                                "direction": [value[0], value[1]],
                            }
                            break
                        previous_hats[index] = value

                if new_binding is not None:
                    new_key = _joystick_binding_key(new_binding)
                    used_by_another_action = any(
                        _joystick_binding_key(binding) == new_key
                        for other_action, binding in mapping.items()
                        if other_action != action and binding is not None
                    )
                    if used_by_another_action:
                        status.set(
                            "Input sudah dipakai fungsi lain. Lepaskan lalu pilih input berbeda."
                        )
                    else:
                        mapping[action] = new_binding
                        capture["action"] = None
                        refresh_rows()
                        status.set(
                            f"{action_labels[action]}: "
                            f"{_format_joystick_binding(new_binding)}"
                        )
            poll_state["after_id"] = dialog.after(16, poll_input)
        except pygame.error as exc:
            status.set(f"Joystick terputus atau tidak dapat dibaca: {exc}")

    def start_polling(dialog, status, _mapping, refresh_rows):
        poll_state["dialog"] = dialog
        poll_state["status"] = status
        poll_state["refresh_rows"] = refresh_rows
        poll_state["after_id"] = dialog.after(16, poll_input)

    def stop_polling():
        dialog = poll_state["dialog"]
        if dialog is not None and poll_state["after_id"] is not None:
            try:
                dialog.after_cancel(poll_state["after_id"])
            except tk.TclError:
                pass
        joystick.quit()
        pygame.joystick.quit()
        pygame.quit()

    _show_mapping_dialog(
        parent,
        f"Pengaturan Joystick · {name}",
        "Pilih Atur lalu tekan tombol, gerakkan trigger/stik, atau tekan arah D-pad. Input terpilih terlihat di samping fungsi.",
        JOYSTICK_ACTIONS,
        mapping,
        _format_joystick_binding,
        on_save,
        capture_callback=begin_capture,
        bind_keyboard=False,
        on_open=start_polling,
        on_close=stop_polling,
    )


def _configure_joystick(parent):
    pygame.init()
    pygame.joystick.init()
    devices = []
    for device_index in range(pygame.joystick.get_count()):
        joystick = pygame.joystick.Joystick(device_index)
        joystick.init()
        devices.append((device_index, joystick.get_name(), joystick.get_guid()))
        joystick.quit()
    pygame.quit()

    if not devices:
        messagebox.showwarning(
            "Joystick tidak ditemukan",
            "Sambungkan joystick sebelum mengatur tombol.",
            parent=parent,
        )
        return

    dialog = tk.Toplevel(parent)
    dialog.title("Pilih joystick")
    dialog.resizable(False, False)
    dialog.transient(parent)
    ttk.Label(
        dialog,
        text="Pilih joystick yang ingin diatur tombolnya:",
        padding=(16, 16, 16, 8),
    ).pack()
    device_names = [f"{name} (ID {index})" for index, name, _ in devices]
    selection = tk.StringVar(value=device_names[0])
    ttk.Combobox(
        dialog,
        textvariable=selection,
        values=device_names,
        state="readonly",
        width=42,
    ).pack(padx=16, pady=4)

    def begin_setup():
        selected_index = device_names.index(selection.get())
        device_index, name, guid = devices[selected_index]
        dialog.destroy()
        try:
            mapping = dict(DEFAULT_JOYSTICK_MAPPING)
            stored_mapping = _load_joystick_mappings().get(guid)
            if isinstance(stored_mapping, dict):
                mapping.update(
                    {
                        action: stored_mapping[action]
                        for action, _, _ in JOYSTICK_ACTIONS
                        if action in stored_mapping
                    }
                )
            _capture_joystick_mapping(
                parent, device_index, guid, name, mapping
            )
        except Exception as exc:
            pygame.quit()
            parent.deiconify()
            messagebox.showerror(
                "Pengaturan joystick - Error",
                str(exc),
                parent=parent,
            )

    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack()
    ttk.Button(buttons, text="Lanjut", command=begin_setup).pack(side="left", padx=5)
    ttk.Button(buttons, text="Batal", command=dialog.destroy).pack(side="left", padx=5)
    dialog.grab_set()
    parent.wait_window(dialog)


def configure_joystick(parent):
    try:
        _configure_joystick(parent)
    except Exception as exc:
        pygame.quit()
        messagebox.showerror(
            "Pengaturan joystick - Error",
            str(exc),
            parent=parent,
        )


class PhotoSorter:
    def __init__(self, source_folder: str = ".", theme: str = "dark"):
        if theme not in THEME_PALETTES:
            raise ValueError(f"Tema tidak dikenal: {theme}")
        self.source_folder = Path(source_folder).resolve()
        self.theme = theme
        self.palette = THEME_PALETTES[theme]
        self.accepted_folder = self.source_folder / "diterima"
        self.rejected_folder = self.source_folder / "ditolak"
        self.accepted_folder.mkdir(exist_ok=True, parents=True)
        self.rejected_folder.mkdir(exist_ok=True, parents=True)

        self.files = self._collect_files()
        self.index = 0
        self.running = True
        self.current_path = self.files[self.index] if self.files else None
        self.font = {}
        self.source_image = None
        self.source_image_path = None
        self.display_image = None
        self.display_image_key = None
        self.zoom = ZOOM_MIN
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.dragging = False
        self.last_mouse_pos = None
        self.joystick_mapping = dict(DEFAULT_JOYSTICK_MAPPING)
        self.joystick_previous_actions = set()
        self.joystick_zoom_repeat_timers = {"zoom_out": 0.0, "zoom_in": 0.0}
        self.keyboard_mapping = _load_keyboard_mapping()
        self.return_to_menu = False
        self.gallery_scroll = 0
        self.gallery_row_height = GALLERY_ROW_HEIGHT
        self.thumbnail_cache = OrderedDict()
        self.gallery_selection_started = 0
        self.resizing_layout = False
        self.transition_image = None
        self.transition_rect = None
        self.transition_started = 0
        self.transition_alpha = 0
        layout_settings = _load_layout_settings()
        self.gallery_ratio = layout_settings["gallery_ratio"]
        self.gallery_visible = layout_settings["gallery_visible"]
        self.windowed_size = (
            layout_settings["window_width"],
            layout_settings["window_height"],
        )
        self.is_fullscreen = False

    def _collect_files(self):
        files = []
        if not self.source_folder.exists():
            raise FileNotFoundError(f"Folder sumber tidak ditemukan: {self.source_folder}")

        for item in sorted(self.source_folder.iterdir()):
            if item.is_file() and self._is_supported_file(item):
                if item.parent.name not in {"diterima", "ditolak"}:
                    files.append(item)

        if not files:
            print(f"Tidak ada foto yang ditemukan di: {self.source_folder}")
            print("Format didukung: JPG, JPEG, PNG, TIFF, BMP, RAW (DNG, NEF, CR2, CR3, ARW, dll)")
        return files

    @staticmethod
    def _is_supported_file(path: Path):
        ext = path.suffix.lower()
        return ext in SUPPORTED_EXTENSIONS or ext in RAW_EXTENSIONS

    def _read_image(self, image_path: Path):
        ext = image_path.suffix.lower()

        if ext in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            with Image.open(image_path) as img:
                return img.convert("RGB")

        if ext in RAW_EXTENSIONS:
            if rawpy is None:
                raise RuntimeError(
                    "rawpy belum terinstal. Jalankan: pip install rawpy"
                )
            if np is None:
                raise RuntimeError(
                    "numpy belum terinstal. Jalankan: pip install numpy"
                )

            with rawpy.imread(str(image_path)) as raw:
                rgb = raw.postprocess()
            return Image.fromarray(rgb)

        raise ValueError(f"Format file tidak didukung: {image_path.name}")

    def _resize_to_fit(self, image: Image.Image, max_width: int, max_height: int):
        img_w, img_h = image.size
        scale = min(max_width / img_w, max_height / img_h)
        if scale < 1:
            new_size = (max(int(img_w * scale), 1), max(int(img_h * scale), 1))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        return image

    def _render_current(self, screen: pygame.Surface):
        screen.fill(self.palette["background"])
        _draw_sketch_panel(
            screen,
            VIEWPORT,
            self.palette["panel"],
            self.palette["border"],
            2,
        )
        if self.gallery_visible:
            _draw_sketch_panel(
                screen,
                GALLERY_RECT,
                self.palette["panel"],
                self.palette["border"],
                2,
            )
        self._draw_text(
            screen,
            "Photo Sorter",
            26,
            self.palette["text"],
            (VIEWPORT.x + 120, 48),
        )
        pygame.draw.lines(
            screen,
            self.palette["accent"],
            False,
            (
                (VIEWPORT.x + 32, 71),
                (VIEWPORT.x + 94, 70),
                (VIEWPORT.x + 164, 72),
                (VIEWPORT.x + 218, 70),
            ),
            2,
        )
        self._draw_button(
            screen,
            MENU_BUTTON_RECT,
            "Kembali ke menu",
            self.palette["panel"],
            self.palette["text"],
        )
        self._draw_button(
            screen,
            GALLERY_TOGGLE_RECT,
            "Sembunyikan daftar" if self.gallery_visible else "Tampilkan daftar",
            self.palette["panel"],
            self.palette["text"],
        )
        if self.gallery_visible:
            pygame.draw.lines(
                screen,
                self.palette["border"],
                False,
                (
                    (LAYOUT_DIVIDER_RECT.centerx - 1, LAYOUT_DIVIDER_RECT.y + 5),
                    (LAYOUT_DIVIDER_RECT.centerx + 1, LAYOUT_DIVIDER_RECT.centery),
                    (LAYOUT_DIVIDER_RECT.centerx - 1, LAYOUT_DIVIDER_RECT.bottom - 5),
                ),
                3,
            )
            self._render_gallery(screen)

        if not self.current_path:
            text = "Tidak ada foto tersisa"
            self._draw_text(
                screen,
                text,
                32,
                self.palette["text"],
                VIEWPORT.center,
            )
            return

        try:
            self._prepare_display_image()
            pygame.draw.rect(screen, self.palette["panel"], VIEWPORT)
            screen.set_clip(VIEWPORT)
            image_rect = self.display_image.get_rect(
                center=(
                    int(VIEWPORT.centerx + self.pan_x),
                    int(VIEWPORT.centery + self.pan_y),
                )
            )
            if self.transition_image is not None:
                elapsed = pygame.time.get_ticks() - self.transition_started
                progress = min(1.0, elapsed / PHOTO_TRANSITION_MS)
                progress = progress * progress * (3 - 2 * progress)
                self.transition_alpha = round(255 * progress)
                old_image = self.transition_image.copy()
                old_image.set_alpha(255 - self.transition_alpha)
                screen.blit(old_image, self.transition_rect)
                if progress >= 1:
                    self.transition_image = None
                    self.transition_rect = None
            new_image = self.display_image.copy()
            if self.transition_image is not None:
                new_image.set_alpha(self.transition_alpha)
            screen.blit(new_image, image_rect)
            screen.set_clip(None)
            _draw_sketch_panel(
                screen,
                VIEWPORT,
                None,
                self.palette["border"],
                2,
            )

            title = f"{self.index + 1} / {len(self.files)}  |  {self.current_path.name}"
            self._draw_text(
                screen,
                title,
                18,
                self.palette["muted"],
                (VIEWPORT.centerx, VIEWPORT.bottom + 27),
            )
            self._draw_text(
                screen,
                f"Zoom {self.zoom:.1f}x  |  Tarik pemisah untuk ubah ukuran panel  |  F11 layar penuh",
                16,
                self.palette["muted"],
                (VIEWPORT.centerx, VIEWPORT.bottom + 57),
            )
            self._draw_text(
                screen,
                "Pilih foto di daftar untuk meninjaunya tanpa memindahkan.",
                15,
                self.palette["muted"],
                (VIEWPORT.centerx, VIEWPORT.bottom + 84),
            )

        except Exception as exc:
            screen.set_clip(None)
            self._draw_text(
                screen,
                f"Gagal membuka foto: {self.current_path.name}",
                28,
                self.palette["error"],
                VIEWPORT.center,
            )
            self._draw_text(
                screen,
                str(exc),
                18,
                self.palette["text"],
                (VIEWPORT.centerx, VIEWPORT.centery + 40),
            )

    def _render_gallery(self, screen: pygame.Surface):
        list_height = GALLERY_RECT.height - 70
        visible_rows = max(1, list_height // self.gallery_row_height)
        self.gallery_scroll = max(
            0,
            min(
                max(0, len(self.files) - visible_rows),
                self.gallery_scroll,
            ),
        )
        header_rect = pygame.Rect(
            GALLERY_RECT.x + 14,
            GALLERY_RECT.y + 12,
            GALLERY_RECT.width - 28,
            48,
        )
        self._draw_text(
            screen,
            f"Foto dalam folder ({len(self.files)})",
            18,
            self.palette["text"],
            header_rect.center,
        )
        list_rect = pygame.Rect(
            GALLERY_RECT.x + 10,
            GALLERY_RECT.y + 58,
            GALLERY_RECT.width - 20,
            GALLERY_RECT.height - 70,
        )
        if list_rect.width <= 0 or list_rect.height <= 0:
            return
        screen.set_clip(list_rect)
        visible_rows = list_rect.height // self.gallery_row_height + 2
        end_index = min(len(self.files), self.gallery_scroll + visible_rows)
        selection_progress = min(
            1.0,
            (pygame.time.get_ticks() - self.gallery_selection_started)
            / PHOTO_TRANSITION_MS,
        )
        selection_progress = selection_progress * selection_progress * (
            3 - 2 * selection_progress
        )
        for file_index in range(self.gallery_scroll, end_index):
            row_rect = pygame.Rect(
                list_rect.x + 3,
                list_rect.y + (file_index - self.gallery_scroll) * self.gallery_row_height,
                list_rect.width - 6,
                self.gallery_row_height - 3,
            )
            if file_index == self.index:
                selected_color = _blend_color(
                    self.palette["panel"],
                    self.palette["accent"],
                    selection_progress,
                )
                _draw_sketch_panel(
                    screen,
                    row_rect,
                    selected_color,
                    self.palette["accent"],
                    2,
                )
                text_color = self.palette["text"]
            else:
                text_color = self.palette["text"]
            thumbnail_rect = pygame.Rect(
                row_rect.x + 6,
                row_rect.y + (row_rect.height - THUMBNAIL_SIZE[1]) // 2,
                *THUMBNAIL_SIZE,
            )
            thumbnail = self._get_thumbnail(self.files[file_index])
            if thumbnail is None:
                _draw_sketch_panel(
                    screen,
                    thumbnail_rect,
                    self.palette["panel"],
                    self.palette["border"],
                    1,
                )
                self._draw_text(
                    screen,
                    "Foto",
                    11,
                    self.palette["muted"],
                    thumbnail_rect.center,
                )
            else:
                screen.blit(thumbnail, thumbnail_rect)
            _draw_sketch_panel(
                screen,
                thumbnail_rect,
                None,
                self.palette["border"],
                1,
            )

            name_rect = pygame.Rect(
                thumbnail_rect.right + 8,
                row_rect.y,
                row_rect.right - thumbnail_rect.right - 14,
                row_rect.height,
            )
            self._draw_text(
                screen,
                self._ellipsize_filename(self.files[file_index].name, name_rect.width),
                13,
                text_color,
                name_rect.center,
            )
        screen.set_clip(None)

    def _get_thumbnail(self, image_path: Path):
        try:
            cache_key = (image_path, image_path.stat().st_mtime_ns)
        except OSError:
            cache_key = (image_path, None)
        if cache_key in self.thumbnail_cache:
            self.thumbnail_cache.move_to_end(cache_key)
            return self.thumbnail_cache[cache_key]

        try:
            image = self._read_image(image_path)
            image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            surface = pygame.image.fromstring(
                image.tobytes(),
                image.size,
                image.mode,
            )
            thumbnail = pygame.Surface(THUMBNAIL_SIZE)
            thumbnail.fill(self.palette["panel"])
            thumbnail.blit(surface, surface.get_rect(center=thumbnail.get_rect().center))
        except (OSError, RuntimeError, ValueError, UnidentifiedImageError):
            thumbnail = None

        self.thumbnail_cache[cache_key] = thumbnail
        self.thumbnail_cache.move_to_end(cache_key)
        while len(self.thumbnail_cache) > THUMBNAIL_CACHE_LIMIT:
            self.thumbnail_cache.popitem(last=False)
        return thumbnail

    def _ellipsize_filename(self, filename: str, max_width: int):
        font = self._get_font(13)
        if font.size(filename)[0] <= max_width:
            return filename
        shortened = filename
        while shortened and font.size(shortened + "...")[0] > max_width:
            shortened = shortened[:-1]
        return shortened + "..." if shortened else "..."

    def _draw_button(self, screen, rect, text, background, foreground):
        shadow_rect = rect.move(0, 3)
        _draw_sketch_panel(
            screen,
            shadow_rect,
            self.palette["shadow"],
            None,
        )
        _draw_sketch_panel(
            screen,
            rect,
            background,
            self.palette["border"],
            2,
        )
        self._draw_text(screen, text, 15, foreground, rect.center)

    def _apply_layout(self, screen):
        _update_layout(
            *screen.get_size(),
            self.gallery_ratio,
            self.gallery_visible,
        )
        self._clamp_pan()

    def _save_layout(self, screen):
        width, height = self.windowed_size
        _save_layout_settings(
            {
                "gallery_ratio": self.gallery_ratio,
                "gallery_visible": self.gallery_visible,
                "window_width": width,
                "window_height": height,
            }
        )

    def _prepare_display_image(self):
        if self.source_image_path != self.current_path:
            image = self._read_image(self.current_path)
            self.source_image = pygame.image.fromstring(
                image.tobytes(), image.size, image.mode
            )
            self.source_image_path = self.current_path
            self.display_image_key = None
            self.zoom = ZOOM_MIN
            self.pan_x = 0.0
            self.pan_y = 0.0

        image_width, image_height = self.source_image.get_size()
        fit_scale = min(
            VIEWPORT.width / image_width,
            VIEWPORT.height / image_height,
        )
        display_size = (
            max(1, round(image_width * fit_scale * self.zoom)),
            max(1, round(image_height * fit_scale * self.zoom)),
        )
        image_key = (self.current_path, display_size)
        if image_key != self.display_image_key:
            self.display_image = pygame.transform.smoothscale(
                self.source_image, display_size
            )
            self.display_image_key = image_key
            self._clamp_pan()

    def _clamp_pan(self):
        if self.display_image is None:
            self.pan_x = self.pan_y = 0.0
            return

        image_width, image_height = self.display_image.get_size()
        max_pan_x = max(0, (image_width - VIEWPORT.width) / 2)
        max_pan_y = max(0, (image_height - VIEWPORT.height) / 2)
        self.pan_x = max(-max_pan_x, min(max_pan_x, self.pan_x))
        self.pan_y = max(-max_pan_y, min(max_pan_y, self.pan_y))

    def _change_zoom(self, direction: int):
        if not self.current_path or direction == 0:
            return
        self._prepare_display_image()
        new_zoom = self.zoom * (ZOOM_STEP if direction > 0 else 1 / ZOOM_STEP)
        self.zoom = min(ZOOM_MAX, max(ZOOM_MIN, new_zoom))
        self.display_image_key = None
        self._prepare_display_image()

    def _reset_view(self):
        if not self.current_path:
            return
        self._prepare_display_image()
        self.zoom = ZOOM_MIN
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.display_image_key = None
        self._prepare_display_image()

    def _pan(self, dx: float, dy: float):
        self.pan_x += dx
        self.pan_y += dy
        self._clamp_pan()

    def handle_joystick_button(self, button: int):
        if button == self.joystick_mapping.get("accept"):
            self.handle_action("accept")
        elif button == self.joystick_mapping.get("reject"):
            self.handle_action("reject")
        elif button == self.joystick_mapping.get("skip"):
            self.handle_action("skip")
        elif button == self.joystick_mapping.get("reset"):
            self._reset_view()
        elif button == self.joystick_mapping.get("zoom_out"):
            self._change_zoom(-1)
        elif button == self.joystick_mapping.get("zoom_in"):
            self._change_zoom(1)

    @staticmethod
    def _joystick_binding_value(joystick, binding):
        if isinstance(binding, int):
            if 0 <= binding < joystick.get_numbuttons():
                return float(joystick.get_button(binding))
            return 0.0
        if not isinstance(binding, dict):
            return 0.0

        binding_type = binding["type"]
        index = binding["index"]
        direction = binding["direction"]
        if binding_type == "axis":
            return max(0.0, joystick.get_axis(index) * direction)
        if binding_type == "hat":
            current = joystick.get_hat(index)
            return float(
                all(
                    wanted == 0 or current[position] == wanted
                    for position, wanted in enumerate(direction)
                )
            )
        return 0.0

    def _poll_joystick_controls(self, joystick, delta_time: float):
        active_actions = set()
        pan_values = {}
        pan_actions = ("pan_left", "pan_right", "pan_up", "pan_down")
        continuous_zoom_actions = set()
        for action, binding in self.joystick_mapping.items():
            if binding is None:
                continue
            value = self._joystick_binding_value(joystick, binding)
            if action in pan_actions:
                if value > 0.18:
                    pan_values[action] = value
            elif (
                action in self.joystick_zoom_repeat_timers
                and isinstance(binding, dict)
                and binding.get("type") == "axis"
            ):
                continuous_zoom_actions.add(action)
                timer = max(
                    0.0,
                    self.joystick_zoom_repeat_timers[action] - delta_time,
                )
                if value >= 0.65 and timer == 0:
                    self._change_zoom(1 if action == "zoom_in" else -1)
                    timer = 0.12
                elif value < 0.65:
                    timer = 0.0
                self.joystick_zoom_repeat_timers[action] = timer
            elif value >= 0.65:
                active_actions.add(action)

        active_actions.difference_update(continuous_zoom_actions)
        for action in active_actions - self.joystick_previous_actions:
            if action in ("accept", "reject", "skip"):
                self.handle_action(action)
            elif action == "zoom_out":
                self._change_zoom(-1)
            elif action == "zoom_in":
                self._change_zoom(1)
            elif action == "reset":
                self._reset_view()
        self.joystick_previous_actions = active_actions

        if any(self.joystick_mapping.get(action) is not None for action in pan_actions):
            pan_x = pan_values.get("pan_right", 0.0) - pan_values.get("pan_left", 0.0)
            pan_y = pan_values.get("pan_down", 0.0) - pan_values.get("pan_up", 0.0)
            if pan_x or pan_y:
                self._pan(
                    pan_x * PAN_SPEED * delta_time,
                    pan_y * PAN_SPEED * delta_time,
                )
            return True
        return False

    def handle_keyboard_key(self, key: int):
        action_by_key = {
            assigned_key: action
            for action, assigned_key in self.keyboard_mapping.items()
            if assigned_key is not None
        }
        action = action_by_key.get(key)
        if action in ("accept", "reject", "skip"):
            self.handle_action(action)
        elif action == "zoom_out":
            self._change_zoom(-1)
        elif action == "zoom_in":
            self._change_zoom(1)
        elif action == "reset":
            self._reset_view()

    def _keyboard_pan_direction(self, keys):
        pan_left = self.keyboard_mapping["pan_left"]
        pan_right = self.keyboard_mapping["pan_right"]
        pan_up = self.keyboard_mapping["pan_up"]
        pan_down = self.keyboard_mapping["pan_down"]
        return (
            int(pan_right is not None and keys[pan_right])
            - int(pan_left is not None and keys[pan_left]),
            int(pan_down is not None and keys[pan_down])
            - int(pan_up is not None and keys[pan_up]),
        )

    def _draw_text(self, screen: pygame.Surface, text: str, size: int, color, center_pos):
        font = self._get_font(size)
        label = font.render(text, True, color)
        rect = label.get_rect(center=center_pos)
        screen.blit(label, rect)

    def _get_font(self, size: int):
        if size not in self.font:
            self.font[size] = pygame.font.SysFont("segoeprint", size)
        return self.font[size]

    def _move_file(self, file_path: Path, destination_dir: Path):
        destination_dir.mkdir(exist_ok=True, parents=True)
        target = destination_dir / file_path.name
        base_name = file_path.stem
        suffix = file_path.suffix
        counter = 1

        while target.exists():
            target = destination_dir / f"{base_name}_{counter}{suffix}"
            counter += 1

        shutil.move(str(file_path), str(target))
        print(f"Dipindahkan: {file_path.name} -> {target}")

    def handle_action(self, action: str):
        if not self.current_path:
            return

        current = self.current_path
        self._prepare_display_image()
        if action == "accept":
            self._move_file(current, self.accepted_folder)
        elif action == "reject":
            self._move_file(current, self.rejected_folder)
        elif action == "skip":
            pass

        if current in self.files:
            self.files.remove(current)

        self._next_photo()

    def select_photo(self, index: int):
        if not 0 <= index < len(self.files):
            return
        if index == self.index and self.files[index] == self.current_path:
            return
        self._prepare_display_image()
        if self.display_image is not None:
            self.transition_image = self.display_image.copy()
            self.transition_rect = self.display_image.get_rect(
                center=(
                    int(VIEWPORT.centerx + self.pan_x),
                    int(VIEWPORT.centery + self.pan_y),
                )
            )
            self.transition_started = pygame.time.get_ticks()
            self.transition_alpha = 0
        self.index = index
        self.current_path = self.files[index]
        self.gallery_selection_started = pygame.time.get_ticks()
        self.zoom = ZOOM_MIN
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.source_image = None
        self.source_image_path = None
        self.display_image = None
        self.display_image_key = None

    def _next_photo(self):
        if not self.files:
            self.current_path = None
            self.transition_image = None
            self.transition_rect = None
            return

        if self.index >= len(self.files):
            self.index = 0

        next_index = min(self.index, len(self.files) - 1)
        self.select_photo(next_index)

    def run(self):
        pygame.init()
        pygame.display.set_caption("Photo Sorter - Joystick")
        layout_settings = _load_layout_settings()
        desktop_sizes = pygame.display.get_desktop_sizes()
        desktop_size = desktop_sizes[0] if desktop_sizes else (
            pygame.display.Info().current_w,
            pygame.display.Info().current_h,
        )
        self.windowed_size = _fit_window_size(
            self.windowed_size,
            desktop_size,
        )
        screen = pygame.display.set_mode(
            self.windowed_size,
            pygame.RESIZABLE,
        )
        self.windowed_size = screen.get_size()
        self.gallery_ratio = layout_settings["gallery_ratio"]
        self.gallery_visible = layout_settings["gallery_visible"]
        self._apply_layout(screen)
        pygame.joystick.init()

        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            print("Tidak ada joystick terdeteksi. Keyboard aktif: A = diterima, D = ditolak, S = lewati, panah = geser, +/- = zoom, Esc = keluar")
            joystick = None
        else:
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            mappings = _load_joystick_mappings()
            stored_mapping = mappings.get(joystick.get_guid())
            if isinstance(stored_mapping, dict):
                configured_mapping = dict(DEFAULT_JOYSTICK_MAPPING)
                configured_mapping.update(
                    {
                        action: stored_mapping[action]
                        for action, _, _ in JOYSTICK_ACTIONS
                        if action in stored_mapping
                    }
                )
                for action, binding in tuple(configured_mapping.items()):
                    if (
                        isinstance(binding, int)
                        and binding >= joystick.get_numbuttons()
                        and action not in stored_mapping
                    ):
                        configured_mapping[action] = None
                self.joystick_mapping = _validate_joystick_mapping(
                    configured_mapping, joystick
                )
            else:
                configured_mapping = dict(DEFAULT_JOYSTICK_MAPPING)
                for action, binding in tuple(configured_mapping.items()):
                    if (
                        isinstance(binding, int)
                        and binding >= joystick.get_numbuttons()
                    ):
                        configured_mapping[action] = None
                self.joystick_mapping = _validate_joystick_mapping(
                    configured_mapping, joystick
                )
            print(f"Joystick terdeteksi: {joystick.get_name()}")
            print("Input joystick: tombol/trigger/sumbu/D-pad bisa diatur dari menu awal.")

        clock = pygame.time.Clock()
        while self.running:
            delta_time = clock.tick(60) / 1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.windowed_size = (max(640, event.w), max(480, event.h))
                    screen = pygame.display.set_mode(
                        self.windowed_size,
                        pygame.RESIZABLE,
                    )
                    self.windowed_size = screen.get_size()
                    self._apply_layout(screen)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.return_to_menu = True
                        self.running = False
                    elif event.key == pygame.K_F11:
                        if self.is_fullscreen:
                            screen = pygame.display.set_mode(
                                self.windowed_size,
                                pygame.RESIZABLE,
                            )
                            self.is_fullscreen = False
                        else:
                            self.windowed_size = screen.get_size()
                            screen = pygame.display.set_mode(
                                (0, 0),
                                pygame.FULLSCREEN,
                            )
                            self.is_fullscreen = True
                        self._apply_layout(screen)
                    else:
                        self.handle_keyboard_key(event.key)
                elif event.type == pygame.MOUSEWHEEL:
                    mouse_position = pygame.mouse.get_pos()
                    if GALLERY_RECT.collidepoint(mouse_position):
                        list_height = GALLERY_RECT.height - 70
                        visible_rows = max(1, list_height // self.gallery_row_height)
                        max_scroll = max(0, len(self.files) - visible_rows)
                        self.gallery_scroll = max(
                            0,
                            min(max_scroll, self.gallery_scroll - event.y * 3),
                        )
                    elif VIEWPORT.collidepoint(mouse_position):
                        self._change_zoom(event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if MENU_BUTTON_RECT.collidepoint(event.pos):
                        self.return_to_menu = True
                        self.running = False
                    elif GALLERY_TOGGLE_RECT.collidepoint(event.pos):
                        self.gallery_visible = not self.gallery_visible
                        self._apply_layout(screen)
                        self._save_layout(screen)
                    elif self.gallery_visible and LAYOUT_DIVIDER_RECT.collidepoint(event.pos):
                        self.resizing_layout = True
                    elif GALLERY_RECT.collidepoint(event.pos):
                        list_rect = pygame.Rect(
                            GALLERY_RECT.x + 10,
                            GALLERY_RECT.y + 58,
                            GALLERY_RECT.width - 20,
                            GALLERY_RECT.height - 70,
                        )
                        if list_rect.collidepoint(event.pos):
                            row = (
                                event.pos[1] - list_rect.y
                            ) // self.gallery_row_height
                            selected_index = self.gallery_scroll + row
                            self.select_photo(selected_index)
                    elif VIEWPORT.collidepoint(event.pos):
                        self.dragging = True
                        self.last_mouse_pos = event.pos
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self.resizing_layout:
                        self.resizing_layout = False
                        self._save_layout(screen)
                    self.dragging = False
                    self.last_mouse_pos = None
                elif event.type == pygame.MOUSEMOTION:
                    if self.resizing_layout and self.gallery_visible:
                        margin = max(24, min(48, screen.get_width() // 35))
                        gap = max(12, min(24, screen.get_width() // 70))
                        available = screen.get_width() - margin * 2
                        gallery_width = screen.get_width() - margin - event.pos[0] - gap
                        self.gallery_ratio = max(
                            0.18,
                            min(0.48, gallery_width / available),
                        )
                        self._apply_layout(screen)
                    elif self.dragging:
                        if self.last_mouse_pos is not None:
                            dx = event.pos[0] - self.last_mouse_pos[0]
                            dy = event.pos[1] - self.last_mouse_pos[1]
                            self._pan(dx, dy)
                        self.last_mouse_pos = event.pos

            keys = pygame.key.get_pressed()
            if keys[pygame.K_ESCAPE]:
                self.running = False
            pan_x, pan_y = self._keyboard_pan_direction(keys)
            if pan_x or pan_y:
                self._pan(
                    pan_x * PAN_SPEED * delta_time,
                    pan_y * PAN_SPEED * delta_time,
                )
            mapped_pan = False
            if joystick:
                mapped_pan = self._poll_joystick_controls(joystick, delta_time)
            mapped_axis_indices = {
                binding["index"]
                for binding in self.joystick_mapping.values()
                if isinstance(binding, dict) and binding.get("type") == "axis"
            }
            mapped_hat_indices = {
                binding["index"]
                for binding in self.joystick_mapping.values()
                if isinstance(binding, dict) and binding.get("type") == "hat"
            }
            if (
                joystick
                and not mapped_pan
                and joystick.get_numaxes() >= 2
                and not mapped_axis_indices.intersection((0, 1))
            ):
                axis_x = joystick.get_axis(0)
                axis_y = joystick.get_axis(1)
                if abs(axis_x) > 0.18 or abs(axis_y) > 0.18:
                    self._pan(
                        -axis_x * PAN_SPEED * delta_time,
                        -axis_y * PAN_SPEED * delta_time,
                    )
            if (
                joystick
                and not mapped_pan
                and joystick.get_numhats() > 0
                and 0 not in mapped_hat_indices
            ):
                hat_x, hat_y = joystick.get_hat(0)
                if hat_x or hat_y:
                    self._pan(
                        -hat_x * PAN_SPEED * delta_time,
                        hat_y * PAN_SPEED * delta_time,
                    )

            self._render_current(screen)
            pygame.display.flip()

        pygame.quit()
        if not self.is_fullscreen:
            self._save_layout(screen)
        print("Aplikasi ditutup.")
        return self.return_to_menu


def main():
    root = tk.Tk()
    root.title("Photo Sorter")
    root.resizable(False, False)
    root.geometry("620x440")

    source_folder = tk.StringVar(
        value=str(Path(sys.argv[1]).resolve()) if len(sys.argv) > 1 else ""
    )
    selected_theme = tk.StringVar(value=_load_theme())
    theme_choice = tk.StringVar(
        value="Gelap" if selected_theme.get() == "dark" else "Terang"
    )
    style = ttk.Style(root)
    style.theme_use("clam")

    def apply_palette(palette):
        colors = {key: _tk_color(value) for key, value in palette.items()}
        root.configure(background=colors["background"])
        style.configure(
            "App.TFrame",
            background=colors["background"],
        )
        style.configure(
            "Card.TFrame",
            background=colors["panel"],
            bordercolor=colors["border"],
            borderwidth=2,
            relief="ridge",
        )
        style.configure(
            "App.TLabel",
            background=colors["background"],
            foreground=colors["text"],
            font=("Segoe Print", 10),
        )
        style.configure(
            "Card.TLabel",
            background=colors["panel"],
            foreground=colors["text"],
            font=("Segoe Print", 10),
        )
        style.configure(
            "Title.TLabel",
            background=colors["background"],
            foreground=colors["text"],
            font=("Segoe Print", 23, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=colors["background"],
            foreground=colors["muted"],
            font=("Segoe Print", 10),
        )
        style.configure(
            "CardTitle.TLabel",
            background=colors["panel"],
            foreground=colors["text"],
            font=("Segoe Print", 11, "bold"),
        )
        style.configure(
            "TButton",
            background=colors["panel"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            borderwidth=2,
            relief="ridge",
            padding=(12, 8),
            font=("Segoe Print", 10),
        )
        style.map(
            "TButton",
            background=[("active", colors["shadow"])],
            foreground=[("disabled", colors["muted"])],
            relief=[("pressed", "sunken")],
        )
        style.configure(
            "Primary.TButton",
            background=colors["accent"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            borderwidth=2,
            relief="ridge",
            padding=(18, 9),
            font=("Segoe Print", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", colors["accent"]), ("disabled", colors["border"])],
            relief=[("pressed", "sunken")],
        )
        style.configure(
            "TEntry",
            fieldbackground=colors["panel"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            borderwidth=2,
            relief="ridge",
            padding=8,
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["panel"],
            foreground=colors["text"],
            background=colors["panel"],
            arrowcolor=colors["text"],
            bordercolor=colors["border"],
            padding=6,
            relief="ridge",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["panel"])],
            foreground=[("readonly", colors["text"])],
        )
    current_palette = dict(THEME_PALETTES[selected_theme.get()])
    apply_palette(current_palette)

    root.columnconfigure(0, weight=1)

    header = ttk.Frame(root, style="App.TFrame", padding=(30, 22, 30, 16))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="Photo Sorter", style="Title.TLabel").grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        header,
        text="Pilih foto terbaik, satu jepretan pada satu waktu.",
        style="Subtitle.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(3, 0))
    ttk.Label(header, text="Tema", style="Subtitle.TLabel").grid(
        row=0, column=1, sticky="e", padx=(16, 8)
    )
    theme_selector = ttk.Combobox(
        header,
        textvariable=theme_choice,
        values=("Gelap", "Terang"),
        state="readonly",
        width=9,
    )
    theme_selector.grid(row=0, column=2, sticky="e")

    theme_animation = {"after_id": None}

    def on_theme_changed(_event=None):
        theme = "dark" if theme_choice.get() == "Gelap" else "light"
        selected_theme.set(theme)
        if theme_animation["after_id"] is not None:
            root.after_cancel(theme_animation["after_id"])
            theme_animation["after_id"] = None

        try:
            _save_theme(theme)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Gagal menyimpan tema",
                f"Tampilan tema berubah, tetapi pengaturan tidak dapat disimpan:\n{exc}",
                parent=root,
            )

        start_palette = dict(current_palette)
        target_palette = THEME_PALETTES[theme]
        frame_count = 18
        frame_duration_ms = 16
        theme_selector.configure(state="disabled")

        def animate(frame=0):
            progress = min(1.0, frame / frame_count)
            eased_progress = progress * progress * (3 - 2 * progress)
            blended_palette = {
                key: _blend_color(
                    start_palette[key],
                    target_palette[key],
                    eased_progress,
                )
                for key in target_palette
            }
            apply_palette(blended_palette)
            current_palette.update(blended_palette)

            if frame < frame_count:
                theme_animation["after_id"] = root.after(
                    frame_duration_ms,
                    lambda: animate(frame + 1),
                )
                return

            theme_animation["after_id"] = None
            theme_selector.configure(state="readonly")

        animate()

    theme_selector.bind("<<ComboboxSelected>>", on_theme_changed)

    card = ttk.Frame(root, style="Card.TFrame", padding=20)
    card.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 12))
    card.columnconfigure(0, weight=1)
    ttk.Label(card, text="Folder foto", style="CardTitle.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    ttk.Label(
        card,
        text="Foto yang dipilih akan dipindahkan ke folder Diterima atau Ditolak.",
        style="Card.TLabel",
        wraplength=500,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
    folder_entry = ttk.Entry(
        card,
        textvariable=source_folder,
        state="readonly",
    )
    folder_entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))

    def choose_folder():
        selected = filedialog.askdirectory(
            parent=root,
            title="Pilih folder foto untuk disortir",
            initialdir=source_folder.get() or str(Path.home()),
        )
        if selected:
            source_folder.set(selected)
            start_button.state(["!disabled"])
            folder_entry.xview_moveto(1)

    def start_sorting():
        folder = source_folder.get()
        if not folder:
            return
        theme = selected_theme.get()
        if theme_animation["after_id"] is not None:
            root.after_cancel(theme_animation["after_id"])
            theme_animation["after_id"] = None
            current_palette.update(THEME_PALETTES[theme])
            apply_palette(current_palette)
        root.withdraw()
        try:
            return_to_menu = PhotoSorter(folder, theme=theme).run()
            if return_to_menu:
                root.deiconify()
                root.lift()
            else:
                root.destroy()
        except Exception as exc:
            root.deiconify()
            root.lift()
            messagebox.showerror("Photo Sorter - Error", str(exc), parent=root)

    ttk.Button(card, text="Pilih folder...", command=choose_folder).grid(
        row=2, column=1, sticky="e"
    )

    controls = ttk.Frame(root, style="App.TFrame", padding=(30, 2, 30, 6))
    controls.grid(row=2, column=0, sticky="ew")
    controls.columnconfigure(0, weight=1)
    ttk.Label(
        controls,
        text="Kontrol",
        style="Subtitle.TLabel",
    ).grid(row=0, column=0, sticky="w", pady=(0, 8))
    button_frame = ttk.Frame(controls, style="App.TFrame")
    button_frame.grid(row=1, column=0, sticky="w")
    ttk.Button(
        button_frame,
        text="Atur keyboard",
        command=lambda: configure_keyboard(root),
    ).pack(side="left", padx=(0, 8))
    ttk.Button(
        button_frame,
        text="Atur joystick",
        command=lambda: configure_joystick(root),
    ).pack(side="left")
    start_button = ttk.Button(
        controls,
        text="Mulai sortir",
        style="Primary.TButton",
        command=start_sorting,
    )
    start_button.grid(row=1, column=1, sticky="e")
    update_results = queue.Queue()
    update_status = tk.StringVar(value=f"Versi {APP_VERSION_LABEL}")

    def finish_update_check():
        try:
            result_type, result = update_results.get_nowait()
        except queue.Empty:
            root.after(100, finish_update_check)
            return

        update_button.configure(state="normal")
        if result_type == "error":
            update_status.set("Pemeriksaan update gagal.")
            messagebox.showerror(
                "Gagal memeriksa update",
                f"Periksa koneksi internet dan coba lagi.\n\n{result}",
                parent=root,
            )
            return
        if result is None:
            update_status.set("Versi terbaru sudah terpasang.")
            messagebox.showinfo(
                "Photo Sorter",
                "Aplikasi Anda sudah menggunakan versi terbaru.",
                parent=root,
            )
            return

        version = result["version"].removeprefix("v")
        update_status.set(f"Update tersedia: {version}")
        if messagebox.askyesno(
            "Update tersedia",
            f"Photo Sorter versi {version} tersedia.\n"
            "Buka halaman GitHub Releases untuk mengunduhnya?",
            parent=root,
        ):
            if not webbrowser.open(result["url"], new=2):
                messagebox.showerror(
                    "Tidak dapat membuka browser",
                    "Buka halaman ini secara manual:\n" + result["url"],
                    parent=root,
                )

    def check_for_updates():
        update_button.configure(state="disabled")
        update_status.set("Sedang memeriksa update...")

        def check_in_background():
            try:
                release = _check_for_update()
            except (
                http.client.HTTPException,
                urllib.error.URLError,
                TimeoutError,
                OSError,
                ValueError,
                TypeError,
            ) as exc:
                update_results.put(("error", str(exc)))
            else:
                update_results.put(("success", release))

        threading.Thread(
            target=check_in_background,
            name="PhotoSorterUpdateCheck",
            daemon=True,
        ).start()
        root.after(100, finish_update_check)

    footer = ttk.Frame(root, style="App.TFrame", padding=(30, 6, 30, 14))
    footer.grid(row=3, column=0, sticky="ew")
    footer.columnconfigure(0, weight=1)
    ttk.Label(
        footer,
        textvariable=update_status,
        style="Subtitle.TLabel",
    ).grid(row=0, column=0, sticky="w")
    ttk.Button(
        footer,
        text="Cek update",
        command=check_for_updates,
    ).grid(row=0, column=1, sticky="e")
    if not source_folder.get():
        start_button.state(["disabled"])

    try:
        root.mainloop()
    except Exception as exc:
        messagebox.showerror("Photo Sorter - Error", str(exc), parent=root)


if __name__ == "__main__":
    main()
