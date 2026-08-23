"""TASK 5 -- adversarial sweep. Six minimal triggers, real unmodified cascade."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from investigation.minimal import *
from matching.model import Determinate, Ambiguous, Unresolved

SETTLED = 5   # settlement day for fixtures

def describe(result, expect_truth):
    out=[]
    for item in sorted(result.stage3.reconstructions, key=lambda x:x.bank_index):
        r=item.resolution
        kind=type(r).__name__
        rows = (r.decomposition.row_ids if isinstance(r,Determinate)
                else tuple(sorted(r.certain_rows)) if isinstance(r,Ambiguous) else ())
        n = len(r.candidates) if isinstance(r,Ambiguous) else (1 if isinstance(r,Determinate) else 0)
        out.append((item.bank_index, kind, n, tuple(sorted(rows))))
    return out

CASES = {}

# 1. two bank credits with identical composition in the same period
def case_identical_composition():
    rows=[payment("pay_A1",100000,0,"setl_1","utrAAA",SETTLED),
          payment("pay_A2",50000,0,"setl_1","utrAAA",SETTLED),
          payment("pay_B1",100000,1,"setl_2","utrBBB",SETTLED+7),
          payment("pay_B2",50000,1,"setl_2","utrBBB",SETTLED+7)]
    b=[bank("utrAAA",SETTLED,150000), bank("utrBBB",SETTLED+7,150000)]
    return rows,b,{"setl_1":("pay_A1","pay_A2"),"setl_2":("pay_B1","pay_B2")}
CASES["identical_composition_two_credits"]=case_identical_composition

# 2. amount reachable by two disjoint subsets of similar-sized payments
def case_disjoint_subsets():
    rows=[payment("pay_X1",100000,0,"setl_1","utrXXX",SETTLED),
          payment("pay_X2",100000,0,"setl_1","utrXXX",SETTLED),
          payment("pay_Y1",100000,0,None,None,None),
          payment("pay_Y2",100000,0,None,None,None)]
    b=[bank("utrXXX",SETTLED,200000)]
    return rows,b,{"setl_1":("pay_X1","pay_X2")}
CASES["two_disjoint_closing_subsets"]=case_disjoint_subsets

# 3. duplicated payment row: same amount, same day, different id
def case_duplicate_payment():
    rows=[payment("pay_D1",250000,0,"setl_1","utrDDD",SETTLED),
          payment("pay_D2",250000,0,None,None,None)]
    b=[bank("utrDDD",SETTLED,250000)]
    return rows,b,{"setl_1":("pay_D1",)}
CASES["duplicate_payment_same_amount_same_day"]=case_duplicate_payment

# 4. partial settlement re-issued under a new UTR (the holdout trigger, minimal)
def case_reissued_utr():
    rows=[payment("pay_R1",300000,0,"setl_2","utrNEW",SETTLED+7),
          payment("pay_R2",200000,0,"setl_2","utrNEW",SETTLED+7)]
    b=[bank("utrOLD",SETTLED,500000),
       {"utr":"utrOLD","date":iso(SETTLED+2),
        "narration":"NEFT-RET-RATN0000088-RETURN-ACCOUNT CLOSED-utrOLD","amount":rupees(-500000)},
       bank("utrNEW",SETTLED+7,500000)]
    return rows,b,{"setl_2":("pay_R1","pay_R2")}
CASES["resettlement_under_new_utr"]=case_reissued_utr

# 5. an adjustment that exactly offsets a payment in the pool
def case_offsetting_adjustment():
    rows=[payment("pay_O1",400000,0,"setl_1","utrOOO",SETTLED),
          payment("pay_O2",150000,0,None,None,None),
          adjustment("adj_O1",150000,1,"debit",None,None)]
    b=[bank("utrOOO",SETTLED,400000)]
    return rows,b,{"setl_1":("pay_O1",)}
CASES["adjustment_exactly_offsets_a_payment"]=case_offsetting_adjustment

# 6. credit reachable only by including a row an earlier credit should have consumed
def case_needs_consumed_row():
    rows=[payment("pay_C1",100000,0,"setl_1","utrC1",SETTLED),
          payment("pay_C2",100000,0,"setl_1","utrC1",SETTLED),
          payment("pay_C3",100000,1,"setl_2","utrC2",SETTLED+7)]
    b=[bank("utrC1",SETTLED,200000), bank("utrC2",SETTLED+7,100000)]
    return rows,b,{"setl_1":("pay_C1","pay_C2"),"setl_2":("pay_C3",)}
CASES["credit_needing_a_consumed_row"]=case_needs_consumed_row

tmp=Path(tempfile.mkdtemp(prefix="minimal_"))
print(f"{'case':<42} {'bank':<5} {'engine':<12} {'cand':<5} verdict")
print("-"*100)
for name,fn in CASES.items():
    rows,b,truth=fn()
    d=write_case(tmp/name, rows, b)
    result=run_case(d)
    lines=describe(result,truth)
    # map bank index -> attested settlement
    b2b=result.bank_to_batch
    true_of={}
    for sid,ids in truth.items():
        for r in ids: true_of[r]=sid
    for idx,kind,n,rws in lines:
        att=b2b.get(idx)
        if kind=="Determinate":
            claimed={true_of.get(r) for r in rws}
            correct = (att is not None and claimed=={att}) or \
                      (att is None and False)
            verdict = "CORRECT" if correct else "*** CONFIDENT WRONG ANSWER ***"
        elif kind=="Ambiguous": verdict="declined (ambiguous)"
        else: verdict="declined (unresolved)"
        print(f"{name:<42} {idx:<5} {kind:<12} {n:<5} {verdict}")
    print()
