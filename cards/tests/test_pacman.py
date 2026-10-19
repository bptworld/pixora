import random
import sys
import unittest
from io import BytesIO
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'addons'))
import pacman


class PacmanTests(unittest.TestCase):
    def test_routes_follow_corridors_and_eat_dots(self):
        for width in (64,128):
            graph=pacman._maze(width);background=pacman._background(width,graph)
            paths=[]
            for seed in (42,43):
                rng=random.Random(seed);start=next(iter(graph));actor=(start,start,None)
                dots=set(graph);route=[]
                for step in range(1000):
                    before=actor[0];actor,direction=pacman._advance(actor,graph,rng)
                    x,y=actor[0];route.append((x,y))
                    self.assertEqual(abs(x-before[0])+abs(y-before[1]),1)
                    for dx in range(-2,3):
                        for dy in range(-2,3):
                            self.assertNotEqual(background.getpixel((x+dx,y+dy)),(20,64,190))
                    dots.add((x,y));pacman._eat(dots,(x,y))
                    self.assertNotIn((x,y),dots)
                paths.append(route)
            self.assertNotEqual(*paths)

    def test_both_sizes_animate(self):
        for width in (64,128):
            body=pacman.render({'_width':width,'_dwell':5})
            with Image.open(BytesIO(body)) as image:
                self.assertEqual(image.size,(width,32))
                self.assertGreater(image.n_frames,40)
                frames=[]
                for frame in range(image.n_frames):
                    image.seek(frame);frames.append(image.convert('RGB').copy())
                self.assertGreater(len({f.tobytes() for f in frames}),40)
                out=Path('D:/planner/.build-tmp')/f'pacman-{width}.gif'
                frames=[f.resize((width*6,192),Image.Resampling.NEAREST) for f in frames]
                frames[0].save(out,save_all=True,append_images=frames[1:],duration=95,loop=0)


if __name__=='__main__':unittest.main()
