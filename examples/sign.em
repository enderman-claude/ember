def sign(x: i64) -> i64:
    if x < 0:
        return -1
    elif x == 0:
        return 0
    else:
        return 1

def main():
    print(sign(-5))
    print(sign(0))
    print(sign(12))
    print(7 % 3 + 10 / 3)
