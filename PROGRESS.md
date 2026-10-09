# PC Cleaner — প্রজেক্ট প্রেক্ষাপট

> এই ফাইলটা নতুন চ্যাটে zip আপলোড করলে দ্রুত প্রজেক্ট বোঝার জন্য। পুরনো কাজের ডিটেইল লগ রাখা হয় না — শুধু বর্তমান অবস্থা।

## প্রজেক্ট কী

Windows-এর জন্য একটা Junk cleanup + সিস্টেম মেইনটেন্যান্স Python/tkinter GUI অ্যাপ (নাম: **PC Cleaner**, বর্তমান ভার্সন **v1.5.6**), `.exe`-এ বিল্ড হয়। ব্যবহারকারী কোডিং জানেন না, মোবাইল থেকে কাজ করেন — তাই যেকোনো পরিবর্তন সবসময় স্পষ্ট বাংলা ব্যাখ্যাসহ, অ্যাপ্রুভাল নিয়ে করতে হবে।

**মূল উদ্দেশ্য (ব্যবহারকারীর নিজের ভাষায়, স্পষ্টভাবে বলা হয়েছে):** পিসিতে নিয়মিত জমে থাকা জাংক ফাইল ক্লিন রাখা, শাটডাউনের সময় এটা অটোমেটিক হওয়া, ব্রাউজার যেন স্মুথ ও দ্রুত থাকে সেজন্য ব্রাউজারে জমা ময়লা পরিষ্কার করা, আর সবচেয়ে গুরুত্বপূর্ণ — **এমন কোনো ফাইল কখনো ডিলিট না হওয়া যেটা কম্পিউটার চালাতে সমস্যা করে**। যেকোনো নতুন ফিচার বিবেচনা করার সময় এই চারটা লক্ষ্যের সাথে মেলে কিনা যাচাই করা উচিত — বিশেষ করে নিরাপত্তার শর্তটা (নিচের হার্ড গ্যারান্টি লিস্ট) কখনো শিথিল করা যাবে না, এমনকি স্পিড বা কনভিনিয়েন্সের জন্যও না।

**UI ডিজাইন নীতি (স্পষ্টভাবে বলা হয়েছে):** অ্যাপটা যেন হিজিবিজি/অপশনে ভরপুর না হয়ে দেখতে ক্লিন থাকে — অপশন কম থাকবে, যাতে কাজের ফোকাস থেকে মনোযোগ না কাড়ে। তাই নতুন ফিচার যোগ করার সময় প্রথমে দেখতে হবে এটা কি existing ক্যাটাগরি/বাটনের ভেতরেই (লজিক আরও ভালো করে) সমাধান করা যায়, নাকি সত্যিই নতুন বাটন/চেকবক্স দরকার — নতুন UI element যোগ করা শেষ অপশন হওয়া উচিত, প্রথম না।

**৪টা ট্যাব:** Quick Clean, Junk Cleanup, Browser & Network, Startup Manager।

**নিরাপত্তার হার্ড গ্যারান্টি (কখনো ভাঙা যাবে না):** Password কখনো ছোঁয়া হয় না, Cookies কখনো মোছা হয় না, root ফোল্ডার কখনো ডিলিট হয় না, Startup Manager-এর disable সবসময় reversible, অ্যাপ কখনো নেটওয়ার্কে কিছু পাঠায় না (সম্পূর্ণ অফলাইন)।

## ফাইল কাঠামো

| ফাইল | কাজ |
|---|---|
| `pc_cleaner.py` | মেইন GUI, Theme/styling, `__version__`। ৪টা ট্যাব: Quick Clean, Junk Cleanup, Browser & Network, Startup Manager |
| `cleaner_core.py` | Junk file ক্লিনআপ লজিক |
| `browser_core.py` | ব্রাউজার হিস্ট্রি/ক্যাশ ক্লিনআপ |
| `system_tools.py` | Disk analyzer, empty folder finder, icon cache, drive helpers, root/critical-folder protection (`is_protected_root`) — **GUI ট্যাব v1.4.0-এ সরানো হয়েছে, মডিউল ও টেস্ট রয়ে গেছে** (header-এর ফ্রি-স্পেস pill এখনো এটা ব্যবহার করে) |
| `startup_manager.py` | Startup প্রোগ্রাম চালু/বন্ধ (registry backup key: `PCCleanerBackup`) — Startup Manager ট্যাবে |
| `history_log.py` | ক্লিনআপ লগ (ডেটা ফোল্ডার: `%LOCALAPPDATA%\PCCleaner`) — এখনো প্রতিটা ক্লিনআপে লেখা হয়, শুধু দেখার UI নেই |
| `error_log.py` | এরর লগ (`error_log.json`) — এখনো প্রতিটা এররে লেখা হয়, শুধু দেখার UI নেই |
| `test_*.py` | প্রতিটা মডিউলের ইউনিট/ইন্টিগ্রেশন টেস্ট (১৬৩টা, GUI-সহ) |
| `Start_Here.bat` / `build_exe.bat` / `run_tests.bat` | লঞ্চার / .exe বিল্ড (`PCCleaner.exe`, `--onedir`) / টেস্ট রানার |
| `lint.bat` / `pyproject.toml` | ঐচ্ছিক dev-টুল: Ruff (lint) + mypy (type check) — অ্যাপে বান্ডেল হয় না, শুধু ডেভেলপমেন্টে ব্যবহার হয়

## যাচাইয়ের পদ্ধতি

