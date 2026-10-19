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
                    if abs(x-before[0])==81:
                        self.assertEqual(y,43);self.assertEqual(before[1],43)
                    else:self.assertEqual(abs(x-before[0])+abs(y-before[1]),1)
                    for dx in range(-1,2):
                        for dy in range(-1,2):
                            self.assertNotEqual(background.getpixel((x+dx,y+dy)),(20,64,190))
                    dots.add((x,y));pacman._eat(dots,(x,y))
                    self.assertNotIn((x,y),dots)
                paths.append(route)
            self.assertNotEqual(*paths)

    def test_classic_layout(self):
        self.assertEqual(len(pacman.MAZE),31)
        self.assertTrue(all(len(row)==28 for row in pacman.MAZE))
        self.assertEqual(sum(row.count("o") for row in pacman.MAZE),4)
        graph=pacman._maze(64)
        self.assertEqual(graph,pacman._maze(128))
        self.assertIn((40,70),graph)
        self.assertNotIn((40,43),graph)  # ghost house is not a hallway

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
