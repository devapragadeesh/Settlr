# TRIVIALITY CHECK -- does a GROUP BY solve the task?

**RESISTANCE is the number that matters**: the fraction of compositions the trivial predicate MISSES. A dataset at 8.3% resistance is not a hard dataset -- a `GROUP BY` still recovers eleven twelfths of it.

family       dataset                line->batch  composition  foreign rej  abstain  RESIST  verdict
------------------------------------------------------------------------------------------------
datasets     A10_B100_Cmax            12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B0_Cmax              12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B100_Cfifo           12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B100_Cmax            12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B100_Crandom         12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B100_Crandom0        12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B50_Cmax             12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_B75_Cmax             12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A20_Bnone_Cmax                   -            -            -        -    100%  N/A (no settlement_id column)
datasets     A30_B100_Cmax            12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A40_B100_Cfifo           12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A40_B100_Cmax            12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A40_B100_Crandom         12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A40_B50_Cmax             12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets     A40_Bnone_Cmax                   -            -            -        -    100%  N/A (no settlement_id column)
datasets     A60_B100_Cmax            12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets_v2  A10_B100_Cmax            12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A20_B0_Cmax              12/13        12/12         7/7             0    0.0%  TRIVIAL
datasets_v2  A20_B100_Cfifo           12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A20_B100_Cmax            12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A20_B100_Crandom         12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A20_B100_Crandom0        12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A20_B50_Cmax             12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A20_B75_Cmax             12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A30_B100_Cmax            12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A40_B100_Cfifo           12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A40_B100_Cmax            12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A40_B100_Crandom         11/12        10/11         7/7             0    9.1%  PARTIAL
datasets_v2  A40_B50_Cmax             12/13        11/12         7/7             0    8.3%  PARTIAL
datasets_v2  A60_B100_Cmax            12/13        11/12         7/7             0    8.3%  PARTIAL
------------------------------------------------------------------------------------------------
TOTAL                                335/363      322/335      196/196           0    3.9%  <- over the 28 datasets a GROUP BY can run on at all

abstentions on 164 determined + 74 reconstructible instances: 0

## The verdict, stated as the measurement rather than as a label

**On 28 of 30 datasets a fifteen-line `GROUP BY` recovers 96.1% of compositions (322 of 335). On 2 it cannot run at all.** Those 2 are the only cells that genuinely defeat the trivial predicate.

The highest resistance among datasets the predicate CAN run on is **9.1%** — one composition in twelve. `PARTIAL` in the table above must not be read as `NOT TRIVIAL`: a dataset where naive gets eleven of twelve right is a dataset naive very nearly solves.

An earlier version of this file concluded that "15 of 30 datasets resist the trivial predicate", counting every `PARTIAL` as resistance. That was too generous by 13 datasets and is withdrawn.

verdict counts: {'TRIVIAL': 15, 'PARTIAL': 13, 'NOT TRIVIAL': 0, 'N/A': 2}
