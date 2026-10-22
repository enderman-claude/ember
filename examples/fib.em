def fib(n: i64) -> i64:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

def main():
    mut i = 0
    while i < 10:
        print(fib(i))
        i = i + 1
