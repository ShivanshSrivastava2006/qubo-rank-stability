import math
from fractions import Fraction
prob = Fraction(2**53 - 1, 2**53)
print("prob:", float(prob))
prob2 = Fraction(2**54 - 1, 2**54)
print("prob2:", float(prob2))
try:
    print(math.log(1.0 - float(prob2)))
except Exception as e:
    print("Error:", e)
