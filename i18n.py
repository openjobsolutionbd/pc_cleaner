"""
i18n.py
-------
All user-visible text in two languages (Bangla "bn" and English "en"),
plus the tiny helper the GUI uses to look text up.

How to use:
    import i18n
    i18n.t("quick.button")                      # text in the current language
    i18n.t("quick.done", freed="1.2 GB")        # with {placeholders}
    i18n.cat_name(cat) / i18n.cat_desc(cat)     # junk-category labels

Rules that keep this safe:
  * Every key must have BOTH languages (test_i18n.py enforces it, and
    that both versions use the same {placeholders}).
  * A missing key or language never crashes: it falls back to English,
    and finally to the key itself.
  * Text is only formatted when placeholders are passed, so literal
    braces elsewhere are safe.

The default is English for now: Tkinter cannot always shape Bengali
conjuncts and vowel signs correctly (seen on Linux; NOT yet verified on
Windows), so Bangla stays one click away on the language button until a
Windows screenshot confirms it renders well. Then flip DEFAULT_LANG to
"bn". The user's choice is saved by settings.py.
"""

LANGS = ("bn", "en")
DEFAULT_LANG = "en"

_current = DEFAULT_LANG


def set_language(lang: str) -> bool:
    """Switch the current language. Unknown codes are ignored (False)."""
    global _current
    if lang not in LANGS:
        return False
    _current = lang
    return True


def get_language() -> str:
    return _current


def other_language() -> str:
    return "en" if _current == "bn" else "bn"


def t(key: str, **kwargs) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry.get("en") or key
    return text.format(**kwargs) if kwargs else text


def cat_name(cat: dict) -> str:
    """Display name of a junk category (falls back to the data's own name)."""
    key = f"cat.{cat.get('id')}.name"
    return t(key) if key in STRINGS else cat.get("name", "")


def cat_desc(cat: dict) -> str:
    key = f"cat.{cat.get('id')}.desc"
    return t(key) if key in STRINGS else cat.get("desc", "")


