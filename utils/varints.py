import leb128
nums = [
    0x130000,
    0x220000,
    123,
    655360,
    0,
    10,
    9,
    96,
    0x053fff,
]

for n in nums:
    v = (''.join(['%02x' % b for b in leb128.i.encode(n)])).rjust(10)
    print(f'{n:10} {n:10x} {v}')
