/* Checks ember_num.h against expected results from tests/gen_num_cases.py.
 * Built and run by tests/test_floats.py. Prints "all numeric checks passed" on success. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ember_num.h"
#include "num_cases.inc"

void *ember_num_alloc(size_t bytes) {
    void *p = malloc(bytes);
    if (!p) abort();
    return p;
}

void ember_num_free(void *p) {
    free(p);
}

void ember_panic(int64_t code) {
    printf("unexpected panic %lld\n", (long long)code);
    exit(101);
}

static int failures;
static int checks;

static void expect_text(const char *what, char *got, const char *want) {
    checks++;
    if (strcmp(got, want) != 0) {
        failures++;
        if (failures <= 20) printf("FAIL %s:\n  got  %s\n  want %s\n", what, got, want);
    }
    ember_num_free(got);
}

/* Parses an optionally negative decimal integer string into a bigfloat handle. */
static int64_t big_int(const char *s) {
    if (s[0] == '-') {
        return ember_big_neg(ember_big_parse(s + 1));
    }
    return ember_big_parse(s);
}

static int64_t big_rational(const char *num, const char *den) {
    return ember_big_div(big_int(num), big_int(den));
}

int main(void) {
    /* f64: shortest round-trip text, and exact round trips through bigfloat. */
    for (size_t i = 0; i < sizeof F64_CASES / sizeof F64_CASES[0]; i++) {
        uint64_t bits = F64_CASES[i].bits;
        expect_text("f64 text", ember_fmt_f64(bits), F64_CASES[i].text);
        /* A bigfloat has no negative zero, so zero (either sign) is skipped here. */
        if (!bits_is_nan(bits, FMT_F64) && !bits_is_inf(bits, FMT_F64) && (bits << 1) != 0) {
            checks++;
            int64_t h = ember_big_from_f64((int64_t)bits);
            if (ember_convert(h, EMBER_T_BIG, EMBER_T_F64) != (int64_t)bits) {
                failures++;
                if (failures <= 20) printf("FAIL f64 round trip via bigfloat: %llx\n", (unsigned long long)bits);
            }
        }
    }

    /* f32: shortest round-trip text. */
    for (size_t i = 0; i < sizeof F32_CASES / sizeof F32_CASES[0]; i++) {
        expect_text("f32 text", ember_fmt_f32(F32_CASES[i].bits), F32_CASES[i].text);
    }

    /* bigfloat: exact arithmetic and exact printing. */
    for (size_t i = 0; i < sizeof BIG_CASES / sizeof BIG_CASES[0]; i++) {
        const big_case *c = &BIG_CASES[i];
        int64_t a = big_rational(c->an, c->ad);
        int64_t b = big_rational(c->bn, c->bd);
        int64_t r;
        switch (c->op) {
            case '+': r = ember_big_add(a, b); break;
            case '-': r = ember_big_sub(a, b); break;
            case '*': r = ember_big_mul(a, b); break;
            default:  r = ember_big_div(a, b); break;
        }
        expect_text("bigfloat text", ember_fmt_big(r), c->text);
    }

    /* Spot checks that do not come from the generator. */
    {
        int64_t third = ember_big_div(ember_big_from_i64(1), ember_big_from_i64(3));
        expect_text("1/3 as f64", ember_fmt_f64((uint64_t)ember_convert(third, EMBER_T_BIG, EMBER_T_F64)),
                    "0.3333333333333333");
    }
    expect_text("100/3", ember_fmt_big(ember_big_div(ember_big_from_i64(100), ember_big_from_i64(3))),
                "33.3333333333333333333333333333333333333333...");
    expect_text("2^100", ember_fmt_big(ember_big_mul(ember_big_from_i64(1LL << 62), ember_big_from_i64(1LL << 38))),
                "1267650600228229401496703205376");
    checks++;
    if (ember_big_cmp(big_rational("1", "3"), big_rational("3333", "10000")) <= 0) {
        failures++;
        printf("FAIL 1/3 is not greater than 0.3333\n");
    }
    checks++;
    if (ember_convert(ember_big_neg(ember_big_parse("7.9")), EMBER_T_BIG, EMBER_T_I64) != -7) {
        failures++;
        printf("FAIL truncation of -7.9\n");
    }

    if (failures) {
        printf("%d of %d numeric checks failed\n", failures, checks);
        return 1;
    }
    printf("all numeric checks passed (%d)\n", checks);
    return 0;
}
