# Longest Collatz chain for starting values below 1000.

def chain_length(start: i64) -> i64:
    mut n = start
    mut steps = 1
    while n != 1:
        if n % 2 == 0:
            n = n / 2
        else:
            n = 3 * n + 1
        steps = steps + 1
    return steps

def main():
    mut best = 1
    mut best_len = 1
    for i in range(1, 1000):
        l = chain_length(i)
        if l > best_len:
            best = i
            best_len = l
    print(best)
    print(best_len)
