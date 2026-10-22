# Windows 11 window test: opens a 480x360 window and animates a colour gradient
# with a moving white circle. Close the window to exit.
#
#   ember build examples/windows/window_test.em --target windows -o window_test.exe
#
# Each frame is written into an [i64] framebuffer, one 0xRRGGBB value per pixel,
# and handed to window_present, which copies it to the window.

def pack(r: i64, g: i64, b: i64) -> i64:
    return r * 65536 + g * 256 + b

def render(fb: [i64], w: i64, h: i64, t: i64):
    cx = (t * 3) % w             # circle centre moves left to right and wraps
    cy = h / 2
    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy < 2500:
                fb[y * w + x] = pack(255, 255, 255)
            else:
                fb[y * w + x] = pack((x + t) % 256, (y * 2 + t) % 256, 160)

def main():
    w = 480
    h = 360
    if not window_open(w, h):
        return
    fb = alloc(w * h)
    mut frame = 0
    while not window_closed():
        render(fb, w, h, frame)
        window_present(fb)
        frame = frame + 1
    free(fb)
