"""Material/Android-inspired Tkinter theme helpers with light/dark modes."""

from __future__ import annotations

from tkinter import Tk, Toplevel
from tkinter import ttk

LIGHT_COLORS = {
    "primary": "#6750A4",
    "primary_dark": "#4F378B",
    "primary_container": "#EADDFF",
    "on_primary": "#FFFFFF",
    "secondary": "#625B71",
    "surface": "#FFFFFF",
    "surface_variant": "#F4EFFA",
    "app_bg": "#F8F7FC",
    "outline": "#CAC4D0",
    "outline_variant": "#E7E0EC",
    "text": "#1D1B20",
    "muted": "#49454F",
    "success": "#146C2E",
    "warning": "#B3261E",
    "table_alt": "#FCF8FF",
    "table_heading": "#F1EBF8",
    "entry_bg": "#FFFFFF",
    "canvas_bg": "#111318",
    "canvas_grid": "#2B2D33",
    "canvas_text": "#F4EFF4",
}

DARK_COLORS = {
    "primary": "#D0BCFF",
    "primary_dark": "#B69DF8",
    "primary_container": "#4F378B",
    "on_primary": "#381E72",
    "secondary": "#CCC2DC",
    "surface": "#1D1B20",
    "surface_variant": "#2B2930",
    "app_bg": "#141218",
    "outline": "#938F99",
    "outline_variant": "#49454F",
    "text": "#E6E1E5",
    "muted": "#CAC4D0",
    "success": "#78DC91",
    "warning": "#FFB4AB",
    "table_alt": "#211F26",
    "table_heading": "#302D36",
    "entry_bg": "#211F26",
    "canvas_bg": "#0E1116",
    "canvas_grid": "#28303A",
    "canvas_text": "#E6E1E5",
}

# Mutable palette used by modules that import MATERIAL_COLORS once.  Do not
# reassign; update it in-place so existing imports see theme changes.
MATERIAL_COLORS = LIGHT_COLORS.copy()


def install_material_theme(root: Tk | Toplevel, dark: bool = False) -> None:
    """Install a Material-style ttk theme on a Tk root/window."""

    MATERIAL_COLORS.clear()
    MATERIAL_COLORS.update(DARK_COLORS if dark else LIGHT_COLORS)

    try:
        root.configure(bg=MATERIAL_COLORS["app_bg"])
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    font_family = "Segoe UI"
    mono_family = "Cascadia Mono"
    c = MATERIAL_COLORS

    style.configure(".", font=(font_family, 10), background=c["app_bg"], foreground=c["text"])

    # Frames / cards / app bars
    style.configure("App.TFrame", background=c["app_bg"])
    style.configure("AppBar.TFrame", background=c["primary"], borderwidth=0)
    style.configure("Card.TFrame", background=c["surface"], relief="flat", borderwidth=0)
    style.configure("Toolbar.TFrame", background=c["surface_variant"], relief="flat", borderwidth=0)

    # Labels
    style.configure("TLabel", background=c["surface"], foreground=c["text"])
    style.configure("Muted.TLabel", background=c["surface"], foreground=c["muted"])
    style.configure("CardTitle.TLabel", background=c["surface"], foreground=c["text"], font=(font_family, 12, "bold"))
    style.configure("CardSubtitle.TLabel", background=c["surface"], foreground=c["muted"], font=(font_family, 9))
    style.configure("AppBarTitle.TLabel", background=c["primary"], foreground=c["on_primary"], font=(font_family, 18, "bold"))
    style.configure("AppBarSubtitle.TLabel", background=c["primary"], foreground=c["on_primary"], font=(font_family, 10))
    style.configure("Status.TLabel", background=c["surface_variant"], foreground=c["muted"], padding=(12, 7))
    style.configure("ViewerHelp.TLabel", background=c["surface_variant"], foreground=c["muted"])
    style.configure("Mono.TLabel", background=c["surface"], foreground=c["muted"], font=(mono_family, 9))

    # Entries / comboboxes
    style.configure("TEntry", fieldbackground=c["entry_bg"], foreground=c["text"], bordercolor=c["outline"], lightcolor=c["outline"], darkcolor=c["outline"], insertcolor=c["text"], padding=(8, 7), relief="flat")
    style.map("TEntry", bordercolor=[("focus", c["primary"])], fieldbackground=[("disabled", c["surface_variant"])])
    style.configure("TCombobox", fieldbackground=c["entry_bg"], background=c["entry_bg"], foreground=c["text"], arrowcolor=c["primary"], bordercolor=c["outline"], padding=(8, 6), relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", c["entry_bg"]), ("focus", c["entry_bg"])], foreground=[("readonly", c["text"])], bordercolor=[("focus", c["primary"])])

    # Buttons
    style.configure("TButton", background=c["surface_variant"], foreground=c["text"], padding=(14, 8), borderwidth=0, relief="flat")
    style.map("TButton", background=[("active", c["outline_variant"]), ("disabled", c["outline_variant"])], foreground=[("disabled", c["muted"])])
    style.configure("Primary.TButton", background=c["primary"], foreground=c["on_primary"], padding=(18, 9), borderwidth=0, relief="flat", font=(font_family, 10, "bold"))
    style.map("Primary.TButton", background=[("active", c["primary_dark"]), ("disabled", c["outline_variant"])], foreground=[("disabled", c["muted"])])
    style.configure("Text.TButton", background=c["surface"], foreground=c["primary"], padding=(12, 7), borderwidth=0, relief="flat")
    style.map("Text.TButton", background=[("active", c["surface_variant"])])
    style.configure("Danger.TButton", background=c["warning"], foreground=c["on_primary"], padding=(18, 9), borderwidth=0, relief="flat", font=(font_family, 10, "bold"))
    style.map("Danger.TButton", background=[("active", c["warning"]), ("disabled", c["outline_variant"])], foreground=[("disabled", c["muted"])])

    # Checkbuttons / progress
    style.configure("TCheckbutton", background=c["surface"], foreground=c["text"], padding=(4, 4))
    style.map("TCheckbutton", background=[("active", c["surface"]), ("selected", c["surface"])], foreground=[("disabled", c["muted"])])
    style.configure("Horizontal.TProgressbar", background=c["primary"], troughcolor=c["surface_variant"], bordercolor=c["surface_variant"], lightcolor=c["primary"], darkcolor=c["primary"])

    # Paned windows / notebooks
    style.configure("TPanedwindow", background=c["app_bg"], borderwidth=0)
    style.configure("TNotebook", background=c["surface"], borderwidth=0, tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", background=c["surface"], foreground=c["muted"], padding=(16, 9), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", c["primary_container"]), ("active", c["surface_variant"])], foreground=[("selected", c["primary"]), ("active", c["primary"])])

    # Modern table styling
    style.configure("Modern.Treeview", background=c["surface"], fieldbackground=c["surface"], foreground=c["text"], rowheight=28, borderwidth=0, relief="flat")
    style.configure("Modern.Treeview.Heading", background=c["table_heading"], foreground=c["text"], font=(font_family, 9, "bold"), padding=(8, 7), relief="flat")
    style.map("Modern.Treeview", background=[("selected", c["primary_container"])], foreground=[("selected", c["text"])])


def tag_tree_rows(tree: ttk.Treeview, dark: bool | None = None) -> None:
    """Apply Material-like alternating-row colors to a treeview."""

    c = MATERIAL_COLORS
    try:
        tree.tag_configure("odd", background=c["surface"], foreground=c["text"])
        tree.tag_configure("even", background=c["table_alt"], foreground=c["text"])
        tree.tag_configure("critical", foreground=c["warning"])
    except Exception:
        pass
