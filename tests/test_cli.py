import unittest

from gpt_image.cli import CliError, _build_body, _validate_quality, _validate_size, build_parser


class CliModelTests(unittest.TestCase):
    def parse(self, *extra: str):
        return build_parser().parse_args(["generate", "--prompt", "test", *extra])

    def test_sunburst_is_the_default_model(self):
        args = self.parse()
        self.assertEqual(args.model, "gpt-image-2.5-sunburst")
        self.assertEqual(args.quality, "auto")

    def test_sunburst_body_uses_25_model(self):
        args = self.parse("--dry-run")
        body = _build_body(args, "test", [])
        tool = body["tools"][0]
        self.assertEqual(tool["model"], "gpt-image-2.5-sunburst")
        self.assertEqual(tool["quality"], "auto")

    def test_flare_is_an_explicit_secondary_model(self):
        args = self.parse("--model", "gpt-image-2.5-flare", "--quality", "xhigh")
        body = _build_body(args, "test", [])
        self.assertEqual(body["tools"][0]["model"], "gpt-image-2.5-flare")
        self.assertEqual(body["tools"][0]["quality"], "xhigh")

    def test_dated_snapshot_accepts_flexible_sizes(self):
        _validate_size("1536x864", "gpt-image-2.5-sunburst-2026-09-08")
        _validate_quality("max", "gpt-image-2.5-sunburst-2026-09-08")

    def test_legacy_models_reject_25_only_quality(self):
        with self.assertRaises(CliError):
            _validate_quality("max", "gpt-image-2")

    def test_25_models_keep_transparent_background(self):
        args = self.parse("--background", "transparent", "--output-format", "webp")
        body = _build_body(args, "test", [])
        tool = body["tools"][0]
        self.assertEqual(tool["model"], "gpt-image-2.5-sunburst")
        self.assertEqual(tool["background"], "transparent")
        self.assertEqual(tool["output_format"], "webp")

    def test_old_gpt_image_2_keeps_legacy_transparency_fallback(self):
        args = self.parse("--model", "gpt-image-2", "--background", "transparent")
        body = _build_body(args, "test", [])
        self.assertEqual(body["tools"][0]["model"], "gpt-image-1.5")


if __name__ == "__main__":
    unittest.main()
