"""Engine tests with a stub chdman on PATH (no real chdman or Qt needed).

Run: python -m unittest discover -s tests
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from deluxechd import converter  # noqa: E402

STUB = r'''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[0] == "createcd":
    src = args[args.index("-i") + 1]; out = args[args.index("-o") + 1]
    if os.environ.get("STUB_CREATE_FAIL"):
        sys.stderr.write("error: stub failure\n"); sys.exit(1)
    with open(out, "wb") as fh: fh.write(b"CHD" + os.path.basename(src).encode())
elif args[0] == "verify":
    sys.exit(1 if os.environ.get("STUB_VERIFY_FAIL") else 0)
'''


@unittest.skipIf(sys.platform == "win32", "stub chdman is a POSIX script")
class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dxchd_test_")
        self.bin = os.path.join(self.tmp, "_bin")
        os.makedirs(self.bin)
        stub = os.path.join(self.bin, "chdman")
        with open(stub, "w") as fh:
            fh.write(STUB)
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = self.bin + os.pathsep + self.old_path
        self.lib = os.path.join(self.tmp, "lib")
        os.makedirs(self.lib)
        for var in ("STUB_CREATE_FAIL", "STUB_VERIFY_FAIL"):
            os.environ.pop(var, None)

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def game(self, folder, name, bins=("Track 1",), extra=b"x" * 4096):
        os.makedirs(folder, exist_ok=True)
        cue = os.path.join(folder, f"{name}.cue")
        with open(cue, "w") as fh:
            for b in bins:
                fh.write(f'FILE "{name} ({b}).bin" BINARY\n  TRACK 01 MODE2/2352\n')
        for b in bins:
            with open(os.path.join(folder, f"{name} ({b}).bin"), "wb") as fh:
                fh.write(extra)
        return cue

    def run_conv(self, mode, delete=False, rezip=False):
        logs = []
        c = converter.Converter(self.lib, mode, delete, rezip, on_log=lambda t, k: logs.append((t, k)))
        saved = c.run()
        return saved, logs

    def test_loose_delete_only_referenced_bins(self):
        self.game(self.lib, "FF")
        decoy = os.path.join(self.lib, "FF VII (Track 1).bin")
        open(decoy, "wb").write(b"keep")
        saved, _ = self.run_conv("all_in_one", delete=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "FF.chd")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "FF.cue")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "FF (Track 1).bin")))
        self.assertTrue(os.path.exists(decoy))
        self.assertGreater(saved, 0)

    def test_verify_failure_keeps_originals(self):
        self.game(self.lib, "Game")
        os.environ["STUB_VERIFY_FAIL"] = "1"
        _, logs = self.run_conv("all_in_one", delete=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Game.cue")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "Game.chd")))
        self.assertTrue(any("verification failed" in t for t, _ in logs))

    def test_create_failure_reports_stderr(self):
        self.game(self.lib, "Game")
        os.environ["STUB_CREATE_FAIL"] = "1"
        _, logs = self.run_conv("all_in_one", delete=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Game.cue")))
        self.assertTrue(any("stub failure" in t for t, _ in logs))

    def test_multidisc_archive(self):
        stage = os.path.join(self.tmp, "stage")
        self.game(stage, "Saga (Disc 1)")
        self.game(stage, "Saga (Disc 2)")
        archive = os.path.join(self.lib, "Saga.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            for f in os.listdir(stage):
                zf.write(os.path.join(stage, f), f)
        self.run_conv("archives", delete=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Saga (Disc 1).chd")))
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Saga (Disc 2).chd")))
        self.assertFalse(os.path.exists(archive))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "tmp_Saga")))

    def test_multidisc_archive_partial_failure_keeps_archive(self):
        stage = os.path.join(self.tmp, "stage")
        self.game(stage, "Saga (Disc 1)")
        self.game(stage, "Saga (Disc 2)")
        archive = os.path.join(self.lib, "Saga.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            for f in os.listdir(stage):
                zf.write(os.path.join(stage, f), f)
        # Disc 1 output already present → skipped; make Disc 2 fail
        os.environ["STUB_VERIFY_FAIL"] = "1"
        self.run_conv("archives", delete=True)
        self.assertTrue(os.path.exists(archive))

    def test_rezip_replaces_same_named_archive(self):
        stage = os.path.join(self.tmp, "stage")
        self.game(stage, "Solo")
        archive = os.path.join(self.lib, "Solo.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            for f in os.listdir(stage):
                zf.write(os.path.join(stage, f), f)
        self.run_conv("archives", delete=True, rezip=True)
        with zipfile.ZipFile(archive) as zf:
            self.assertEqual(zf.namelist(), ["Solo.chd"])

    def test_rezip_keep_originals_uses_suffix(self):
        self.game(self.lib, "Keep")
        self.run_conv("all_in_one", delete=False, rezip=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Keep_CHD.zip")))
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Keep.cue")))

    def test_per_game_folders_and_multidisc_folder(self):
        self.game(os.path.join(self.lib, "One"), "One")
        multi = os.path.join(self.lib, "Two")
        self.game(multi, "Two (Disc 1)")
        self.game(multi, "Two (Disc 2)")
        open(os.path.join(multi, "readme.txt"), "w").write("hi")
        self.run_conv("folders", delete=True)
        for name in ("One", "Two (Disc 1)", "Two (Disc 2)"):
            self.assertTrue(os.path.exists(os.path.join(self.lib, f"{name}.chd")), name)
        self.assertFalse(os.path.exists(os.path.join(self.lib, "One")))
        self.assertFalse(os.path.exists(multi))  # only a .txt was left, so it's purged
        self.assertTrue(os.path.isdir(self.lib))

    def test_recursive_purge_stops_at_selected_folder_and_keeps_other_files(self):
        deep = os.path.join(self.lib, "a", "b")
        self.game(deep, "Deep")
        open(os.path.join(self.lib, "a", "save.mcr"), "w").write("x")
        self.run_conv("recursive", delete=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Deep.chd")))
        self.assertFalse(os.path.exists(deep))
        self.assertTrue(os.path.exists(os.path.join(self.lib, "a", "save.mcr")))

    def test_existing_output_skips_and_deletes_original(self):
        self.game(self.lib, "Done")
        open(os.path.join(self.lib, "Done.chd"), "w").write("old")
        _, logs = self.run_conv("all_in_one", delete=True)
        self.assertEqual(open(os.path.join(self.lib, "Done.chd")).read(), "old")
        self.assertFalse(os.path.exists(os.path.join(self.lib, "Done.cue")))
        self.assertTrue(any("Already Exists" in t for t, _ in logs))

    @unittest.skipUnless(shutil.which("7z") or shutil.which("7za") or shutil.which("7zz"), "needs 7-Zip")
    def test_7z_archive(self):
        stage = os.path.join(self.tmp, "stage")
        self.game(stage, "Seven")
        exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
        subprocess.run([exe, "a", os.path.join(self.lib, "Seven.7z"), "."], cwd=stage,
                       stdout=subprocess.DEVNULL, check=True)
        self.run_conv("archives", delete=True)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "Seven.chd")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "Seven.7z")))


class UpdaterTests(unittest.TestCase):
    def test_versions(self):
        from deluxechd import updater
        self.assertEqual(updater.parse_version("v1.0"), (1, 0, 0))
        self.assertEqual(updater.parse_version("2.10.1-beta"), (2, 10, 1))
        self.assertTrue(updater.is_newer("v2.0.1", "2.0.0"))
        self.assertFalse(updater.is_newer("v1.0", "2.0.0"))


if __name__ == "__main__":
    unittest.main()
