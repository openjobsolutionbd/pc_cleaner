"""
pc_cleaner.py
-------------------
Main GUI application. Six tabs:
  0. Quick Clean         - one-button shortcut that cleans only the
                           "safe"-badge categories, for everyday use
  1. Junk Cleanup      - temp/cache/update-leftover files + Recycle Bin
  2. Browser & Network  - browsing history (never cookies) + DNS flush
  3. System Tools       - disk space analyzer, empty folder finder, icon cache reset
  4. Startup Manager    - enable/disable auto-start programs (reversibly)
  5. Automation & History - scheduled auto-clean + log of past runs

Run with a GUI:      python pc_cleaner.py
Run headless (used by the scheduled task): python pc_cleaner.py --auto-clean
"""

import os
import sys
import threading
import queue
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

import cleaner_core
import browser_core
import system_tools
import startup_manager
import scheduler
import history_log
import shutdown_setup
import error_log


__version__ = "1.2.0"


# ----------------------------------------------------------------------
# Visual theme — one place to tweak colors/fonts for the whole app.
# ----------------------------------------------------------------------
class Theme:
    # Neutral surfaces — a touch cooler and softer than plain gray/white,
    # closer to the slate palette used in most modern app UIs.
    BG = "#eef1f8"
    SURFACE = "#ffffff"
    SURFACE_ALT = "#f6f7fb"
    BORDER = "#e2e5ee"
    SHADOW = "#d7dbe8"
    TEXT = "#1a1d29"
    TEXT_MUTED = "#6b7086"

    # Indigo/violet accent instead of plain blue — reads as more current.
    PRIMARY = "#5b5bf0"
    PRIMARY_DARK = "#4646d1"
    PRIMARY_SOFT = "#eeeefe"
    PRIMARY_TEXT = "#ffffff"

    SUCCESS = "#15915a"
    SUCCESS_SOFT = "#e5f7ee"
    WARNING = "#b35c00"
    WARNING_BG = "#fff4e5"
    DANGER = "#e0464f"
    DANGER_SOFT = "#fdeced"

    FONT_FAMILY = "Segoe UI"
    FONT_BASE = (FONT_FAMILY, 10)
    FONT_MUTED = (FONT_FAMILY, 9)
    FONT_SECTION = (FONT_FAMILY, 12, "bold")
    FONT_TOTAL = (FONT_FAMILY, 11, "bold")
    FONT_TAB = (FONT_FAMILY, 10)
    FONT_MONO = ("Consolas", 9)


def apply_theme(root):
    """Configure ttk styles once, at startup. Widgets below just reference
    these style names (or pick up the defaults automatically)."""
    root.configure(bg=Theme.BG)

    style = ttk.Style(root)
    # "vista" is Windows' native ttk theme, but it renders buttons with the
    # OS's own drawing code and ignores our custom background color (only
    # the text color partially applies). That's what made "Accent.TButton"
    # buttons like "Clean Now" show up as near-invisible white-on-white/gray
    # text. "clam" is drawn entirely by Tk itself, so it honors the
    # background/foreground colors set below and keeps buttons legible.
    for candidate in ("clam", "vista"):
        try:
            style.theme_use(candidate)
            break
        except tk.TclError:
            continue
    else:
        # Neither clam nor vista is available on this Tk build (unusual, but
        # possible on some Windows/Python combos). Fall back to whatever
        # theme actually exists rather than leaving the raw unstyled
        # default active, which is what produced the "classic Windows"
        # look this fix addresses.
        available = style.theme_names()
        if available:
            style.theme_use(available[0])

    style.configure(".", font=Theme.FONT_BASE, background=Theme.BG, foreground=Theme.TEXT)
    style.configure("TFrame", background=Theme.BG)
    style.configure("TLabel", background=Theme.BG, foreground=Theme.TEXT, font=Theme.FONT_BASE)
    style.configure("Muted.TLabel", background=Theme.BG, foreground=Theme.TEXT_MUTED, font=Theme.FONT_MUTED)
    style.configure("Section.TLabel", background=Theme.BG, foreground=Theme.TEXT, font=Theme.FONT_SECTION)
    style.configure("Total.TLabel", background=Theme.BG, foreground=Theme.PRIMARY_DARK, font=Theme.FONT_TOTAL)
    style.configure("Warning.TLabel", background=Theme.WARNING_BG, foreground=Theme.WARNING, font=Theme.FONT_BASE)
    style.configure("Warning.TFrame", background=Theme.WARNING_BG)

    style.configure("TCheckbutton", background=Theme.BG, font=Theme.FONT_BASE)
    style.map("TCheckbutton", background=[("active", Theme.BG)])

    style.configure("TSeparator", background=Theme.BORDER)

    # Tabs styled as a flat segmented control: unselected tabs sit flush
    # with the page background so only the active one reads as "raised"
    # (via the surface-white fill + bold accent-colored label).
    style.configure("TNotebook", background=Theme.BG, borderwidth=0, tabmargins=(0, 6, 0, 0))
    style.configure(
        "TNotebook.Tab",
        font=Theme.FONT_TAB,
        padding=(18, 10),
        background=Theme.BG,
        foreground=Theme.TEXT_MUTED,
        borderwidth=0,
        focuscolor=Theme.BG,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", Theme.SURFACE)],
        foreground=[("selected", Theme.PRIMARY_DARK), ("!selected", Theme.TEXT_MUTED)],
        font=[("selected", (Theme.FONT_FAMILY, 10, "bold"))],
        expand=[("selected", (0, 0, 0, 0))],
    )

    style.configure("TButton", font=Theme.FONT_BASE, padding=(13, 7), borderwidth=0, focuscolor=Theme.BG)
    style.map(
        "TButton",
        background=[("active", Theme.SURFACE_ALT), ("!disabled", Theme.SURFACE)],
        foreground=[("!disabled", Theme.TEXT)],
        bordercolor=[("!disabled", Theme.BORDER)],
        relief=[("!disabled", "flat")],
    )
    style.configure(
        "Accent.TButton",
        font=(Theme.FONT_FAMILY, 10, "bold"),
        padding=(16, 9),
        foreground=Theme.PRIMARY_TEXT,
        background=Theme.PRIMARY,
        borderwidth=0,
        focuscolor=Theme.PRIMARY,
    )
    style.map(
        "Accent.TButton",
        background=[("active", Theme.PRIMARY_DARK), ("disabled", Theme.BORDER)],
        foreground=[("disabled", Theme.TEXT_MUTED)],
    )
    style.configure(
        "Danger.TButton",
        font=Theme.FONT_BASE,
        padding=(13, 7),
        foreground=Theme.DANGER,
        borderwidth=0,
        focuscolor=Theme.BG,
    )
    style.map("Danger.TButton", background=[("active", Theme.DANGER_SOFT), ("!disabled", Theme.SURFACE)])

    style.configure(
        "Treeview",
        background=Theme.SURFACE,
        fieldbackground=Theme.SURFACE,
        foreground=Theme.TEXT,
        rowheight=28,
        font=Theme.FONT_BASE,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        font=(Theme.FONT_FAMILY, 9, "bold"),
        background=Theme.SURFACE_ALT,
        foreground=Theme.TEXT_MUTED,
        relief="flat",
        padding=(8, 8),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", Theme.SURFACE_ALT)],
    )
    style.map("Treeview", background=[("selected", Theme.PRIMARY)], foreground=[("selected", Theme.PRIMARY_TEXT)])

    style.configure("Card.TFrame", background=Theme.SURFACE)

    return style


def build_full_categories():
    """Junk categories plus the Recycle Bin, which isn't a plain folder
    (it needs the Shell API), so it's added as a special-cased entry.
    """
    cats = cleaner_core.build_categories()
    cats.append({
        "id": "recycle_bin",
        "name": "Recycle Bin",
        "desc": "Files you've already deleted, sitting in the bin.",
        "paths": [],
        "needs_admin": False,
        "default_checked": True,
        "badge": "safe",
        "special": "recycle_bin",
    })
    return cats


