# Counts N-queens placements with backtracking. cols[r] holds the column of the queen in row r.

def safe(cols: [i64], row: i64, col: i64) -> bool:
    for r in range(row):
        c = cols[r]
        if c == col:
            return false
        d = row - r
        if c - col == d or col - c == d:
            return false
    return true

def place(cols: [i64], row: i64, n: i64) -> i64:
    if row == n:
        return 1
    mut total = 0
    for col in range(n):
        if safe(cols, row, col):
            cols[row] = col
            total = total + place(cols, row + 1, n)
    return total

def main():
    for n in range(4, 9):
        cols = alloc(n)
        print(place(cols, 0, n))
        free(cols)
