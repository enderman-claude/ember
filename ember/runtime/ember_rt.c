/* Runtime support for Ember programs. Linked into every executable.
 *
 * Arrays ([i64]) are heap blocks: slot 0 holds the length, slots 1..n hold the
 * elements. A handle is the block's address stored in an i64. Element access is
 * bounds-checked. Memory is manual: every alloc needs one matching free.
 *
 * Windows builds (_WIN32) also get a window: window_open, window_present and
 * window_closed. A framebuffer is an [i64] array of packed 0x00RRGGBB pixels,
 * one per window pixel, row by row from the top.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#endif

extern void em_main(void);

static int input_ended_flag = 0;

/* Stop the program with a message. Exit code 101 matches Rust's panic exit code. */
void ember_panic(int64_t code) {
    const char *msg;
    switch (code) {
        case 1:  msg = "division by zero"; break;
        case 2:  msg = "array index out of bounds"; break;
        case 3:  msg = "out of memory"; break;
        case 4:  msg = "invalid array handle"; break;
        case 5:  msg = "window is not open"; break;
        case 6:  msg = "framebuffer is smaller than the window"; break;
        default: msg = "runtime error"; break;
    }
#ifdef _WIN32
    /* GUI programs have no console, so show the message in a dialog. */
    MessageBoxA(NULL, msg, "Ember panic", MB_ICONERROR | MB_OK);
#else
    fflush(stdout);
    fprintf(stderr, "ember: panic: %s\n", msg);
#endif
    exit(101);
}

void ember_print_i64(int64_t value) {
    printf("%lld\n", (long long)value);
}

void ember_print_bool(int64_t value) {
    puts(value ? "true" : "false");
}

/* Writes one raw byte to stdout. Used for binary output such as BMP files. */
void ember_put_byte(int64_t value) {
    putchar((int)(value & 0xFF));
}

static int64_t *array_block(int64_t handle) {
    if (handle == 0) {
        ember_panic(4);
    }
    return (int64_t *)(intptr_t)handle;
}

int64_t ember_alloc(int64_t n) {
    if (n < 0) {
        ember_panic(3);
    }
    int64_t *block = calloc((size_t)n + 1, sizeof(int64_t));
    if (block == NULL) {
        ember_panic(3);
    }
    block[0] = n;
    return (int64_t)(intptr_t)block;
}

void ember_free(int64_t handle) {
    free(array_block(handle));
}

int64_t ember_len(int64_t handle) {
    return array_block(handle)[0];
}

static int64_t *element(int64_t handle, int64_t i) {
    int64_t *block = array_block(handle);
    if (i < 0 || i >= block[0]) {
        ember_panic(2);
    }
    return block + 1 + i;
}

int64_t ember_load(int64_t handle, int64_t i) {
    return *element(handle, i);
}

void ember_store(int64_t handle, int64_t i, int64_t value) {
    *element(handle, i) = value;
}

/* Reads one integer from stdin. At end of input it returns 0 and sets the flag
 * that input_ended() reports. */
int64_t ember_read_int(void) {
    long long v = 0;
    if (scanf("%lld", &v) == 1) {
        input_ended_flag = 0;
        return (int64_t)v;
    }
    input_ended_flag = 1;
    return 0;
}

int64_t ember_input_ended(void) {
    return input_ended_flag;
}

#ifdef _WIN32

static HWND g_window = NULL;
static int g_closed = 0;
static int g_w = 0, g_h = 0;
static uint32_t *g_pixels = NULL;
static BITMAPINFO g_bmi;

static LRESULT CALLBACK ember_wndproc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CLOSE:
            DestroyWindow(hwnd);
            return 0;
        case WM_DESTROY:
            g_closed = 1;
            PostQuitMessage(0);
            return 0;
        default:
            return DefWindowProcA(hwnd, msg, wp, lp);
    }
}

/* Opens a window whose client area is w x h pixels. Returns 1 on success. */
int64_t ember_window_open(int64_t w, int64_t h) {
    if (g_window != NULL) {
        return 1;
    }
    if (w <= 0 || h <= 0 || w > 8192 || h > 8192) {
        return 0;
    }

    HINSTANCE inst = GetModuleHandleA(NULL);
    WNDCLASSA wc;
    memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = ember_wndproc;
    wc.hInstance = inst;
    wc.lpszClassName = "EmberWindow";
    wc.hCursor = LoadCursorA(NULL, IDC_ARROW);
    if (!RegisterClassA(&wc)) {
        return 0;
    }

    /* AdjustWindowRect makes the client area exactly w x h, excluding borders and title bar. */
    RECT r = {0, 0, (LONG)w, (LONG)h};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    g_window = CreateWindowExA(0, "EmberWindow", "Ember", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                               CW_USEDEFAULT, CW_USEDEFAULT,
                               r.right - r.left, r.bottom - r.top,
                               NULL, NULL, inst, NULL);
    if (g_window == NULL) {
        return 0;
    }

    g_w = (int)w;
    g_h = (int)h;
    g_pixels = malloc((size_t)g_w * (size_t)g_h * sizeof(uint32_t));
    if (g_pixels == NULL) {
        ember_panic(3);
    }
    memset(&g_bmi, 0, sizeof g_bmi);
    g_bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    g_bmi.bmiHeader.biWidth = g_w;
    g_bmi.bmiHeader.biHeight = -g_h;          /* negative: rows are stored top-down */
    g_bmi.bmiHeader.biPlanes = 1;
    g_bmi.bmiHeader.biBitCount = 32;
    g_bmi.bmiHeader.biCompression = BI_RGB;

    ShowWindow(g_window, SW_SHOW);
    return 1;
}

/* Processes window messages, copies the framebuffer to the window, and caps the
 * frame rate at about 60 per second. Returns immediately once the window is closed. */
void ember_window_present(int64_t handle) {
    if (g_window == NULL) {
        ember_panic(5);
    }
    int64_t *block = array_block(handle);
    if (block[0] < (int64_t)g_w * (int64_t)g_h) {
        ember_panic(6);
    }

    MSG msg;
    while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
        if (msg.message == WM_QUIT) {
            g_closed = 1;
        }
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    if (g_closed) {
        return;
    }

    /* Pixels are 0x00RRGGBB, which is exactly the layout of a 32-bit BI_RGB pixel. */
    int64_t *src = block + 1;
    size_t count = (size_t)g_w * (size_t)g_h;
    for (size_t i = 0; i < count; i++) {
        g_pixels[i] = (uint32_t)(src[i] & 0xFFFFFF);
    }

    HDC dc = GetDC(g_window);
    StretchDIBits(dc, 0, 0, g_w, g_h, 0, 0, g_w, g_h,
                  g_pixels, &g_bmi, DIB_RGB_COLORS, SRCCOPY);
    ReleaseDC(g_window, dc);

    Sleep(16);
}

int64_t ember_window_closed(void) {
    return g_closed;
}

#endif /* _WIN32 */

int main(void) {
    em_main();
    return 0;
}
