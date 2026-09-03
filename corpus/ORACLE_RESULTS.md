# ORACLE -- evidence-tiered resolver v1

Scored by `corpus/oracle.py`, which shares no code with the resolver. The resolver was committed before this ran.

## Gates -- every one of these must be zero

dataset                             G1  G2  G3  G4  G6  G7  G8  G9   verdict
------------------------------------------------------------------------------
datasets/A10_B100_Cmax               0   0   0   0   0   0   0   0   PASS
datasets/A20_B0_Cmax                 0   0   0   0   0   0   0   0   PASS
datasets/A20_B100_Cfifo              0   0   0   0   0   0   0   0   PASS
datasets/A20_B100_Cmax               0   0   0   0   0   0   0   0   PASS
datasets/A20_B100_Crandom            0   0   0   0   0   0   0   0   PASS
datasets/A20_B100_Crandom0           0   0   0   0   0   0   0   0   PASS
datasets/A20_B50_Cmax                0   0   0   0   0   0   0   0   PASS
datasets/A20_B75_Cmax                0   0   0   0   0   0   0   0   PASS
datasets/A20_Bnone_Cmax              0   0   9   0   0   0   9   0   FAIL
datasets/A30_B100_Cmax               0   0   0   0   0   0   0   0   PASS
datasets/A40_B100_Cfifo              0   0   0   0   0   0   0   0   PASS
datasets/A40_B100_Cmax               0   0   0   0   0   0   0   0   PASS
datasets/A40_B100_Crandom            0   0   0   0   0   0   0   0   PASS
datasets/A40_B50_Cmax                0   0   0   0   0   0   0   0   PASS
datasets/A40_Bnone_Cmax              0   0  11   0   0   0   6   0   FAIL
datasets/A60_B100_Cmax               0   0   0   0   0   0   0   0   PASS
datasets_v2/A10_B100_Cmax            0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B0_Cmax              0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Cfifo           0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Cmax            0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Crandom         0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B100_Crandom0        0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B50_Cmax             0   0   0   0   0   0   0   0   PASS
datasets_v2/A20_B75_Cmax             0   0   0   0   0   0   0   0   PASS
datasets_v2/A30_B100_Cmax            0   0   0   0   0   0   0   0   PASS
datasets_v2/A40_B100_Cfifo           0   0   0   0   0   0   0   0   PASS
datasets_v2/A40_B100_Cmax            0   0   0   0   0   0   0   0   PASS
datasets_v2/A40_B100_Crandom         0   0   0   0   0   0   0   0   PASS
datasets_v2/A40_B50_Cmax             0   0   0   0   0   0   0   0   PASS
datasets_v2/A60_B100_Cmax            0   0   0   0   0   0   0   0   PASS
------------------------------------------------------------------------------
TOTAL                                0   0  20   0   0   0  15   0

## Measured, not gated

dataset                              V  nd  AD   R  Amb  Unr   mean k  max k   det   rec
----------------------------------------------------------------------------------------
datasets/A10_B100_Cmax              10   4   2   0    0    8     1.00      1 10/11  0/1 
datasets/A20_B0_Cmax                11  11   1   0    2    6    16.38    200  0/0   0/11
datasets/A20_B100_Cfifo             10  10   2   0    1    7    19.09    200  9/10  0/1 
datasets/A20_B100_Cmax              10   9   2   0    1    7     1.18      3  9/10  0/1 
datasets/A20_B100_Crandom           10  10   2   0    1    7     3.27     26  8/9   0/1 
datasets/A20_B100_Crandom0          10   8   2   0    2    6     4.42     34  6/6   0/0 
datasets/A20_B50_Cmax               10   9   2   0    3    5    32.31    200  4/4   0/7 
datasets/A20_B75_Cmax               10   7   2   0    2    6    34.17    200  7/8   0/4 
datasets/A20_Bnone_Cmax              0   0   1   1   13    5   130.36    200  0/0   1/11
datasets/A30_B100_Cmax              11  10   1   0    4    4    44.00    200  9/9   0/1 
datasets/A40_B100_Cfifo             10   9   2   0    3    5     7.38     55  5/6   0/1 
datasets/A40_B100_Cmax              10  10   2   0    3    5     2.92     14  4/5   0/0 
datasets/A40_B100_Crandom           11  10   1   0    3    5    43.64    200  7/7   0/1 
datasets/A40_B50_Cmax               10   9   2   0    4    4    57.86    200  0/0   0/2 
datasets/A40_Bnone_Cmax              0   0   1   0   15    4   188.27    200  0/0   0/7 
datasets/A60_B100_Cmax              10   9   2   0    4    4    44.14    200  3/3   0/0 
datasets_v2/A10_B100_Cmax            9   7   3   0    2    6    19.36    200  9/10  0/2 
datasets_v2/A20_B0_Cmax             11  10   1   0    0    8     1.00      1  0/0   0/11
datasets_v2/A20_B100_Cfifo           9   6   3   0    0    8     1.00      1  9/10  0/2 
datasets_v2/A20_B100_Cmax            9   6   3   0    2    6    20.00    200  8/9   0/2 
datasets_v2/A20_B100_Crandom        10   9   2   0    3    5     3.92     18  7/7   0/2 
datasets_v2/A20_B100_Crandom0        9   8   3   0    2    6     2.64     17  5/5   0/2 
datasets_v2/A20_B50_Cmax            10   7   2   0    2    6    34.17    200  4/4   0/7 
datasets_v2/A20_B75_Cmax             9   8   3   0    0    8     1.00      1  5/6   0/5 
datasets_v2/A30_B100_Cmax            9   7   3   0    4    4    48.54    200  7/7   0/2 
datasets_v2/A40_B100_Cfifo          10  10   2   0    3    5    16.62    200  4/5   0/2 
datasets_v2/A40_B100_Cmax            9   9   3   0    4    4    62.23    200  5/6   0/1 
datasets_v2/A40_B100_Crandom         9   9   2   0    4    4     2.23      6  2/3   0/1 
datasets_v2/A40_B50_Cmax             9   8   3   0    3    5     5.75     29  0/0   0/4 
datasets_v2/A60_B100_Cmax           10  10   2   0    3    5    46.92    200  4/4   0/0 