এই sandbox-এ `apt-get install python3-tk xvfb` করে `xvfb-run python3 -m unittest discover` দিয়ে সব ১৬৩টা টেস্ট (GUI-সহ) বাস্তবে চালিয়ে যাচাই করা যায় — GUI ভিজুয়াল যাচাইয়ের জন্য headless স্ক্রিনশটও নেওয়া সম্ভব। কোড শুধু পড়ে/কম্পাইল করে অনুমান না করে সবসময় বাস্তবে চালিয়ে যাচাই করা হয়। (নোট: এই নির্দিষ্ট sandbox session-এ apt-এর নেটওয়ার্ক অ্যাক্সেস ব্লকড ছিল বলে `python3-tk` ইনস্টল করা যায়নি — তখন `libarchive`/`ctypes` দিয়ে ম্যানুয়ালি আর্কাইভ পড়া হয়েছে এবং একটা হালকা tkinter স্টাব দিয়ে GUI-ওয়্যারিং যাচাই করা হয়েছে; non-GUI ১৮৩টা টেস্ট বাস্তবে রান করে দেখা হয়েছে। CI-তে (GitHub Actions) এখন Xvfb ইনস্টল করা থাকায় GUI টেস্টসহ সবকটাই সত্যিই রান হয়।)

## Quick Clean ট্যাব (রোজকার ব্যবহারের জন্য)

সবচেয়ে প্রথম ট্যাব — কোনো checkbox/choice নেই, শুধু একটা "Clean Now" বাটন। শুধু `badge == "safe"` ক্যাটাগরিগুলো ক্লিন করে (Junk Cleanup ট্যাবের green-badge ক্যাটাগরির সাবসেট), caution ক্যাটাগরি (Windows Update Old Files, Crash Dumps, Prefetch) কখনো ছোঁয় না। History log-এ `mode: "quick"` হিসেবে আলাদাভাবে লগ হয় (manual/auto থেকে আলাদা করার জন্য)। শেষ কবে ক্লিন করা হয়েছিল তা ট্যাবেই দেখায়। Admin-প্রয়োজনীয় safe ক্যাটাগরি (Windows Temp, Delivery Optimization) non-admin মোডে gracefully স্কিপ হয়, ঠিক Junk Cleanup ট্যাবের মতোই।

**যাচাইয়ে ধরা পড়া ২টা বাগ, ঠিক করা হয়েছে:** (১) অব্যবহৃত `free_before` প্যারামিটার পুরো chain-এ পাস হচ্ছিল কিন্তু কোথাও ব্যবহার হচ্ছিল না — সরিয়ে ফেলা হয়েছে, যেহেতু Quick Clean-এর ডিজাইনে "before/after" তুলনার প্রতিশ্রুতি কখনোই ছিল না। (২) history log সেভ ব্যর্থ হলে যে warning বার্তা দেখানোর কথা ছিল, সেটা ঠিক তার পরের কোডেই success message দিয়ে নিঃশব্দে ওভাররাইট হয়ে যাচ্ছিল — ব্যবহারকারী কখনো এই warning দেখতে পেত না। এখন দুটো বার্তা একসাথে মিলিয়ে দেখানো হয়।

## নিরাপত্তা: history_log.py-এ race condition ফিক্স

**বাগ:** `history_log.log_cleanup()` কোনো file locking ছাড়াই read-modify-write করত। অ্যাপে তিনটা আলাদা জায়গা থেকে (Quick Clean ট্যাব, Junk Cleanup ট্যাব, এবং আলাদা প্রসেস হিসেবে চলা scheduled auto-clean টাস্ক) এটা কল হতে পারে — দুইটা কল প্রায় একই সময়ে শেষ হলে একটার এন্ট্রি নিঃশব্দে হারিয়ে যেতে পারত (lost update)। থ্রেড দিয়ে ইচ্ছাকৃতভাবে race window তৈরি করে এই বাগ বাস্তবে প্রমাণ করা হয়েছে (৩০ ট্রায়ালে ১টা লস)।

**ফিক্স:** `msvcrt`/`fcntl` দিয়ে exclusive file lock যোগ করা হয়েছে (যেটা উপলব্ধ না থাকলে gracefully স্কিপ হয়, `startup_manager.py`-এর `_HAS_WINREG` প্যাটার্নের মতো)। ফাইল open করার জন্য `"a+"` মোড ব্যবহার করা হয়েছে (আগে ছিল আলাদা `exists()`-চেক-তারপর-create — এটাও lock-এর বাইরে একটা দ্বিতীয় race window তৈরি করছিল, যেটা প্রথম ফিক্সের পরও ১০৭-টেস্ট সুট চালিয়ে ধরা পড়েছিল)। ফিক্সের পর ২০০ ট্রায়াল ও ৫ বার পুরো টেস্ট সুট চালিয়ে কোনো data loss পাওয়া যায়নি।

## নিরাপত্তা: root/critical-folder guard

