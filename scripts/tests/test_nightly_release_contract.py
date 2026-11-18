from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).parents[2]
SOURCE_ROOT = Path(os.environ["LUNCO_NIGHTLY_SOURCE_PATH"])


def workflow_run_block(step_header: str) -> str:
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
    step = workflow.split(f"      - {step_header}\n", 1)[1]
    run = step.split("        run: |\n", 1)[1]
    return textwrap.dedent(re.split(r"\n(?=      - |  #)", run, maxsplit=1)[0])


class NightlyReleaseContractTests(unittest.TestCase):
    def test_release_staging_uses_the_shared_source_helper(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
        helper = SOURCE_ROOT / "scripts/stage_release_artifacts.py"

        self.assertTrue(helper.is_file(), f"missing release staging helper: {helper}")
        self.assertIn("python3 scripts/stage_release_artifacts.py", workflow)
        self.assertNotIn("stage_dev_release.py", workflow)
        self.assertNotIn("stage_nightly_release.py", workflow)

    def test_release_notes_use_the_previous_published_nightly(self) -> None:
        script = workflow_run_block("name: Prepare nightly release notes")
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT, text=True
        ).strip()
        previous = subprocess.check_output(
            ["git", "rev-parse", "HEAD^"], cwd=SOURCE_ROOT, text=True
        ).strip()
        source_url = "https://github.com/LunCoSim/lunco-sim"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gh = root / "gh"
            gh.write_text('#!/bin/bash\nprintf "%s\\n" "$TEST_RELEASES" | jq -r "$4"\n')
            gh.chmod(0o755)
            output = root / "output"
            for baseline in (previous, "0" * 40):
                with self.subTest(baseline=baseline):
                    releases = [
                        {
                            "tag_name": "nightly-previous",
                            "draft": False,
                            "published_at": "2026-11-13T19:51:00Z",
                            "body": f"Source commit: [{baseline}]({source_url}/commit/{baseline})",
                        },
                        {
                            "tag_name": "0.6.0-dev.1",
                            "draft": False,
                            "published_at": "2026-11-15T08:35:03Z",
                            "body": f"Source commit: [{current}]({source_url}/commit/{current})",
                        },
                    ]
                    result = subprocess.run(
                        ["bash", "-euo", "pipefail", "-c", script],
                        cwd=SOURCE_ROOT,
                        env=dict(
                            os.environ,
                            PATH=f"{root}:{os.environ['PATH']}",
                            TEST_RELEASES=json.dumps(releases),
                            GITHUB_OUTPUT=str(output),
                            GITHUB_REPOSITORY="LunCoSim/lunco-sim-updates",
                            RELEASE_DATE="2026-11-18 03:16 UTC",
                            SOURCE_SHA=current,
                            SOURCE_REPOSITORY_URL=source_url,
                        ),
                        capture_output=True,
                        text=True,
                    )
                    if baseline == previous:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        notes = output.read_text()
                        self.assertTrue(notes.startswith("body<<NIGHTLY_RELEASE_NOTES\n"))
                        self.assertIn(f"{source_url}/compare/{previous}...{current}", notes)
                        self.assertIn(f"Source commit: [{current}]({source_url}/commit/{current})", notes)
                        self.assertIn("`LunCoSim-Windows-x86_64.msi`", notes)
                        self.assertTrue(notes.endswith("\nNIGHTLY_RELEASE_NOTES\n"))
                        output.unlink()
                    else:
                        self.assertEqual(result.returncode, 1)
                        self.assertIn("no valid LunCoSim source commit", result.stderr)
                        self.assertFalse(output.exists())

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
        script = workflow_run_block("id: version")
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
