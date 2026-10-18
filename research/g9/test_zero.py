import struct
value = -0.0
if value == 0.0:
    value = 0.0
print("After assignment:", struct.pack("<d", value).hex())
print("Expected positive 0:", struct.pack("<d", 0.0).hex())
print("Expected negative 0:", struct.pack("<d", -0.0).hex())

def encode_float(v):
    if v == 0.0:
        v = 0.0
    return struct.pack("<d", v).hex()

print("encode_float(-0.0):", encode_float(-0.0))
