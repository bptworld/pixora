import sys
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR / "addons"))

import aquarium


class AquariumRenderTests(unittest.TestCase):
    def test_64_pixel_card_is_static_for_device_stability(self):
        body = aquarium.render({"_dwell": 10, "speed": "slow"})
        with Image.open(BytesIO(body)) as image:
            self.assertEqual(image.size, (64, 32))
            self.assertEqual(getattr(image, "n_frames", 1), 1)

    def test_128_pixel_card_remains_animated(self):
        body = aquarium.render({"_target": "matrixportal-s3-128x32", "_dwell": 3})
        with Image.open(BytesIO(body)) as image:
            self.assertEqual(image.size, (128, 32))
            self.assertGreater(getattr(image, "n_frames", 1), 1)


if __name__ == "__main__":
    unittest.main()
