/* Numeric support for Ember: f32, f64 and bigfloat.
 *
 * Included by ember_rt.c and ember_rt_shard.c, so it uses no libc. The including runtime
 * provides ember_num_alloc, ember_num_free and ember_panic.
 *
 * f32 and f64 values travel through generated code as their IEEE bit patterns in an i64.
 * A bigfloat is a handle to an exact rational: a sign, and a numerator and denominator in
 * lowest terms. 100/3 is stored as 100/3 and is never rounded. Operations allocate;
 * bigfloat values are never freed.
 *
 * Printing is deterministic and identical on every target: a float prints as the shortest
 * decimal that reads back as the same value (like Python's repr), and a bigfloat prints
 * exactly when its decimal expansion terminates, and otherwise with 40 digits and "...".
 */
#ifndef EMBER_NUM_H
#define EMBER_NUM_H

#include <stddef.h>
#include <stdint.h>

void *ember_num_alloc(size_t bytes); /* never returns NULL */
void ember_num_free(void *p);
void ember_panic(int64_t code);

#define EMBER_BIG_FRACTION_DIGITS 40

/* ---- natural numbers: little-endian 32-bit limbs, n == 0 means zero ------------- */

typedef uint32_t nlimb;
typedef struct {
    size_t n;
    nlimb *d;
} nat;

static inline nat nat_alloc(size_t n) {
    nat r;
    r.n = n;
    r.d = ember_num_alloc((n ? n : 1) * sizeof(nlimb));
    for (size_t i = 0; i < n; i++) r.d[i] = 0;
    return r;
}

static inline void nat_free(nat a) {
    ember_num_free(a.d);
}

static inline void nat_trim(nat *a) {
    while (a->n && a->d[a->n - 1] == 0) a->n--;
}

static inline nat nat_from_u64(uint64_t v) {
    nat r = nat_alloc(2);
    r.d[0] = (nlimb)v;
    r.d[1] = (nlimb)(v >> 32);
    nat_trim(&r);
    return r;
}

static inline nat nat_copy(nat a) {
    nat r = nat_alloc(a.n);
    for (size_t i = 0; i < a.n; i++) r.d[i] = a.d[i];
    r.n = a.n;
    return r;
}

static inline uint64_t nat_to_u64(nat a) { /* caller ensures a fits in 64 bits */
    uint64_t v = 0;
    if (a.n > 0) v = a.d[0];
    if (a.n > 1) v |= (uint64_t)a.d[1] << 32;
    return v;
}

static inline int nat_cmp(nat a, nat b) {
    if (a.n != b.n) return a.n < b.n ? -1 : 1;
    for (size_t i = a.n; i-- > 0;) {
        if (a.d[i] != b.d[i]) return a.d[i] < b.d[i] ? -1 : 1;
    }
    return 0;
}

static inline int nat_is_one(nat a) {
    return a.n == 1 && a.d[0] == 1;
}

static inline nat nat_add(nat a, nat b) {
    size_t m = a.n > b.n ? a.n : b.n;
    nat r = nat_alloc(m + 1);
    uint64_t carry = 0;
    for (size_t i = 0; i < m; i++) {
        uint64_t s = carry;
        if (i < a.n) s += a.d[i];
        if (i < b.n) s += b.d[i];
        r.d[i] = (nlimb)s;
        carry = s >> 32;
    }
    r.d[m] = (nlimb)carry;
    nat_trim(&r);
    return r;
}

/* a - b, requires a >= b */
static inline nat nat_sub(nat a, nat b) {
    nat r = nat_alloc(a.n);
    int64_t borrow = 0;
    for (size_t i = 0; i < a.n; i++) {
        int64_t d = (int64_t)a.d[i] - borrow - (i < b.n ? (int64_t)b.d[i] : 0);
        if (d < 0) {
            d += (int64_t)1 << 32;
            borrow = 1;
        } else {
            borrow = 0;
        }
        r.d[i] = (nlimb)d;
    }
    nat_trim(&r);
    return r;
}

