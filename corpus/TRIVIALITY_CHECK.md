# TRIVIALITY CHECK -- does a GROUP BY solve the task?

family       dataset                line->batch  composition  foreign rej  abstain  verdict
----------------------------------------------------------------------------------------
datasets     A10_B100_Cmax            12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B0_Cmax              12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B100_Cfifo           12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B100_Cmax            12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B100_Crandom         12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B100_Crandom0        12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B50_Cmax             12/13        12/12         7/7             0  TRIVIAL
datasets     A20_B75_Cmax             12/13        12/12         7/7             0  TRIVIAL
datasets     A20_Bnone_Cmax                   -            -            -        -  N/A (no settlement_id column)
datasets     A30_B100_Cmax            12/13        12/12         7/7             0  TRIVIAL
datasets     A40_B100_Cfifo           12/13        12/12         7/7             0  TRIVIAL
datasets     A40_B100_Cmax            12/13        12/12         7/7             0  TRIVIAL
datasets     A40_B100_Crandom         12/13        12/12         7/7             0  TRIVIAL
datasets     A40_B50_Cmax             12/13        12/12         7/7             0  TRIVIAL
datasets     A40_Bnone_Cmax                   -            -            -        -  N/A (no settlement_id column)
datasets     A60_B100_Cmax            12/13        12/12         7/7             0  TRIVIAL
datasets_v2  A10_B100_Cmax            12/13        11/12         7/7             0  PARTIAL
datasets_v2  A20_B0_Cmax              12/13        12/12         7/7             0  TRIVIAL
datasets_v2  A20_B100_Cfifo           12/13        11/12         7/7             0  PARTIAL
datasets_v2  A20_B100_Cmax            12/13        11/12         7/7             0  PARTIAL
datasets_v2  A20_B100_Crandom         12/13        11/12         7/7             0  PARTIAL
datasets_v2  A20_B100_Crandom0        12/13        11/12         7/7             0  PARTIAL
datasets_v2  A20_B50_Cmax             12/13        11/12         7/7             0  PARTIAL
datasets_v2  A20_B75_Cmax             12/13        11/12         7/7             0  PARTIAL
datasets_v2  A30_B100_Cmax            12/13        11/12         7/7             0  PARTIAL
datasets_v2  A40_B100_Cfifo           12/13        11/12         7/7             0  PARTIAL
datasets_v2  A40_B100_Cmax            12/13        11/12         7/7             0  PARTIAL
datasets_v2  A40_B100_Crandom         11/12        10/11         7/7             0  PARTIAL
datasets_v2  A40_B50_Cmax             12/13        11/12         7/7             0  PARTIAL
datasets_v2  A60_B100_Cmax            12/13        11/12         7/7             0  PARTIAL
----------------------------------------------------------------------------------------
TOTAL                                335/363      322/335      196/196           0

abstentions on 164 determined + 74 reconstructible instances: 0

verdicts: {'TRIVIAL': 15, 'PARTIAL': 13, 'NOT TRIVIAL': 0, 'N/A': 2}

15 of 30 datasets resist the trivial predicate. Those are the cells that measure anything.
