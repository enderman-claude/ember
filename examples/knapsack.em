# 0/1 knapsack by dynamic programming over capacities.
# Input: item count n, capacity cap, then n pairs of (weight, value).

def knapsack(weights: [i64], values: [i64], cap: i64) -> i64:
    n = len(weights)
    best = alloc(cap + 1)           # best[c] = highest value achievable with capacity c
    for i in range(n):
        w = weights[i]
        v = values[i]
        mut c = cap
        while c >= w:
            candidate = best[c - w] + v
            if candidate > best[c]:
                best[c] = candidate
            c = c - 1
    result = best[cap]
    free(best)
    return result

def main():
    n = read_int()
    cap = read_int()
    weights = alloc(n)
    values = alloc(n)
    for i in range(n):
        weights[i] = read_int()
        values[i] = read_int()
    print(knapsack(weights, values, cap))
    free(weights)
    free(values)