static inline nat nat_mul(nat a, nat b) {
    nat r = nat_alloc(a.n + b.n + 1);
    for (size_t i = 0; i < a.n; i++) {
        uint64_t carry = 0;
        for (size_t j = 0; j < b.n; j++) {
            uint64_t t = (uint64_t)a.d[i] * b.d[j] + r.d[i + j] + carry;
            r.d[i + j] = (nlimb)t;
            carry = t >> 32;
        }
        r.d[i + b.n] = (nlimb)carry;
    }
    nat_trim(&r);
    return r;
}

/* a * m + add, for single-limb m and add */
static inline nat nat_mul_small_add(nat a, nlimb m, nlimb add) {
    nat r = nat_alloc(a.n + 1);
    uint64_t carry = add;
    for (size_t i = 0; i < a.n; i++) {
        uint64_t t = (uint64_t)a.d[i] * m + carry;
        r.d[i] = (nlimb)t;
        carry = t >> 32;
    }
    r.d[a.n] = (nlimb)carry;
    nat_trim(&r);
    return r;
}

static inline nat nat_shl(nat a, size_t bits) {
    size_t limbs = bits / 32, sh = bits % 32;
    nat r = nat_alloc(a.n + limbs + 1);
    for (size_t i = 0; i < a.n; i++) {
        uint64_t v = (uint64_t)a.d[i] << sh;
        r.d[i + limbs] |= (nlimb)v;
        r.d[i + limbs + 1] |= (nlimb)(v >> 32);
    }
    nat_trim(&r);
    return r;
}

static inline nat nat_pow2(size_t k) {
    nat one = nat_from_u64(1);
    nat r = nat_shl(one, k);
    nat_free(one);
    return r;
}

static inline nat nat_pow10(size_t k) {
    nat r = nat_from_u64(1);
    while (k >= 9) {
        nat t = nat_mul_small_add(r, 1000000000u, 0);
        nat_free(r);
        r = t;
        k -= 9;
    }
    nlimb m = 1;
    while (k--) m *= 10;
    nat t = nat_mul_small_add(r, m, 0);
    nat_free(r);
    return t;
}

static inline size_t nat_bits(nat a) {
    if (a.n == 0) return 0;
    nlimb top = a.d[a.n - 1];
    size_t b = 0;
    while (top) {
        b++;
        top >>= 1;
    }
    return (a.n - 1) * 32 + b;
}

static inline int nat_bit(nat a, size_t i) {
    size_t w = i / 32;
    return w < a.n ? (int)((a.d[w] >> (i % 32)) & 1) : 0;
}

/* Quotient and remainder by one limb. The caller frees *q. */
static inline nlimb nat_divmod_small(nat a, nlimb d, nat *q) {
    nat r = nat_alloc(a.n);
    uint64_t rem = 0;
    for (size_t i = a.n; i-- > 0;) {
        uint64_t cur = (rem << 32) | a.d[i];
        r.d[i] = (nlimb)(cur / d);
        rem = cur % d;
    }
    r.n = a.n;
    nat_trim(&r);
    *q = r;
    return (nlimb)rem;
}

/* Quotient and remainder (binary long division). b must be non-zero. The caller frees both. */
static inline void nat_divmod(nat a, nat b, nat *q, nat *r) {
    nat quo = nat_alloc(a.n);
    nat rem = nat_alloc(b.n + 1);
    size_t rn = 0;
    for (size_t i = nat_bits(a); i-- > 0;) {
        nlimb carry = (nlimb)nat_bit(a, i);
        for (size_t k = 0; k < rn; k++) {
            nlimb top = rem.d[k] >> 31;
            rem.d[k] = (rem.d[k] << 1) | carry;
            carry = top;
        }
        if (carry) rem.d[rn++] = carry;
        nat cur = {rn, rem.d};
        if (nat_cmp(cur, b) >= 0) {
            nat diff = nat_sub(cur, b);
            for (size_t k = 0; k < rn; k++) rem.d[k] = 0;
            for (size_t k = 0; k < diff.n; k++) rem.d[k] = diff.d[k];
            rn = diff.n;
            nat_free(diff);
            quo.d[i / 32] |= (nlimb)1 << (i % 32);
        }
    }
    nat_trim(&quo);
    nat rr = nat_alloc(rn);
    for (size_t k = 0; k < rn; k++) rr.d[k] = rem.d[k];
    rr.n = rn;
    nat_trim(&rr);
    nat_free(rem);
    *q = quo;
    *r = rr;
}

