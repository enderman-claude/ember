# Out-of-bounds access panics instead of corrupting memory.

def main():
    xs = [10, 20, 30]
    print(xs[2])
    print(xs[3])
