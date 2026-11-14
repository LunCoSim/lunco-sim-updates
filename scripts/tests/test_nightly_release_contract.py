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
    def test_next_run_cli_continues_the_published_nightly_sequence(self) -> None:
        assets = [
            "luncosim-0.6.0-nightly.135.2-win-x64-full.nupkg",
            "LunCoSim-win-x64-0.6.0-nightly.151.1-full.nupkg",
            "luncosim-0.6.0-nightly.999.1-osx-x64-full.nupkg",
            "luncosim-0.6.0-dev.3-win-x64-full.nupkg",
        ]
        result = subprocess.run(
            ["python3", "scripts/msi_version.py", "--next-run"],
            cwd=SOURCE_ROOT,
            input="\n".join(assets),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "152\n")

    def test_version_generation_rejects_failed_or_missing_metadata(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
        step = workflow.split("      - id: version\n", 1)[1]
        script = textwrap.dedent(
            step.split("        run: |\n", 1)[1].split("\n  #", 1)[0]
        )
        cases = [
            (0, [{"name": "lunco-luncosim", "version": "0.1.0-dev"}], True),
            (101, [], False),
            (0, [], False),
        ]
        for cargo_status, packages, succeeds in cases:
            with self.subTest(cargo_status=cargo_status, packages=packages):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    cargo = root / "cargo"
                    cargo.write_text(
                        '#!/bin/sh\nprintf "%s\\n" "$TEST_METADATA"\n'
                        'exit "$TEST_CARGO_STATUS"\n'
                    )
                    cargo.chmod(0o755)
                    output = root / "output"
                    env = dict(
                        os.environ,
                        PATH=f"{root}:{os.environ['PATH']}",
                        TEST_METADATA=json.dumps({"packages": packages}),
                        TEST_CARGO_STATUS=str(cargo_status),
                        GITHUB_OUTPUT=str(output),
                        RUN_NUMBER="139",
                        RUN_ATTEMPT="1",
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
                            "version=0.1.0-nightly.139.1\n"
                            "msi_version=1.0.13901\n"
                            "run_number=139\n",
                        )
                    else:
                        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