class LogBox:
    """A small read-only scrolling text area for status messages."""

    def __init__(self, parent, height=6):
        self.frame = ttk.Frame(parent, style="Card.TFrame")
        self.text = tk.Text(
            self.frame,
            height=height,
            state="disabled",
            wrap="word",
            font=Theme.FONT_MONO,
            bg=Theme.SURFACE,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            highlightcolor=Theme.BORDER,
            padx=8,
            pady=6,
        )
        scrollbar = ttk.Scrollbar(self.frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def log(self, msg):
        self.text.configure(state="normal")
        self.text.insert("end", str(msg) + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def pack(self, **kw):
        self.frame.pack(**kw)


class ScrollableFrame(ttk.Frame):
    """A vertically scrollable container. Put widgets in .inner."""

    def __init__(self, parent, height=260):
        super().__init__(parent)
        canvas = tk.Canvas(self, height=height, highlightthickness=0, bg=Theme.BG)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


class CleanerApp:
    def __init__(self, root):
        self.root = root
        root.title(f"PC Cleaner v{__version__}")
        root.geometry("900x720")
        root.minsize(760, 580)
        apply_theme(root)

        # --- Safety net: part 1 of 2 ------------------------------------
        # Tkinter calls this automatically whenever an exception escapes
        # a widget callback (button click, timer, etc.) instead of that
        # exception propagating up and killing the whole app. Every
        # button in this app is protected by this from the moment the
        # window exists — see _handle_gui_exception below. (Part 2 is
        # _run_safely(), used for background-thread workers, since
        # exceptions in a thread never reach report_callback_exception.)
        self.root.report_callback_exception = self._handle_gui_exception

        self.categories = build_full_categories()
        self.category_vars = {}
        self.category_size_labels = {}
        self.category_sizes = {}
        self._free_before = None

        # Background threads never touch Tk widgets directly (Tkinter is
        # not thread-safe). Instead they push (function, args) onto this
        # queue, and the main thread drains it on a timer. This is the
        # standard safe pattern — calling root.after() *from* a worker
        # thread is not reliable.
        self.ui_queue = queue.Queue()
        self._poll_after_id = self.root.after(50, self._poll_queue)

        self._build_ui()
        self.refresh_startup_items()
        self._refresh_schedule_status()
        self._refresh_history_view()

    def _handle_gui_exception(self, exc_type, exc_value, exc_tb):
        """Installed as Tkinter's report_callback_exception hook (see
        __init__). Tkinter calls this automatically whenever an
        exception escapes a widget callback instead of letting it
        crash the whole app. We log full details to error_log.py and
        show a small, calm notice — the window stays open and
        everything else keeps working.

        This is deliberately the ONLY place a bug in a button click can
        end up: no exception from a callback can skip this handler, so
        "the app just disappeared" should no longer happen from here.
        """
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            error_log.record("gui_callback", exc_value, tb_str)
        except Exception:
            pass
        try:
            self._refresh_error_indicator()
        except Exception:
            pass
        messagebox.showwarning(
            "ছোট একটা সমস্যা হয়েছে",
            "একটা অপ্রত্যাশিত সমস্যা হয়েছিল, কিন্তু অ্যাপ চলছে এবং কোনো ফাইল মোছা হয়নি।\n\n"
            "বিস্তারিত Automation ট্যাবের 'Error Log দেখুন' বাটনে সংরক্ষিত আছে — "
            "সেটা Claude-কে দেখালে দ্রুত ফিক্স করা যাবে।"
        )

    def _run_safely(self, fn, *args, **kwargs):
        """Safety net part 2 of 2 — wraps every background-thread worker
        (see threading.Thread(target=self._run_safely, args=(self.X_worker, ...))
        calls throughout this file). report_callback_exception (above)
        only catches exceptions in the main GUI thread; a bug inside a
        worker thread would otherwise just kill that thread silently —
        no crash, no message, the button simply never finishes and
        nothing tells you why. This makes that impossible: any
        exception is caught, logged to error_log.py with the worker's
        name attached, and reported through the same UI queue every
        worker already uses to talk to the main thread.
        """
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            worker_name = getattr(fn, "__name__", str(fn))
            try:
                error_log.record(worker_name, exc)
            except Exception:
                pass
            self._ui(self._refresh_error_indicator)
            self._ui(lambda: messagebox.showwarning(
                "ছোট একটা সমস্যা হয়েছে",
                "একটা কাজ চলার সময় অপ্রত্যাশিত সমস্যা হয়েছিল এবং সেটা থেমে গেছে, "
                "কিন্তু বাকি অ্যাপ ঠিকঠাক চলছে।\n\n"
                "বিস্তারিত Automation ট্যাবের 'Error Log দেখুন' বাটনে সংরক্ষিত আছে।"
            ))

    def _ui(self, func, *args):
        """Call from any thread to safely run func(*args) on the main thread."""
        self.ui_queue.put((func, args))

    def _poll_queue(self):
        try:
            while True:
                func, args = self.ui_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        self._poll_after_id = self.root.after(50, self._poll_queue)

    def shutdown(self):
        """Stops the queue-polling timer. Call before destroying the root
        (the app itself does this automatically on window close)."""
        if self._poll_after_id is not None:
            try:
                self.root.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None

    # ------------------------------------------------------------------
    # Overall layout
    # ------------------------------------------------------------------
    def _build_ui(self):
        header = tk.Frame(self.root, bg=Theme.BG)
        header.pack(fill="x", padx=16, pady=(14, 8))

        icon_badge = tk.Frame(header, bg=Theme.PRIMARY, width=38, height=38)
        icon_badge.pack(side="left", padx=(0, 10))
        icon_badge.pack_propagate(False)
        tk.Label(icon_badge, text="\u2728", bg=Theme.PRIMARY, fg=Theme.PRIMARY_TEXT, font=(Theme.FONT_FAMILY, 15)).pack(
            expand=True
        )

        title_frame = tk.Frame(header, bg=Theme.BG)
        title_frame.pack(side="left")
        tk.Label(title_frame, text="PC Cleaner", bg=Theme.BG, fg=Theme.TEXT, font=(Theme.FONT_FAMILY, 15, "bold")).pack(anchor="w")
        tk.Label(title_frame, text=f"Free up space and keep your PC tidy  ·  v{__version__}", bg=Theme.BG, fg=Theme.TEXT_MUTED, font=Theme.FONT_MUTED).pack(anchor="w")

        drive_pill = tk.Frame(header, bg=Theme.SUCCESS_SOFT)
        drive_pill.pack(side="right", anchor="e")
        self.header_drive_label = tk.Label(
            drive_pill, text="", bg=Theme.SUCCESS_SOFT, fg=Theme.SUCCESS, font=(Theme.FONT_FAMILY, 10, "bold"),
            padx=12, pady=6,
        )
        self.header_drive_label.pack()
        self._refresh_header_drive_label()

        ttk.Separator(self.root).pack(fill="x", padx=0, pady=(0, 2))

        notebook = ttk.Notebook(self.root)
        self.tab_quick = ttk.Frame(notebook)
        self.tab_junk = ttk.Frame(notebook)
        self.tab_browser = ttk.Frame(notebook)
        self.tab_tools = ttk.Frame(notebook)
        self.tab_startup = ttk.Frame(notebook)
        self.tab_auto = ttk.Frame(notebook)

        notebook.add(self.tab_quick, text="Quick Clean")
        notebook.add(self.tab_junk, text="Junk Cleanup")
        notebook.add(self.tab_browser, text="Browser && Network")
        notebook.add(self.tab_tools, text="System Tools")
        notebook.add(self.tab_startup, text="Startup Manager")
        notebook.add(self.tab_auto, text="Automation && History")
        notebook.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self._build_quick_tab()
        self._build_junk_tab()
        self._build_browser_tab()
        self._build_tools_tab()
        self._build_startup_tab()
        self._build_auto_tab()

    def _refresh_header_drive_label(self):
        system_drive = os.environ.get("SystemDrive", "C:") + "\\"
        usage = system_tools.get_free_space(system_drive)
        if usage:
            total, used, free = usage
            self.header_drive_label.config(text=f"{system_drive}  {cleaner_core.format_size(free)} free of {cleaner_core.format_size(total)}")

    # ------------------------------------------------------------------
    # Tab 1: Junk Cleanup
    # ------------------------------------------------------------------
    def _build_quick_tab(self):
        frame = self.tab_quick

        wrapper = tk.Frame(frame, bg=Theme.BG)
        wrapper.pack(fill="both", expand=True, padx=14, pady=14)

        card = tk.Frame(wrapper, bg=Theme.SURFACE, highlightbackground=Theme.SHADOW, highlightthickness=1)
        card.pack(fill="x", pady=(20, 12))
        tk.Frame(card, bg=Theme.PRIMARY, height=4).pack(fill="x")

        inner = tk.Frame(card, bg=Theme.SURFACE)
        inner.pack(fill="x", padx=32, pady=28)

        icon_circle = tk.Frame(inner, bg=Theme.PRIMARY_SOFT, width=44, height=44)
        icon_circle.pack(anchor="w", pady=(0, 12))
        icon_circle.pack_propagate(False)
        tk.Label(icon_circle, text="\U0001F9F9", bg=Theme.PRIMARY_SOFT, font=(Theme.FONT_FAMILY, 18)).pack(expand=True)

        tk.Label(
            inner, text="Everyday Cleanup", bg=Theme.SURFACE, fg=Theme.TEXT,
            font=(Theme.FONT_FAMILY, 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            inner,
            text="Only safe junk files (Temp, Cache, Recycle Bin, etc.) will be cleaned.\n"
                 "Documents, photos, and programs are never touched.",
            bg=Theme.SURFACE, fg=Theme.TEXT_MUTED, font=Theme.FONT_BASE,
            justify="left", wraplength=560,
        ).pack(anchor="w", pady=(6, 20))

        self.quick_clean_btn = ttk.Button(
            inner, text="Clean Now", style="Accent.TButton", command=self.quick_clean,
        )
        self.quick_clean_btn.pack(anchor="w", ipadx=20, ipady=10)

        self.quick_last_cleaned_label = tk.Label(
            inner, text="", bg=Theme.SURFACE, fg=Theme.TEXT_MUTED, font=Theme.FONT_MUTED,
        )
        self.quick_last_cleaned_label.pack(anchor="w", pady=(14, 0))

        self.quick_status_label = tk.Label(
            wrapper, text="", bg=Theme.BG, fg=Theme.SUCCESS,
            font=(Theme.FONT_FAMILY, 11, "bold"), justify="left", wraplength=560,
        )
        self.quick_status_label.pack(anchor="w", pady=(4, 0))

        self._refresh_quick_last_cleaned()

    def _refresh_quick_last_cleaned(self):
        history = history_log.read_history()
        if not history:
            self.quick_last_cleaned_label.config(text="No cleanup has been run yet.")
            return
        last = history[-1]
        when = last.get("timestamp", "")
        freed = cleaner_core.format_size(last.get("bytes_freed", 0))
        self.quick_last_cleaned_label.config(text=f"Last cleaned: {when}  ·  {freed} freed")

    def quick_clean(self):
        if not messagebox.askyesno(
            "Confirm",
            "Clean safe junk files (Temp, Cache, Recycle Bin, etc.)?\n\n"
            "Documents, photos, and programs will not be touched.",
        ):
            return
        self.quick_clean_btn.config(state="disabled")
        self.quick_status_label.config(text="Cleaning…", fg=Theme.TEXT_MUTED)
        threading.Thread(target=self._run_safely, args=(self._quick_clean_worker,), daemon=True).start()

    def _quick_clean_worker(self):
        # Only the everyday-safe categories — same list the Junk Cleanup
        # tab shows with a green "Safe — daily cleanup" badge. Anything
        # marked "caution" (Windows Update Old Files, Crash Dumps,
        # Prefetch) is intentionally never touched here; those still
        # require a deliberate visit to the Junk Cleanup tab.
        safe_categories = [c for c in self.categories if c.get("badge") == "safe"]

        total_freed = 0
        cleaned_ids = []
        skipped_admin = []

        for cat in safe_categories:
            if cat.get("needs_admin") and not cleaner_core.is_admin():
                skipped_admin.append(cat["name"])
                continue

            if cat.get("special") == "recycle_bin":
                freed = cleaner_core.get_recycle_bin_size()
                if cleaner_core.empty_recycle_bin():
                    total_freed += freed
                    cleaned_ids.append(cat["id"])
                continue

            cat_freed = 0
            file_filter = cat.get("file_filter")
            for p in cat["paths"]:
                summary = cleaner_core.delete_dir_contents(p, log=None, file_filter=file_filter)
                cat_freed += summary["deleted_bytes"]
            total_freed += cat_freed
            cleaned_ids.append(cat["id"])

        self._ui(self._quick_clean_done, total_freed, cleaned_ids, skipped_admin)


    def _quick_clean_done(self, total_freed, cleaned_ids, skipped_admin):
        self.quick_clean_btn.config(state="normal")

        logged = history_log.log_cleanup({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "categories": cleaned_ids,
            "bytes_freed": total_freed,
            "mode": "quick",
        })
        self._refresh_history_view()
        self._refresh_quick_last_cleaned()
        self._refresh_header_drive_label()

        message = f"{cleaner_core.format_size(total_freed)} of space freed."
        if skipped_admin:
            message += (
                f"\n\n{len(skipped_admin)} categor{'y was' if len(skipped_admin) == 1 else 'ies were'} skipped without Administrator rights "
                "(these can be cleaned from the Junk Cleanup tab in Administrator mode)."
            )
        if not logged:
            message += "\n\nCouldn't save to the history log."

        self.quick_status_label.config(text=message, fg=(Theme.WARNING if not logged else Theme.SUCCESS))

        # Junk Cleanup tab's own size numbers are now stale (some of the
        # same safe categories were just emptied) — rescan it quietly so
        # the two tabs stay consistent if the user switches over.
        self.scan_junk()

    def _build_junk_tab(self):
        frame = self.tab_junk

        if not cleaner_core.is_admin():
            banner = tk.Frame(frame, bg=Theme.WARNING_BG, highlightbackground=Theme.WARNING_BG, highlightthickness=1)
            banner.pack(fill="x", padx=14, pady=(14, 0))
            tk.Label(
                banner,
                text="⚠  Not running as Administrator — some categories will be skipped.",
                bg=Theme.WARNING_BG,
                fg=Theme.WARNING,
                font=Theme.FONT_BASE,
                padx=12,
                pady=10,
            ).pack(side="left")
            ttk.Button(banner, text="Restart as Administrator", command=self.restart_as_admin).pack(
                side="right", padx=10, pady=8
            )

        scrollable = ScrollableFrame(frame, height=300)
        scrollable.pack(fill="both", expand=True, padx=14, pady=14)

        for cat in self.categories:
            card = tk.Frame(
                scrollable.inner,
                bg=Theme.SURFACE,
                highlightbackground=Theme.SHADOW,
                highlightthickness=1,
            )
            card.pack(fill="x", pady=5)
            row = tk.Frame(card, bg=Theme.SURFACE)
            row.pack(fill="x", padx=14, pady=12)

            var = tk.BooleanVar(value=cat.get("default_checked", True))
            self.category_vars[cat["id"]] = var
            cb = ttk.Checkbutton(row, variable=var)
            cb.pack(side="left")

            text_frame = tk.Frame(row, bg=Theme.SURFACE)
            text_frame.pack(side="left", fill="x", expand=True, padx=10)

            name_row = tk.Frame(text_frame, bg=Theme.SURFACE)
            name_row.pack(anchor="w", fill="x")

            name = cat["name"]
            if cat.get("needs_admin"):
                name += "  (needs Administrator)"
            tk.Label(name_row, text=name, bg=Theme.SURFACE, fg=Theme.TEXT, font=(Theme.FONT_FAMILY, 10, "bold")).pack(side="left")

            badge = cat.get("badge")
            if badge == "safe":
                tk.Label(
                    name_row, text="  Safe — daily cleanup  ",
                    bg=Theme.SUCCESS_SOFT, fg=Theme.SUCCESS, font=Theme.FONT_MUTED,
                ).pack(side="left", padx=(10, 0))
            elif badge == "caution":
                tk.Label(
                    name_row, text="  Use caution  ",
                    bg=Theme.WARNING_BG, fg=Theme.WARNING, font=Theme.FONT_MUTED,
                ).pack(side="left", padx=(10, 0))

            tk.Label(
                text_frame,
                text=cat["desc"],
                bg=Theme.SURFACE,
                fg=Theme.TEXT_MUTED,
                font=Theme.FONT_MUTED,
                wraplength=520,
                justify="left",
            ).pack(anchor="w", pady=(3, 0))

            size_label = tk.Label(
                row, text="—", width=10, anchor="e", bg=Theme.SURFACE, fg=Theme.TEXT, font=(Theme.FONT_FAMILY, 10, "bold")
            )
            size_label.pack(side="right", padx=5)
            self.category_size_labels[cat["id"]] = size_label

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        self.scan_btn = ttk.Button(btn_row, text="Scan", command=self.scan_junk)
        self.scan_btn.pack(side="left")
        self.clean_btn = ttk.Button(btn_row, text="Clean Selected", style="Accent.TButton", command=self.clean_junk)
        self.clean_btn.pack(side="left", padx=8)
        self.total_label = ttk.Label(btn_row, text="Total reclaimable: —", style="Total.TLabel")
        self.total_label.pack(side="right")

        self.junk_log = LogBox(frame, height=7)
        self.junk_log.pack(fill="both", expand=False, padx=12, pady=(0, 12))

        self.scan_junk()

    def scan_junk(self):
        self.scan_btn.config(state="disabled")
        threading.Thread(target=self._run_safely, args=(self._scan_junk_worker,), daemon=True).start()

    def _scan_junk_worker(self):
        total = 0
        for cat in self.categories:
            if cat.get("special") == "recycle_bin":
                size = cleaner_core.get_recycle_bin_size()
            else:
                size = sum(cleaner_core.get_dir_size(p) for p in cat["paths"])
            self.category_sizes[cat["id"]] = size
            total += size
            self._ui(self._update_category_size, cat["id"], size)
        self._ui(self._scan_done, total)

    def _update_category_size(self, cat_id, size):
        self.category_size_labels[cat_id].config(text=cleaner_core.format_size(size))

    def _scan_done(self, total):
        self.total_label.config(text=f"Total reclaimable: {cleaner_core.format_size(total)}")
        self.scan_btn.config(state="normal")
        self.junk_log.log("Scan complete.")

    def clean_junk(self):
        selected = [c for c in self.categories if self.category_vars[c["id"]].get()]
        if not selected:
            messagebox.showinfo("Nothing selected", "Please select at least one category.")
            return
        if not messagebox.askyesno(
            "Confirm cleanup",
            f"Delete files in {len(selected)} selected categories?\n\n"
            "These are temporary/cache files only — no personal documents, "
            "photos, or programs will be touched.",
        ):
            return
        self.clean_btn.config(state="disabled")
        system_drive = os.environ.get("SystemDrive", "C:") + "\\"
        usage_before = system_tools.get_free_space(system_drive)
        self._free_before = usage_before[2] if usage_before else None
        threading.Thread(target=self._run_safely, args=(self._clean_junk_worker, selected,), daemon=True).start()

    def _clean_junk_worker(self, selected):
        total_freed = 0
        cleaned_ids = []
        log = lambda m: self._ui(self.junk_log.log, m)

        for cat in selected:
            if cat.get("needs_admin") and not cleaner_core.is_admin():
                log(f"Skipped {cat['name']} — needs Administrator.")
                continue

            if cat.get("special") == "recycle_bin":
                freed = cleaner_core.get_recycle_bin_size()
                if cleaner_core.empty_recycle_bin():
                    total_freed += freed
                    cleaned_ids.append(cat["id"])
                    log("Recycle Bin emptied.")
                else:
                    log("Could not empty Recycle Bin.")
                continue

            # For categories that require the Windows Update service to be
            # stopped first, check the outcome before touching any files:
            #   "stopped"         — we stopped it; clean, then restart.
            #   "already_stopped" — already down; safe to clean, no restart.
            #   "failed"          — still running; skip entirely to avoid
            #                       corrupting a cache that's in active use.
            service_state = None
            if cat.get("stop_service"):
                service_state = cleaner_core.stop_windows_update_service(log)
                if service_state == "failed":
                    log(f"Skipped {cat['name']} — could not stop Windows Update service.")
                    continue

            cat_freed = 0
            file_filter = cat.get("file_filter")
            for p in cat["paths"]:
                summary = cleaner_core.delete_dir_contents(p, log, file_filter=file_filter)
                cat_freed += summary["deleted_bytes"]

            if service_state == "stopped":
                cleaner_core.start_windows_update_service(log)

            total_freed += cat_freed
            cleaned_ids.append(cat["id"])
            log(f"{cat['name']}: freed {cleaner_core.format_size(cat_freed)}")

        self._ui(self._clean_done, total_freed, cleaned_ids)

    def _clean_done(self, total_freed, cleaned_ids):
        self.junk_log.log(f"Done. Freed approximately {cleaner_core.format_size(total_freed)}.")
        self.clean_btn.config(state="normal")
        logged = history_log.log_cleanup({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "categories": cleaned_ids,
            "bytes_freed": total_freed,
            "mode": "manual",
        })
        if not logged:
            self.junk_log.log("Warning: could not save this cleanup to the history log.")
        self._refresh_history_view()

        system_drive = os.environ.get("SystemDrive", "C:") + "\\"

        if self._free_before is not None:
            usage_after = system_tools.get_free_space(system_drive)
            free_after = usage_after[2] if usage_after else None

            summary_lines = [f"Freed approximately {cleaner_core.format_size(total_freed)}."]
            if free_after is not None:
                actual_gain = free_after - self._free_before
                summary_lines.append("")
                summary_lines.append(f"Free space on {system_drive}")
                summary_lines.append(f"  Before:  {cleaner_core.format_size(self._free_before)}")
                summary_lines.append(f"  After:   {cleaner_core.format_size(free_after)}")
                summary_lines.append(f"  Gained:  {cleaner_core.format_size(max(actual_gain, 0))}")
                self.junk_log.log(f"Free space on {system_drive}: {cleaner_core.format_size(self._free_before)} -> {cleaner_core.format_size(free_after)}")

            messagebox.showinfo("Cleanup complete", "\n".join(summary_lines))
            self._refresh_header_drive_label()

        self._free_before = None
        self.scan_junk()

    def restart_as_admin(self):
        """Re-launches this app with elevated privileges.

        ShellExecuteW with "runas" shows a UAC prompt and returns
        immediately — before the user has clicked Yes or No — so its
        return value only tells us whether the launch *request* was
        accepted by the OS (> 32 means ok), not whether the user
        approved the UAC dialog.

        Strategy:
          1. Hide this window so it doesn't sit behind the UAC dialog.
          2. Fire ShellExecuteW.
          3. If the call itself failed (return <= 32), restore the window
             and show an error — nothing was launched.
          4. If the call succeeded, wait briefly to give the UAC dialog
             time to appear, then destroy this window.  If the user
             cancels UAC, the new elevated process simply never starts —
             the user is left with nothing, which is acceptable because
             they can reopen the app normally.  We don't try to detect
             the UAC outcome (that would require waiting on hProcess via
             ShellExecuteEx, adding significant complexity for marginal
             benefit on a personal tool).
        """
        try:
            import ctypes
            params = " ".join(f'"{a}"' for a in sys.argv)
            self.root.withdraw()   # hide before UAC so we don't sit behind it
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            if ret <= 32:
                # Launch request rejected by the OS (not a UAC cancel —
                # those never reach here). Restore the window and report.
                self.root.deiconify()
                messagebox.showerror(
                    "Error",
                    f"Could not request Administrator restart (code {ret}).\n"
                    "Try right-clicking the app and choosing 'Run as administrator'."
                )
            else:
                # Request accepted — UAC dialog is (or will be) showing.
                # Give it 300 ms to appear, then close this instance.
                self.root.after(300, lambda: (self.shutdown(), self.root.destroy()))
        except Exception as e:
            self.root.deiconify()
            messagebox.showerror("Error", f"Could not restart as administrator: {e}")

    # ------------------------------------------------------------------
    # Tab 2: Browser & Network
    # ------------------------------------------------------------------
    def _build_browser_tab(self):
        frame = self.tab_browser
        ttk.Label(frame, text="Browsing History", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(
            frame,
            text="Clears visited-site history only. Cookies, saved passwords, and logins are never touched — "
                 "you will not be logged out of any site.",
            style="Muted.TLabel", wraplength=760, justify="left",
        ).pack(anchor="w", padx=10)

        self.browser_status_label = ttk.Label(frame, text="Click \"Check Status\" to scan.")
        self.browser_status_label.pack(anchor="w", padx=10, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(anchor="w", padx=10, pady=5)
        ttk.Button(btn_frame, text="Check Status", command=self.check_browser_status).pack(side="left")
        self.clear_history_btn = ttk.Button(btn_frame, text="Clear Browsing History", style="Accent.TButton", command=self.clear_history, state="disabled")
        self.clear_history_btn.pack(side="left", padx=5)

        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)
        ttk.Label(frame, text="Network", style="Section.TLabel").pack(anchor="w", padx=10)
        ttk.Label(frame, text="Clears stale website-address lookups. Can fix some \"site won't load\" issues.", style="Muted.TLabel").pack(anchor="w", padx=10)
        ttk.Button(frame, text="Flush DNS Cache", command=self.flush_dns).pack(anchor="w", padx=10, pady=5)

        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)
        self.browser_log = LogBox(frame, height=8)
        self.browser_log.pack(fill="both", expand=True, padx=10, pady=10)

    def check_browser_status(self):
        threading.Thread(target=self._run_safely, args=(self._check_browser_status_worker,), daemon=True).start()

    def _check_browser_status_worker(self):
        profiles = browser_core.get_browser_profiles()
        lines = []
        running_any = False
        for label, (browser_name, path) in profiles.items():
            count = browser_core.get_history_entry_count(path)
            running = browser_core.is_browser_running(browser_name)
            if running:
                running_any = True
            status = " (running — close it first)" if running else ""
            lines.append(f"{label}: {count} history entries{status}")
        if not profiles:
            lines.append("No supported browsers found (Chrome/Edge).")
        self._ui(self._update_browser_status, "\n".join(lines), running_any, bool(profiles))

    def _update_browser_status(self, text, running_any, has_profiles):
        self.browser_status_label.config(text=text)
        self.clear_history_btn.config(state=("normal" if has_profiles and not running_any else "disabled"))

    def clear_history(self):
        if not messagebox.askyesno(
            "Confirm",
            "Clear browsing history for all detected browsers?\n\nThis will NOT log you out of any site.",
        ):
            return
        threading.Thread(target=self._run_safely, args=(self._clear_history_worker,), daemon=True).start()

    def _clear_history_worker(self):
        log = lambda m: self._ui(self.browser_log.log, m)
        profiles = browser_core.get_browser_profiles()
        for label, (browser_name, path) in profiles.items():
            if browser_core.is_browser_running(browser_name):
                log(f"Skipped {label} — please close it first.")
                continue
            ok = browser_core.clear_browsing_history(path, lambda m, n=label: log(f"[{n}] {m}"))
            log(f"{label}: {'done' if ok else 'failed'}")
        self._ui(self.check_browser_status)

    def flush_dns(self):
        log = lambda m: self._ui(self.browser_log.log, m)
        threading.Thread(target=self._run_safely, args=(browser_core.flush_dns, log), daemon=True).start()

    # ------------------------------------------------------------------
    # Tab 3: System Tools
    # ------------------------------------------------------------------
    def _build_tools_tab(self):
        frame = self.tab_tools

        ttk.Label(frame, text="Disk Space Analyzer", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 0))
        drive_row = ttk.Frame(frame)
        drive_row.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Label(drive_row, text="Drive:").pack(side="left")
        self.drive_var = tk.StringVar(value="")
        self.drive_combo = ttk.Combobox(drive_row, textvariable=self.drive_var, state="readonly", width=28)
        self.drive_combo.pack(side="left", padx=5)
        self.drive_combo.bind("<<ComboboxSelected>>", self._on_drive_selected)
        ttk.Button(drive_row, text="Refresh Drives", command=self.refresh_drive_list).pack(side="left")

        row = ttk.Frame(frame)
        row.pack(fill="x", padx=10, pady=5)
        self.analyzer_path_label = ttk.Label(row, text="No folder selected", style="Muted.TLabel")
        self.analyzer_path_label.pack(side="left")
        ttk.Button(row, text="Choose Folder", command=self.choose_analyzer_folder).pack(side="right")
        self.analyze_btn = ttk.Button(frame, text="Analyze", style="Accent.TButton", command=self.run_analyzer)
        self.analyze_btn.pack(anchor="w", padx=10)

        self.drive_summary_label = ttk.Label(frame, text="", style="Muted.TLabel")
        self.drive_summary_label.pack(anchor="w", padx=10)

        columns = ("name", "size", "type")
        self.analyzer_tree = ttk.Treeview(frame, columns=columns, show="headings", height=6)
        for col, label in zip(columns, ("Name", "Size", "Type")):
            self.analyzer_tree.heading(col, text=label)
        self.analyzer_tree.column("name", width=400)
        self.analyzer_tree.pack(fill="both", expand=False, padx=10, pady=5)

        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)

        ttk.Label(frame, text="Empty Folder Finder", style="Section.TLabel").pack(anchor="w", padx=10)
        row2 = ttk.Frame(frame)
        row2.pack(fill="x", padx=10, pady=5)
        self.empty_path_label = ttk.Label(row2, text="No folder selected", style="Muted.TLabel")
        self.empty_path_label.pack(side="left")
        ttk.Button(row2, text="Choose Folder", command=self.choose_empty_folder).pack(side="right")
        btn_row = ttk.Frame(frame)
        btn_row.pack(anchor="w", padx=10)
        self.scan_empty_btn = ttk.Button(btn_row, text="Scan", command=self.scan_empty_folders)
        self.scan_empty_btn.pack(side="left")
        ttk.Button(btn_row, text="Delete All Found", style="Danger.TButton", command=self.delete_empty_folders_found).pack(side="left", padx=5)
        self.empty_listbox = tk.Listbox(frame, height=5)
        self.empty_listbox.pack(fill="both", expand=False, padx=10, pady=5)
        self.empty_folders_found = []

        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)

        ttk.Label(frame, text="Icon Cache Reset", style="Section.TLabel").pack(anchor="w", padx=10)
        ttk.Label(frame, text="Fixes wrong/blank icons. Restarts Explorer — your screen will flicker briefly.", style="Muted.TLabel").pack(anchor="w", padx=10)
        ttk.Button(frame, text="Reset Icon Cache", style="Accent.TButton", command=self.reset_icon_cache).pack(anchor="w", padx=10, pady=5)

        self.tools_log = LogBox(frame, height=5)
        self.tools_log.pack(fill="both", expand=True, padx=10, pady=10)

        self.refresh_drive_list()

    def refresh_drive_list(self):
        drives = system_tools.list_drives()
        self._drives_by_label = {}
        labels = []
        for d in drives:
            free_str = cleaner_core.format_size(d["free"])
            total_str = cleaner_core.format_size(d["total"])
            label = f"{d['path']}  ({free_str} free of {total_str})"
            labels.append(label)
            self._drives_by_label[label] = d
        self.drive_combo.config(values=labels)
        if labels and not self.drive_var.get():
            self.drive_combo.current(0)

    def _on_drive_selected(self, event=None):
        label = self.drive_var.get()
        drive = self._drives_by_label.get(label)
        if drive:
            self.analyzer_folder = drive["path"]
            self.analyzer_path_label.config(text=drive["path"])

    def choose_analyzer_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.analyzer_folder = path
            self.analyzer_path_label.config(text=path)
            self.drive_var.set("")

    def run_analyzer(self):
        if not getattr(self, "analyzer_folder", None):
            messagebox.showinfo("No folder", "Please choose a folder first.")
            return
        self.analyze_btn.config(state="disabled")
        self.tools_log.log(f"Scanning {self.analyzer_folder} — this can take a while for large folders...")
        threading.Thread(target=self._run_safely, args=(self._run_analyzer_worker,), daemon=True).start()

    def _run_analyzer_worker(self):
        results = system_tools.analyze_folder(self.analyzer_folder)
        self._ui(self._show_analyzer_results, results)

    def _show_analyzer_results(self, results):
        self.analyzer_tree.delete(*self.analyzer_tree.get_children())
        usage = system_tools.get_free_space(self.analyzer_folder)
        drive_total = usage[0] if usage else 0
        for r in results[:200]:
            pct = f"  ({r['size'] / drive_total * 100:.1f}%)" if drive_total else ""
            self.analyzer_tree.insert("", "end", values=(r["name"], cleaner_core.format_size(r["size"]) + pct, "Folder" if r["is_dir"] else "File"))
        self.tools_log.log(f"Analyzed {len(results)} item(s).")
        if usage:
            total, used, free = usage
            self.drive_summary_label.config(
                text=f"Drive: {cleaner_core.format_size(free)} free of {cleaner_core.format_size(total)} total"
            )
        self.analyze_btn.config(state="normal")

    def choose_empty_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.empty_folder = path
            self.empty_path_label.config(text=path)

    def scan_empty_folders(self):
        if not getattr(self, "empty_folder", None):
            messagebox.showinfo("No folder", "Please choose a folder first.")
            return
        self.scan_empty_btn.config(state="disabled")
        self.tools_log.log(f"Scanning {self.empty_folder} — this can take a while for large folders...")
        threading.Thread(target=self._run_safely, args=(self._scan_empty_worker,), daemon=True).start()

    def _scan_empty_worker(self):
        found = system_tools.find_empty_folders(self.empty_folder)
        self._ui(self._show_empty_results, found)

    def _show_empty_results(self, found):
        self.empty_folders_found = found
        self.empty_listbox.delete(0, "end")
        for p in found:
            self.empty_listbox.insert("end", p)
        self.tools_log.log(f"Found {len(found)} empty folder(s).")
        self.scan_empty_btn.config(state="normal")

    def delete_empty_folders_found(self):
        found = self.empty_folders_found
        if not found:
            messagebox.showinfo("Nothing to delete", "Scan first, or no empty folders were found.")
            return
        if not messagebox.askyesno("Confirm", f"Delete {len(found)} empty folder(s)?"):
            return
        threading.Thread(target=self._run_safely, args=(self._delete_empty_worker, found,), daemon=True).start()

    def _delete_empty_worker(self, found):
        log = lambda m: self._ui(self.tools_log.log, m)
        summary = system_tools.delete_empty_folders(found, log)
        self._ui(self._empty_delete_done, summary)

    def _empty_delete_done(self, summary):
        self.tools_log.log(f"Deleted {summary['deleted']} folder(s).")
        self.empty_listbox.delete(0, "end")
        self.empty_folders_found = []

    def reset_icon_cache(self):
        if not messagebox.askyesno("Confirm", "This will restart Explorer. Continue?"):
            return
        log = lambda m: self._ui(self.tools_log.log, m)
        threading.Thread(target=self._run_safely, args=(system_tools.reset_icon_cache, log), daemon=True).start()

    # ------------------------------------------------------------------
    # Tab 4: Startup Manager
    # ------------------------------------------------------------------
    def _build_startup_tab(self):
        frame = self.tab_startup
        ttk.Label(frame, text="Programs that launch automatically when Windows starts.", style="Muted.TLabel").pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(frame, text="Disabling here is reversible — you can always re-enable from this list.", style="Muted.TLabel").pack(anchor="w", padx=10)

        btn_row = ttk.Frame(frame)
        btn_row.pack(anchor="w", padx=10, pady=5)
        ttk.Button(btn_row, text="Refresh", command=self.refresh_startup_items).pack(side="left")
        ttk.Button(btn_row, text="Disable Selected", command=self.disable_selected_startup).pack(side="left", padx=5)
        ttk.Button(btn_row, text="Enable Selected", command=self.enable_selected_startup).pack(side="left")

        columns = ("name", "source", "status")
        self.startup_tree = ttk.Treeview(frame, columns=columns, show="headings", height=14, selectmode="extended")
        for col, label in zip(columns, ("Name", "Location", "Status")):
            self.startup_tree.heading(col, text=label)
        self.startup_tree.pack(fill="both", expand=True, padx=10, pady=5)

        self.startup_log = LogBox(frame, height=5)
        self.startup_log.pack(fill="both", expand=False, padx=10, pady=10)
        self.startup_items = []

    def refresh_startup_items(self):
        threading.Thread(target=self._run_safely, args=(self._refresh_startup_worker,), daemon=True).start()

    def _refresh_startup_worker(self):
        items = startup_manager.list_startup_items()
        self._ui(self._show_startup_items, items)

    def _show_startup_items(self, items):
        self.startup_items = items
        self.startup_tree.delete(*self.startup_tree.get_children())
        for idx, item in enumerate(items):
            status = "Enabled" if item["enabled"] else "Disabled"
            self.startup_tree.insert("", "end", iid=str(idx), values=(item["name"], item["source"], status))
        self.startup_log.log(f"Found {len(items)} startup item(s).")

    def _selected_startup_items(self):
        sel = self.startup_tree.selection()
        return [self.startup_items[int(i)] for i in sel]

    def disable_selected_startup(self):
        items = [i for i in self._selected_startup_items() if i["enabled"]]
        if not items:
            messagebox.showinfo("Nothing selected", "Select one or more enabled items first.")
            return
        threading.Thread(target=self._run_safely, args=(self._disable_startup_worker, items,), daemon=True).start()

    def _disable_startup_worker(self, items):
        log = lambda m: self._ui(self.startup_log.log, m)
        for item in items:
            ok = startup_manager.disable_startup_item(item, log)
            log(f"{item['name']}: {'disabled' if ok else 'failed'}")
        self._ui(self.refresh_startup_items)

    def enable_selected_startup(self):
        items = [i for i in self._selected_startup_items() if not i["enabled"]]
        if not items:
            messagebox.showinfo("Nothing selected", "Select one or more disabled items first.")
            return
        threading.Thread(target=self._run_safely, args=(self._enable_startup_worker, items,), daemon=True).start()

    def _enable_startup_worker(self, items):
        log = lambda m: self._ui(self.startup_log.log, m)
        for item in items:
            ok = startup_manager.enable_startup_item(item, log)
            log(f"{item['name']}: {'enabled' if ok else 'failed'}")
        self._ui(self.refresh_startup_items)

    # ------------------------------------------------------------------
    # Tab 5: Automation & History
    # ------------------------------------------------------------------
    def _build_auto_tab(self):
        frame = self.tab_auto
        ttk.Label(frame, text="Scheduled Auto-Clean", style="Section.TLabel").pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(frame, text="Runs the same Junk Cleanup categories automatically in the background.", style="Muted.TLabel").pack(anchor="w", padx=10)

        row = ttk.Frame(frame)
        row.pack(anchor="w", padx=10, pady=5)
        ttk.Label(row, text="Frequency:").pack(side="left")
        self.freq_var = tk.StringVar(value="WEEKLY")
        ttk.Combobox(row, textvariable=self.freq_var, values=["DAILY", "WEEKLY"], width=10, state="readonly").pack(side="left", padx=5)
        ttk.Label(row, text="Day:").pack(side="left", padx=(10, 0))
        self.day_var = tk.StringVar(value="SUN")
        ttk.Combobox(row, textvariable=self.day_var, values=["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"], width=6, state="readonly").pack(side="left", padx=5)
        ttk.Label(row, text="Time (HH:MM):").pack(side="left", padx=(10, 0))
        self.time_var = tk.StringVar(value="03:00")
        ttk.Entry(row, textvariable=self.time_var, width=8).pack(side="left", padx=5)

        btn_row = ttk.Frame(frame)
        btn_row.pack(anchor="w", padx=10, pady=5)
        ttk.Button(btn_row, text="Enable Schedule", style="Accent.TButton", command=self.enable_schedule).pack(side="left")
        ttk.Button(btn_row, text="Remove Schedule", command=self.remove_schedule).pack(side="left", padx=5)
        self.schedule_status_label = ttk.Label(frame, text="")
        self.schedule_status_label.pack(anchor="w", padx=10)

        self.auto_log = LogBox(frame, height=4)
        self.auto_log.pack(fill="both", expand=False, padx=10, pady=(5, 10))

        # ── Shutdown Clean ──────────────────────────────────────────────
        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)
        ttk.Label(frame, text="Shutdown Auto-Clean", style="Section.TLabel").pack(anchor="w", padx=10)
        ttk.Label(
            frame,
            text="Automatically cleans temp files, cache, and thumbnails every time you shut down the PC.",
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=10)
        ttk.Label(
            frame,
            text="• Cleans: Temp files, Windows Temp, Chrome cache, Thumbnail cache, Error reports, Recycle Bin\n"
                 "• Fast Startup is disabled automatically so the clean always runs\n"
                 "• Requires Administrator rights to register",
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", padx=20, pady=(4, 0))

        sd_btn_row = ttk.Frame(frame)
        sd_btn_row.pack(anchor="w", padx=10, pady=6)
        ttk.Button(
            sd_btn_row, text="Enable Shutdown Clean",
            style="Accent.TButton", command=self.enable_shutdown_clean
        ).pack(side="left")
        ttk.Button(
            sd_btn_row, text="Disable Shutdown Clean",
            command=self.disable_shutdown_clean
        ).pack(side="left", padx=6)
        ttk.Button(
            sd_btn_row, text="Run Now (Test)",
            command=self.run_shutdown_clean_now
        ).pack(side="left")

        self.shutdown_status_label = ttk.Label(frame, text="")
        self.shutdown_status_label.pack(anchor="w", padx=10)
        self._refresh_shutdown_status()

        self.shutdown_log = LogBox(frame, height=4)
        self.shutdown_log.pack(fill="both", expand=False, padx=10, pady=(4, 10))

        # ── Error Log (automatic bug-handling safety net) ─────────────────
        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)
        ttk.Label(frame, text="Error Log", style="Section.TLabel").pack(anchor="w", padx=10)
        ttk.Label(
            frame,
            text="If something unexpected ever goes wrong, the app catches it, keeps running, "
                 "and saves the details here instead of crashing or failing silently.",
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=10)

        err_btn_row = ttk.Frame(frame)
        err_btn_row.pack(anchor="w", padx=10, pady=6)
        ttk.Button(err_btn_row, text="Error Log দেখুন", command=self.show_error_log).pack(side="left")
        ttk.Button(err_btn_row, text="Clear Error Log", command=self.clear_error_log).pack(side="left", padx=6)

        self.error_indicator = ttk.Label(frame, text="")
        self.error_indicator.pack(anchor="w", padx=10)
        self._refresh_error_indicator()

        # ── History ─────────────────────────────────────────────────────
        ttk.Separator(frame).pack(fill="x", padx=10, pady=10)
        ttk.Label(frame, text="Cleanup History", style="Section.TLabel").pack(anchor="w", padx=10)
        columns = ("date", "categories", "freed", "mode")
        self.history_tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        for col, label in zip(columns, ("Date", "Categories Cleaned", "Space Freed", "Mode")):
            self.history_tree.heading(col, text=label)
        self.history_tree.pack(fill="both", expand=True, padx=10, pady=5)

    def _refresh_schedule_status(self):
        scheduled = scheduler.is_task_scheduled()
        self.schedule_status_label.config(text=("Auto-clean is currently ENABLED." if scheduled else "Auto-clean is currently OFF."))

    def enable_schedule(self):
        threading.Thread(target=self._run_safely, args=(self._enable_schedule_worker,), daemon=True).start()

    def _enable_schedule_worker(self):
        log = lambda m: self._ui(self.auto_log.log, m)
        run_command = scheduler.build_run_command()
        scheduler.create_scheduled_task(
            run_command, self.freq_var.get(), self.day_var.get(), self.time_var.get(), log
        )
        self._ui(self._refresh_schedule_status)

    def remove_schedule(self):
        threading.Thread(target=self._run_safely, args=(self._remove_schedule_worker,), daemon=True).start()

    def _remove_schedule_worker(self):
        log = lambda m: self._ui(self.auto_log.log, m)
        ok = scheduler.remove_scheduled_task(log)
        if ok:
            log("Schedule removed.")
        self._ui(self._refresh_schedule_status)

    def _refresh_history_view(self):
        self.history_tree.delete(*self.history_tree.get_children())
        for entry in reversed(history_log.read_history()):
            ts = entry.get("timestamp", "")
            # Show category names instead of just a count
            cat_ids = entry.get("categories", [])
            cats_display = ", ".join(cat_ids) if cat_ids else "—"
            freed = cleaner_core.format_size(entry.get("bytes_freed", 0))
            mode = entry.get("mode", "manual")
            self.history_tree.insert("", "end", values=(ts, cats_display, freed, mode))

    # ------------------------------------------------------------------
    # Shutdown Clean
    # ------------------------------------------------------------------
    def _refresh_shutdown_status(self):
        try:
            status = shutdown_setup.get_status()
            gpo = status.get("gpo_registered", False)
            task = status.get("task_registered", False)
            fast_ok = status.get("fast_startup_disabled", False)

            if gpo:
                method = "Group Policy Shutdown Script"
            elif task:
                method = "Task Scheduler (Event 1074)"
            else:
                method = None

            if method:
                fs_note = " | Fast Startup: OFF ✓" if fast_ok else " | ⚠ Fast Startup still ON"
                self.shutdown_status_label.config(
                    text=f"✅  Shutdown Clean ENABLED — method: {method}{fs_note}",
                    foreground=Theme.SUCCESS,
                )
            else:
                self.shutdown_status_label.config(
                    text="⭕  Shutdown Clean is NOT set up.",
                    foreground=Theme.TEXT_MUTED,
                )
        except Exception:
            self.shutdown_status_label.config(text="Status unknown.", foreground=Theme.TEXT_MUTED)

    def enable_shutdown_clean(self):
        if not cleaner_core.is_admin():
            if messagebox.askyesno(
                "Admin Rights Required",
                "Enabling Shutdown Clean requires Administrator rights.\n\n"
                "Restart this app as Administrator now?"
            ):
                self.restart_as_admin()
            return
        threading.Thread(target=self._run_safely, args=(self._enable_shutdown_worker,), daemon=True).start()

    def _enable_shutdown_worker(self):
        log = lambda m: self._ui(self.shutdown_log.log, m)
        ok = shutdown_setup.setup_shutdown_clean(log)
        if ok:
            log("✅ Done. The cleaner will now run silently on every shutdown.")
        else:
            log("❌ Setup failed. Check the log above.")
        self._ui(self._refresh_shutdown_status)

    def disable_shutdown_clean(self):
        threading.Thread(target=self._run_safely, args=(self._disable_shutdown_worker,), daemon=True).start()

    def _disable_shutdown_worker(self):
        log = lambda m: self._ui(self.shutdown_log.log, m)
        shutdown_setup.remove_shutdown_clean(log)
        log("Shutdown Clean removed.")
        self._ui(self._refresh_shutdown_status)

    def run_shutdown_clean_now(self):
        """Test run — executes the shutdown clean immediately in a background thread."""
        log = lambda m: self._ui(self.shutdown_log.log, m)
        log("Running shutdown clean now (test)...")
        threading.Thread(target=self._run_safely, args=(self._run_shutdown_clean_worker,), daemon=True).start()

    def _run_shutdown_clean_worker(self):
        log = lambda m: self._ui(self.shutdown_log.log, m)
        try:
            import shutdown_clean
            import logging
            # Use a simple lambda logger so output goes to GUI
            class _GuiLogger:
                def info(self, m): log(m)
                def warning(self, m): log(f"⚠ {m}")
                def error(self, m): log(f"❌ {m}")
                def critical(self, m): log(f"🔴 {m}")
                handlers = []
            result = shutdown_clean.run_shutdown_clean(_GuiLogger())
            history_log.log_cleanup(result)
            freed = cleaner_core.format_size(result.get("bytes_freed", 0))
            log(f"✅ Test run done — freed {freed}")
            self._ui(self._refresh_history_view)
        except Exception as exc:
            log(f"❌ Error: {exc}")
            error_log.record("run_shutdown_clean_now", exc)
            self._ui(self._refresh_error_indicator)

    # ------------------------------------------------------------------
    # Error Log (automatic bug-handling safety net)
    # ------------------------------------------------------------------
    def _refresh_error_indicator(self):
        n = error_log.count_errors()
        if n:
            self.error_indicator.config(
                text=f"⚠ {n} টা টেকনিক্যাল সমস্যা লগ হয়েছে (কাজে বাধা দেয়নি)",
                foreground=Theme.WARNING,
            )
        else:
            self.error_indicator.config(text="✅ কোনো এরর লগ হয়নি", foreground=Theme.SUCCESS)

    def show_error_log(self):
        errors = error_log.read_errors()
        win = tk.Toplevel(self.root)
        win.title("Error Log")
        win.geometry("760x520")
        apply_theme(win)

        if not errors:
            ttk.Label(win, text="কোনো এরর লগ নেই — সবকিছু ঠিকঠাক চলছে।", padding=20).pack()
            return

        text = tk.Text(win, wrap="word", font=Theme.FONT_MONO, bg=Theme.SURFACE, fg=Theme.TEXT)
        text.pack(fill="both", expand=True, padx=10, pady=10)
        for e in reversed(errors[-50:]):
            text.insert(
                "end",
                f"[{e.get('timestamp', '?')}] {e.get('context', '?')} — "
                f"{e.get('error_type', '?')}: {e.get('message', '')}\n"
            )
            text.insert("end", f"{e.get('traceback', '')}\n{'-' * 70}\n")
        text.config(state="disabled")

    def clear_error_log(self):
        if not messagebox.askyesno("Confirm", "Clear the entire error log?"):
            return
        error_log.clear_errors()
        self._refresh_error_indicator()