/* a * 10^k, with the power freed. */
static inline nat nat_mul_pow10(nat a, size_t k) {
    nat p = nat_pow10(k);
    nat r = nat_mul(a, p);
    nat_free(p);
    return r;
}

static inline nat nat_gcd(nat a, nat b) {
    nat x = nat_copy(a), y = nat_copy(b);
    while (y.n) {
        nat q, r;
        nat_divmod(x, y, &q, &r);
        nat_free(q);
        nat_free(x);
        x = y;
        y = r;
    }
    nat_free(y);
    return x;
}

/* Decimal digits of a, with no leading zeros. The caller frees the returned buffer. */
static inline char *nat_to_dec(nat a, size_t *len) {
    if (a.n == 0) {
        char *z = ember_num_alloc(2);
        z[0] = '0';
        z[1] = '\0';
        *len = 1;
        return z;
    }
    size_t chunks = 2 * a.n + 4;
    nlimb *parts = ember_num_alloc(chunks * sizeof(nlimb));
    size_t nc = 0;
    nat cur = nat_copy(a);
    while (cur.n) {
        nat q;
        parts[nc++] = nat_divmod_small(cur, 1000000000u, &q);
        nat_free(cur);
        cur = q;
    }
    nat_free(cur);
    char *out = ember_num_alloc(nc * 9 + 2);
    size_t pos = 0;
    for (size_t c = nc; c-- > 0;) {
        nlimb v = parts[c];
        char tmp[9];
        for (int k = 8; k >= 0; k--) {
            tmp[k] = (char)('0' + v % 10);
            v /= 10;
        }
        int start = 0;
        if (c == nc - 1) {
            while (start < 8 && tmp[start] == '0') start++;
        }
        for (int k = start; k < 9; k++) out[pos++] = tmp[k];
    }
    out[pos] = '\0';
    ember_num_free(parts);
    *len = pos;
    return out;
}

/* ---- rationals ----------------------------------------------------------------- */

/* Value = (neg ? -1 : 1) * num / den. Reduced, den > 0, zero is 0/1 with neg = 0.
 * Owns num and den. */
typedef struct {
    int neg;
    nat num, den;
} rat;

static inline rat rat_make(int neg, nat num, nat den) {
    if (num.n == 0) {
        nat_free(num);
        nat_free(den);
        rat z = {0, nat_from_u64(0), nat_from_u64(1)};
        return z;
    }
    nat g = nat_gcd(num, den);
    if (!nat_is_one(g)) {
        nat q, r;
        nat_divmod(num, g, &q, &r);
        nat_free(r);
        nat_free(num);
        num = q;
        nat_divmod(den, g, &q, &r);
        nat_free(r);
        nat_free(den);
        den = q;
    }
    nat_free(g);
    rat out = {neg, num, den};
    return out;
}

static inline void rat_free(rat r) {
    nat_free(r.num);
    nat_free(r.den);
}

static inline rat rat_copy(rat r) {
    rat c = {r.neg, nat_copy(r.num), nat_copy(r.den)};
    return c;
}

static inline rat rat_from_i64(int64_t v) {
    int neg = v < 0;
    uint64_t mag = neg ? (uint64_t)0 - (uint64_t)v : (uint64_t)v;
    return rat_make(neg, nat_from_u64(mag), nat_from_u64(1));
}

/* mant * 2^exp with the given sign */
static inline rat rat_from_mant_exp(int neg, uint64_t mant, long exp) {
    nat m = nat_from_u64(mant);
    if (exp >= 0) {
        nat num = nat_shl(m, (size_t)exp);
        nat_free(m);
        return rat_make(neg, num, nat_from_u64(1));
    }
    return rat_make(neg, m, nat_pow2((size_t)(-exp)));
}

static inline rat rat_add(rat a, rat b) {
    nat x = nat_mul(a.num, b.den);
    nat y = nat_mul(b.num, a.den);
    nat den = nat_mul(a.den, b.den);
    nat num;
    int neg;
    if (a.neg == b.neg) {
        num = nat_add(x, y);
        neg = a.neg;
    } else if (nat_cmp(x, y) >= 0) {
        num = nat_sub(x, y);
        neg = a.neg;
    } else {
        num = nat_sub(y, x);
        neg = b.neg;
    }
    nat_free(x);
    nat_free(y);
    return rat_make(neg, num, den);
}

