"""Exact conversion of decimal literals to IEEE 754 bit patterns.

The compiler uses this for f32 and f64 literals. It rounds the exact value to the nearest
float, ties to even, and does the same as the runtime's rat_to_bits in ember_num.h.
"""
from fractions import Fraction

# (significand bits including the hidden bit, exponent of the smallest subnormal,
#  exponent bias, all-ones exponent field)
FORMATS = {
    "f64": (53, -1074, 1023, 2047),
    "f32": (24, -149, 127, 255),
}


def round_bits(value: Fraction, kind: str):
    """Bit pattern of the nearest `kind` float to value (value >= 0), or None if it overflows."""
    p, minq, bias, expmax = FORMATS[kind]
    num, den = value.numerator, value.denominator
    if num == 0:
        return 0
    # 2^E <= value < 2^(E+1)
    E = num.bit_length() - den.bit_length()
    if E >= 0:
        if num < (den << E):
            E -= 1
    elif (num << -E) < den:
        E -= 1

    qe = max(E - (p - 1), minq)
    if qe >= 0:
        n, d = num, den << qe
    else:
        n, d = num << -qe, den
    q, r = divmod(n, d)
    if 2 * r > d or (2 * r == d and q & 1):
        q += 1
    hidden = 1 << (p - 1)
    if q == 2 * hidden:
        q = hidden
        qe += 1
    if q == 0:
        return 0
    if q < hidden:
        return q                                   # subnormal
    biased = qe + (p - 1) + bias
    if biased >= expmax:
        return None                                # overflow
    return (biased << (p - 1)) | (q - hidden)


def literal_bits(text: str, kind: str):
    """Bit pattern for a decimal literal such as "33.25", or None if it does not fit."""
    return round_bits(Fraction(text), kind)


def bits_to_float_text(bits: int, kind: str) -> float:
    """Decodes a bit pattern (used by tests; f32 values come back as a Python float)."""
    import struct
    if kind == "f64":
        return struct.unpack("<d", struct.pack("<Q", bits))[0]
    return struct.unpack("<f", struct.pack("<I", bits))[0]
