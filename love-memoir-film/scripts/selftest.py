#!/usr/bin/env python3
"""Offline smoke tests using synthetic media only; requires ffmpeg/ffprobe."""
import sys
sys.dont_write_bytecode = True
import json
from pathlib import Path
import tempfile
import unittest
import filmkit as f

class FilmKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f.require_media_tools()
        cls.tmp = tempfile.TemporaryDirectory(prefix="filmkit-test-")
        cls.root = Path(cls.tmp.name) / "中文 folder's project"
        cls.root.mkdir()
        cls.a = cls.root / "blue scene.mp4"
        cls.b = cls.root / "warm scene.mp4"
        cls.music = cls.root / "tone.wav"
        for color, file in (("blue", cls.a), ("orange", cls.b)):
            f.run(["ffmpeg", "-v", "error", "-n", "-f", "lavfi", "-i",
                   f"color=c={color}:s=160x120:r=24:d=3", "-an",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", str(file)])
        f.run(["ffmpeg", "-v", "error", "-n", "-f", "lavfi",
               "-i", "sine=frequency=440:sample_rate=48000:duration=5", str(cls.music)])
        cls.plan = {"schema_version": 1, "title": "Synthetic validation",
                    "width": 160, "height": 120, "fps": 24, "fit": "contain",
                    "clips": [{"file": cls.a.name, "in": 0.5, "frames": 48},
                              {"file": cls.b.name, "in": 0.5, "frames": 48}],
                    "music": {"file": cls.music.name, "in": 0, "allow_silence": False}}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def plan_file(self, name, plan):
        p = self.root / name
        p.write_text(json.dumps(plan), encoding="utf-8")
        return p

    def test_export_real_media(self):
        p = self.plan_file("valid.json", self.plan)
        out = self.root / "render.mp4"
        result = f.render(p, out)
        info = f.probe(out)
        self.assertEqual(result["frames"], 96)
        self.assertAlmostEqual(f.length(info, "video"), 4, places=2)
        self.assertTrue(any(x["codec_type"] == "audio" for x in info["streams"]))
        self.assertEqual(result["visual_review"], "pending")
        self.assertEqual(result["audio_listening"], "not performed")
        old_bytes = out.read_bytes()
        with self.assertRaises(ValueError):
            f.render(p, out)
        self.assertEqual(out.read_bytes(), old_bytes)

    def test_source_overrun_is_rejected(self):
        p = json.loads(json.dumps(self.plan))
        p["clips"][0]["frames"] = 120
        with self.assertRaises(ValueError):
            f.check(self.plan_file("overrun.json", p))

    def test_short_music_is_rejected(self):
        p = json.loads(json.dumps(self.plan))
        p["music"]["in"] = 4
        with self.assertRaises(ValueError):
            f.check(self.plan_file("short-music.json", p))

    def test_silence_requires_explicit_boolean(self):
        p = json.loads(json.dumps(self.plan))
        p["music"].update({"in": 4, "allow_silence": "false"})
        with self.assertRaises(ValueError):
            f.check(self.plan_file("bad-bool.json", p))
        p["music"]["allow_silence"] = True
        result = f.check(self.plan_file("allowed-silence.json", p))
        self.assertTrue(result["music"]["allow_silence"])

    def test_transition_not_silently_ignored(self):
        p = json.loads(json.dumps(self.plan))
        p["clips"][0]["transition"] = "shoulder"
        with self.assertRaises(ValueError):
            f.check(self.plan_file("transition.json", p))

    def test_contact_covers_requested_interval(self):
        result = f.contact(self.a, self.root / "contact", .5, .5, 2.5, 20)
        samples = f.load(self.root / "contact" / "samples.json")
        self.assertEqual([x["source_time"] for x in samples], [.5, 1, 1.5, 2])
        self.assertEqual(result["frames"], 4)
        self.assertTrue(all((self.root / "contact" / x["file"]).stat().st_size > 0 for x in samples))

    def test_html_treats_user_content_as_data(self):
        b = {"title": "<script>alert(1)</script>", "units": [
            {"id": "U1", "prompt_zh": "</pre><script>bad()</script>"}]}
        path = self.plan_file("brief-html.json", b)
        dest = self.root / "board.html"
        f.board(path, dest)
        markup = dest.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;bad()", markup)
        self.assertNotIn("<script>bad()", markup)

    def test_init_preserves_existing_files(self):
        project = self.root / "new project"
        f.init_project(project, "新项目")
        content = (project / "brief.json").read_bytes()
        with self.assertRaises(ValueError):
            f.init_project(project, "overwrite")
        self.assertEqual((project / "brief.json").read_bytes(), content)

if __name__ == "__main__":
    unittest.main(verbosity=2)