`system_tools.py`-তে `is_protected_root()` / `is_drive_root()` যোগ হয়েছে — ইউজার-চোজেন যেকোনো ফোল্ডার (folder picker দিয়ে) থেকে drive root বা critical ফোল্ডার (Windows, Program Files, Users, Documents/Desktop/Downloads ইত্যাদি — শুধু user profile-এর নিচে) সরাসরি স্ক্যান/ডিলিট করা কোড-লেভেলে ব্লক করা আছে। `find_empty_folders` scan-এর শুরুতে চেক করে, `delete_empty_folders` প্রতিটা path delete করার ঠিক আগে আবার independently চেক করে (double-validation), `analyze_folder` শুধু bare drive root (`C:\`) refuse করে। ভেতরের সাবফোল্ডার (যেমন `Documents\OldReports`) স্বাভাবিকভাবে কাজ করে — শুধু critical ফোল্ডারটা নিজে root হিসেবে দিলে refuse হয়।

## Junk Cleanup: নিরাপত্তা ব্যাজ

প্রতিটা junk category-তে (`cleaner_core.py`-এর `build_categories()` এবং `pc_cleaner.py`-এর Recycle Bin entry) এখন `"badge"` key আছে — `"safe"` অথবা `"caution"`। GUI-তে নামের পাশে রঙিন লেবেল দেখা যায় (সবুজ "Safe — daily cleanup" / হলুদ "Use caution")।

- **safe + ডিফল্টে checked:** User Temp, Windows Temp, Chrome Cache, Edge Cache, Thumbnail Cache, Error Reports, Recycle Bin
- **caution + ডিফল্টে unchecked:** Crash Dumps, Prefetch

আগে Crash Dumps ডিফল্টে checked ছিল — ইউজারের অনুরোধে এখন unchecked (ইউজার নিজে চাইলে টিক দেবে)। "Windows Update Old Files" আর "Delivery Optimization Files" ক্যাটাগরি দুটো এই মেশিনে Windows Update স্থায়ীভাবে বন্ধ থাকায় আগেই সরানো হয়েছে (`disable_windows_update.bat/.reg` দেখুন)।

**Chrome/Edge Cache এখন multi-profile + multi-folder (v1.4.1):** UI-তে কোনো নতুন বাটন/চেকবক্স নেই — একই দুইটা ক্যাটাগরি, শুধু ভেতরের `"paths"` এখন `cleaner_core._chromium_cache_paths()` দিয়ে ডাইনামিকভাবে বসে: `browser_core.get_browser_profiles()` দিয়ে প্রতিটা প্রোফাইল (আগে শুধু Default) খুঁজে বের করে প্রতিটার Cache, Code Cache, GPUCache, DawnCache, Service Worker CacheStorage/ScriptCache (আগে শুধু main Cache ফোল্ডার) যোগ করে। এই ক্যাটাগরি safe + ডিফল্টে checked, তাই Quick Clean-ও স্বয়ংক্রিয়ভাবে এই সুবিধা পায়। ইউজারের স্পষ্ট নির্দেশ ছিল app-এ নতুন অপশন/বাটন যোগ না করে existing ফিচার আরও ভালো করার — এই ধরনের রিকোয়েস্ট এলে সবসময় আগে দেখতে হবে existing ক্যাটাগরির ভেতরেই সমাধান হয় কিনা।

## v1.5.6 — হিস্ট্রি মোছার পরও URL ফাইলে থেকে যেত

নতুন বাগ খোঁজার অনুরোধে পাওয়া, ব্যবহারকারীর অনুমতিতে ঠিক করা। `clear_browsing_history()` টেবিলের সারি মুছত কিন্তু `secure_delete` বন্ধ থাকলে মোছা পেজের লেখা ফাইলে থেকে যেত, আর সেই ফাইলই `History`-র জায়গায় ফেরত যেত। reproduce করা হয়েছে (২০০টা URL, অ্যাপ ০ সারি দেখাচ্ছিল, ফাইলে ২০০টাই পাওয়া যাচ্ছিল — SQLite স্টক ডিফল্টে চালিয়ে)। ফিক্স: `PRAGMA secure_delete=ON` + মোছার পর best-effort `VACUUM` (ব্যর্থ হলে ক্লিয়ার সফলই থাকে)। ৪টা নতুন টেস্ট (`test_browser_core.py`, `TestClearedHistoryIsNotRecoverableFromTheFile`) — প্রতিটাতে SQLite-এর `secure_delete` জোর করে বন্ধ করা হয় যাতে ফল প্ল্যাটফর্ম-নির্ভর না হয়; ২টা পুরনো কোডে fail করে। টেস্ট ১৫৯ → ১৬৩। **সীমা:** Windows-এ SQLite-এর আসল ডিফল্ট সরাসরি যাচাই হয়নি। Cookies/Login Data এখনো কখনো খোলা হয় না।

## v1.5.5 — `format_size()`: "1024.0 KB" বাগ

বাগ খোঁজার সময় পাওয়া, পরে ব্যবহারকারীর অনুমতিতে ঠিক করা। `format_size()` রাউন্ড করার **আগের** মান ১০২৪-এর সাথে তুলনা করত, তাই ১,০৪৮,৫৭৫ বাইট "1.0 MB"-এর বদলে "1024.0 KB" দেখাত (MB/GB/TB সীমাতেও একই)। স্ক্রিপ্ট চালিয়ে reproduce করা হয়েছে। ফিক্স: রাউন্ড করা মান তুলনা করা, না হলে পরের ইউনিটে যাওয়া; PB শেষ ইউনিট। নতুন ৫টা টেস্ট (`test_cleaner_core.py`, `TestFormatSize`), পুরনো কোডে ২টা (৪টা সীমার কেস) fail করে। টেস্ট ১৫৪ → ১৫৯।

## v1.5.4 — Startup Manager: নিঃশব্দ ওভাররাইট বাগ

বাগ খোঁজার অনুরোধে পাওয়া। `_move_file()` (`os.replace`) ও `_move_registry_value()` (`SetValueEx`) গন্তব্যে একই নামের জিনিস থাকলে চুপচাপ ওভাররাইট করত, তাই "Disable সবসময় reversible" গ্যারান্টি এক কোণে ভাঙত (Disable → প্রোগ্রাম নিজেকে আবার যোগ করে → আবার Disable = প্রথম ব্যাকআপ লস; Enable-এর সময় পুরনো কপি নতুনটাকে ঢেকে দেওয়া)। দুই ক্ষেত্রই স্ক্রিপ্ট চালিয়ে reproduce করা হয়েছে। ফিক্স: গন্তব্যে **ভিন্ন** কিছু থাকলে কিছু না বদলে `False` + লগ; **হুবহু এক** থাকলে সরানো চলে (নইলে সাধারণ ক্ষেত্রে ব্যবহারকারী আটকে যেত)। `filecmp` ইমপোর্ট ও `_same_file_content()` হেল্পার যোগ। নতুন ৬টা টেস্ট (`test_startup_manager.py`), ৪টা পুরনো কোডে fail করে। টেস্ট ১৪৮ → ১৫৪। **জানা সীমা:** ভিন্ন কিছু থাকলে অ্যাপ নিজে মেটায় না — ইচ্ছাকৃত। (আরেকটা ছোট বাগ — `format_size()` — v1.5.5-এ ঠিক হয়েছে, নিচে।)

## v1.5.3 — স্ক্যান সাইজ বনাম আসল ক্লিন (file_filter উপেক্ষা)

`pc_cleaner._scan_junk_worker()` ক্যাটাগরির `file_filter` না মেনে `get_dir_size(p)` দিয়ে ফোল্ডারের সব ফাইল গুনত — Thumbnail Cache ক্যাটাগরির ক্লিন শুধু `thumbcache_*` মোছে, তাই স্ক্রিনে সাইজ ও "Total reclaimable" ফুলে দেখাত (reproduce: স্ক্যান ৮১৫০ বাইট বনাম ক্লিনে ১৫০ বাইট)। ফিক্স: `cleaner_core.get_dir_size(path, file_filter=None)` — ফিল্টার থাকলে শুধু top-level মিলে যাওয়া ফাইল গোনে, সাবফোল্ডার বাদ (হুবহু `delete_dir_contents`-এর নিয়ম); স্ক্যান ওয়ার্কার ফিল্টার পাস করে। Quick Clean-এর হিসাব আগেও ঠিক ছিল (আসল মোছা বাইট গোনে)। নতুন ৪টা টেস্ট (`test_cleaner_core.py`-তে `TestGetDirSizeFileFilter`-এর ৩টা, আর `test_integration_gui.py`-তে GUI স্ক্যানের ১টা; "ফিল্টার ছাড়া আগের মতো" টেস্টটা রিগ্রেশন-গার্ড, বাকি ৩টা পুরনো কোডে fail করে যাচাই করা)। টেস্ট ১৪৪ → ১৪৮। নোট: `get_dir_size` এখনো Windows junction অনুসরণ করে কিনা — যাচাই করা হয়নি (Linux sandbox-এ junction নেই), এই ফিক্সের আওতার বাইরে।

## v1.5.2 — locked ফাইলে সাবফোল্ডার মোছা থেমে যাওয়ার বাগ

`cleaner_core.delete_dir_contents()` সাবফোল্ডার মুছত `shutil.rmtree(full)` দিয়ে, যেটা প্রথম locked ফাইলেই থেমে যায় (exception তুলে) — ফলে ওই সাবফোল্ডারের বাকি মোছার-যোগ্য ফাইল থেকে যেত আর `deleted_bytes` ০ থাকত (যদিও কিছু বাইট আসলে মুছে গেছে)। এটা ফাংশনের নিজের ডকস্ট্রিংয়ের বিরুদ্ধে ("locked ফাইল স্কিপ করে চালিয়ে যাবে"), আর বাস্তবে Temp/Chrome-Edge Cache/WER-এ প্রায়ই ঘটার কথা (ব্রাউজার চালু থাকলে)। আগে নিজে reproduce (১০ ফাইল, ১টা locked → ৭টা থেকে যায়, ০ freed), তারপর ফিক্স: নতুন `_remove_tree_best_effort()` + `_is_link_or_reparse_point()` (symlink/junction/reparse point কখনো অনুসরণ বা ডিলিট হয় না, ভেতরের সাবফোল্ডারেও)। `deleted_files` আগের মতোই শুধু top-level ফাইল গোনে, `deleted_dirs` শুধু সম্পূর্ণ মোছা top-level সাবফোল্ডার। নতুন ৩টা টেস্ট `test_cleaner_core.py`-তে; পুরনো কোডে `test_locked_file_in_subfolder_does_not_stop_the_rest` fail করে যাচাই করা হয়েছে। টেস্ট ১৪১ → ১৪৪। শুধু `cleaner_core.py` বদলেছে।

## v1.5.1 — ট্যাবের নামে `&&` বাগ

ব্যবহারকারী ধরিয়ে দিয়েছিলেন: Browser ট্যাব স্ক্রিনে "Browser && Network" দেখাচ্ছে। headless স্ক্রিনশট নিয়ে আগে reproduce করা হয়েছে (সত্যিই দুটো `&` দেখাচ্ছিল)। কারণ: ttk.Notebook ট্যাব টেক্সটে `&` বিশেষ কিছু না, তাই `"Browser && Network"` হুবহু দেখায়। ফিক্স: `pc_cleaner.py`-তে `"Browser & Network"`। নতুন টেস্ট `test_tab_titles_show_a_single_ampersand` (`TestTabStructure`)। টেস্ট ১৪০ → ১৪১। নোট: কোডের এই একটাই জায়গায় ভুল ছিল; পুরনো ডকুমেন্টেশনে কিছু জায়গায় "&&" লেখা ইতিহাস হিসেবে রাখা আছে।

## v1.5.0 — Chrome Profile Manager ও Shutdown Auto-Clean সরানো হয়েছে

ব্যবহারকারীর স্পষ্ট নির্দেশে এই দুই ফিচার ফাইল ও টেস্টসহ সম্পূর্ণ মুছে ফেলা হয়েছে। **Startup Manager রাখা হয়েছে** (প্রথমে সেটাও মুছে ফেলা হয়েছিল, পরে ব্যবহারকারী ফিরিয়ে রাখতে বলেছেন)। আগের "Startup && Shutdown" ট্যাব এখন শুধু **"Startup Manager"** নামে, ভেতরে শুধু স্টার্টআপ তালিকা ও Disable/Enable বাটন।

মোছা ফাইল: `chrome_profile_manager.py`, `shutdown_setup.py`, `shutdown_clean.py`, `test_chrome_profile_manager.py`, `test_shutdown_setup.py`। `pc_cleaner.py` থেকে সংশ্লিষ্ট UI/হ্যান্ডলার/ইমপোর্ট সরানো, `pyproject.toml` থেকে `shutdown_clean.py`-র E402 ignore সরানো। `test_integration_gui.py`-তে `TestTabStructure` এখন ঠিক ৪টা ট্যাব, "Startup Manager" নামের ট্যাব আর `startup_tree` আছে কিনা, এবং সরানো widget (`shutdown_*`, Chrome বাটন) নেই কিনা যাচাই করে; `TestShutdownCleanIntegration` (জানা flaky টেস্টসহ) মুছে গেছে। `startup_manager.py` ও `test_startup_manager.py` অপরিবর্তিত। টেস্ট ১৯৯ → ১৪০।

**নিরাপত্তা গ্যারান্টি:** পাঁচটাই অপরিবর্তিত (Password, Cookies, root ফোল্ডার, Startup disable reversible, অফলাইন) — `cleaner_core.py`/`browser_core.py`/`startup_manager.py` ছোঁয়া হয়নি।

**ব্যবহারকারীর জন্য সতর্কতা:** আগে Shutdown Clean চালু থাকলে Windows-এ Group Policy শাটডাউন স্ক্রিপ্ট বা Task Scheduler-এর `PC_Cleaner_ShutdownClean` টাস্ক থেকে যাবে — নতুন ভার্সনে অ্যাপ থেকে সেটা বন্ধ করার উপায় নেই। আপডেটের আগে পুরনো ভার্সনে "Disable Shutdown Clean" চাপা উচিত, নইলে ম্যানুয়ালি সরাতে হবে। Fast Startup অ্যাপ বন্ধ করেছিল, সেটা নিজে আবার চালু করা যাবে।

**নিচের পুরনো সেকশনগুলো (v1.4.2–v1.4.5) ইতিহাস:** সেগুলোতে `shutdown_setup.py`, `chrome_profile_manager.py` ও Shutdown Auto-Clean-এর যেসব উল্লেখ আছে সেগুলো v1.5.0-এ মুছে ফেলা হয়েছে।

**System Tools ট্যাব ও Automation & History ট্যাবের বাকি অংশ (v1.4.0-এ সরানো):** `system_tools.py` মডিউল (আর তার টেস্ট) প্রজেক্টেই আছে, শুধু GUI থেকে ডিসকানেক্ট — `system_tools.get_free_space()` এখনো header-এর ফ্রি-স্পেস pill-এর জন্য ব্যবহৃত হয়। `history_log`/`error_log` এখনো প্রতিটা ক্লিনআপ/এররে ডিস্কে লেখে, শুধু GUI-তে দেখার উপায় নেই।

## এক্সিকিউটেবল বিল্ড ও কোড-হার্ডেনিং (v1.4.2)

**exe বিল্ড:** `build_exe.bat` এখন `--onedir --noupx` ব্যবহার করে (আগে `--onefile`) — একটা `PCCleaner` ফোল্ডার বানায়, একটা মাত্র exe না। single-file + UPX-compressed PyInstaller exe অ্যান্টিভাইরাসের false-positive হিসেবে ধরার ঝুঁকি বেশি (নিজেকে প্রতিবার রান-টাইমে temp ফোল্ডারে আনপ্যাক করে — ঠিক যে আচরণ ম্যালওয়্যার হিউরিস্টিক flag করে); `--onedir` এই self-extraction ধাপটাই এড়িয়ে যায়। README-তে ইউজারকে জানানো আছে পুরো ফোল্ডার নিতে হবে, শুধু exe না, আর সাইন-না-করা exe প্রথমবার Defender সতর্কতা দেখাতে পারে সেটাও।

**ctypes নিরাপত্তা:** `cleaner_core.py` (Recycle Bin functions) আর (তখনকার) `chrome_profile_manager.py` (v1.5.0-এ মুছে ফেলা)-এর Windows API কলগুলোতে এখন explicit `argtypes`/`restype` আছে আর রিটার্ন ভ্যালু চেক করা হয় — আগে ব্যর্থ হলেও silently ভুল/stale ডেটা রিটার্ন করতে পারত। একটা real bug ধরা পড়েছিল ফিক্স করার সময়: `SHEmptyRecycleBinW`-এর HRESULT নিজে নিজে বিশ্বাসযোগ্য success সিগন্যাল না — ডকুমেন্টেড আচরণ (আর PowerShell-এর `Clear-RecycleBin` cmdlet-এর বিরুদ্ধে রিপোর্ট করা bug-ও) হলো bin আগে থেকে খালি থাকলেও একটা non-zero/error কোড রিটার্ন করে। তাই `empty_recycle_bin()` এখন HRESULT না দেখে, কল করার পরে `get_recycle_bin_size() == 0` চেক করে প্রকৃত ফলাফল যাচাই করে। ১৩টা নতুন টেস্ট এই আচরণ কভার করে (mock করা `ctypes.windll` দিয়ে, যেহেতু Linux sandbox-এ আসল Windows API নেই)।

**CI গ্যাপ ফিক্স:** `.github/workflows/tests.yml`-এ আগে টেস্ট ফাইলের নাম হাতে-লেখা লিস্ট ছিল, যেটাতে `test_chrome_profile_manager.py` আর `test_integration_gui.py` কখনো যোগ হয়নি (v1.3.0-এ chrome_profile_manager যোগ হওয়ার পরও)। এখন `unittest discover` দিয়ে সব `test_*.py` ফাইল অটোমেটিক পাওয়া যায়, আর CI-তে `python3-tk` + `xvfb` ইনস্টল করে GUI টেস্টও আসলেই রান হয় (আগে GUI টেস্ট কখনো CI-তে রান হতোই না)।

**dev-টুল:** `pyproject.toml`-এ Ruff + mypy config, `lint.bat` দিয়ে লোকালি রান করা যায়, CI-তে একটা আলাদা `lint` job হিসেবেও চলে (Ruff blocking, mypy শুধু তথ্যের জন্য যেহেতু কোডবেস type hint ছাড়াই লেখা)। Ruff দিয়ে ম্যানুয়ালি (network না থাকায় সরাসরি রান করা যায়নি এই sandbox-এ) স্ক্যান করে একটা dead import (`filedialog`, System Tools ট্যাব সরানোর সময় ব্যবহার বাদ গিয়েছিল কিন্তু import থেকে গিয়েছিল) খুঁজে ফিক্স করা হয়েছে।

## পারফরম্যান্স (v1.4.3)

Junk স্ক্যান আর ক্লিন-এর মূল দুইটা ফাংশন (`get_dir_size`, `delete_dir_contents`) `os.walk()`/`os.listdir()` + আলাদা `os.path.getsize()`/`islink()`/`isdir()` কল থেকে `os.scandir()`-এ বদলানো হয়েছে — `os.walk()` ইতিমধ্যেই ভেতরে `scandir` ব্যবহার করে কিন্তু ফলাফল হিসেবে শুধু ফাইলের নাম (string) রিটার্ন করে, তাই এরপর `getsize()` কল করলে একটা দ্বিতীয়, অপ্রয়োজনীয় stat syscall লাগে প্রতিটা ফাইলের জন্য। `os.scandir()`-এর `DirEntry` অবজেক্ট থেকে সরাসরি টাইপ/সাইজ পড়লে সেই দ্বিতীয় কলটা লাগে না — Windows-এ এটা ডকুমেন্টেড ২-২০x পার্থক্য আনতে পারে (বিশেষ করে অনেক ছোট ফাইলের ফোল্ডারে, যেমন ব্রাউজার cache — এই লোকাল Linux sandbox-এই বেঞ্চমার্কে ২x পার্থক্য দেখা গেছে)। `delete_dir_contents` নিরাপত্তা-সংবেদনশীল ফাংশন বলে রিরাইট করার সময় বিদ্যমান সব টেস্ট (root ফোল্ডার কখনো ডিলিট না হওয়া, symlink স্কিপ, locked file স্কিপ ইত্যাদি) অপরিবর্তিত রেখে যাচাই করা হয়েছে।

সাথে একটা ছোট রিডানডেন্সি ফিক্স: Chrome আর Edge cache ক্যাটাগরি বানানোর সময় `browser_core.get_browser_profiles()` আগে দুইবার কল হতো (প্রতিটা ব্রাউজারের জন্য একবার), যদিও একটা কলই দুই ব্রাউজারের প্রোফাইল ফোল্ডার স্ক্যান করে ফেলে — এখন একবারই স্ক্যান হয়, ফলাফল দুই ক্যাটাগরির মধ্যে শেয়ার হয়।

## বাগ হান্ট (v1.4.4) — ৩টা আসল বাগ পাওয়া গেছে

সম্পূর্ণ কোডবেস ফাইল-বাই-ফাইল রিভিউ করে (শুধু পড়ে না — সন্দেহজনক জায়গা পেলেই আসল Python দিয়ে reproduce করে যাচাই করা হয়েছে) ৩টা real bug পাওয়া গেছে ও ঠিক করা হয়েছে:

**১. Browsing History পরিষ্কার করার পর আবার ফিরে আসতে পারত (গুরুত্বপূর্ণ — privacy bug)।** `browser_core.clear_browsing_history()` History ফাইলের একটা কপি বানিয়ে, সেখানে DELETE চালিয়ে, তারপর কপিটা আসল জায়গায় ফেরত রাখে — কিন্তু যদি Chrome আগে অস্বাভাবিকভাবে বন্ধ হয়ে থাকে (ক্র্যাশ, force-kill, পাওয়ার লস — এগুলো বাস্তবে হয়) তাহলে আসল প্রোফাইল ফোল্ডারে একটা `History-wal` ফাইল থেকে যেতে পারে, যেটাতে পুরনো (মোছার আগের) ডেটা থাকে। এই ফাংশন সেই leftover `-wal`/`-shm` ফাইল কখনো মোছেনি — ফলে পরের বার Chrome (বা যেকোনো কিছু) প্রোফাইলটা খুললে SQLite সেই স্টেল WAL ফাইল replay করে ফেলত, আর "মোছা" হিস্ট্রি ফিরে আসত। আসল Python দিয়ে reproduce করে (subprocess crash সিমুলেট করে) নিশ্চিত করা হয়েছে বাগটা সত্যিকারের — fix না থাকলে টেস্ট fail করে দেখানো হয়েছে। এখন ক্লিয়ার করার পর মূল ফোল্ডারের leftover `-wal`/`-shm` ফাইলও মোছা হয়। (`test_browser_core.py`-তে ৪টা নতুন টেস্ট)

**২. Shutdown Auto-Clean চালু করার সময় ব্যর্থতা silently চাপা পড়ত।** `shutdown_setup.setup_shutdown_clean()` Fast Startup বন্ধ করার (`disable_fast_startup()`) রিটার্ন ভ্যালু সম্পূর্ণ উপেক্ষা করত — GPO/Task Scheduler রেজিস্ট্রেশন সফল হলেই "✅ Done, এখন থেকে প্রতি শাটডাউনে চলবে" দেখাত, এমনকি Fast Startup বন্ধ করা ব্যর্থ হলেও। কিন্তু Fast Startup চালু থাকলে Windows আসলে শাটডাউন স্ক্রিপ্ট স্কিপ করে দেয় (মডিউলের নিজের ডকস্ট্রিং-এই লেখা) — তাই ফিচারটা "enabled" দেখালেও silently কাজ নাও করতে পারত। এখন `setup_shutdown_clean()` এটা ট্র্যাক করে, আর Fast Startup বন্ধ না হলে স্পষ্ট সতর্কতা লগ করে ("Registered, but Fast Startup is still ON...")। GUI-র সাকসেস মেসেজও এখন এই অবস্থা অনুযায়ী বদলায়। (নতুন `test_shutdown_setup.py` — এই ফাইলের আগে কোনো টেস্টই ছিল না, এখন ২০টা)

**৩. Chrome Profile Manager-এ পারফরম্যান্স বাগ।** `open_profiles()` প্রতিটা প্রোফাইলের জন্য আলাদাভাবে `profile_is_open()` কল করত, আর সেটা প্রতিবার একটা নতুন PowerShell প্রসেস চালু করত (ধীর, PowerShell startup overhead) — ৩০টা প্রোফাইল খুলতে গেলে ৩০টা আলাদা PowerShell লঞ্চ হতো, শুধু "কী আগে থেকে খোলা" জানতে। এখন ব্যাচের শুরুতে একবারই চেক করে সেই ফলাফল সব প্রোফাইলের জন্য শেয়ার করে।

**অতিরিক্ত টেস্ট কভারেজ গ্যাপ পূরণ:** `startup_manager.py`-র Startup Folder (শর্টকাট ফাইল, রেজিস্ট্রি না) অংশের আগে কোনো টেস্ট ছিল না (শুধু Registry অংশের ছিল) — এখন `_move_file`, `list_startup_items` (folder scan), আর disable/enable-এর ফুল রাউন্ড-ট্রিপ কভার করা হয়েছে। মোট টেস্ট ১৬৫ → ১৯৮।

## নাম ও ভার্সনিং

অ্যাপের নাম **"Windows Cleaner"** থেকে বদলে **"PC Cleaner"** করা হয়েছে (v1.1.0-এ) — ফাইলের নাম (`windows_cleaner.py` → `pc_cleaner.py`), `.exe` নাম (`WindowsCleaner.exe` → `PCCleaner.exe`), GUI টাইটেল/হেডার, রেজিস্ট্রি ব্যাকআপ key, Task Scheduler নাম, ডেটা ফোল্ডার নাম — সব জায়গায়। ভার্সন নম্বর `pc_cleaner.py`-এর `__version__` কনস্ট্যান্টে আছে এবং GUI হেডারে দেখা যায়।

## নিরাপত্তা: অফলাইন-গ্যারান্টি ও Time ইনপুট ভ্যালিডেশন

- **`test_no_network_guarantee.py`** — নতুন স্বতন্ত্র টেস্ট ফাইল যেটা প্রজেক্টের প্রতিটা `.py` সোর্স ফাইল (`ast` দিয়ে পার্স করে, রান না করে) স্ক্যান করে নিশ্চিত করে কোথাও network লাইব্রেরি (socket, urllib, requests, ftplib, smtplib ইত্যাদি) ইম্পোর্ট করা হয়নি। কেউ ভবিষ্যতে ভুলবশত network কোড যোগ করলে এই টেস্ট সাথে সাথে fail করবে এবং ঠিক কোন ফাইলে কী পাওয়া গেছে তা বলে দেবে।
- **`scheduler.is_valid_time_format()`** — যখন Scheduled Auto-Clean-এর UI ছিল (v1.4.0-এ সরানো হয়েছে), Time ফিল্ড (একমাত্র ফ্রি-টেক্সট ইনপুট যেটা `schtasks` subprocess কমান্ডে যেত) কঠোরভাবে "HH:MM" ফরম্যাট যাচাই করত, ভুল/অস্বাভাবিক ইনপুট থাকলে subprocess কল-ই না করে সরাসরি রিজেক্ট করত। এই ফাংশনসহ পুরো `scheduler.py` মডিউল ও তার টেস্ট v1.4.5-এ সম্পূর্ণ মুছে ফেলা হয়েছে (নিচের v1.4.5 সেকশন দেখুন)।

## বাগ হান্ট + লিন্ট ক্লিনআপ (v1.4.5)

ব্যবহারকারী নিজে টেস্ট স্যুট, `ruff`/`mypy`, আর ম্যানুয়াল কোড রিভিউ চালিয়ে ৪টা বাগ রিপোর্ট করেছিলেন — সবকটা আগে বাস্তবে reproduce করে, তারপর ফিক্স করে, আবার বাস্তবে verify করা হয়েছে:

**১. CI লাল হওয়ার দুই কারণ, দুটোই ঠিক করা হয়েছে।** `shutdown_setup.py`-তে `import winreg` কোনো গার্ড ছাড়া top-level-এ ছিল (`startup_manager.py`-র মতো try/except ছিল না) — Windows ছাড়া যেকোনো মেশিনে (এই Linux sandbox, GitHub Actions CI) `pc_cleaner.py` ইমপোর্ট করলেই সাথে সাথে `ModuleNotFoundError` দিয়ে ক্র্যাশ করত, ফলে `test_integration_gui.py` কখনো রানই হতো না। এখন ঐচ্ছিক ইমপোর্ট (`_HAS_WINREG`) + নতুন `is_windows()` গার্ড ৬টা registry-touching ফাংশনে যোগ হয়েছে — অন্য মডিউলের established প্যাটার্নই। `test_shutdown_setup.py`-ও সেই অনুযায়ী সহজ করা হয়েছে (আগে `sys.modules` স্টাব করে ঘুরপথে ইমপোর্ট করানো হতো, যেটা import-order-এর উপর নির্ভরশীল ছিল), আর একটা নতুন টেস্ট ক্লাস (`TestGracefulDegradationOffWindows`) যোগ হয়েছে যেটা এই non-Windows sandbox-এ আসল, unpatched বিহেভিয়ার সরাসরি যাচাই করে।

দ্বিতীয় কারণ: `.github/workflows/tests.yml`-এর lint job-এ `ruff check .` স্টেপে `continue-on-error` ছিল না (mypy-তে ছিল), আর বাস্তবে `ruff` চালিয়ে ৬০টা finding পাওয়া গিয়েছিল। প্রতিটা category ম্যানুয়ালি রিভিউ করা হয়েছে: ৪১টা (`E731` — `log = lambda...` প্যাটার্ন, ২৭টা; আর `SIM105` — best-effort `try/except: pass`, ১৪টা) এই কোডবেসের ইচ্ছাকৃত, বহুল-ব্যবহৃত idiom বলে চিহ্নিত করে কারণসহ `pyproject.toml`-এ ignore করা হয়েছে (mypy-র জন্য আগে থেকেই যেমন ডকুমেন্টেড আছে)। বাকি ১৯টা (loop-variable capture ৪টা, `SIM112`/`UP015`/ইত্যাদি ছোট জিনিস, ১টা genuinely unused variable, ১টা unused import) সরাসরি কোডে ফিক্স হয়েছে। ফলাফল: `ruff check .` এখন সত্যিকারভাবেই exit code ০ — তাই workflow ফাইলে `continue-on-error` যোগ করারই দরকার হয়নি, lint স্টেপ এখনো হার্ড-ব্লকিং, যেটা প্রকৃতপক্ষে ভালো (ভবিষ্যতে নতুন lint সমস্যা এলে CI সত্যিই আটকাবে)।

**২. Chrome Profile Manager-এ Chrome/Edge মিক্সআপ।** `_chrome_window_handles()` শুধু window class name (`Chrome_WidgetWin_1`) দিয়ে Chrome চিনত — কিন্তু Microsoft Edge-ও Chromium-based বলে ঠিক একই class name ব্যবহার করে। প্রোফাইল খোলার সময় এটা সমস্যা করত না (শুধু before/after কাউন্ট হিসেবে ব্যবহৃত হতো), কিন্তু "Chrome বন্ধ করে PC শাটডাউন করুন" বাটনে `close_all_chrome_windows()` প্রতিটা matching window-কে `WM_CLOSE` পাঠাত — অর্থাৎ Edge-এ সেভ-না-করা কাজও হারানোর সত্যিকারের ঝুঁকি ছিল। ফিক্স: নতুন `_pids_for_exe()` হেল্পার `tasklist`-এর মাধ্যমে chrome.exe-এর আসল PID সেট বের করে, আর প্রতিটা window-এর `GetWindowThreadProcessId()`-এর সাথে সেটা ক্রস-চেক করা হয় — filtering লজিকটা `_filter_chrome_handles()` নামে একটা ছোট pure function-এ আলাদা করা হয়েছে যাতে ctypes-লেভেল মক ছাড়াই সরাসরি টেস্ট করা যায়। ১০টা নতুন টেস্ট যোগ হয়েছে, যার মধ্যে একটা সত্যিকারের end-to-end টেস্ট আছে যেটা fake `user32`/`EnumWindows` দিয়ে হুবহু রিপোর্ট করা সিনারিও (একই class name, ভিন্ন process) পিন করে রাখে।

**৩. Chrome Profile Manager-এর দুটো বাটনে ডাবল-ট্যাপ প্রোটেকশন ছিল না।** বাকি লম্বা-চলা কাজের বাটন (Quick Clean, Scan, Clean Selected) কাজ চলাকালীন নিজেকে disable রাখে, কিন্তু "সব Chrome প্রোফাইল খুলুন" আর "Chrome বন্ধ করে শাটডাউন" বাটন দুটো তা করত না। এখন দুটো বাটনই `self.xxx_btn` হিসেবে instance attribute-এ সেভ হয়, worker শুরুর আগে disable আর শেষে (একটা নতুন `_done` কলব্যাকের মাধ্যমে) আবার enable হয় — বাকি বাটনগুলোর প্যাটার্নই।

**৪. `scheduler.py` (আর তার টেস্ট) সম্পূর্ণ মুছে ফেলা হয়েছে।** v1.4.0-এ GUI থেকে ডিসকানেক্ট করার পর ভবিষ্যতে ফিরিয়ে আনার সম্ভাবনার জন্য রাখা হয়েছিল, কিন্তু আর কোনো পরিকল্পনা নেই বলে নিশ্চিত হওয়ার পর মুছে ফেলা হয়েছে (docs-এর সব রেফারেন্সও আপডেট করা হয়েছে)। `system_tools.py` একই কারণে GUI থেকে ডিসকানেক্টেড কিন্তু প্রজেক্টে আছে — সেটা অপরিবর্তিত রাখা হয়েছে (`get_free_space()` এখনো header-এ ব্যবহৃত হয়)।

ছোট নোট: একটা অব্যবহৃত `import logging` (`_run_shutdown_clean_worker`-এর ভেতরে) সরানো হয়েছে। মোট টেস্ট ১৯৮ → ১৯৯ (scheduler-এর টেস্ট বাদ, নতুন ১৪টা যোগ)। পুরো স্যুট পরপর ৩ বার চালিয়ে যাচাই করা হয়েছে — প্রতিবার ১৯৯/১৯৯।

## পরিচিত সীমাবদ্ধতা
- প্রথমবার চালাতে Windows-এ Python ইনস্টল থাকা আবশ্যক (bundled exe নেই)
- Administrator ছাড়া চালালে কিছু ক্যাটাগরি (Windows Temp, Crash Dumps, Prefetch) স্কিপ হয় — অ্যাপ নিজেই জানায় ও "Restart as Administrator" বাটন দেয়
- এই Linux sandbox-এ `vista` ttk থিম নেই (Windows-only) — শুধু `clam` ফলব্যাক ভিজুয়ালি যাচাই করা যায়
