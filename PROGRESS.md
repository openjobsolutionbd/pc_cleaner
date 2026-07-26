# PC Cleaner — প্রজেক্ট প্রেক্ষাপট

> এই ফাইলটা নতুন চ্যাটে zip আপলোড করলে দ্রুত প্রজেক্ট বোঝার জন্য। পুরনো কাজের ডিটেইল লগ রাখা হয় না — শুধু বর্তমান অবস্থা।

## প্রজেক্ট কী

Windows-এর জন্য একটা Junk cleanup + সিস্টেম মেইনটেন্যান্স Python/tkinter GUI অ্যাপ (নাম: **PC Cleaner**, বর্তমান ভার্সন **v1.1.0**), `.exe`-এ বিল্ড হয়। ব্যবহারকারী কোডিং জানেন না, মোবাইল থেকে কাজ করেন — তাই যেকোনো পরিবর্তন সবসময় স্পষ্ট বাংলা ব্যাখ্যাসহ, অ্যাপ্রুভাল নিয়ে করতে হবে।

**৬টা ট্যাব:** Quick Clean, Junk Cleanup, Browser & Network, System Tools, Startup Manager, Automation & History।

**নিরাপত্তার হার্ড গ্যারান্টি (কখনো ভাঙা যাবে না):** Password কখনো ছোঁয়া হয় না, Cookies কখনো মোছা হয় না, root ফোল্ডার কখনো ডিলিট হয় না, Startup Manager-এর disable সবসময় reversible, অ্যাপ কখনো নেটওয়ার্কে কিছু পাঠায় না (সম্পূর্ণ অফলাইন)।

## ফাইল কাঠামো

| ফাইল | কাজ |
|---|---|
| `pc_cleaner.py` | মেইন GUI, Theme/styling, `__version__` |
| `cleaner_core.py` | Junk file ক্লিনআপ লজিক |
| `browser_core.py` | ব্রাউজার হিস্ট্রি/ক্যাশ ক্লিনআপ |
| `system_tools.py` | Disk analyzer, empty folder finder, icon cache, drive helpers, root/critical-folder protection (`is_protected_root`) |
| `startup_manager.py` | Startup প্রোগ্রাম চালু/বন্ধ (registry backup key: `PCCleanerBackup`) |
| `scheduler.py` | Windows Task Scheduler দিয়ে অটো-ক্লিন (task name: `PCCleanerAutoClean`), Time ফিল্ড ভ্যালিডেশন (`is_valid_time_format`) |
| `history_log.py` | ক্লিনআপ লগ (ডেটা ফোল্ডার: `%LOCALAPPDATA%\PCCleaner`) |
| `test_*.py` | প্রতিটা মডিউলের ইউনিট/ইন্টিগ্রেশন টেস্ট (১০৭টা, GUI-সহ) — `test_no_network_guarantee.py` সহ |
| `Start_Here.bat` / `build_exe.bat` / `run_tests.bat` | লঞ্চার / .exe বিল্ড (`PCCleaner.exe`) / টেস্ট রানার |

## যাচাইয়ের পদ্ধতি

এই sandbox-এ `apt-get install python3-tk xvfb` করে `xvfb-run python3 -m unittest discover` দিয়ে সব ১০৭টা টেস্ট (GUI-সহ) বাস্তবে চালিয়ে যাচাই করা যায় — GUI ভিজুয়াল যাচাইয়ের জন্য headless স্ক্রিনশটও নেওয়া সম্ভব। কোড শুধু পড়ে/কম্পাইল করে অনুমান না করে সবসময় বাস্তবে চালিয়ে যাচাই করা হয়।

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

- **safe + ডিফল্টে checked:** User Temp, Windows Temp, Chrome Cache, Edge Cache, Thumbnail Cache, Error Reports, Delivery Optimization, Recycle Bin
- **caution + ডিফল্টে unchecked:** Windows Update Old Files, Crash Dumps, Prefetch

আগে Windows Update Old Files আর Crash Dumps ডিফল্টে checked ছিল — ইউজারের অনুরোধে এখন unchecked (ইউজার নিজে চাইলে টিক দেবে)।

## নাম ও ভার্সনিং

অ্যাপের নাম **"Windows Cleaner"** থেকে বদলে **"PC Cleaner"** করা হয়েছে (v1.1.0-এ) — ফাইলের নাম (`windows_cleaner.py` → `pc_cleaner.py`), `.exe` নাম (`WindowsCleaner.exe` → `PCCleaner.exe`), GUI টাইটেল/হেডার, রেজিস্ট্রি ব্যাকআপ key, Task Scheduler নাম, ডেটা ফোল্ডার নাম — সব জায়গায়। ভার্সন নম্বর `pc_cleaner.py`-এর `__version__` কনস্ট্যান্টে আছে এবং GUI হেডারে দেখা যায়।

## নিরাপত্তা: অফলাইন-গ্যারান্টি ও Time ইনপুট ভ্যালিডেশন

- **`test_no_network_guarantee.py`** — নতুন স্বতন্ত্র টেস্ট ফাইল যেটা প্রজেক্টের প্রতিটা `.py` সোর্স ফাইল (`ast` দিয়ে পার্স করে, রান না করে) স্ক্যান করে নিশ্চিত করে কোথাও network লাইব্রেরি (socket, urllib, requests, ftplib, smtplib ইত্যাদি) ইম্পোর্ট করা হয়নি। কেউ ভবিষ্যতে ভুলবশত network কোড যোগ করলে এই টেস্ট সাথে সাথে fail করবে এবং ঠিক কোন ফাইলে কী পাওয়া গেছে তা বলে দেবে।
- **`scheduler.is_valid_time_format()`** — Automation ট্যাবের Time ফিল্ড (একমাত্র ফ্রি-টেক্সট ইনপুট যেটা `schtasks` subprocess কমান্ডে যায়) এখন কঠোরভাবে "HH:MM" ফরম্যাট যাচাই করে, ভুল/অস্বাভাবিক ইনপুট থাকলে subprocess কল-ই না করে সরাসরি রিজেক্ট করে। বর্তমানে exploit সম্ভব না (কোথাও `shell=True` ব্যবহার হয় না), তবে এটা defense-in-depth — ভবিষ্যতে কোনো রিফ্যাক্টরে ভুলবশত shell=True যোগ হলেও এই গার্ড সুরক্ষা দেবে।

## পরিচিত সীমাবদ্ধতা
- প্রথমবার চালাতে Windows-এ Python ইনস্টল থাকা আবশ্যক (bundled exe নেই)
- Administrator ছাড়া চালালে কিছু ক্যাটাগরি (Windows Temp, Update Old Files, Delivery Optimization, Crash Dumps) স্কিপ হয় — অ্যাপ নিজেই জানায় ও "Restart as Administrator" বাটন দেয়
- এই Linux sandbox-এ `vista` ttk থিম নেই (Windows-only) — শুধু `clam` ফলব্যাক ভিজুয়ালি যাচাই করা যায়