## Composition cardinality — how much of this was actually hard

Every figure here is a re-cut of outcomes already scored above; no new measurement is introduced. It exists because `Verified 14, mean k 3.4` does not tell a reconciliation practitioner the one thing they ask first: **how much of this was one-to-one, and how much needed netting?** A 1:1 match is what a join on a shared key already solves. Reporting the split is what prevents a strong headline from being read as a claim about the hard cases.

`N:N` is **0 by construction, not by measurement**: `ResolverOutput` carries exactly one outcome per bank line, so no answer can span two credits. That is a design boundary of this contract and is stated rather than left as an unexplained zero.

dataset                              1:1   N:1   N:N  w/debits   by outcome class
----------------------------------------------------------------------------------------------------
datasets/A10_B100_Cmax                 0    10     0         7   Verified {'N:1': 10}
datasets/A20_B0_Cmax                   0    11     0        10   Verified {'N:1': 11}
datasets/A20_B100_Cfifo                0    10     0         7   Verified {'N:1': 10}
datasets/A20_B100_Cmax                 0    10     0         9   Verified {'N:1': 10}
datasets/A20_B100_Crandom              0    10     0         7   Verified {'N:1': 10}
datasets/A20_B100_Crandom0             0    10     0         7   Verified {'N:1': 10}
datasets/A20_B50_Cmax                  0    10     0         7   Verified {'N:1': 10}
datasets/A20_B75_Cmax                  0    10     0         7   Verified {'N:1': 10}
datasets/A20_Bnone_Cmax                0     1     0         0   Reconstructed {'N:1': 1}
datasets/A30_B100_Cmax                 0    11     0         9   Verified {'N:1': 11}
datasets/A40_B100_Cfifo                0    10     0         9   Verified {'N:1': 10}
datasets/A40_B100_Cmax                 0    10     0         9   Verified {'N:1': 10}
datasets/A40_B100_Crandom              0    11     0        10   Verified {'N:1': 11}
datasets/A40_B50_Cmax                  0    10     0        10   Verified {'N:1': 10}
datasets/A40_Bnone_Cmax                0     0     0         0   
datasets/A60_B100_Cmax                 0    10     0        10   Verified {'N:1': 10}
datasets_v2/A10_B100_Cmax              0     9     0         5   Verified {'N:1': 9}
datasets_v2/A20_B0_Cmax                1    10     0         7   Verified {'1:1': 1, 'N:1': 10}
datasets_v2/A20_B100_Cfifo             0     9     0         8   Verified {'N:1': 9}
datasets_v2/A20_B100_Cmax              0     9     0         7   Verified {'N:1': 9}
datasets_v2/A20_B100_Crandom           0    10     0         9   Verified {'N:1': 10}
datasets_v2/A20_B100_Crandom0          1     8     0         8   Verified {'1:1': 1, 'N:1': 8}
datasets_v2/A20_B50_Cmax               0    10     0         7   Verified {'N:1': 10}
datasets_v2/A20_B75_Cmax               0     9     0         6   Verified {'N:1': 9}
datasets_v2/A30_B100_Cmax              1     8     0         7   Verified {'1:1': 1, 'N:1': 8}
datasets_v2/A40_B100_Cfifo             0    10     0         9   Verified {'N:1': 10}
datasets_v2/A40_B100_Cmax              0     9     0         9   Verified {'N:1': 9}
datasets_v2/A40_B100_Crandom           0     9     0         9   Verified {'N:1': 9}
datasets_v2/A40_B50_Cmax               0     9     0         9   Verified {'N:1': 9}
datasets_v2/A60_B100_Cmax              0    10     0         9   Verified {'N:1': 10}
----------------------------------------------------------------------------------------------------
TOTAL                                  3   273     0       227

`w/debits` counts answered lines whose composition carries at least one DEBIT row — a refund or an adjustment netted against credits inside the same payout. Those are the lines where a credits-only sum would have produced the wrong figure, so it is the narrowest honest measure of what netting bought.

