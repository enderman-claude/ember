def gcd(a: i64, b: i64) -> i64:
    mut x = a
    mut y = b
    while y != 0:
        r = x % y
        x = y
        y = r
    return x

def main():
    print(gcd(48, 18))
    print(gcd(17, 5))
    print(gcd(1071, 462))
