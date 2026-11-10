"""Check installation copies, preserves existing work and rejects linked sources."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install import install, NAME, FILES, DIRECTORIES


class InstallationTests(unittest.TestCase):
    def test_copy_and_preserve_existing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for name in FILES:
                (source / name).write_text(name, encoding="utf-8")
            for name in DIRECTORIES:
                (source / name).mkdir()
                (source / name / "resource.txt").write_text(name, encoding="utf-8")
            target = install(source, root / "skills")
            self.assertEqual(target.name, NAME)
            self.assertEqual((target / "assets/resource.txt").read_text(), "assets")
            (target / "SKILL.md").write_text("teacher's changes", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Existing skill preserved"):
                install(source, root / "skills")
            self.assertEqual((target / "SKILL.md").read_text(), "teacher's changes")
            with self.assertRaisesRegex(ValueError, "outside"):
                install(source, source / "nested")

    def test_incomplete_source_does_not_create_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            with self.assertRaisesRegex(ValueError, "Missing or linked"):
                install(source, root / "skills")
            self.assertFalse((root / "skills").exists())

    def test_linked_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            original = root / "original.md"
            original.write_text("external", encoding="utf-8")
            try:
                (source / "SKILL.md").symlink_to(original)
            except OSError:
                self.skipTest("This OS does not allow symlink creation for the current user")
            with self.assertRaisesRegex(ValueError, "Missing or linked"):
                install(source, root / "skills")
            self.assertFalse((root / "skills").exists())


if __name__ == "__main__":
    unittest.main()
