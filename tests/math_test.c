/* Checks ember/runtime/ember_math.h against the system libm.
 * Built and run by tests/test_math.py. Prints "all math checks passed" on success.
 *
 * sqrt, floor, ceil and abs must match exactly. The rest are held to a bound in ulps
 * (units in the last place) that the test prints, so a regression is visible as a number. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ember_num.h"
#include "ember_math.h"

void *ember_num_alloc(size_t bytes) {
    void *p = malloc(bytes);
    if (!p) abort();
    return p;
}
void ember_num_free(void *p) { free(p); }
void ember_panic(int64_t code) {
    printf("unexpected panic %lld\n", (long long)code);
    exit(101);
}

static uint64_t rng_state = 0x9E3779B97F4A7C15ULL;
static uint64_t rnd(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return rng_state;
}
static double rnd_unit(void) { return (double)(rnd() >> 11) / 9007199254740992.0; } /* [0,1) */
static double rnd_range(double lo, double hi) { return lo + (hi - lo) * rnd_unit(); }
static double rnd_bits(void) { return bits_to_f64(rnd()); }

/* distance in representable doubles; both must be finite and not NaN */
static double ulps(double a, double b) {
    int64_t x = (int64_t)f64_to_bits(a), y = (int64_t)f64_to_bits(b);
    if (x < 0) x = INT64_MIN - x;
    if (y < 0) y = INT64_MIN - y;
    return (double)(x > y ? x - y : y - x);
}

static int failures, checks;
static void fail(const char *fn, double in, double in2, double got, double want) {
    if (failures++ < 20)
        printf("FAIL %s(%a, %a): got %a, want %a\n", fn, in, in2, got, want);
}

/* got and want must agree on NaN-ness, infinities and the sign of zero, and otherwise be
 * within bound ulps. Returns the ulp distance (0 for the special cases that agree). */
static double compare(const char *fn, double in, double in2, double got, double want,
                      double bound) {
    checks++;
    if (want != want) {
        if (got == got) fail(fn, in, in2, got, want);
        return 0;
    }
    if (got != got) { fail(fn, in, in2, got, want); return 0; }
    if (isinf(want) || isinf(got) || want == 0.0 || got == 0.0) {
        if (f64_to_bits(got) != f64_to_bits(want)) {
            /* a result that rounds to zero or inf may differ by one step at the edge */
            if (!(ulps(got, want) <= bound)) fail(fn, in, in2, got, want);
        }
        return 0;
    }
    double d = ulps(got, want);
    if (d > bound) fail(fn, in, in2, got, want);
    return d;
}

typedef struct { double max, at; } worst_t;
static void note(worst_t *w, double d, double at) {
    if (d > w->max) { w->max = d; w->at = at; }
}
static void report(const char *fn, worst_t w, double bound) {
    printf("  %-6s worst %.0f ulp (bound %.0f)", fn, w.max, bound);
    if (w.max > 0) printf(" at %a", w.at);
    printf("\n");
}

static void run1(const char *fn, double (*mine)(double), double (*ref)(double), double bound,
                 double (*gen)(void), int n) {
    worst_t w = {0, 0};
    for (int i = 0; i < n; i++) {
        double x = gen();
        note(&w, compare(fn, x, 0, mine(x), ref(x), bound), x);
    }
    report(fn, w, bound);
}

static double ref_floor(double x) { return floor(x); }
static double ref_ceil(double x) { return ceil(x); }
static double ref_sqrt(double x) { return sqrt(x); }
static double ref_sin(double x) { return sin(x); }
static double ref_cos(double x) { return cos(x); }
static double ref_tan(double x) { return tan(x); }
static double ref_atan(double x) { return atan(x); }
static double ref_exp(double x) { return exp(x); }
static double ref_ln(double x) { return log(x); }

static double g_any_bits(void) { return rnd_bits(); }
static double g_pos_bits(void) { return em_fabs(rnd_bits()); }
static double g_subnormal(void) { return bits_to_f64(rnd() & 0xFFFFFFFFFFFFFULL); }
static double g_small(void) { return rnd_range(-10.0, 10.0); }
static double g_mid(void) { return rnd_range(-1000.0, 1000.0); }
static double g_trig_wide(void) { return rnd_range(-1.6e6, 1.6e6); }
static double g_near_quarter(void) { /* within a few ulp of k * pi/2 */
    double k = floor(rnd_range(-1e6, 1e6));
    double x = k * 1.5707963267948966;
    return x * (1.0 + (rnd_unit() - 0.5) * 1e-15);
}
static double g_exp_dom(void) { return rnd_range(-745.0, 709.0); }
static double g_exp_small(void) { return rnd_range(-1.0, 1.0); }
static double g_ln_pos(void) { return exp(rnd_range(-700.0, 700.0)); }
static double g_ln_near1(void) { return 1.0 + (rnd_unit() - 0.5) * 1e-3; }
static double g_atan_wide(void) { return rnd_bits(); }
static double g_atan_mid(void) { return rnd_range(-5.0, 5.0); }

