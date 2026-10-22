# Towers of Hanoi. Each move is printed as two digits: from-peg then to-peg.

def solve(n: i64, src: i64, dst: i64, via: i64):
    if n == 0:
        return
    solve(n - 1, src, via, dst)
    print(src * 10 + dst)
    solve(n - 1, via, dst, src)

def count_moves(n: i64) -> i64:
    if n == 0:
        return 0
    return 2 * count_moves(n - 1) + 1

def main():
    solve(3, 1, 3, 2)
    print(count_moves(12))
