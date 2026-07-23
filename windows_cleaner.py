"""
windows_cleaner.py
-------------------
Main GUI application. Five tabs:
  1. Junk Cleanup      - temp/cache/update-leftover files + Recycle Bin
  2. Browser & Network  - browsing history (never cookies) + DNS flush
  3. System Tools       - disk space analyzer, empty folder finder, icon cache reset
  4. Startup Manager    - enable/disable auto-start programs (reversibly)
  5. Automation & History - scheduled auto-clean + log of past runs

Run with a GUI:      python windows_cleaner.py
Run headless (used by the scheduled task): python windows_cleaner.py --auto-clean
"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

import cleaner_core
import browser_core
import system_tools
import startup_manager
import scheduler
import history_log


# ----------------------------------------------------------------------
# Visual theme — one place to tweak colors/fonts for the whole app.
# ----------------------------------------------------------------------
class Theme:
    BG = "#f4f6f9"
    SURFACE = "#ffffff"
    BORDER = "#dfe4ea"
    TEXT = "#1f2733"
    TEXT_MUTED = "#6b7280"
    PRIMARY = "#2f6fed"
    PRIMARY_DARK = "#2457bf"
    PRIMARY_TEXT = "#ffffff"
    SUCCESS = "#1a8f5e"
    WARNING = "#b35c00"
    WARNING_BG = "#fff4e5"
    DANGER = "#d64545"

    FONT_FAMILY = "Segoe UI"
    FONT_BASE = (FONT_FAMILY, 10)
    FONT_MUTED = (FONT_FAMILY, 9)
    FONT_SECTION = (FONT_FAMILY, 11, "bold")
    FONT_TOTAL = (FONT_FAMILY, 11, "bold")
    FONT_TAB = (FONT_FAMILY, 10)
    FONT_MONO = ("Consolas", 9)


def apply_theme(root):
    """Configure ttk styles once, at startup. Widgets below just reference
    these style names (or pick up the defaults automatically)."""
    root.configure(bg=Theme.BG)

    style = ttk.Style(root)
    for candidate in ("vista", "clam"):
        try:
            style.theme_use(candidate)
            break
        except tk.TclError:
            continue
    else:
        # Neither vista nor clam is available on this Tk build (unusual, but
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

    style.configure("TNotebook", background=Theme.BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        font=Theme.FONT_TAB,
        padding=(16, 8),
        background=Theme.BG,
        foreground=Theme.TEXT_MUTED,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", Theme.SURFACE)],
        foreground=[("selected", Theme.PRIMARY_DARK)],
        font=[("selected", (Theme.FONT_FAMILY, 10, "bold"))],
    )

    style.configure("TButton", font=Theme.FONT_BASE, padding=(12, 6))
    style.configure(
        "Accent.TButton",
        font=(Theme.FONT_FAMILY, 10, "bold"),
        padding=(14, 7),
        foreground=Theme.PRIMARY_TEXT,
        background=Theme.PRIMARY,
    )
    style.map(
        "Accent.TButton",
        background=[("active", Theme.PRIMARY_DARK), ("disabled", Theme.BORDER)],
        foreground=[("disabled", Theme.TEXT_MUTED)],
    )
    style.configure(
        "Danger.TButton",
        font=Theme.FONT_BASE,
        padding=(12, 6),
        foreground=Theme.DANGER,
    )

    style.configure(
        "Treeview",
        background=Theme.SURFACE,
        fieldbackground=Theme.SURFACE,
        foreground=Theme.TEXT,
        rowheight=24,
        font=Theme.FONT_BASE,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        font=(Theme.FONT_FAMILY, 9, "bold"),
        background=Theme.BG,
        foreground=Theme.TEXT_MUTED,
        relief="flat",
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
        root.title("Windows Cleaner")
        root.geometry("900x720")
        root.minsize(760, 580)
        apply_theme(root)

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
        header.pack(fill="x", padx=12, pady=(10, 4))
        title_frame = tk.Frame(header, bg=Theme.BG)
        title_frame.pack(side="left")
        tk.Label(title_frame, text="Windows Cleaner", bg=Theme.BG, fg=Theme.TEXT, font=(Theme.FONT_FAMILY, 14, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Free up space and keep your PC tidy", bg=Theme.BG, fg=Theme.TEXT_MUTED, font=Theme.FONT_MUTED).pack(anchor="w")

        self.header_drive_label = tk.Label(header, text="", bg=Theme.BG, fg=Theme.SUCCESS, font=(Theme.FONT_FAMILY, 10, "bold"))
        self.header_drive_label.pack(side="right", anchor="e")
        self._refresh_header_drive_label()

        ttk.Separator(self.root).pack(fill="x", padx=0, pady=(0, 4))

        notebook = ttk.Notebook(self.root)
        self.tab_junk = ttk.Frame(notebook)
        self.tab_browser = ttk.Frame(notebook)
        self.tab_tools = ttk.Frame(notebook)
        self.tab_startup = ttk.Frame(notebook)
        self.tab_auto = ttk.Frame(notebook)

        notebook.add(self.tab_junk, text="  Junk Cleanup  ")
        notebook.add(self.tab_browser, text="  Browser && Network  ")
        notebook.add(self.tab_tools, text="  System Tools  ")
        notebook.add(self.tab_startup, text="  Startup Manager  ")
        notebook.add(self.tab_auto, text="  Automation && History  ")
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

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
    def _build_junk_tab(self):
        frame = self.tab_junk

        if not cleaner_core.is_admin():
            banner = tk.Frame(frame, bg=Theme.WARNING_BG, highlightbackground=Theme.WARNING, highlightthickness=1)
            banner.pack(fill="x", padx=12, pady=(12, 0))
            tk.Label(
                banner,
                text="⚠  Not running as Administrator — some categories will be skipped.",
                bg=Theme.WARNING_BG,
                fg=Theme.WARNING,
                font=Theme.FONT_BASE,
                padx=10,
                pady=8,
            ).pack(side="left")
            ttk.Button(banner, text="Restart as Administrator", command=self.restart_as_admin).pack(
                side="right", padx=8, pady=6
            )

        scrollable = ScrollableFrame(frame, height=300)
        scrollable.pack(fill="both", expand=True, padx=12, pady=12)

        for cat in self.categories:
            card = tk.Frame(
                scrollable.inner,
                bg=Theme.SURFACE,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
            )
            card.pack(fill="x", pady=4)
            row = tk.Frame(card, bg=Theme.SURFACE)
            row.pack(fill="x", padx=10, pady=8)

            var = tk.BooleanVar(value=cat.get("default_checked", True))
            self.category_vars[cat["id"]] = var
            cb = ttk.Checkbutton(row, variable=var)
            cb.pack(side="left")

            text_frame = tk.Frame(row, bg=Theme.SURFACE)
            text_frame.pack(side="left", fill="x", expand=True, padx=8)

            name_row = tk.Frame(text_frame, bg=Theme.SURFACE)
            name_row.pack(anchor="w", fill="x")

            name = cat["name"]
            if cat.get("needs_admin"):
                name += "  (needs Administrator)"
            tk.Label(name_row, text=name, bg=Theme.SURFACE, fg=Theme.TEXT, font=Theme.FONT_BASE).pack(side="left")

            badge = cat.get("badge")
            if badge == "safe":
                tk.Label(
                    name_row, text="  Safe — daily cleanup  ",
                    bg=Theme.SUCCESS, fg="#ffffff", font=Theme.FONT_MUTED,
                ).pack(side="left", padx=(8, 0))
            elif badge == "caution":
                tk.Label(
                    name_row, text="  Use caution  ",
                    bg=Theme.WARNING_BG, fg=Theme.WARNING, font=Theme.FONT_MUTED,
                ).pack(side="left", padx=(8, 0))

            tk.Label(
                text_frame,
                text=cat["desc"],
                bg=Theme.SURFACE,
                fg=Theme.TEXT_MUTED,
                font=Theme.FONT_MUTED,
                wraplength=520,
                justify="left",
            ).pack(anchor="w")

            size_label = tk.Label(
                row, text="—", width=10, anchor="e", bg=Theme.SURFACE, fg=Theme.TEXT, font=Theme.FONT_BASE
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
        threading.Thread(target=self._scan_junk_worker, daemon=True).start()

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
        threading.Thread(target=self._clean_junk_worker, args=(selected,), daemon=True).start()

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

            service_stopped = cat.get("stop_service") and cleaner_core.stop_windows_update_service(log)
            cat_freed = 0
            for p in cat["paths"]:
                summary = cleaner_core.delete_dir_contents(p, log)
                cat_freed += summary["deleted_bytes"]
            if service_stopped:
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
        try:
            import ctypes
            params = " ".join(f'"{a}"' for a in sys.argv)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            self.root.destroy()
        except Exception as e:
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
        threading.Thread(target=self._check_browser_status_worker, daemon=True).start()

    def _check_browser_status_worker(self):
        profiles = browser_core._browser_profiles()
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
        threading.Thread(target=self._clear_history_worker, daemon=True).start()

    def _clear_history_worker(self):
        log = lambda m: self._ui(self.browser_log.log, m)
        profiles = browser_core._browser_profiles()
        for label, (browser_name, path) in profiles.items():
            if browser_core.is_browser_running(browser_name):
                log(f"Skipped {label} — please close it first.")
                continue
            ok = browser_core.clear_browsing_history(path, lambda m, n=label: log(f"[{n}] {m}"))
            log(f"{label}: {'done' if ok else 'failed'}")
        self._ui(self.check_browser_status)

    def flush_dns(self):
        log = lambda m: self._ui(self.browser_log.log, m)
        threading.Thread(target=lambda: browser_core.flush_dns(log), daemon=True).start()

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
        threading.Thread(target=self._run_analyzer_worker, daemon=True).start()

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
        threading.Thread(target=self._scan_empty_worker, daemon=True).start()

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
        threading.Thread(target=self._delete_empty_worker, args=(found,), daemon=True).start()

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
        threading.Thread(target=lambda: system_tools.reset_icon_cache(log), daemon=True).start()

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
        threading.Thread(target=self._refresh_startup_worker, daemon=True).start()

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
        threading.Thread(target=self._disable_startup_worker, args=(items,), daemon=True).start()

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
        threading.Thread(target=self._enable_startup_worker, args=(items,), daemon=True).start()

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
        threading.Thread(target=self._enable_schedule_worker, daemon=True).start()

    def _enable_schedule_worker(self):
        log = lambda m: self._ui(self.auto_log.log, m)
        run_command = scheduler.build_run_command()
        scheduler.create_scheduled_task(
            run_command, self.freq_var.get(), self.day_var.get(), self.time_var.get(), log
        )
        self._ui(self._refresh_schedule_status)

    def remove_schedule(self):
        threading.Thread(target=self._remove_schedule_worker, daemon=True).start()

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
            cats = len(entry.get("categories", []))
            freed = cleaner_core.format_size(entry.get("bytes_freed", 0))
            mode = entry.get("mode", "manual")
            self.history_tree.insert("", "end", values=(ts, cats, freed, mode))


# ---------------------------------------------------------------------------
# Headless auto-clean, used by the scheduled task (no window, no prompts)
# ---------------------------------------------------------------------------

def run_auto_clean():
    categories = build_full_categories()
    total_freed = 0
    cleaned_ids = []

    for cat in categories:
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

        service_stopped = cat.get("stop_service") and cleaner_core.stop_windows_update_service()
        for p in cat["paths"]:
            summary = cleaner_core.delete_dir_contents(p)
            total_freed += summary["deleted_bytes"]
        if service_stopped:
            cleaner_core.start_windows_update_service()
        cleaned_ids.append(cat["id"])

    history_log.log_cleanup({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "categories": cleaned_ids,
        "bytes_freed": total_freed,
        "mode": "auto",
    })


def main():
    if "--auto-clean" in sys.argv:
        run_auto_clean()
        return
    root = tk.Tk()
    app = CleanerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.shutdown(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
