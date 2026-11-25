# Compare two folders of screenshots (tests/play_page_visual.js): files must match, each image within a few pixels. usage: compare_shots.py A B [tolerance]
import sys, os
from PIL import Image, ImageChops
a, b = sys.argv[1], sys.argv[2]; tol = int(sys.argv[3]) if len(sys.argv) > 3 else 8
bad = 0; fa, fb = sorted(os.listdir(a)), sorted(os.listdir(b))
if fa != fb: print('file lists differ', set(fa) ^ set(fb)); bad = 1
for f in fa:
    if f not in fb: continue
    x = Image.open(os.path.join(a, f)).convert('RGB'); y = Image.open(os.path.join(b, f)).convert('RGB')
    if x.size != y.size: print('SIZE', f); bad = 1; continue
    d = ImageChops.difference(x, y); n = sum(1 for p in d.get_flattened_data() if p != (0, 0, 0)) if hasattr(d, 'get_flattened_data') else sum(1 for p in d.getdata() if p != (0, 0, 0))
    if n > tol: print('DIFF', f, n, 'pixels, bbox', d.getbbox()); bad = 1
print('SAME within %d pixels per image (%d images)' % (tol, len(fa)) if not bad else 'DIFFERENT')
