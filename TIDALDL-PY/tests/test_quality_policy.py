import unittest

from tidal_dl.enums import (
    AUDIO_QUALITY_ORDER, AudioQuality, audio_quality_fallbacks, playback_quality_priority,
)
from tidal_dl.settings import getDefaultAudioQualityPriority


class QualityPolicyTests(unittest.TestCase):
    def test_modern_fallbacks_share_one_order_without_master(self):
        self.assertNotIn(AudioQuality.Master, AUDIO_QUALITY_ORDER)
        for index, quality in enumerate(AUDIO_QUALITY_ORDER):
            self.assertEqual(audio_quality_fallbacks(quality), list(AUDIO_QUALITY_ORDER[index:]))
        self.assertEqual(getDefaultAudioQualityPriority(), audio_quality_fallbacks(AudioQuality.Max))

    def test_legacy_priority_is_lossless_and_explicit_order_is_preserved(self):
        cases = [
            ([], []),
            ([AudioQuality.Master], [AudioQuality.Max, AudioQuality.HiFi]),
            ([AudioQuality.Max], [AudioQuality.Max]),
            ([AudioQuality.High, AudioQuality.Master, AudioQuality.Max], [AudioQuality.High, AudioQuality.Max]),
        ]
        for saved, expected in cases:
            with self.subTest(saved=saved):
                self.assertEqual(playback_quality_priority(iter(saved)), expected)


if __name__ == '__main__':
    unittest.main()
