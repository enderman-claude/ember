# Sieve of Eratosthenes: mark composites in an array, then list the primes.

def sieve(n: i64) -> [i64]:
    flags = alloc(n + 1)            # zeroed; 1 means "prime candidate"
    for i in range(2, n + 1):
        flags[i] = 1
    for i in range(2, n + 1):
        if flags[i] == 1:
            mut j = i * i
            while j <= n:
                flags[j] = 0
                j = j + i
    return flags

def main():
    limit = 100
    flags = sieve(limit)
    mut count = 0
    for i in range(2, limit + 1):
        if flags[i] == 1:
            print(i)
            count = count + 1
    print(count)
    free(flags)