static inline rat rat_neg(rat a) {
    return rat_make(!a.neg, nat_copy(a.num), nat_copy(a.den));
}

static inline rat rat_mul(rat a, rat b) {
    return rat_make(a.neg != b.neg, nat_mul(a.num, b.num), nat_mul(a.den, b.den));
}

static inline rat rat_div(rat a, rat b) {
    if (b.num.n == 0) ember_panic(1); /* division by zero */
    return rat_make(a.neg != b.neg, nat_mul(a.num, b.den), nat_mul(a.den, b.num));
}

static inline int rat_sign(rat a) {
    if (a.num.n == 0) return 0;
    return a.neg ? -1 : 1;
}

static inline int rat_cmp(rat a, rat b) {
    int sa = rat_sign(a), sb = rat_sign(b);
    if (sa != sb) return sa < sb ? -1 : 1;
    if (sa == 0) return 0;
    nat x = nat_mul(a.num, b.den);
    nat y = nat_mul(b.num, a.den);
    int c = nat_cmp(x, y);
    nat_free(x);
    nat_free(y);
    return sa > 0 ? c : -c;
}

/* Compares |r| with 10^k. Returns -1, 0 or 1. */
static inline int rat_cmp_pow10(rat r, long k) {
    nat x, y;
    if (k >= 0) {
        x = nat_copy(r.num);
        y = nat_mul_pow10(r.den, (size_t)k);
    } else {
        x = nat_mul_pow10(r.num, (size_t)(-k));
        y = nat_copy(r.den);
    }
    int c = nat_cmp(x, y);
    nat_free(x);
    nat_free(y);
    return c;
}

/* Parses digits with an optional '.', as written in a bigfloat literal: "33.3" is 333/10. */
static inline rat rat_parse_decimal(const char *s) {
    nat num = nat_from_u64(0);
    size_t frac = 0;
    int seen_dot = 0;
    for (const char *p = s; *p; p++) {
        if (*p == '.') {
            seen_dot = 1;
        } else if (*p >= '0' && *p <= '9') {
            nat t = nat_mul_small_add(num, 10, (nlimb)(*p - '0'));
            nat_free(num);
            num = t;
            if (seen_dot) frac++;
        }
    }
    return rat_make(0, num, nat_pow10(frac));
}

/* ---- float bit patterns --------------------------------------------------------- */

/* Format parameters: p = significand bits (with the hidden bit), minq = exponent of the
 * smallest subnormal, bias, and expmax = the all-ones exponent field. */
typedef struct {
    int p, minq, bias, expmax, signpos;
} fmt_t;

static const fmt_t FMT_F64 = {53, -1074, 1023, 2047, 63};
static const fmt_t FMT_F32 = {24, -149, 127, 255, 31};

/* Rounds |r| to the nearest float in the format (ties to even). Returns the bits,
 * with the sign bit set when r is negative. Overflow gives infinity. */
