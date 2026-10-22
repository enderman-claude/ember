/* Runtime support for Ember programs. Linked into every executable. */
#include <stdint.h>
#include <stdio.h>

/* The compiled Ember entry point (`def main()`), emitted as em_main. */
extern void em_main(void);

/* Builtin: print(x: i64). Writes the value followed by a newline. */
void ember_print_i64(int64_t value) {
    printf("%lld\n", (long long)value);
}

int main(void) {
    em_main();
    return 0;
}
