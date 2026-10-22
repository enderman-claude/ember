# Calls C functions through `extern def`. Build with a C file that defines them:
#   ember run examples/ffi/extern_demo.em --link examples/ffi/extern_demo_impl.c
extern def c_add(a: i64, b: i64) -> i64
extern def c_print_twice(x: i64)

def main():
    print(c_add(40, 2))
    c_print_twice(7)