static inline uint64_t rat_to_bits(rat r, fmt_t f) {
    uint64_t signbit = r.neg ? ((uint64_t)1 << f.signpos) : 0;
    if (r.num.n == 0) return 0;

    /* 2^E <= |r| < 2^(E+1) */
    long E = (long)nat_bits(r.num) - (long)nat_bits(r.den);
    if (E >= 0) {
        nat t = nat_shl(r.den, (size_t)E);
        if (nat_cmp(r.num, t) < 0) E--;
        nat_free(t);
    } else {
        nat t = nat_shl(r.num, (size_t)(-E));
        if (nat_cmp(t, r.den) < 0) E--;
        nat_free(t);
    }

    long qe = E - (f.p - 1);
    if (qe < f.minq) qe = f.minq;
    nat n, d;
    if (qe >= 0) {
        n = nat_copy(r.num);
        d = nat_shl(r.den, (size_t)qe);
    } else {
        n = nat_shl(r.num, (size_t)(-qe));
        d = nat_copy(r.den);
    }
    nat q, rem;
    nat_divmod(n, d, &q, &rem);
    nat twice = nat_shl(rem, 1);
    int c = nat_cmp(twice, d);
    if (c > 0 || (c == 0 && q.n && (q.d[0] & 1))) {
        nat one = nat_from_u64(1);
        nat t = nat_add(q, one);
        nat_free(q);
        nat_free(one);
        q = t;
    }
    nat_free(n);
    nat_free(d);
    nat_free(rem);
    nat_free(twice);

    uint64_t m = nat_to_u64(q);
    nat_free(q);
    uint64_t hidden = (uint64_t)1 << (f.p - 1);
    if (m == hidden * 2) {
        m = hidden;
        qe++;
    }
    if (m == 0) return signbit;
    if (m < hidden) return signbit | m; /* subnormal: qe is minq here */
    long biased = qe + (f.p - 1) + f.bias;
    if (biased >= f.expmax) {
        return signbit | ((uint64_t)f.expmax << (f.p - 1)); /* infinity */
    }
    return signbit | ((uint64_t)biased << (f.p - 1)) | (m - hidden);
}

/* Exact value of a finite, non-NaN float bit pattern (sign included). */
static inline rat rat_from_bits(uint64_t bits, fmt_t f) {
    int neg = (int)((bits >> f.signpos) & 1);
    uint64_t frac_mask = ((uint64_t)1 << (f.p - 1)) - 1;
    uint64_t e = (bits >> (f.p - 1)) & (((uint64_t)f.expmax + 1) - 1);
    uint64_t m = bits & frac_mask;
    uint64_t mant;
    long exp;
    if (e == 0) {
        mant = m;
        exp = f.minq;
    } else {
        mant = m | ((uint64_t)1 << (f.p - 1));
        exp = (long)e - f.bias - (f.p - 1);
    }
    return rat_from_mant_exp(neg, mant, exp);
}

static inline int bits_is_nan(uint64_t bits, fmt_t f) {
    uint64_t e = (bits >> (f.p - 1)) & (((uint64_t)f.expmax + 1) - 1);
    uint64_t m = bits & (((uint64_t)1 << (f.p - 1)) - 1);
    return e == (uint64_t)f.expmax && m != 0;
}

static inline int bits_is_inf(uint64_t bits, fmt_t f) {
    uint64_t e = (bits >> (f.p - 1)) & (((uint64_t)f.expmax + 1) - 1);
    uint64_t m = bits & (((uint64_t)1 << (f.p - 1)) - 1);
    return e == (uint64_t)f.expmax && m == 0;
}

/* Digits: the integer Q with exactly ndig digits, closest to |r| * 10^(ndig-1-E10). */
static inline void rat_digits(rat r, int ndig, nat *Q, long *E10out) {
    long E2 = (long)nat_bits(r.num) - (long)nat_bits(r.den);
    long E10 = E2 * 30103 / 100000;
    while (rat_cmp_pow10(r, E10 + 1) >= 0) E10++;
    while (rat_cmp_pow10(r, E10) < 0) E10--;

    long s = (long)ndig - 1 - E10;
    nat N, D;
    if (s >= 0) {
        N = nat_mul_pow10(r.num, (size_t)s);
        D = nat_copy(r.den);
    } else {
        N = nat_copy(r.num);
        D = nat_mul_pow10(r.den, (size_t)(-s));
    }
    nat q, rem;
    nat_divmod(N, D, &q, &rem);
    nat twice = nat_shl(rem, 1);
    int c = nat_cmp(twice, D);
    if (c > 0 || (c == 0 && q.n && (q.d[0] & 1))) {
        nat one = nat_from_u64(1);
        nat t = nat_add(q, one);
        nat_free(q);
        nat_free(one);
        q = t;
    }
    nat_free(N);
    nat_free(D);
    nat_free(rem);
    nat_free(twice);

    nat limit = nat_pow10((size_t)ndig);
    if (nat_cmp(q, limit) == 0) { /* rounded up to the next power of ten */
        nat_free(q);
        q = nat_pow10((size_t)(ndig - 1));
        E10++;
    }
    nat_free(limit);
    *Q = q;
    *E10out = E10;
}

/* ---- output buffer --------------------------------------------------------------- */

