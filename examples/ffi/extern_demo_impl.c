#include <stdint.h>
#include <stdio.h>

int64_t c_add(int64_t a, int64_t b) { return a + b; }

void c_print_twice(int64_t x) {
    printf("%lld\n%lld\n", (long long)x, (long long)x);
}
