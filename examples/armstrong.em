# Armstrong numbers below 1000: a number equal to the sum of its digits raised to the digit count.

def digit_count(n: i64) -> i64:
    mut d = 1
    mut m = n / 10
    while m > 0:
        d = d + 1
        m = m / 10
    return d

def power(base: i64, exp: i64) -> i64:
    mut result = 1
    for i in range(exp):
        result = result * base
    return result

def is_armstrong(n: i64) -> bool:
    k = digit_count(n)
    mut rest = n
    mut total = 0
    while rest > 0:
        total = total + power(rest % 10, k)
        rest = rest / 10
    return total == n

def main():
    for n in range(1, 1000):
        if is_armstrong(n):
            print(n)