typedef struct {
    char *buf;
    size_t cap, len;
} out_t;

static inline void out_init(out_t *o) {
    o->cap = 64;
    o->len = 0;
    o->buf = ember_num_alloc(o->cap);
}

static inline void out_char(out_t *o, char c) {
    if (o->len + 1 >= o->cap) {
        size_t ncap = o->cap * 2;
        char *nb = ember_num_alloc(ncap);
        for (size_t i = 0; i < o->len; i++) nb[i] = o->buf[i];
        ember_num_free(o->buf);
        o->buf = nb;
        o->cap = ncap;
    }
    o->buf[o->len++] = c;
    o->buf[o->len] = '\0';
}

static inline void out_chars(out_t *o, const char *s, size_t n) {
    for (size_t i = 0; i < n; i++) out_char(o, s[i]);
}

/* Finds the shortest decimal (fewest significant digits, correctly rounded) that reads back
 * as the same float as the magnitude target. Writes its significant digits (trailing zeros
 * removed) and the decimal exponent of the first digit. */
static inline void shortest_digits(rat mag, fmt_t f, uint64_t target, int maxdig,
                                   char *digits, size_t *ndig_out, long *x_out) {
    nat Q = nat_from_u64(0);
    long E10 = 0;
    for (int ndig = 1; ndig <= maxdig; ndig++) {
        nat q;
        long e10;
        rat_digits(mag, ndig, &q, &e10);
        long e = e10 - ndig + 1;
        rat cand;
        if (e >= 0) {
            cand = rat_make(0, nat_mul_pow10(q, (size_t)e), nat_from_u64(1));
        } else {
            cand = rat_make(0, nat_copy(q), nat_pow10((size_t)(-e)));
        }
        uint64_t got = rat_to_bits(cand, f);
        rat_free(cand);
        nat_free(Q);
        Q = q;
        E10 = e10;
        if (got == target) break;   /* the last ndig (maxdig) is always exact enough */
    }
    size_t len;
    char *dec = nat_to_dec(Q, &len);
    size_t k = len;
    while (k > 1 && dec[k - 1] == '0') k--;
    for (size_t i = 0; i < k; i++) digits[i] = dec[i];
    *ndig_out = k;
    *x_out = E10;
    ember_num_free(dec);
    nat_free(Q);
}

static inline void write_plain_or_sci(out_t *o, const char *digits, size_t k, long x) {
    if (x >= -4 && x < 16) {
        if (x >= 0) {
            for (long i = 0; i <= x; i++) out_char(o, (size_t)i < k ? digits[i] : '0');
            out_char(o, '.');
            if ((size_t)x + 1 < k) {
                out_chars(o, digits + x + 1, k - (size_t)x - 1);
            } else {
                out_char(o, '0');
            }
        } else {
            out_char(o, '0');
            out_char(o, '.');
            for (long i = 0; i < -x - 1; i++) out_char(o, '0');
            out_chars(o, digits, k);
        }
        return;
    }
    out_char(o, digits[0]);
    if (k > 1) {
        out_char(o, '.');
        out_chars(o, digits + 1, k - 1);
    }
    out_char(o, 'e');
    out_char(o, x < 0 ? '-' : '+');
    long ax = x < 0 ? -x : x;
    char tmp[12];
    int tn = 0;
    do {
        tmp[tn++] = (char)('0' + ax % 10);
        ax /= 10;
    } while (ax);
    if (tn < 2) tmp[tn++] = '0';
    while (tn) out_char(o, tmp[--tn]);
}

static inline char *fmt_float(uint64_t bits, fmt_t f) {
    out_t o;
    out_init(&o);
    if (bits_is_nan(bits, f)) {
        out_chars(&o, "nan", 3);
        return o.buf;
    }
    int neg = (int)((bits >> f.signpos) & 1);
    if (bits_is_inf(bits, f)) {
        if (neg) out_char(&o, '-');
        out_chars(&o, "inf", 3);
        return o.buf;
    }
    if (neg) out_char(&o, '-');
    uint64_t magbits = bits & (((uint64_t)1 << f.signpos) - 1);
    if (magbits == 0) {
        out_chars(&o, "0.0", 3);
        return o.buf;
    }
    rat mag = rat_from_bits(magbits, f);
    char digits[32];
    digits[0] = '0';   /* shortest_digits always writes at least one digit */
    size_t k;
    long x;
    shortest_digits(mag, f, magbits, f.p == 53 ? 17 : 9, digits, &k, &x);
    rat_free(mag);
    write_plain_or_sci(&o, digits, k, x);
    return o.buf;
}

