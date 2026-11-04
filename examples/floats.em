# Floating-point numbers: f64 (the default for literals) and f32 (suffix f32).
# Values print as the shortest decimal that reads back as the same number.

def main():
    print(1.0 / 3.0)           # 0.3333333333333333
    print(0.1 + 0.2)           # 0.30000000000000004
    print(2.0 * 3.5)           # 7.0
    print(-2.5)                # -2.5
    print(1.0 / 1024.0)        # 0.0009765625
    print(0.00001)             # 1e-05
    print(12345678901234567890.0)   # 1.2345678901234567e+19

    print(1.0 / 0.0)           # inf
    print(-1.0 / 0.0)          # -inf
    print(-0.0)                # -0.0
    print(0.0 / 0.0 == 0.0 / 0.0)   # false: NaN is not equal to itself

    x = 0.5f32
    y = 0.1f32
    print(x + y)               # 0.6
    print(f32(1.0) / f32(3.0)) # 0.33333334
    print(f32(16777217.0))     # 16777216.0 (rounded to the nearest f32)

    print(1.5 < 2.0)           # true
    print(0.1 + 0.2 == 0.3)    # false
    print(f64(7) / 2.0)        # 3.5
    print(i64(3.99))           # 3: conversions truncate toward zero
    print(i64(-3.99))          # -3
    print(f64(i64(2.5 * 2.0)) + 0.5)   # 5.5