static void test_specials(void) {
    const double nan = em_nan(), inf = em_inf();
    const double vals[] = {nan, inf, -inf, 0.0, -0.0, 1.0, -1.0, 0.5, -0.5, 2.0, 4.0, 1e308,
                           -1e308, 5e-324, -5e-324, 2.2250738585072014e-308, 3.0, 100.0};
    const int nv = (int)(sizeof vals / sizeof vals[0]);
    for (int i = 0; i < nv; i++) {
        double x = vals[i];
        compare("sqrt", x, 0, em_sqrt(x), sqrt(x), 0);
        compare("floor", x, 0, em_floor(x), floor(x), 0);
        compare("ceil", x, 0, em_ceil(x), ceil(x), 0);
        compare("abs", x, 0, em_fabs(x), fabs(x), 0);
        compare("exp", x, 0, em_exp(x), exp(x), 2);
        compare("ln", x, 0, em_ln(x), log(x), 2);
        compare("atan", x, 0, em_atan(x), atan(x), 2);
        if (em_fabs(x) < EM_TRIG_LIMIT || x != x) {
            compare("sin", x, 0, em_sin(x), sin(x), 2);
            compare("cos", x, 0, em_cos(x), cos(x), 2);
            compare("tan", x, 0, em_tan(x), tan(x), 4);
        }
        for (int j = 0; j < nv; j++) {
            double y = vals[j];
            compare("atan2", y, x, em_atan2(y, x), atan2(y, x), 2);
        }
    }
    /* beyond the argument-reduction range: NaN, not a wrong number */
    checks += 6;
    if (!(em_sin(1e7) != em_sin(1e7)) || !(em_cos(-1e9) != em_cos(-1e9)) ||
        !(em_tan(inf) != em_tan(inf))) { printf("FAIL: out-of-range trig is not NaN\n"); failures++; }
    if (!(em_sin(1.6e6) == em_sin(1.6e6))) { printf("FAIL: sin(1.6e6) is NaN\n"); failures++; }
    /* exact values */
    checks += 5;
    if (em_sqrt(4.0) != 2.0 || em_sqrt(2.25) != 1.5 || em_floor(-1.5) != -2.0 ||
        em_ceil(-1.5) != -1.0 || em_exp(0.0) != 1.0) { printf("FAIL: exact values\n"); failures++; }
}

int main(void) {
    printf("math checks against libm:\n");
    run1("sqrt", em_sqrt, ref_sqrt, 0, g_pos_bits, 300000);
    run1("sqrt", em_sqrt, ref_sqrt, 0, g_subnormal, 100000);
    run1("sqrt", em_sqrt, ref_sqrt, 0, g_small, 100000);
    run1("floor", em_floor, ref_floor, 0, g_any_bits, 200000);
    run1("floor", em_floor, ref_floor, 0, g_mid, 200000);
    run1("ceil", em_ceil, ref_ceil, 0, g_any_bits, 200000);
    run1("ceil", em_ceil, ref_ceil, 0, g_mid, 200000);
    run1("sin", em_sin, ref_sin, 2, g_small, 300000);
    run1("sin", em_sin, ref_sin, 2, g_trig_wide, 300000);
    run1("sin", em_sin, ref_sin, 2, g_near_quarter, 200000);
    run1("cos", em_cos, ref_cos, 2, g_small, 300000);
    run1("cos", em_cos, ref_cos, 2, g_trig_wide, 300000);
    run1("cos", em_cos, ref_cos, 2, g_near_quarter, 200000);
    run1("tan", em_tan, ref_tan, 4, g_small, 300000);
    run1("tan", em_tan, ref_tan, 4, g_trig_wide, 300000);
    run1("tan", em_tan, ref_tan, 4, g_near_quarter, 200000);
    run1("atan", em_atan, ref_atan, 2, g_atan_mid, 300000);
    run1("atan", em_atan, ref_atan, 2, g_atan_wide, 200000);
    run1("exp", em_exp, ref_exp, 2, g_exp_dom, 300000);
    run1("exp", em_exp, ref_exp, 2, g_exp_small, 200000);
    run1("ln", em_ln, ref_ln, 2, g_ln_pos, 300000);
    run1("ln", em_ln, ref_ln, 2, g_ln_near1, 200000);
    run1("ln", em_ln, ref_ln, 2, g_pos_bits, 200000);
    run1("ln", em_ln, ref_ln, 2, g_subnormal, 100000);
    {
        worst_t w = {0, 0};
        for (int i = 0; i < 400000; i++) {
            double y = (i & 1) ? rnd_range(-10, 10) : rnd_bits();
            double x = (i & 2) ? rnd_range(-10, 10) : rnd_bits();
            note(&w, compare("atan2", y, x, em_atan2(y, x), atan2(y, x), 2), y);
        }
        report("atan2", w, 2);
    }
    test_specials();
    if (failures) {
        printf("%d of %d math checks FAILED\n", failures, checks);
        return 1;
    }
    printf("all math checks passed (%d)\n", checks);
    return 0;
}