static inline char *fmt_bigfloat(int64_t handle) {
    rat r = *(rat *)(intptr_t)handle;
    out_t o;
    out_init(&o);
    if (r.num.n == 0) {
        out_char(&o, '0');
        return o.buf;
    }
    if (r.neg) out_char(&o, '-');

    /* A terminating decimal has a denominator of the form 2^a * 5^b. */
    nat d = nat_copy(r.den);
    size_t a = 0, b = 0;
    for (;;) {
        nat q;
        if (nat_divmod_small(d, 2, &q)) { nat_free(q); break; }
        nat_free(d);
        d = q;
        a++;
    }
    for (;;) {
        nat q;
        if (nat_divmod_small(d, 5, &q)) { nat_free(q); break; }
        nat_free(d);
        d = q;
        b++;
    }
    int terminating = nat_is_one(d);
    nat_free(d);

    if (terminating) {
        size_t k = a > b ? a : b;
        nat scaled = nat_mul_pow10(r.num, k);
        nat ip, rem;
        nat_divmod(scaled, r.den, &ip, &rem);
        nat_free(rem);
        nat_free(scaled);
        size_t len;
        char *dec = nat_to_dec(ip, &len);
        nat_free(ip);
        if (k == 0) {
            out_chars(&o, dec, len);
        } else {
            /* pad to at least k+1 digits, then place the point k digits from the right */
            size_t total = len < k + 1 ? k + 1 : len;
            size_t pad = total - len;
            size_t int_len = total - k;
            for (size_t i = 0; i < total; i++) {
                if (i == int_len) out_char(&o, '.');
                out_char(&o, i < pad ? '0' : dec[i - pad]);
            }
        }
        ember_num_free(dec);
        return o.buf;
    }

    nat ip, rem;
    nat_divmod(r.num, r.den, &ip, &rem);
    size_t ilen;
    char *idec = nat_to_dec(ip, &ilen);
    nat_free(ip);
    out_chars(&o, idec, ilen);
    ember_num_free(idec);
    out_char(&o, '.');
    nat scale = nat_pow10(EMBER_BIG_FRACTION_DIGITS);
    nat fracdigits = nat_mul(rem, scale);
    nat fq, fr;
    nat_divmod(fracdigits, r.den, &fq, &fr);
    nat_free(fr);
    nat_free(fracdigits);
    nat_free(scale);
    nat_free(rem);
    size_t flen;
    char *fdec = nat_to_dec(fq, &flen);
    nat_free(fq);
    for (size_t i = flen; i < EMBER_BIG_FRACTION_DIGITS; i++) out_char(&o, '0');
    out_chars(&o, fdec, flen);
    ember_num_free(fdec);
    out_chars(&o, "...", 3);
    return o.buf;
}

/* ---- exported runtime functions ------------------------------------------------- */

static inline int64_t big_box(rat r) {
    rat *p = ember_num_alloc(sizeof *p);
    *p = r;
    return (int64_t)(intptr_t)p;
}

static inline rat big_get(int64_t h) {
    return *(rat *)(intptr_t)h;
}

/* Format helpers used by the runtime's print functions. The caller frees the result. */
char *ember_fmt_f64(uint64_t bits) {
    return fmt_float(bits, FMT_F64);
}

char *ember_fmt_f32(uint64_t bits) {
    return fmt_float(bits, FMT_F32);
}

char *ember_fmt_big(int64_t handle) {
    return fmt_bigfloat(handle);
}

static inline double bits_to_f64(uint64_t b) {
    union { uint64_t u; double d; } x;
    x.u = b;
    return x.d;
}

static inline uint64_t f64_to_bits(double d) {
    union { uint64_t u; double d; } x;
    x.d = d;
    return x.u;
}

static inline float bits_to_f32(uint64_t b) {
    union { uint32_t u; float f; } x;
    x.u = (uint32_t)b;
    return x.f;
}

