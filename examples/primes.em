def is_prime(n: i64) -> bool:
    if n < 2:
        return false
    mut d = 2
    while d * d <= n:
        if n % d == 0:
            return false
        d = d + 1
    return true

def main():
    mut count = 0
    mut i = 0
    while i < 30:
        if is_prime(i) and i % 4 != 1:
            print(i)
            count = count + 1
        i = i + 1
    print(count)
