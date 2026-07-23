# Windows Cleaner — প্রজেক্ট প্রেক্ষাপট

> এই ফাইলটা নতুন চ্যাটে zip আপলোড করলে দ্রুত প্রজেক্ট বোঝার জন্য। পুরনো কাজের ডিটেইল লগ রাখা হয় না — শুধু বর্তমান অবস্থা।

## প্রজেক্ট কী

Windows-এর জন্য একটা Junk cleanup + সিস্টেম মেইনটেন্যান্স Python/tkinter GUI অ্যাপ, `.exe`-এ বিল্ড হয়। ব্যবহারকারী কোডিং জানেন না, মোবাইল থেকে কাজ করেন — তাই যেকোনো পরিবর্তন সবসময় স্পষ্ট বাংলা ব্যাখ্যাসহ, অ্যাপ্রুভাল নিয়ে করতে হবে।

**৫টা ট্যাব:** Junk Cleanup, Browser & Network, System Tools, Startup Manager, Automation & History।

**নিরাপত্তার হার্ড গ্যারান্টি (কখনো ভাঙা যাবে না):** Password কখনো ছোঁয়া হয় না, Cookies কখনো মোছা হয় না, root ফোল্ডার কখনো ডিলিট হয় না, Startup Manager-এর disable সবসময় reversible।

## ফাইল কাঠামো

| ফাইল | কাজ |
|---|---|
| `windows_cleaner.py` | মেইন GUI, Theme/styling |
| `cleaner_core.py` | Junk file ক্লিনআপ লজিক |
| `browser_core.py` | ব্রাউজার হিস্ট্রি/ক্যাশ ক্লিনআপ |
| `system_tools.py` | Disk analyzer, empty folder finder, icon cache, drive helpers, root/critical-folder protection (`is_protected_root`) |
| `startup_manager.py` | Startup প্রোগ্রাম চালু/বন্ধ (registry) |
| `scheduler.py` | Windows Task Scheduler দিয়ে অটো-ক্লিন |
| `history_log.py` | ক্লিনআপ লগ |
| `test_*.py` | প্রতিটা মডিউলের ইউনিট/ইন্টিগ্রেশন টেস্ট (৯৪টা, GUI-সহ) |
| `Start_Here.bat` / `build_exe.bat` / `run_tests.bat` | লঞ্চার / .exe বিল্ড / টেস্ট রানার |

## যাচাইয়ের পদ্ধতি

এই sandbox-এ `apt-get install python3-tk xvfb` করে `xvfb-run python3 -m unittest discover` দিয়ে সব ৯৪টা টেস্ট (GUI-সহ) বাস্তবে চালিয়ে যাচাই করা যায় — GUI ভিজুয়াল যাচাইয়ের জন্য headless স্ক্রিনশটও নেওয়া সম্ভব। কোড শুধু পড়ে/কম্পাইল করে অনুমান না করে সবসময় বাস্তবে চালিয়ে যাচাই করা হয়।

## নিরাপত্তা: root/critical-folder guard

`system_tools.py`-তে `is_protected_root()` / `is_drive_root()` যোগ হয়েছে — ইউজার-চোজেন যেকোনো ফোল্ডার (folder picker দিয়ে) থেকে drive root বা critical ফোল্ডার (Windows, Program Files, Users, Documents/Desktop/Downloads ইত্যাদি — শুধু user profile-এর নিচে) সরাসরি স্ক্যান/ডিলিট করা কোড-লেভেলে ব্লক করা আছে। `find_empty_folders` scan-এর শুরুতে চেক করে, `delete_empty_folders` প্রতিটা path delete করার ঠিক আগে আবার independently চেক করে (double-validation), `analyze_folder` শুধু bare drive root (`C:\`) refuse করে। ভেতরের সাবফোল্ডার (যেমন `Documents\OldReports`) স্বাভাবিকভাবে কাজ করে — শুধু critical ফোল্ডারটা নিজে root হিসেবে দিলে refuse হয়।

## Junk Cleanup: নিরাপত্তা ব্যাজ

প্রতিটা junk category-তে (`cleaner_core.py`-এর `build_categories()` এবং `windows_cleaner.py`-এর Recycle Bin entry) এখন `"badge"` key আছে — `"safe"` অথবা `"caution"`। GUI-তে নামের পাশে রঙিন লেবেল দেখা যায় (সবুজ "Safe — daily cleanup" / হলুদ "Use caution")।

- **safe + ডিফল্টে checked:** User Temp, Windows Temp, Chrome Cache, Edge Cache, Thumbnail Cache, Error Reports, Delivery Optimization, Recycle Bin
- **caution + ডিফল্টে unchecked:** Windows Update Old Files, Crash Dumps, Prefetch

আগে Windows Update Old Files আর Crash Dumps ডিফল্টে checked ছিল — ইউজারের অনুরোধে এখন unchecked (ইউজার নিজে চাইলে টিক দেবে)।

## পরিচিত সীমাবদ্ধতা
- প্রথমবার চালাতে Windows-এ Python ইনস্টল থাকা আবশ্যক (bundled exe নেই)
- Administrator ছাড়া চালালে কিছু ক্যাটাগরি (Windows Temp, Update Old Files, Delivery Optimization, Crash Dumps) স্কিপ হয় — অ্যাপ নিজেই জানায় ও "Restart as Administrator" বাটন দেয়
- এই Linux sandbox-এ `vista` ttk থিম নেই (Windows-only) — শুধু `clam` ফলব্যাক ভিজুয়ালি যাচাই করা যায়