static inline uint64_t f32_to_bits(float f) {
    union { uint32_t u; float f; } x;
    x.f = f;
    return x.u;
}

int64_t ember_big_parse(const char *s) {
    return big_box(rat_parse_decimal(s));
}

int64_t ember_big_from_i64(int64_t v) {
    return big_box(rat_from_i64(v));
}

int64_t ember_big_from_f64(int64_t bits) {
    if (bits_is_nan((uint64_t)bits, FMT_F64) || bits_is_inf((uint64_t)bits, FMT_F64)) ember_panic(8);
    return big_box(rat_from_bits((uint64_t)bits, FMT_F64));
}

int64_t ember_big_from_f32(int64_t bits) {
    if (bits_is_nan((uint64_t)bits, FMT_F32) || bits_is_inf((uint64_t)bits, FMT_F32)) ember_panic(8);
    return big_box(rat_from_bits((uint64_t)bits, FMT_F32));
}

int64_t ember_big_neg(int64_t a) {
    return big_box(rat_neg(big_get(a)));
}

int64_t ember_big_add(int64_t a, int64_t b) {
    return big_box(rat_add(big_get(a), big_get(b)));
}

int64_t ember_big_sub(int64_t a, int64_t b) {
    rat nb = rat_neg(big_get(b));
    rat r = rat_add(big_get(a), nb);
    rat_free(nb);
    return big_box(r);
}

int64_t ember_big_mul(int64_t a, int64_t b) {
    return big_box(rat_mul(big_get(a), big_get(b)));
}

int64_t ember_big_div(int64_t a, int64_t b) {
    return big_box(rat_div(big_get(a), big_get(b)));
}

int64_t ember_big_cmp(int64_t a, int64_t b) {
    return rat_cmp(big_get(a), big_get(b));
}

/* Truncates a rational toward zero into an i64. Panics if the result does not fit. */
static inline int64_t big_to_i64(rat r) {
    nat q, rem;
    nat_divmod(r.num, r.den, &q, &rem);
    nat_free(rem);
    if (nat_bits(q) > 64) ember_panic(7);
    uint64_t mag = nat_to_u64(q);
    nat_free(q);
    if (!r.neg) {
        if (mag > (uint64_t)INT64_MAX) ember_panic(7);
        return (int64_t)mag;
    }
    if (mag > (uint64_t)INT64_MAX + 1) ember_panic(7);
    return (int64_t)((uint64_t)0 - mag);
}

/* Type codes used by the code generators. */
#define EMBER_T_I64 0
#define EMBER_T_F32 1
#define EMBER_T_F64 2
#define EMBER_T_BIG 3

int64_t ember_convert(int64_t bits, int64_t from, int64_t to) {
    if (from == to) return bits;
    uint64_t u = (uint64_t)bits;
    if (from == EMBER_T_I64) {
        if (to == EMBER_T_F32) return (int64_t)f32_to_bits((float)bits);
        if (to == EMBER_T_F64) return (int64_t)f64_to_bits((double)bits);
        return ember_big_from_i64(bits);
    }
    if (from == EMBER_T_F32) {
        float f = bits_to_f32(u);
        if (to == EMBER_T_F64) return (int64_t)f64_to_bits((double)f);
        if (to == EMBER_T_BIG) return ember_big_from_f32(bits);
        if (!(f >= -9223372036854775808.0f && f < 9223372036854775808.0f)) ember_panic(7);
        return (int64_t)f;
    }
    if (from == EMBER_T_F64) {
        double d = bits_to_f64(u);
        if (to == EMBER_T_F32) return (int64_t)f32_to_bits((float)d);
        if (to == EMBER_T_BIG) return ember_big_from_f64(bits);
        if (!(d >= -9223372036854775808.0 && d < 9223372036854775808.0)) ember_panic(7);
        return (int64_t)d;
    }
    /* from bigfloat */
    rat r = big_get(bits);
    if (to == EMBER_T_I64) return big_to_i64(r);
    if (to == EMBER_T_F32) return (int64_t)rat_to_bits(r, FMT_F32);
    return (int64_t)rat_to_bits(r, FMT_F64);
}

#endif
