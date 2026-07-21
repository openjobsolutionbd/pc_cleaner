"""
Automated tests for scheduler.py.

Run with: python -m unittest test_scheduler.py -v
"""

import sys
import unittest
import unittest.mock

import scheduler


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestBuildRunCommand(unittest.TestCase):
    """Bug fix: before building the .exe, running windows_cleaner.py
    straight from source and scheduling it used to put the raw .py path
    into the task's /TR command, which Task Scheduler can't reliably run
    as a program. The Python interpreter must be invoked explicitly with
    the script path as an argument in that case.
    """

    def test_frozen_runs_the_exe_directly(self):
        with unittest.mock.patch.object(sys, "frozen", True, create=True), \
             unittest.mock.patch.object(sys, "executable", r"C:\Users\selim\dist\WindowsCleaner.exe"):
            cmd = scheduler.build_run_command()
        self.assertEqual(cmd, r'"C:\Users\selim\dist\WindowsCleaner.exe" --auto-clean')

    def test_unfrozen_invokes_python_interpreter_with_script_argument(self):
        with unittest.mock.patch.object(sys, "frozen", False, create=True), \
             unittest.mock.patch.object(sys, "executable", r"C:\Python312\python.exe"), \
             unittest.mock.patch.object(sys, "argv", [r"windows_cleaner.py"]):
            cmd = scheduler.build_run_command()
        # Must be TWO separately-quoted tokens: the interpreter, then the
        # script — not the .py path alone, and not both in one pair of
        # quotes (which schtasks would treat as a single invalid program).
        self.assertTrue(cmd.startswith(r'"C:\Python312\python.exe" "'))
        self.assertTrue(cmd.endswith(r'windows_cleaner.py" --auto-clean'))
        self.assertEqual(cmd.count('"'), 4)

    def test_unfrozen_script_path_is_absolute(self):
        with unittest.mock.patch.object(sys, "frozen", False, create=True), \
             unittest.mock.patch.object(sys, "executable", "/usr/bin/python3"), \
             unittest.mock.patch.object(sys, "argv", ["windows_cleaner.py"]):
            cmd = scheduler.build_run_command()
        self.assertNotIn('"windows_cleaner.py"', cmd, "the script path must be resolved to an absolute path")


class TestCreateScheduledTask(unittest.TestCase):
    def test_success_returns_true_and_uses_run_command_verbatim(self):
        fake_result = _FakeCompletedProcess(0)
        with unittest.mock.patch.object(scheduler, "is_windows", return_value=True), \
             unittest.mock.patch("scheduler.subprocess.run", return_value=fake_result) as run:
            ok = scheduler.create_scheduled_task('"C:\\app.exe" --auto-clean', "WEEKLY", "SUN", "03:00")
        self.assertTrue(ok)
        called_cmd = run.call_args[0][0]
        self.assertIn("/TR", called_cmd)
        self.assertEqual(called_cmd[called_cmd.index("/TR") + 1], '"C:\\app.exe" --auto-clean')

    def test_nonzero_returncode_is_failure_and_logs_stderr(self):
        fake_result = _FakeCompletedProcess(1, stderr="ERROR: Invalid Start Time value.")
        messages = []
        with unittest.mock.patch.object(scheduler, "is_windows", return_value=True), \
             unittest.mock.patch("scheduler.subprocess.run", return_value=fake_result):
            ok = scheduler.create_scheduled_task(
                '"C:\\app.exe" --auto-clean', "WEEKLY", "SUN", "not-a-time", log=messages.append
            )
        self.assertFalse(ok)
        self.assertTrue(any("Invalid Start Time" in m for m in messages))

    def test_not_windows_fails_without_calling_subprocess(self):
        with unittest.mock.patch.object(scheduler, "is_windows", return_value=False), \
             unittest.mock.patch("scheduler.subprocess.run") as run:
            ok = scheduler.create_scheduled_task('"C:\\app.exe" --auto-clean')
        self.assertFalse(ok)
        run.assert_not_called()


class TestRemoveScheduledTask(unittest.TestCase):
    def test_nonzero_returncode_is_failure_and_logs_stderr(self):
        fake_result = _FakeCompletedProcess(1, stderr="ERROR: The system cannot find the task specified.")
        messages = []
        with unittest.mock.patch.object(scheduler, "is_windows", return_value=True), \
             unittest.mock.patch("scheduler.subprocess.run", return_value=fake_result):
            ok = scheduler.remove_scheduled_task(log=messages.append)
        self.assertFalse(ok)
        self.assertTrue(any("cannot find the task" in m for m in messages))

    def test_success_returns_true(self):
        fake_result = _FakeCompletedProcess(0)
        with unittest.mock.patch.object(scheduler, "is_windows", return_value=True), \
             unittest.mock.patch("scheduler.subprocess.run", return_value=fake_result):
            self.assertTrue(scheduler.remove_scheduled_task())


if __name__ == "__main__":
    unittest.main()