The split is reported per outcome class rather than pooled. A 1:1 `Verified` (two independent parties agree on the composition) and a 1:1 `Reconstructed` (this resolver's own arithmetic, with no second party attesting anything) are different evidential objects, and averaging them would undo the distinction the contract's tiers exist to draw.

## Row disposition (contract 4.7)

`ProvenUnmatched` asserts; `OpenBreak` does not. They are never added together -- a total over both is exactly the conflation the amendment undoes.

dataset                            proven  G9   open  clust causes /cause  0-30 31-60 61-90   90+ unexpl
--------------------------------------------------------------------------------------------------------
datasets/A10_B100_Cmax                  9   0     48     20      2   10.0    42     4     2     0      5
datasets/A20_B0_Cmax                   15   0     47      0      0    0.0    40     4     3     0     17
datasets/A20_B100_Cfifo                17   0    102     49      2   24.5    50    29    23     0     19
datasets/A20_B100_Cmax                 17   0     93     46      2   23.0    45     2    46     0     13
datasets/A20_B100_Crandom              17   0    102     59      2   29.5    86    14     2     0     15
datasets/A20_B100_Crandom0             15   0     72     33      2   16.5    64     8     0     0     11
datasets/A20_B50_Cmax                  17   0     84     15      1   15.0    70    10     4     0     32
datasets/A20_B75_Cmax                  15   0     99     52      2   26.0    47    51     1     0     26
datasets/A20_Bnone_Cmax                17   0    294      0      0    0.0   133   107    54     0    258
datasets/A30_B100_Cmax                 25   0     89     32      1   32.0    53    21    15     0     18
datasets/A40_B100_Cfifo                32   0    168     79      2   39.5    83     4    81     0     29
datasets/A40_B100_Cmax                 34   0    139     46      2   23.0    89    42     8     0     36
datasets/A40_B100_Crandom              34   0    125     34      1   34.0    87     3    35     0     29
datasets/A40_B50_Cmax                  32   0    174     42      1   42.0   129     3    42     0     66
datasets/A40_Bnone_Cmax                32   0    567      0      0    0.0   282   172   113     0    500
datasets/A60_B100_Cmax                 51   0    285    156      2   78.0   206     8    71     0     48
datasets_v2/A10_B100_Cmax               9   0     58     36      3   12.0    19    25    14     0     10
datasets_v2/A20_B0_Cmax                17   0     61      0      0    0.0    33    25     3     0     33
datasets_v2/A20_B100_Cfifo             17   0    109     64      3   21.3    64    44     1     0     18
datasets_v2/A20_B100_Cmax              13   0    101     51      3   17.0    90     6     5     0      8
datasets_v2/A20_B100_Crandom           17   0     73     17      1   17.0    37    32     4     0     31
datasets_v2/A20_B100_Crandom0          13   0    109     71      3   23.7    56    12    41     0     12
datasets_v2/A20_B50_Cmax               17   0    103     58      2   29.0   101     2     0     0     20
datasets_v2/A20_B75_Cmax               17   0    121     74      3   24.7    45    49    27     0     16
datasets_v2/A30_B100_Cmax              25   0    159     99      3   33.0   119    36     4     0     21
datasets_v2/A40_B100_Cfifo             30   0    127     38      2   19.0    88    36     3     0     35
datasets_v2/A40_B100_Cmax              32   0    172     88      3   29.3   112    51     9     0     38
datasets_v2/A40_B100_Crandom           32   0    158     99      2   49.5    54    32    72     0     12
datasets_v2/A40_B50_Cmax               34   0    219     87      2   43.5   123    41    55     0     61
datasets_v2/A60_B100_Cmax              49   0    250    137      2   68.5   160    87     3     0     35
--------------------------------------------------------------------------------------------------------
TOTAL                                 701   0   4308   1582     54   29.3  2607   960   741     0   1472

## `AttestationDiscrepancy` — the four-way split

`reported − planted` is **not** a false-alarm rate. A bank debit revoking an earlier credit is a genuine cross-party contradiction; it is simply not one the corpus planted. Each is checked against a `reversal_debit` line in the answer key rather than assumed.

| | count |
|---|---:|
| reported | 62 |
| planted and found | 37 |
| **true finding of another kind** (reversal, corroborated) | **25** |
| **genuinely false** | **0** |
| planted but missed | 2 |

Planted discrepancies missed, by settlement id:

* `setl_igkKlAiC79ERI6` in `datasets_v2/A40_B100_Cfifo`
* `setl_97AhUNQc71f0nz` in `datasets_v2/A40_B100_Crandom`

**No genuinely false findings.** The false-alarm rate is zero.

### `OpenBreak` by reason, all datasets

reason                      rows   owner / closes when
upstream_unresolved         1582   whoever owns the causing finding / the causing bank line becomes Verified or ProvenUnmatched
unexplained                 1472   investigation / -- no close condition is known, which is the point
timing_difference            950   none -- carry forward / the item settles in a later window
unexpected_change            304   disputes ops / the hold or reversal resolves
