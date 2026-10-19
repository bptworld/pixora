import random
import sys
import unittest
from unittest.mock import patch
from io import BytesIO
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'addons'))
import pacman


class PacmanTests(unittest.TestCase):
    def test_contact_triggers_death_and_restart(self):
        self.assertTrue(pacman._touching((20,20),(24,20)))
        self.assertFalse(pacman._touching((20,20),(24,24)))
        self.assertTrue(pacman._touching((1,72),(139,72)))
        deaths=[]
        original=pacman._caught
        def caught(draw,position,step):
            deaths.append(step);original(draw,position,step)
        initial=pacman._spawn(pacman._maze(64),64,random.Random(42))
        with patch('pacman._spawn',side_effect=lambda *args:list(initial)),patch('pacman._touching',return_value=True),patch('pacman._caught',side_effect=caught):
            pacman.render({'_width':64,'_dwell':3})
        self.assertEqual(deaths[:16],list(range(8))*2)

    def test_random_starting_positions(self):
        graph=pacman._maze(64)
        starts=[pacman._spawn(graph,64,random.Random(seed)) for seed in range(20)]
        self.assertGreaterEqual(len({actors[0][0] for actors in starts}),15)
        self.assertGreater(len({tuple(a[0] for a in actors) for actors in starts}),15)
        for actors in starts:
            self.assertIsNotNone(pacman._focus(actors,64))
            self.assertTrue(all(a[0] in graph for a in actors))
            self.assertFalse(any(pacman._touching(actors[i][0],actors[j][0]) for i in range(5) for j in range(i+1,5)))

    def test_two_ghosts_visible_in_every_frame(self):
        colors={(255,65,65),(255,153,214),(75,220,255),(255,170,55)}
        for width in (64,128):
            for seed in range(4):
                with patch('pacman.random.Random',return_value=random.Random(seed)):
                    body=pacman.render({'_width':width,'_dwell':60,'speed':'fast'})
                with Image.open(BytesIO(body)) as image:
                    for index in range(image.n_frames):
                        image.seek(index)
                        visible=colors.intersection(set(image.convert('RGB').getdata()))
                        self.assertGreaterEqual(len(visible),2,(width,seed,index))

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
                    if (before,(x,y)) in graph.tunnels:
                        self.assertEqual(before[1],y)
                    else:self.assertEqual(abs(x-before[0])+abs(y-before[1]),1)
                    for dx in range(-pacman.RADIUS,pacman.RADIUS+1):
                        for dy in range(-pacman.RADIUS,pacman.RADIUS+1):
                            self.assertNotEqual(background.getpixel((x+dx,y+dy)),(35,48,185))
                    dots.add((x,y));pacman._eat(dots,(x,y))
                    self.assertNotIn((x,y),dots)
                paths.append(route)
            self.assertNotEqual(*paths)

    def test_collapsed_walls_keep_large_characters(self):
        graph=pacman._maze(64)
        self.assertEqual(pacman.RADIUS,2)
        self.assertLessEqual(graph.world[0],90)
        self.assertLessEqual(graph.world[1],76)
        self.assertTrue(all(n in graph for neighbors in graph.values() for n in neighbors))

    def test_classic_layout(self):
        self.assertEqual(len(pacman.MAZE),31)
        self.assertTrue(all(len(row)==28 for row in pacman.MAZE))
        self.assertEqual(sum(row.count("o") for row in pacman.MAZE),4)
        graph=pacman._raw_maze(64)
        self.assertEqual(graph,pacman._raw_maze(128))
        self.assertIn((13*pacman.TILE+pacman.RADIUS,23*pacman.TILE+pacman.RADIUS),graph)
        self.assertNotIn((13*pacman.TILE+pacman.RADIUS,14*pacman.TILE+pacman.RADIUS),graph)  # ghost house is not a hallway

    def test_both_sizes_animate(self):
        for width in (64,128):
            body=pacman.render({'_width':width,'_dwell':5})
            with Image.open(BytesIO(body)) as image:
                self.assertEqual(image.size,(width,32))
                self.assertGreater(image.n_frames,40)
                frames=[]
                for frame in range(image.n_frames):
                    image.seek(frame);frames.append(image.convert('RGB').copy())
                self.assertGreater(len({f.tobytes() for f in frames}),20)  # caught animation deliberately holds still
                out=Path('D:/planner/.build-tmp')/f'pacman-{width}.gif'
                frames=[f.resize((width*6,192),Image.Resampling.NEAREST) for f in frames]
                frames[0].save(out,save_all=True,append_images=frames[1:],duration=95,loop=0)


if __name__=='__main__':unittest.main()
