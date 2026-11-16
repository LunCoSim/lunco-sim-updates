from pathlib import Path
import json
import os
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).parents[2]
SOURCE_ROOT = Path(os.environ["LUNCO_NIGHTLY_SOURCE_PATH"])


class NightlyReleaseContractTests(unittest.TestCase):
    def test_release_staging_uses_the_shared_source_helper(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
        helper = SOURCE_ROOT / "scripts/stage_release_artifacts.py"

        self.assertTrue(helper.is_file(), f"missing release staging helper: {helper}")
        self.assertIn("python3 scripts/stage_release_artifacts.py", workflow)
        self.assertNotIn("stage_dev_release.py", workflow)
        self.assertNotIn("stage_nightly_release.py", workflow)

    def test_dev_version_cli_continues_the_shared_development_sequence(self) -> None:
        assets = [
            "luncosim-0.6.0-nightly.161.1-win-x64-full.nupkg",
            "luncosim-0.6.0-dev.1-win-x64-full.nupkg",
            "luncosim-0.6.0-dev.1-linux-x64-full.nupkg",
        ]
        result = subprocess.run(
            ["python3", "scripts/msi_version.py", "--next-version", "0.6.0"],
            cwd=SOURCE_ROOT,
            input="\n".join(assets),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "0.6.0-dev.2\n")

    def test_version_generation_rejects_failed_or_missing_metadata(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
        step = workflow.split("      - id: version\n", 1)[1]
        script = textwrap.dedent(
            step.split("        run: |\n", 1)[1].split("\n  #", 1)[0]
        )
        cases = [
            (
                0,
                [{"name": "lunco-luncosim", "version": "0.1.0-dev"}],
                ["luncosim-0.1.0-dev.1-win-x64-full.nupkg"],
                True,
            ),
            (101, [], [], False),
            (0, [], [], False),
        ]
        for cargo_status, packages, assets, succeeds in cases:
            with self.subTest(cargo_status=cargo_status, packages=packages):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    cargo = root / "cargo"
                    cargo.write_text(
                        '#!/bin/sh\nprintf "%s\\n" "$TEST_METADATA"\n'
                        'exit "$TEST_CARGO_STATUS"\n'
                    )
                    cargo.chmod(0o755)
                    gh = root / "gh"
                    gh.write_text(
                        '#!/bin/sh\nprintf "%s\\n" "$TEST_PUBLISHED_ASSETS"\n'
                    )
                    gh.chmod(0o755)
                    expected_msi = subprocess.run(
                        ["python3", "scripts/msi_version.py", "--version", "0.1.0-dev.2"],
                        cwd=SOURCE_ROOT,
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout.strip()
                    output = root / "output"
                    env = dict(
                        os.environ,
                        PATH=f"{root}:{os.environ['PATH']}",
                        TEST_METADATA=json.dumps({"packages": packages}),
                        TEST_CARGO_STATUS=str(cargo_status),
                        TEST_PUBLISHED_ASSETS="\n".join(assets),
                        GITHUB_OUTPUT=str(output),
                    )
                    result = subprocess.run(
                        ["bash", "-e", "-c", script],
                        cwd=SOURCE_ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                    if succeeds:
                        self.assertEqual(
                            output.read_text(),
                            "version=0.1.0-dev.2\n"
                            f"msi_version={expected_msi}\n",
                        )
                    else:
                        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
