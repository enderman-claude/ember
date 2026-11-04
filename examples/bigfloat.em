# bigfloat: exact arithmetic. Values are rationals kept in lowest terms, so 100/3 is
# stored as 100/3 and never rounded. A value prints exactly when its decimal expansion
# terminates, and otherwise with 40 digits followed by "...".
# Literals with the suffix big are bigfloats: 0.1big is exactly one tenth.

def main():
    third = 100big / 3big
    print(third)                       # 33.3333333333333333333333333333333333333333...
    print(third * 3big)                # 100
    print(0.1big + 0.2big)             # 0.3 (exact, unlike f64)
    print(0.1big * 0.1big)             # 0.01
    print(1big / 8big)                 # 0.125
    print(-7big / 4big)                # -1.75
    print(1big / 3big + 1big / 6big)   # 0.5 (exact)
    print(0.1big == 1big / 10big)      # true
    print(1big / 3big < 0.34big)       # true
    print(bigfloat(0.1))               # 0.1000000000000000055511151231257827021181583404541015625
    print(f64(1big / 3big))            # 0.3333333333333333
    print(f32(0.1big))                 # 0.1
    print(i64(7.9big))                 # 7: truncates toward zero
    print(i64(-7.9big))                # -7
