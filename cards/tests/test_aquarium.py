import sys
import random
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR / "addons"))

import aquarium


class AquariumRenderTests(unittest.TestCase):
    def test_ha_animates_both_sizes(self):
        for width in (64, 128):
            with self.subTest(width=width):
                body = aquarium.render({"_width": width, "_local_frame_stream": True, "_dwell": 3})
                with Image.open(BytesIO(body)) as image:
                    self.assertEqual(image.size, (width, 32))
                    self.assertGreater(image.n_frames, 20)
                    frames = []
                    for frame in range(image.n_frames):
                        image.seek(frame)
                        frames.append(image.convert("RGB").tobytes())
                    self.assertGreater(len(set(frames)), 20)

    def test_random_routes_stay_in_tank_and_loop_smoothly(self):
        for width in (64, 128):
            routes = aquarium._swim_routes(width, random.Random(42))
            self.assertNotEqual(routes, aquarium._swim_routes(width, random.Random(43)))
            self.assertEqual(len(set(routes)), 3)
            for route in routes:
                positions = [aquarium._swim_position(width, route, n / 600, 2) for n in range(601)]
                self.assertEqual(positions[0], positions[-1])
                self.assertEqual({p[2] for p in positions}, {True, False})
                for x, y, _ in positions:
                    self.assertTrue(10 <= x <= width - 11)
                    self.assertTrue(8 <= y <= 22)
                for first, second in zip(positions, positions[1:]):
                    self.assertLessEqual(abs(first[0] - second[0]), 2)
                    self.assertLessEqual(abs(first[1] - second[1]), 1)

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
