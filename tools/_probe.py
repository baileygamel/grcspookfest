from PIL import Image
from collections import deque
import sys

src = sys.argv[1]
im = Image.open(src).convert("RGB")
W,H = im.size
px = list(im.getdata())

def is_bg(i):
    r,g,b = px[i]
    mx = max(r,g,b); mn = min(r,g,b)
    return mx >= 196 and (mx-mn) <= 18

mask = bytearray(W*H)          # 1 = background
seen = bytearray(W*H)
dq = deque()
for x in range(W):
    for y in (0, H-1):
        i = y*W+x
        if not seen[i] and is_bg(i): seen[i]=1; dq.append(i)
for y in range(H):
    for x in (0, W-1):
        i = y*W+x
        if not seen[i] and is_bg(i): seen[i]=1; dq.append(i)

while dq:
    i = dq.popleft()
    mask[i] = 1
    x = i % W; y = i // W
    if x>0:
        j=i-1
        if not seen[j] and is_bg(j): seen[j]=1; dq.append(j)
    if x<W-1:
        j=i+1
        if not seen[j] and is_bg(j): seen[j]=1; dq.append(j)
    if y>0:
        j=i-W
        if not seen[j] and is_bg(j): seen[j]=1; dq.append(j)
    if y<H-1:
        j=i+W
        if not seen[j] and is_bg(j): seen[j]=1; dq.append(j)

print("bg pixels:", sum(mask), "of", W*H)

COLS, ROWS = 8, 4
cw, ch = W//COLS, H//ROWS
for r in range(ROWS):
    prof = []
    for yy in range(ch):
        y = r*ch + yy
        n = sum(0 if mask[y*W+x] else 1 for x in range(0, W))
        prof.append(n)
    # report last 60 rows of the cell
    tail = [(ch-60+k, prof[ch-60+k]) for k in range(60)]
    print("ROW", r, [f"{i}:{v}" for i,v in tail])
