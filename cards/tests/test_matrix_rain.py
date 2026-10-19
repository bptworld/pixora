import random
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'addons'))
import matrix_rain


class MatrixRainTests(unittest.TestCase):
    def test_independent_streams(self):
        columns=matrix_rain._columns(128,random.Random(42))
        self.assertGreater(len({c['speed'] for c in columns}),20)
        self.assertGreater(len({c['length'] for c in columns}),20)
        self.assertNotEqual(columns,matrix_rain._columns(128,random.Random(43)))
        self.assertTrue(all(len(g)==5 and all(0<=r<=7 for r in g) for g in matrix_rain.GLYPHS))

    def test_animation_at_both_sizes_and_all_speeds(self):
        for width in (64,128):
            bodies=[]
            for speed in ('slow','normal','fast'):
                with patch('matrix_rain.random.Random',return_value=random.Random(42)):
                    body=matrix_rain.render({'_width':width,'speed':speed,'_dwell':5})
                bodies.append(body)
                with Image.open(BytesIO(body)) as image:
                    self.assertEqual(image.size,(width,32))
                    self.assertGreater(image.n_frames,50)
                    frames=[];timing=0;has_head=False;has_black=False
                    for frame in range(image.n_frames):
                        image.seek(frame);rgb=image.convert('RGB');frames.append(rgb.copy())
                        timing+=image.info.get('duration',0)
                        pixels=set(rgb.getdata())
                        has_head |= any(r>90 and g>r and b>90 for r,g,b in pixels)
                        has_black |= (0,0,0) in pixels
                        self.assertTrue(all(g>=r and g>=b for r,g,b in pixels))
                    self.assertTrue(has_head and has_black)
                    self.assertGreater(len({f.tobytes() for f in frames}),50)
                    self.assertTrue(4900<=timing<=5100)
                    if speed=='normal':
                        frames=[f.resize((width*6,192),Image.Resampling.NEAREST) for f in frames]
                        frames[0].save(f'D:/planner/.build-tmp/matrix-rain-{width}.gif',save_all=True,append_images=frames[1:],duration=80,loop=0)
                        frames[10].save(f'D:/planner/.build-tmp/matrix-rain-{width}.png')
            self.assertEqual(len(set(bodies)),3,'Speed choices did not change the rain')


if __name__=='__main__':unittest.main()
