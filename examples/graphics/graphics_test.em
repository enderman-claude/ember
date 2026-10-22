# Windows 11 graphics test: renders a 320x240 framebuffer and writes it as a 24-bit BMP.
#
#   ember build examples/graphics/graphics_test.em -o graphics_test
#   ./graphics_test > graphics_test.bmp        (or: ember run ... > graphics_test.bmp)
#
# Double-click the .bmp on Windows 11 to open it in Photos. The program writes only
# binary image data to stdout, so the redirected file must not contain anything else.
#
# The framebuffer is an ordinary [i64] array. Each pixel is packed as 0xRRGGBB.

def pack(r: i64, g: i64, b: i64) -> i64:
    return r * 65536 + g * 256 + b

def put_u16(v: i64):
    put_byte(v % 256)
    put_byte(v / 256 % 256)

def put_u32(v: i64):
    put_byte(v % 256)
    put_byte(v / 256 % 256)
    put_byte(v / 65536 % 256)
    put_byte(v / 16777216 % 256)

def write_bmp(fb: [i64], w: i64, h: i64):
    row = w * 3                        # bytes per row before padding
    pad = (4 - row % 4) % 4            # BMP rows are padded to a multiple of 4 bytes
    put_byte(66)                       # 'B'
    put_byte(77)                       # 'M'
    put_u32(54 + (row + pad) * h)      # total file size
    put_u32(0)                         # reserved
    put_u32(54)                        # offset of pixel data
    put_u32(40)                        # BITMAPINFOHEADER size
    put_u32(w)
    put_u32(h)                         # positive height: rows are stored bottom-up
    put_u16(1)                         # colour planes
    put_u16(24)                        # bits per pixel
    put_u32(0)                         # no compression
    put_u32((row + pad) * h)           # image data size
    put_u32(2835)                      # horizontal resolution (about 72 dpi)
    put_u32(2835)                      # vertical resolution
    put_u32(0)                         # colours in palette
    put_u32(0)                         # important colours
    for y in range(h):
        py = h - 1 - y
        for x in range(w):
            p = fb[py * w + x]
            put_byte(p % 256)          # blue
            put_byte(p / 256 % 256)    # green
            put_byte(p / 65536 % 256)  # red
        for k in range(pad):
            put_byte(0)

def main():
    w = 320
    h = 240
    fb = alloc(w * h)

    # 1. Gradient: red increases left to right, green top to bottom.
    for y in range(h):
        for x in range(w):
            fb[y * w + x] = pack(x * 255 / (w - 1), y * 255 / (h - 1), 160)

    # 2. Filled red rectangle.
    for y in range(40, 100):
        for x in range(30, 130):
            fb[y * w + x] = pack(230, 40, 40)

    # 3. Filled yellow circle, centre (230, 150), radius 60.
    cx = 230
    cy = 150
    rad = 60
    for y in range(cy - rad, cy + rad + 1):
        for x in range(cx - rad, cx + rad + 1):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= rad * rad:
                fb[y * w + x] = pack(250, 210, 30)

    # 4. 4-pixel checkerboard in the top-right corner, for checking pixel alignment.
    for y in range(10, 42):
        for x in range(250, 282):
            if ((x - 250) / 4 + (y - 10) / 4) % 2 == 0:
                fb[y * w + x] = pack(255, 255, 255)
            else:
                fb[y * w + x] = pack(0, 0, 0)

    # 5. One-pixel white border.
    for x in range(w):
        fb[x] = pack(255, 255, 255)
        fb[(h - 1) * w + x] = pack(255, 255, 255)
    for y in range(h):
        fb[y * w] = pack(255, 255, 255)
        fb[y * w + w - 1] = pack(255, 255, 255)

    write_bmp(fb, w, h)
    free(fb)
