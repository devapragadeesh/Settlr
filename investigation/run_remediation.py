import json, sys, time
from pathlib import Path
sys.path.insert(0,'.')
from matching import run
from matching.loaders import load
from investigation.remediation import policy_run, accounting

POLICIES = {
 "0. baseline (frozen engine)": {},
 "1a. require line attested before Determinate": dict(require_attested_for_determinate=True),
 "1b. UTR-contradiction veto": dict(utr_contradiction_veto=True),
 "2.  require attested composition match": dict(require_attested_composition=True),
 "3.  never consume on uncorroborated Determinate": dict(consume_only_on_attestation=True),
 "4.  reversal pre-pass": dict(reversal_prepass=True),
 "5.  unfiltered closure uniqueness": dict(unfiltered_closure=True),
 "1b+3 veto + no uncorroborated consumption": dict(utr_contradiction_veto=True, consume_only_on_attestation=True),
 "5+1b unfiltered closure + veto": dict(unfiltered_closure=True, utr_contradiction_veto=True),
}
sets={}
for which,dd,tp in (('primary',None,'engine/ground_truth/ground_truth.json'),
                    ('holdout',Path('holdout/data'),'holdout/ground_truth/ground_truth.json')):
    ds=load(dd) if dd else load(); truth=json.load(open(tp)); res=run(dataset=ds)
    sets[which]=(ds,truth,res.bank_to_batch)

out={}
print(f"{'policy':<48} {'PRIMARY':>28}   {'HELD-OUT':>28}")
print(f"{'':<48} {'rate':>8}{'wrong':>7}{'decl':>6}{'miss':>7}   {'rate':>8}{'wrong':>7}{'decl':>6}{'miss':>7}")
print("-"*112)
for name,kw in POLICIES.items():
    line=f"{name:<48}"; rec={}
    for which in ('primary','holdout'):
        ds,truth,b2b=sets[which]
        t=time.perf_counter()
        a,c,k=policy_run(ds,b2b,**kw)
        acc=accounting(ds,truth,b2b,a,c); acc['seconds']=time.perf_counter()-t
        rec[which]=acc
        line+=f"{acc['match_rate']*100:>7.2f}%{acc['placed_incorrectly']:>7}{acc['declined']:>6}{acc['missed']:>7}   "
    out[name]=rec
    print(line)
Path('investigation/remediation_results.json').write_text(json.dumps(out,indent=1))