# ---------------------------------------------------------------------------
# Headless auto-clean, used by the scheduled task (no window, no prompts)
# ---------------------------------------------------------------------------

def run_auto_clean():
    """Legacy CLI entry point (python pc_cleaner.py --auto-clean).
    The newer shutdown_clean.py (registered via the Automation tab's
    "Shutdown Clean" button) is now the primary automatic-cleaning
    path, but this is kept for anyone who scheduled this flag directly.

    Hardened the same way as shutdown_clean.py: one category's failure
    can't take down the rest of the run, and nothing here fails
    silently — this runs with no console attached (pythonw / Task
    Scheduler), so without logging to error_log, a bug here would be
    completely invisible with no trace anywhere.
    """
    try:
        categories = build_full_categories()
        total_freed = 0
        cleaned_ids = []

        for cat in categories:
            try:
                if not cat.get("default_checked", True):
                    continue
                if cat.get("needs_admin") and not cleaner_core.is_admin():
                    continue

                if cat.get("special") == "recycle_bin":
                    freed = cleaner_core.get_recycle_bin_size()
                    if cleaner_core.empty_recycle_bin():
                        total_freed += freed
                        cleaned_ids.append(cat["id"])
                    continue

                service_state = None
                if cat.get("stop_service"):
                    service_state = cleaner_core.stop_windows_update_service()
                    if service_state == "failed":
                        continue   # skip category — service still running

                file_filter = cat.get("file_filter")
                for p in cat["paths"]:
                    summary = cleaner_core.delete_dir_contents(p, file_filter=file_filter)
                    total_freed += summary["deleted_bytes"]

                if service_state == "stopped":
                    cleaner_core.start_windows_update_service()
                cleaned_ids.append(cat["id"])
            except Exception as exc:
                try:
                    error_log.record(f"run_auto_clean:{cat.get('id', '?')}", exc)
                except Exception:
                    pass
                continue   # one category's bug must not stop the rest

        history_log.log_cleanup({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "categories": cleaned_ids,
            "bytes_freed": total_freed,
            "mode": "auto",
        })
    except Exception as exc:
        try:
            error_log.record("run_auto_clean", exc)
        except Exception:
            pass


def main():
    if "--auto-clean" in sys.argv:
        run_auto_clean()
        return
    root = tk.Tk()
    try:
        app = CleanerApp(root)
    except Exception as exc:
        # This happens before CleanerApp has installed its own safety
        # net (report_callback_exception is set inside __init__), so it
        # needs its own catch — otherwise a startup bug means the app
        # silently never opens, which is the worst failure mode for
        # someone who isn't a coder: no window, no message, no clue.
        try:
            error_log.record("startup", exc)
        except Exception:
            pass
        try:
            messagebox.showerror(
                "চালু করা যায়নি",
                f"PC Cleaner চালু করতে সমস্যা হয়েছে।\n\n{type(exc).__name__}: {exc}\n\n"
                "বিস্তারিত error_log.json ফাইলে সংরক্ষিত হয়েছে — এই ফাইলটা Claude-কে "
                "দেখালে দ্রুত ঠিক করে দেওয়া সম্ভব।"
            )
        except Exception:
            pass
        root.destroy()
        return
    root.protocol("WM_DELETE_WINDOW", lambda: (app.shutdown(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
