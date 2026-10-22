# Sums every integer on stdin until end of input.

def main():
    mut total = 0
    mut count = 0
    while true:
        v = read_int()
        if input_ended():
            break
        total = total + v
        count = count + 1
    print(count)
    print(total)