STRINGS = {
    # ---- header / tabs
    "app.tagline": {
        "en": "Free up space and keep your PC tidy  ·  v{version}",
        "bn": "জায়গা খালি করুন, PC গুছিয়ে রাখুন  ·  v{version}",
    },
    "header.drive": {
        "en": "{drive}  {free} free of {total}",
        "bn": "{drive}  {total}-এর মধ্যে {free} খালি",
    },
    "lang.switch": {"en": "বাংলা", "bn": "English"},
    "lang.busy": {
        "en": "A task is running. Please change the language when it finishes.",
        "bn": "একটা কাজ চলছে। কাজ শেষ হলে ভাষা বদলান।",
    },
    "tab.quick": {"en": "Quick Clean", "bn": "দ্রুত পরিষ্কার"},
    "tab.junk": {"en": "Junk Cleanup", "bn": "জাঙ্ক ফাইল পরিষ্কার"},
    "tab.browser": {"en": "Browser & Network", "bn": "ব্রাউজার ও নেটওয়ার্ক"},
    "tab.startup": {"en": "Startup Manager", "bn": "স্টার্টআপ ম্যানেজার"},
    # ---- common
    "common.confirm": {"en": "Confirm", "bn": "নিশ্চিত করুন"},
    "common.error": {"en": "Error", "bn": "ত্রুটি"},
    "common.nothing_selected": {"en": "Nothing selected", "bn": "কিছু বাছাই করা হয়নি"},
    "common.done": {"en": "done", "bn": "হয়েছে"},
    "common.failed": {"en": "failed", "bn": "হয়নি"},
    # ---- quick tab
    "quick.title": {"en": "Everyday Cleanup", "bn": "প্রতিদিনের পরিষ্কার"},
    "quick.desc": {
        "en": "Only safe junk files (Temp, Cache, Recycle Bin, etc.) will be cleaned.\nDocuments, photos, and programs are never touched.",
        "bn": "শুধু নিরাপদ জাঙ্ক ফাইল (Temp, ক্যাশ, Recycle Bin ইত্যাদি) পরিষ্কার হবে।\nআপনার ডকুমেন্ট, ছবি ও প্রোগ্রাম কখনো ছোঁয়া হয় না।",
    },
    "quick.button": {"en": "Clean Now", "bn": "এখনই পরিষ্কার করুন"},
    "quick.never": {
        "en": "No cleanup has been run yet.",
        "bn": "এখনো কোনো পরিষ্কার করা হয়নি।",
    },
    "quick.last": {
        "en": "Last cleaned: {when}  ·  {freed} freed",
        "bn": "শেষ পরিষ্কার: {when}  ·  {freed} খালি হয়েছিল",
    },
    "quick.confirm": {
        "en": "Clean safe junk files (Temp, Cache, Recycle Bin, etc.)?\n\nDocuments, photos, and programs will not be touched.",
        "bn": "নিরাপদ জাঙ্ক ফাইল (Temp, ক্যাশ, Recycle Bin ইত্যাদি) পরিষ্কার করবেন?\n\nডকুমেন্ট, ছবি ও প্রোগ্রাম ছোঁয়া হবে না।",
    },
    "quick.cleaning": {"en": "Cleaning…", "bn": "পরিষ্কার হচ্ছে…"},
    "quick.done": {"en": "{freed} of space freed.", "bn": "{freed} জায়গা খালি হয়েছে।"},
    "quick.skipped_admin": {
        "en": "\n\n{n} skipped without Administrator rights (these can be cleaned from the Junk Cleanup tab in Administrator mode).",
        "bn": "\n\nAdministrator অধিকার ছাড়া {n}টা ক্যাটাগরি বাদ গেছে (Administrator মোডে \"জাঙ্ক ফাইল পরিষ্কার\" ট্যাব থেকে এগুলো পরিষ্কার করা যাবে)।",
    },
    "quick.refused": {
        "en": "\n\n{n} skipped for safety: its folder is a protected system or personal folder (check your Windows TEMP setting). Nothing was deleted there.",
        "bn": "\n\nনিরাপত্তার জন্য {n}টা ক্যাটাগরি বাদ দেওয়া হয়েছে: এর ফোল্ডার একটা সুরক্ষিত সিস্টেম বা ব্যক্তিগত ফোল্ডার (আপনার Windows-এর TEMP সেটিং দেখুন)। সেখানে কিছু মোছা হয়নি।",
    },
    "quick.history_fail": {
        "en": "\n\nCouldn't save to the history log.",
        "bn": "\n\nপরিষ্কারের ইতিহাস সেভ করা যায়নি।",
    },
    # ---- junk tab
    "junk.admin_banner": {
        "en": "⚠  Not running as Administrator — some categories will be skipped.",
        "bn": "⚠  Administrator হিসেবে চালানো হয়নি — কিছু ক্যাটাগরি বাদ যাবে।",
    },
    "junk.restart_admin": {
        "en": "Restart as Administrator",
        "bn": "Administrator হিসেবে আবার চালু করুন",
    },
    "junk.needs_admin": {"en": "  (needs Administrator)", "bn": "  (Administrator লাগবে)"},
    "badge.safe": {
        "en": "  Safe — daily cleanup  ",
        "bn": "  নিরাপদ — প্রতিদিন পরিষ্কার করা যায়  ",
    },
    "badge.caution": {"en": "  Use caution  ", "bn": "  সাবধানে ব্যবহার করুন  "},
    "junk.scan": {"en": "Scan", "bn": "স্ক্যান"},
    "junk.clean_selected": {"en": "Clean Selected", "bn": "বাছাইগুলো পরিষ্কার করুন"},
    "junk.total_none": {"en": "Total reclaimable: —", "bn": "মোট খালি করা যাবে: —"},
    "junk.total": {"en": "Total reclaimable: {size}", "bn": "মোট খালি করা যাবে: {size}"},
    "junk.scan_done": {"en": "Scan complete.", "bn": "স্ক্যান শেষ।"},
    "junk.select_one": {
        "en": "Please select at least one category.",
        "bn": "অন্তত একটা ক্যাটাগরি বাছাই করুন।",
    },
    "junk.confirm_title": {"en": "Confirm cleanup", "bn": "পরিষ্কার নিশ্চিত করুন"},
    "junk.confirm_body": {
        "en": "Delete files in {n} selected categories?\n\nThese are temporary/cache files only — no personal documents, photos, or programs will be touched.",
        "bn": "বাছাই করা {n}টা ক্যাটাগরির ফাইল মুছবেন?\n\nএগুলো শুধু সাময়িক/ক্যাশ ফাইল — আপনার ডকুমেন্ট, ছবি বা প্রোগ্রাম ছোঁয়া হবে না।",
    },
    "junk.log.skip_admin": {
        "en": "Skipped {name} — needs Administrator.",
        "bn": "{name} বাদ গেছে — Administrator লাগবে।",
    },
    "junk.log.bin_emptied": {"en": "Recycle Bin emptied.", "bn": "Recycle Bin খালি করা হয়েছে।"},
    "junk.log.bin_failed": {
        "en": "Could not empty Recycle Bin.",
        "bn": "Recycle Bin খালি করা যায়নি।",
    },
    "junk.log.service_fail": {
        "en": "Skipped {name} — could not stop Windows Update service.",
        "bn": "{name} বাদ গেছে — Windows Update সার্ভিস বন্ধ করা যায়নি।",
    },
    "junk.log.protected": {
        "en": "Skipped {name} — its folder is protected (check your Windows settings).",
        "bn": "{name} বাদ গেছে — এর ফোল্ডার সুরক্ষিত (আপনার Windows সেটিং দেখুন)।",
    },
    "junk.log.freed": {"en": "{name}: freed {size}", "bn": "{name}: {size} খালি হয়েছে"},
    "junk.log.done": {
        "en": "Done. Freed approximately {size}.",
        "bn": "শেষ। প্রায় {size} খালি হয়েছে।",
    },
    "junk.log.history_fail": {
        "en": "Warning: could not save this cleanup to the history log.",
        "bn": "সতর্কতা: এই পরিষ্কারের ইতিহাস সেভ করা যায়নি।",
    },
    "junk.log.space": {
        "en": "Free space on {drive}: {before} -> {after}",
        "bn": "{drive}-তে খালি জায়গা: {before} -> {after}",
    },
    "junk.summary.freed": {
        "en": "Freed approximately {size}.",
        "bn": "প্রায় {size} খালি হয়েছে।",
    },
    "junk.summary.drive": {"en": "Free space on {drive}", "bn": "{drive}-তে খালি জায়গা"},
    "junk.summary.before": {"en": "  Before:  {size}", "bn": "  আগে:  {size}"},
    "junk.summary.after": {"en": "  After:   {size}", "bn": "  পরে:   {size}"},
    "junk.summary.gained": {"en": "  Gained:  {size}", "bn": "  বেড়েছে:  {size}"},
    "junk.complete_title": {"en": "Cleanup complete", "bn": "পরিষ্কার শেষ"},
    "admin.restart_fail": {
        "en": "Could not request Administrator restart (code {code}).\nTry right-clicking the app and choosing 'Run as administrator'.",
        "bn": "Administrator হিসেবে আবার চালু করার অনুরোধ করা যায়নি (কোড {code})।\nঅ্যাপে রাইট-ক্লিক করে 'Run as administrator' বেছে নিন।",
    },
    "admin.restart_exc": {
        "en": "Could not restart as administrator: {err}",
        "bn": "Administrator হিসেবে আবার চালু করা যায়নি: {err}",
    },
    # ---- browser tab
    "br.history_title": {"en": "Browsing History", "bn": "ব্রাউজিং হিস্ট্রি"},
    "br.history_desc": {
        "en": "Clears visited-site history only. Cookies, saved passwords, and logins are never touched — you will not be logged out of any site.",
        "bn": "শুধু দেখা সাইটের হিস্ট্রি মোছে। Cookies, সেভ করা পাসওয়ার্ড ও লগইন কখনো ছোঁয়া হয় না — কোনো সাইট থেকে লগআউট হবেন না।",
    },
    "br.status_initial": {
        "en": "Click \"Check Status\" to scan.",
        "bn": "স্ক্যান করতে \"অবস্থা দেখুন\" চাপুন।",
    },
    "br.check": {"en": "Check Status", "bn": "অবস্থা দেখুন"},
    "br.clear": {"en": "Clear Browsing History", "bn": "ব্রাউজিং হিস্ট্রি মুছুন"},
    "br.network_title": {"en": "Network", "bn": "নেটওয়ার্ক"},
    "br.network_desc": {
        "en": "Clears stale website-address lookups. Can fix some \"site won't load\" issues.",
        "bn": "পুরনো ওয়েবসাইট-ঠিকানার তথ্য মোছে। কিছু \"সাইট খুলছে না\" সমস্যা ঠিক হতে পারে।",
    },
    "br.flush": {"en": "Flush DNS Cache", "bn": "DNS ক্যাশ পরিষ্কার করুন"},
    "br.entry": {
        "en": "{label}: {count} history entries{status}",
        "bn": "{label}: {count}টা হিস্ট্রি এন্ট্রি{status}",
    },
    "br.running": {
        "en": " (running — close it first)",
        "bn": " (চালু আছে — আগে বন্ধ করুন)",
    },
    "br.none": {
        "en": "No supported browsers found (Chrome/Edge).",
        "bn": "কোনো সমর্থিত ব্রাউজার পাওয়া যায়নি (Chrome/Edge)।",
    },
    "br.confirm": {
        "en": "Clear browsing history for all detected browsers?\n\nThis will NOT log you out of any site.",
        "bn": "পাওয়া সব ব্রাউজারের হিস্ট্রি মুছবেন?\n\nএতে কোনো সাইট থেকে লগআউট হবেন না।",
    },
    "br.log.skip": {
        "en": "Skipped {label} — please close it first.",
        "bn": "{label} বাদ গেছে — আগে ব্রাউজার বন্ধ করুন।",
    },
    "br.log.result": {"en": "{label}: {result}", "bn": "{label}: {result}"},
    # ---- startup tab
    "st.desc1": {
        "en": "Programs that launch automatically when Windows starts.",
        "bn": "Windows চালু হলে যেসব প্রোগ্রাম নিজে থেকে চালু হয়।",
    },
    "st.desc2": {
        "en": "Disabling here is reversible — you can always re-enable from this list.",
        "bn": "এখানে বন্ধ করলে আবার চালু করা যায় — এই তালিকা থেকেই ফিরিয়ে আনতে পারবেন।",
    },
    "st.refresh": {"en": "Refresh", "bn": "রিফ্রেশ"},
    "st.disable": {"en": "Disable Selected", "bn": "বাছাইগুলো বন্ধ করুন"},
    "st.enable": {"en": "Enable Selected", "bn": "বাছাইগুলো চালু করুন"},
    "st.col.name": {"en": "Name", "bn": "নাম"},
    "st.col.location": {"en": "Location", "bn": "অবস্থান"},
    "st.col.status": {"en": "Status", "bn": "অবস্থা"},
    "st.enabled": {"en": "Enabled", "bn": "চালু"},
    "st.disabled": {"en": "Disabled", "bn": "বন্ধ"},
    "st.found": {"en": "Found {n} startup item(s).", "bn": "{n}টা স্টার্টআপ আইটেম পাওয়া গেছে।"},
    "st.select_enabled": {
        "en": "Select one or more enabled items first.",
        "bn": "আগে এক বা একাধিক চালু আইটেম বাছাই করুন।",
    },
    "st.select_disabled": {
        "en": "Select one or more disabled items first.",
        "bn": "আগে এক বা একাধিক বন্ধ আইটেম বাছাই করুন।",
    },
    "st.log.result": {"en": "{name}: {result}", "bn": "{name}: {result}"},
    "st.res.disabled": {"en": "disabled", "bn": "বন্ধ করা হয়েছে"},
    "st.res.enabled": {"en": "enabled", "bn": "চালু করা হয়েছে"},
    # ---- safety-net dialogs
    "err.title": {"en": "A small problem occurred", "bn": "ছোট একটা সমস্যা হয়েছে"},
    "err.gui_body": {
        "en": "An unexpected problem occurred, but the app is still running and no files were deleted.\n\nDetails were saved to error_log.json — please include this file when you report the problem so it can be fixed quickly.",
        "bn": "একটা অপ্রত্যাশিত সমস্যা হয়েছিল, কিন্তু অ্যাপ চলছে এবং কোনো ফাইল মোছা হয়নি।\n\nবিস্তারিত error_log.json ফাইলে সংরক্ষিত হয়েছে — সমস্যা জানানোর সময় এই ফাইলটা সাথে দিলে দ্রুত ঠিক করা যাবে।",
    },
    "err.worker_body": {
        "en": "An unexpected problem occurred while a task was running and it stopped, but the rest of the app is working fine.\n\nDetails were saved to error_log.json.",
        "bn": "একটা কাজ চলার সময় অপ্রত্যাশিত সমস্যা হয়েছিল এবং সেটা থেমে গেছে, কিন্তু বাকি অ্যাপ ঠিকঠাক চলছে।\n\nবিস্তারিত error_log.json ফাইলে সংরক্ষিত হয়েছে।",
    },
    "err.start_title": {"en": "Could not start", "bn": "চালু করা যায়নি"},
    "err.start_body": {
        "en": "PC Cleaner could not start.\n\n{kind}: {err}\n\nDetails were saved to error_log.json — please include this file when you report the problem.",
        "bn": "PC Cleaner চালু করতে সমস্যা হয়েছে।\n\n{kind}: {err}\n\nবিস্তারিত error_log.json ফাইলে সংরক্ষিত হয়েছে — সমস্যা জানানোর সময় এই ফাইলটা সাথে দিন।",
    },
    # ---- junk categories (name + description, keyed by category id)
    "cat.user_temp.name": {"en": "User Temp Files", "bn": "ইউজার Temp ফাইল"},
    "cat.user_temp.desc": {
        "en": "Temporary files created by programs. Builds up constantly.",
        "bn": "প্রোগ্রামের তৈরি সাময়িক ফাইল। প্রতিদিন জমতে থাকে।",
    },
    "cat.windows_temp.name": {"en": "Windows Temp Files", "bn": "Windows Temp ফাইল"},
    "cat.windows_temp.desc": {
        "en": "System-level temp files. Safe to delete.",
        "bn": "সিস্টেমের সাময়িক ফাইল। মুছে ফেলা নিরাপদ।",
    },
    "cat.chrome_cache.name": {"en": "Chrome Browser Cache", "bn": "Chrome ব্রাউজার ক্যাশ"},
    "cat.chrome_cache.desc": {
        "en": "Temporary copies of website files/images, across every profile. Sites may load slightly slower the first time after clearing.",
        "bn": "ওয়েবসাইটের ফাইল/ছবির সাময়িক কপি (সব প্রোফাইলে)। মোছার পর প্রথমবার সাইট একটু ধীরে খুলতে পারে।",
    },
    "cat.edge_cache.name": {"en": "Edge Browser Cache", "bn": "Edge ব্রাউজার ক্যাশ"},
    "cat.edge_cache.desc": {
        "en": "Microsoft Edge's temporary browsing files, across every profile.",
        "bn": "Microsoft Edge-এর সাময়িক ব্রাউজিং ফাইল (সব প্রোফাইলে)।",
    },
    "cat.thumbnail_cache.name": {"en": "Thumbnail Cache", "bn": "থাম্বনেইল ক্যাশ"},
    "cat.thumbnail_cache.desc": {
        "en": "Preview images for photos/videos in folders. Regenerates automatically.",
        "bn": "ফোল্ডারে ছবি/ভিডিওর প্রিভিউ। নিজে থেকে আবার তৈরি হয়।",
    },
    "cat.wer_reports.name": {"en": "Error Report Files", "bn": "এরর রিপোর্ট ফাইল"},
    "cat.wer_reports.desc": {
        "en": "Crash reports saved for diagnostics only.",
        "bn": "শুধু সমস্যা নির্ণয়ের জন্য রাখা ক্র্যাশ রিপোর্ট।",
    },
    "cat.crash_dumps.name": {
        "en": "Crash Dump Files (Minidump)",
        "bn": "ক্র্যাশ ডাম্প ফাইল (Minidump)",
    },
    "cat.crash_dumps.desc": {
        "en": "System crash diagnostic files. Safe to delete unless you're actively debugging a crash.",
        "bn": "সিস্টেম ক্র্যাশের ডায়াগনস্টিক ফাইল। ক্র্যাশের কারণ খুঁজছেন না হলে মুছে ফেলা নিরাপদ।",
    },
    "cat.prefetch.name": {"en": "Prefetch Files (Optional)", "bn": "Prefetch ফাইল (ঐচ্ছিক)"},
    "cat.prefetch.desc": {
        "en": "Files Windows keeps to speed up program launches. Deleting means the first launch after may be a bit slower.",
        "bn": "প্রোগ্রাম দ্রুত খুলতে Windows যা জমিয়ে রাখে। মুছলে পরের প্রথমবার একটু ধীরে খুলতে পারে।",
    },
    "cat.recycle_bin.name": {"en": "Recycle Bin", "bn": "Recycle Bin"},
    "cat.recycle_bin.desc": {
        "en": "Files you've already deleted, sitting in the bin.",
        "bn": "আপনি আগেই মুছে ফেলেছেন, কিন্তু বিনে পড়ে আছে এমন ফাইল।",
    },
}
