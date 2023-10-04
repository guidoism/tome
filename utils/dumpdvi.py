import sys
ch = lambda b: chr(b) if chr(b).isprintable() else '.'
i = 0
with open(sys.argv[1], 'rb') as f:
    while (b := f.read(1)):
        b = int.from_bytes(b)
        print(f'| {i:3} | {b:02x} | {b:3} | {ch(b)} |')
        i += 1
