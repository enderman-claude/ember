/* Runtime support for Ember programs. Linked into every executable.
 *
 * Arrays ([i64]) are heap blocks: slot 0 holds the length, slots 1..n hold the
 * elements. A handle is the block's address stored in an i64. Element access is
 * bounds-checked. Memory is manual: every alloc needs one matching free.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern void em_main(void);

static int input_ended_flag = 0;

/* Stop the program with a message. Exit code 101 is the same one Rust uses for panics. */
void ember_panic(int64_t code) {
    const char *msg;
    switch (code) {
        case 1:  msg = "division by zero"; break;
        case 2:  msg = "array index out of bounds"; break;
        case 3:  msg = "out of memory"; break;
        case 4:  msg = "invalid array handle"; break;
        default: msg = "runtime error"; break;
    }
    fflush(stdout);
    fprintf(stderr, "ember: panic: %s\n", msg);
    exit(101);
}

void ember_print_i64(int64_t value) {
    printf("%lld\n", (long long)value);
}

void ember_print_bool(int64_t value) {
    puts(value ? "true" : "false");
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
/* Writes one raw byte to stdout. Used for binary output such as BMP files. */
void ember_put_byte(int64_t value) {
    putchar((int)(value & 0xFF));
}

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

int main(void) {
    em_main();
    return 0;
}
