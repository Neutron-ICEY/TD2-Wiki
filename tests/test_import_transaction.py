import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.equipment.import_transaction import digest, install


class ImportRecovery(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        review = self.root / "dist/review"
        review.mkdir(parents=True)
        self.targets = ["page.wiki", "records.json", "catalog.json", "baseline.json"]
        entries = []
        for name in self.targets:
            target, payload = self.root / name, review / name
            if name != "page.wiki":
                target.write_bytes(b"A")
            payload.write_bytes(b"B")
            entries.append(dict(target=name, before=digest(target), after=digest(payload), artifact=name))
        self.resume = dict(identity="same input", baseline="baseline.json", targets=self.targets)
        self.batch = dict(self.resume, review="review", entries=entries)

    def interrupt(self, name):
        replace = os.replace
        def cut(src, dst):
            replace(src, dst)
            if dst == self.root / name:
                raise InterruptedError
        with patch("tools.equipment.import_transaction.os.replace", side_effect=cut):
            with self.assertRaises(InterruptedError):
                install(self.root, self.batch)

    def test_each_install_boundary_resumes_the_original_review(self):
        for name in self.targets:
            with self.subTest(name=name):
                for row in self.batch["entries"]:
                    target = self.root / row["target"]
                    if row["before"] is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(b"A")
                self.interrupt(name)
                expected = b"B" if name == self.targets[-1] else b"A"
                self.assertEqual((self.root / "baseline.json").read_bytes(), expected)
                self.assertEqual(install(self.root, self.resume), "review")
                self.assertTrue(all((self.root / n).read_bytes() == b"B" for n in self.targets))
                self.assertIsNone(install(self.root, self.resume))

    def test_intervening_edit_or_different_projection_cannot_advance_baseline(self):
        self.interrupt("records.json")
        with self.assertRaisesRegex(ValueError, "pending import"):
            install(self.root, dict(self.resume, identity="different"))
        for name in ["page.wiki", "catalog.json"]:
            target = self.root / name
            original = target.read_bytes()
            target.write_bytes(b"manual correction")
            with self.assertRaisesRegex(ValueError, "target changed"):
                install(self.root, self.resume)
            self.assertEqual(target.read_bytes(), b"manual correction")
            self.assertEqual((self.root / "baseline.json").read_bytes(), b"A")
            target.write_bytes(original)
        self.assertEqual(install(self.root, self.resume), "review")

    def test_edit_while_staging_the_baseline_is_preserved(self):
        copy = shutil.copyfileobj
        def edit(src, out):
            copy(src, out)
            if Path(src.name).name == "baseline.json":
                (self.root / "catalog.json").write_bytes(b"parallel edit")
        with patch("tools.equipment.import_transaction.shutil.copyfileobj", side_effect=edit):
            with self.assertRaisesRegex(ValueError, "target changed: catalog.json"):
                install(self.root, self.batch)
        self.assertEqual((self.root / "catalog.json").read_bytes(), b"parallel edit")
        self.assertEqual((self.root / "baseline.json").read_bytes(), b"A")


class ImportCommand(unittest.TestCase):
    def test_same_command_recovers_catalog_and_keeps_baseline_last_after_process_exit(self):
        importer = Path(__file__).resolve().parents[1] / "tools/equipment/import.cjs"
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, database = "wiki/pages/weapons/test.wiki", "data/equipment/records.json"
            catalog, baseline = "data/brand-sets/acquisition-methods.json", "data/equipment/native-baseline.json"
            def write(name, value):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf8")
            entity = dict(source=source, id="sample", template="武器信息")
            write("publishing/registry.json", {"entries": [
                dict(source=source, id="page-sample", related_entity="sample", kind="pages", title="测试",
                     namespace=0, ownership="generated", generator="tools/equipment/import.cjs@v1")]})
            write(database, {"schema_version": 1, "entities": {"sample": dict(
                template="武器信息", fields={"装备名称": "A"}, effects=[], collections={}, slots=[])}})
            write(catalog, {"blueprints": [], "blueprint_sources": [], "testValue": "A"})
            def projection(value):
                return {"schema_version": 1, "entities": [dict(entity, units=[dict(
                    target={"field": "装备名称"}, semantic=value, value=value)])], "catalogs": [
                        dict(file=catalog, path=["testValue"], semantic=value, value=value)]}
            def run(output, env=None):
                args = ["node", "-e", "require(process.argv[1]).main(process.argv.slice(2),process.cwd())",
                        str(importer), "projection.json", "dist/"+output, "--write"]
                return subprocess.run(args, cwd=root, capture_output=True, encoding="utf8", env=env)
            write("projection.json", projection("A"))
            first = run("first")
            self.assertEqual(first.returncode, 0, first.stderr)
            old = (root / baseline).read_bytes()
            (root / source).unlink()  # Exercise creation during the interrupted batch too.
            write("projection.json", projection("B"))
            (root / "sitecustomize.py").write_text(
                "import os\nreal = os.replace\ndef stop(src, dst):\n"
                "    real(src, dst)\n    if str(dst) == os.environ['CUT_AFTER']: os._exit(73)\n"
                "os.replace = stop\n", encoding="utf8")
            failed = run("review", {**os.environ, "PYTHONPATH": str(root), "CUT_AFTER": str(root / database)})
            self.assertNotEqual(failed.returncode, 0)
            self.assertTrue((root / source).exists())
            self.assertEqual(json.loads((root / database).read_text("utf8"))["entities"]["sample"]["fields"]["装备名称"], "B")
            self.assertEqual((root / baseline).read_bytes(), old)
            self.assertEqual(json.loads((root / catalog).read_text("utf8"))["testValue"], "A")
            resumed = run("review")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertIn("Completed pending import", resumed.stdout)
            self.assertEqual(json.loads((root / catalog).read_text("utf8"))["testValue"], "B")
            self.assertNotEqual((root / baseline).read_bytes(), old)
            again = run("again")
            self.assertEqual(again.returncode, 0, again.stderr)
            audit = json.loads((root / "dist/again/result.json").read_text("utf8"))
            self.assertEqual(audit["pages"][0]["fields"], [])
            self.assertEqual(audit["catalogs"], [])
