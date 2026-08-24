# ORACLE -- evidence-tiered resolver v1

Scored by `corpus/oracle.py`, which shares no code with the resolver. The resolver was committed before this ran.

## Gates -- every one of these must be zero

dataset                             G1  G2  G3  G4  G6  G7  G8   verdict
------------------------------------------------------------------------------
datasets/A10_B100_Cmax               0   0   0   0   0   0   0   PASS
datasets/A20_B0_Cmax                 0   0   0   0   0   0   0   PASS
datasets/A20_B100_Cfifo              0   0   0   0   0   0   0   PASS
datasets/A20_B100_Cmax               0   0   0   0   0   0   0   PASS
datasets/A20_B100_Crandom            0   0   0   0   0   0   0   PASS
datasets/A20_B100_Crandom0           0   0   0   0   0   0   0   PASS
datasets/A20_B50_Cmax                0   0   0   0   0   0   0   PASS
datasets/A20_B75_Cmax                0   0   0   0   0   0   0   PASS
datasets/A20_Bnone_Cmax              0   0   9   0   0   0   9   FAIL
datasets/A30_B100_Cmax               0   0   0   0   0   0   0   PASS
datasets/A40_B100_Cfifo              0   0   0   0   0   0   0   PASS
datasets/A40_B100_Cmax               0   0   0   0   0   0   0   PASS
datasets/A40_B100_Crandom            0   0   0   0   0   0   0   PASS
datasets/A40_B50_Cmax                0   0   0   0   0   0   0   PASS
datasets/A40_Bnone_Cmax              0   0  11   0   0   0   6   FAIL
datasets/A60_B100_Cmax               0   0   0   0   0   0   0   PASS
datasets_v2/A10_B100_Cmax            0   0   0   0   0   0   0   PASS
datasets_v2/A20_B0_Cmax              0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Cfifo           0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Cmax            0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Crandom         0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Crandom0        0   0   0   0   0   0   0   PASS
datasets_v2/A20_B50_Cmax             0   0   0   0   0   0   0   PASS
datasets_v2/A20_B75_Cmax             0   0   0   0   0   0   0   PASS
datasets_v2/A30_B100_Cmax            0   0   0   0   0   0   0   PASS
datasets_v2/A40_B100_Cfifo           0   0   0   0   0   0   0   PASS
datasets_v2/A40_B100_Cmax            0   0   0   0   0   0   0   PASS
datasets_v2/A40_B100_Crandom         0   0   0   0   0   0   0   PASS
datasets_v2/A40_B50_Cmax             0   0   0   0   0   0   0   PASS
datasets_v2/A60_B100_Cmax            0   0   0   0   0   0   0   PASS
------------------------------------------------------------------------------
TOTAL                                0   0  20   0   0   0  15

## Measured, not gated

dataset                              V  nd  AD   R  Amb  Unr   mean k  max k   det   rec
----------------------------------------------------------------------------------------
datasets/A10_B100_Cmax              10   4   2   0    0    8     1.00      1 10/11  0/1 
datasets/A20_B0_Cmax                11  11   1   0    1    7     1.50      7  0/0   0/11
datasets/A20_B100_Cfifo             10  10   2   0    0    8     1.00      1  9/10  0/1 
datasets/A20_B100_Cmax              10   9   2   0    0    8     1.00      1  9/10  0/1 
datasets/A20_B100_Crandom           10  10   2   0    0    8     1.00      1  8/9   0/1 
datasets/A20_B100_Crandom0          10   8   2   0    1    7    11.45    116  6/6   0/0 
datasets/A20_B50_Cmax               10   9   2   1    0    7     1.00      1  4/4   0/7 
datasets/A20_B75_Cmax               10   7   2   0    0    8     1.00      1  7/8   0/4 
datasets/A20_Bnone_Cmax              0   0   1   1    1   17    38.50     76  0/0   1/11
datasets/A30_B100_Cmax              11  10   1   0    0    8     1.00      1  9/9   0/1 
datasets/A40_B100_Cfifo             10   9   2   0    0    8     1.00      1  5/6   0/1 
datasets/A40_B100_Cmax              10  10   2   0    0    8     1.00      1  4/5   0/0 
datasets/A40_B100_Crandom           11  10   1   0    0    8     1.00      1  7/7   0/1 
datasets/A40_B50_Cmax               10   9   2   0    0    8     1.00      1  0/0   0/2 
datasets/A40_Bnone_Cmax              0   0   1   0    0   19     0.00      0  0/0   0/7 
datasets/A60_B100_Cmax              10   9   2   0    0    8     1.00      1  3/3   0/0 
datasets_v2/A10_B100_Cmax            9   7   3   0    0    8     1.00      1  9/10  0/2 
datasets_v2/A20_B0_Cmax             11   9   1   0    0    8     1.00      1  0/0   0/11
datasets_v2/A20_B100_Cfifo           9   6   3   0    0    8     1.00      1  9/10  0/2 
datasets_v2/A20_B100_Cmax            9   6   3   0    1    7     1.30      4  8/9   0/2 
datasets_v2/A20_B100_Crandom        10   9   2   0    0    8     1.00      1  7/7   0/2 
datasets_v2/A20_B100_Crandom0        9   8   3   0    0    8     1.00      1  5/5   0/2 
datasets_v2/A20_B50_Cmax            10   7   2   0    0    8     1.00      1  4/4   0/7 
datasets_v2/A20_B75_Cmax             9   8   3   0    0    8     1.00      1  5/6   0/5 
datasets_v2/A30_B100_Cmax            9   7   3   0    0    8     1.00      1  7/7   0/2 
datasets_v2/A40_B100_Cfifo          10  10   2   0    1    7     1.27      4  4/5   0/2 
datasets_v2/A40_B100_Cmax            9   9   3   0    0    8     1.00      1  5/6   0/1 
datasets_v2/A40_B100_Crandom         9   9   2   0    0    8     1.00      1  2/3   0/1 
datasets_v2/A40_B50_Cmax             9   8   3   0    0    8     1.00      1  0/0   0/4 
datasets_v2/A60_B100_Cmax           10  10   2   0    0    8     1.00      1  4/4   0/0 
