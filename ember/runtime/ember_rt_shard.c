/* Freestanding runtime for Ember programs built with --target shard.
 *
 * SHARD images cannot call into libc (no DT_NEEDED, no undefined symbols), so this
 * file talks to the Linux kernel directly with system calls and provides the
 * same ember_* entry points as ember_rt.c.
 *
 * Arrays use the same layout as ember_rt.c: slot 0 holds the length. Each array
 * gets its own anonymous mapping, so ember_free returns memory to the kernel.
 *
 * Build with -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns so the
 * compiler never emits a call to memset or memcpy, which would be undefined.
 */
#include <stddef.h>
#include <stdint.h>

extern void em_main(void);

#define SYS_READ       0
#define SYS_WRITE      1
#define SYS_MMAP       9
#define SYS_MUNMAP     11
#define SYS_EXIT_GROUP 231

#define PAGE_SIZE 4096u

static long sys3(long n, long a, long b, long c)
{
    long ret;
    __asm__ volatile("syscall"
                     : "=a"(ret)
                     : "a"(n), "D"(a), "S"(b), "d"(c)
                     : "rcx", "r11", "memory");
    return ret;
}

static long sys6(long n, long a, long b, long c, long d, long e, long f)
{
    long ret;
    register long r10 __asm__("r10") = d;
    register long r8 __asm__("r8") = e;
    register long r9 __asm__("r9") = f;
    __asm__ volatile("syscall"
                     : "=a"(ret)
                     : "a"(n), "D"(a), "S"(b), "d"(c), "r"(r10), "r"(r8), "r"(r9)
                     : "rcx", "r11", "memory");
    return ret;
}

static void write_all(int fd, const char *buf, size_t len)
{
    while (len > 0) {
        long n = sys3(SYS_WRITE, fd, (long)(intptr_t)buf, (long)len);
        if (n <= 0) {
            return;
        }
        buf += n;
        len -= (size_t)n;
    }
}

static size_t cstr_len(const char *s)
{
    size_t n = 0;
    while (s[n] != '\0') {
        n++;
    }
    return n;
}

static void exit_now(int code) __attribute__((noreturn));
static void exit_now(int code)
{
    sys3(SYS_EXIT_GROUP, code, 0, 0);
    for (;;) {
    }
}

/* Stop the program with a message. Exit code 101 matches ember_rt.c. */
void ember_panic(int64_t code)
{
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
    write_all(2, "ember: panic: ", 14);
    write_all(2, msg, cstr_len(msg));
    write_all(2, "\n", 1);
    exit_now(101);
}

void ember_print_i64(int64_t value)
{
    char buf[24];
    size_t i = sizeof buf;
    uint64_t u = value < 0 ? (uint64_t)0 - (uint64_t)value : (uint64_t)value;

    buf[--i] = '\n';
    do {
        buf[--i] = (char)('0' + u % 10);
        u /= 10;
    } while (u != 0);
    if (value < 0) {
        buf[--i] = '-';
    }
    write_all(1, buf + i, sizeof buf - i);
}

void ember_print_bool(int64_t value)
{
    if (value) {
        write_all(1, "true\n", 5);
    } else {
        write_all(1, "false\n", 6);
    }
}

/* Writes one raw byte to stdout. Used for binary output such as BMP files. */
void ember_put_byte(int64_t value)
{
    char c = (char)(value & 0xFF);
    write_all(1, &c, 1);
}

static size_t mapping_bytes(int64_t n)
{
    size_t bytes = ((size_t)n + 1) * sizeof(int64_t);
    return (bytes + PAGE_SIZE - 1) & ~((size_t)PAGE_SIZE - 1);
}

static int64_t *array_block(int64_t handle)
{
    if (handle == 0) {
        ember_panic(4);
    }
    return (int64_t *)(intptr_t)handle;
}

int64_t ember_alloc(int64_t n)
{
    if (n < 0 || n > (INT64_MAX / 8) - 2) {
        ember_panic(3);
    }
    /* Anonymous mappings are zero-filled, which matches calloc. */
    long p = sys6(SYS_MMAP, 0, (long)mapping_bytes(n), 3 /* PROT_READ|PROT_WRITE */,
                  0x22 /* MAP_PRIVATE|MAP_ANONYMOUS */, -1, 0);
    if (p < 0 && p > -4096) {
        ember_panic(3);
    }
    int64_t *block = (int64_t *)(intptr_t)p;
    block[0] = n;
    return (int64_t)p;
}

void ember_free(int64_t handle)
{
    int64_t *block = array_block(handle);
    sys3(SYS_MUNMAP, (long)(intptr_t)block, (long)mapping_bytes(block[0]), 0);
}

int64_t ember_len(int64_t handle)
{
    return array_block(handle)[0];
}

static int64_t *element(int64_t handle, int64_t i)
{
    int64_t *block = array_block(handle);
    if (i < 0 || i >= block[0]) {
        ember_panic(2);
    }
    return block + 1 + i;
}

int64_t ember_load(int64_t handle, int64_t i)
{
    return *element(handle, i);
}

void ember_store(int64_t handle, int64_t i, int64_t value)
{
    *element(handle, i) = value;
}

/* Buffered stdin. */
static unsigned char in_buf[4096];
static size_t in_pos;
static size_t in_len;
static int in_eof;
static int input_ended_flag;

/* Returns the next byte of stdin, or -1 at end of input. */
static int next_byte(void)
{
    if (in_pos == in_len) {
        if (in_eof) {
            return -1;
        }
        long n = sys3(SYS_READ, 0, (long)(intptr_t)in_buf, sizeof in_buf);
        if (n <= 0) {
            in_eof = 1;
            return -1;
        }
        in_len = (size_t)n;
        in_pos = 0;
    }
    return in_buf[in_pos++];
}

/* Gives back the byte most recently returned by next_byte. */
static void push_back(int c)
{
    if (c != -1) {
        in_pos--;
    }
}

/* Reads one integer from stdin, skipping leading whitespace as scanf("%lld") does.
 * On failure it returns 0 and sets the flag that input_ended() reports. */
int64_t ember_read_int(void)
{
    int c;
    do {
        c = next_byte();
    } while (c == ' ' || (c >= '\t' && c <= '\r'));

    int neg = 0;
    if (c == '+' || c == '-') {
        neg = (c == '-');
        c = next_byte();
    }
    if (c < '0' || c > '9') {
        push_back(c);
        input_ended_flag = 1;
        return 0;
    }

    uint64_t v = 0;
    while (c >= '0' && c <= '9') {
        v = v * 10 + (uint64_t)(c - '0');
        c = next_byte();
    }
    push_back(c);
    input_ended_flag = 0;
    return neg ? -(int64_t)v : (int64_t)v;
}

int64_t ember_input_ended(void)
{
    return input_ended_flag;
}

/* Entry point. SHARD has no C runtime start-up code, so this calls the program
 * and exits the process when it returns. */
void _start(void) __attribute__((noreturn));
void _start(void)
{
    em_main();
    exit_now(0);
}
