# Reads n, then n integers from stdin. Sorts them in place with bubble sort and prints them.

def bubble_sort(a: [i64]):
    n = len(a)
    for p in range(n):
        for j in range(n - 1 - p):
            if a[j] > a[j + 1]:
                tmp = a[j]
                a[j] = a[j + 1]
                a[j + 1] = tmp

def main():
    n = read_int()
    data = alloc(n)
    for i in range(n):
        data[i] = read_int()
    bubble_sort(data)
    for i in range(n):
        print(data[i])
    free(data)
