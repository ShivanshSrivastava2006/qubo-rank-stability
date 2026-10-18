#!/usr/bin/env python3
"""Fixtures for the Gate-9 CUDA image channel probe release generator."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stage2_cuda_image_channel_probe_release as release

class TestProbeRelease(unittest.TestCase):

    def setUp(self):
        self.root = Path(release.__file__).resolve().parent
        if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            release.sys.dont_write_bytecode = True

    def test_plan_determinism_and_builder_equivalence(self):
        plan1 = release.build_plan(self.root)
        plan2 = release.build_plan(self.root)
        self.assertEqual(plan1, plan2)
        
        with tempfile.TemporaryDirectory() as d:
            output_dir = Path(d)
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            builder_script = self.root / "build_g9_cuda_image_channel_probe_bundle.py"
            proc = subprocess.run(
                [sys.executable, "-O", str(builder_script), "--kaggle-user", release.ACCOUNT_SLUG, "--output-dir", str(output_dir)],
                env=env, capture_output=True
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
            builder_summary = json.loads(proc.stdout)
            self.assertEqual(plan1["bundle_hashes"], builder_summary["files_sha256"])

    def test_source_map_mismatch_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            temp_root = Path(d)
            for name in release.EXPECTED_PROBE_FILES:
                src = self.root / name
                dst = temp_root / name
                dst.write_bytes(src.read_bytes())
            
            (temp_root / "GATE_9_CUDA_IMAGE_CHANNEL_PROBE_DRAFT.md").unlink()
            with self.assertRaisesRegex(ValueError, "missing file"):
                release.build_plan(temp_root)
                
            src = self.root / "GATE_9_CUDA_IMAGE_CHANNEL_PROBE_DRAFT.md"
            dst = temp_root / "GATE_9_CUDA_IMAGE_CHANNEL_PROBE_DRAFT.md"
            dst.write_bytes(src.read_bytes())
            
            dst.write_bytes(b"altered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                release.build_plan(temp_root)
                
            dst.unlink()
            os.symlink(src, dst)
            with self.assertRaisesRegex(ValueError, "symlink rejected"):
                release.build_plan(temp_root)

    def test_metadata_internet_on_refusal(self):
        original_loads = json.loads
        
        def mock_loads_internet(s):
            d = original_loads(s)
            d["enable_internet"] = True
            return d
            
        with mock.patch("stage2_cuda_image_channel_probe_release.json.loads", side_effect=mock_loads_internet):
            with self.assertRaises(ValueError):
                release.build_plan(self.root)
                
        def mock_loads_pin(s):
            d = original_loads(s)
            d["docker_image_pinning_type"] = "original"
            return d
            
        with mock.patch("stage2_cuda_image_channel_probe_release.json.loads", side_effect=mock_loads_pin):
            with self.assertRaises(ValueError):
                release.build_plan(self.root)

    def test_generated_launcher_tamper_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            output_dir = Path(d)
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            builder_script = self.root / "build_g9_cuda_image_channel_probe_bundle.py"
            subprocess.run(
                [sys.executable, "-O", str(builder_script), "--kaggle-user", release.ACCOUNT_SLUG, "--output-dir", str(output_dir)],
                env=env, capture_output=True, check=True
            )
            
            launcher_path = output_dir / "g9_cuda_image_channel_probe_kaggle.py"
            launcher_text = launcher_path.read_text("ascii")
            
            import re
            import base64
            probe_bytes = (self.root / "stage2_cuda_image_channel_probe.py").read_bytes()
            tampered_probe = probe_bytes + b"tampered"
            tampered_b64 = base64.b64encode(tampered_probe).decode("ascii")
            tampered_launcher = re.sub(r'PAYLOAD_B64 = ".*"', f'PAYLOAD_B64 = "{tampered_b64}"', launcher_text)
            
            launcher_path.write_text(tampered_launcher, "ascii")
            os.chmod(launcher_path, 0o755)
            
            proc = subprocess.run([sys.executable, "-O", str(launcher_path)], env=env, capture_output=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn(b"REFUSED: embedded payload hash mismatch", proc.stderr)

    def test_no_project_output_writes(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = Path(d)
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            
            release_script = self.root / "stage2_cuda_image_channel_probe_release.py"
            proc = subprocess.run([sys.executable, "-O", str(release_script)], env=env, cwd=str(cwd), capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode('utf-8'))
            self.assertEqual(list(cwd.iterdir()), [])

if __name__ == "__main__":
    if "PYTHONDONTWRITEBYTECODE" not in os.environ:
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main()
