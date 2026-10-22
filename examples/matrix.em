# 3x3 matrix multiply on flattened row-major arrays.

def matmul(a: [i64], b: [i64], n: i64) -> [i64]:
    c = alloc(n * n)
    for i in range(n):
        for j in range(n):
            mut total = 0
            for k in range(n):
                total = total + a[i * n + k] * b[k * n + j]
            c[i * n + j] = total
    return c

def main():
    a = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    b = [2, 0, 1, 0, 1, 0, 1, 0, 2]
    c = matmul(a, b, 3)
    for i in range(3):
        for j in range(3):
            print(c[i * 3 + j])
    free(c)
