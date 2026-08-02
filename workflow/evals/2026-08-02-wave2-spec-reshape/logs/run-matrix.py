import re, subprocess, sys, os
ROOT="/Users/arkaphatp/Documents/HUN/dev/hun-registry-skill/kestra-upstream"
V=ROOT+"/workflow/kestra-build/scripts/validate_spec.py"
E=ROOT+"/workflow/evals"
NEW=E+"/2026-08-02-wave2-spec-reshape/fixtures"
targets=[]
for f in sorted(os.listdir(NEW)):
    if f.endswith(".md"): targets.append((NEW+"/"+f, ROOT))
targets += [
 (ROOT+"/workflow/runs/order-cancellation-refund/0-spec.md", ROOT),
 (E+"/2026-08-02-spec-instrumented-rerun/spec-pass/0-spec.md", E+"/2026-08-02-spec-instrumented-rerun/fixture"),
 (E+"/2026-08-02-spec-instrumented-rerun/spec-pass/0-spec-verbatim.md", E+"/2026-08-02-spec-instrumented-rerun/fixture"),
 (E+"/2026-08-02-spec-instrumented-rerun/to-spec-pass/spec-ticket.md", E+"/2026-08-02-spec-instrumented-rerun/fixture"),
 (E+"/2026-07-28-batch-chunk-lite/0-spec.md", E+"/2026-07-28-dlq-retry-cap/fixture"),
 (E+"/2026-07-28-dlq-retry-cap/new/0-spec.md", E+"/2026-07-28-dlq-retry-cap/fixture"),
 (E+"/2026-07-28-dlq-retry-cap/old/0-spec.md", E+"/2026-07-28-dlq-retry-cap/fixture"),
 (E+"/2026-07-31-build-ablation-antipatterns/spec/0-spec.md", E+"/2026-07-31-build-ablation-antipatterns/fixture"),
 (E+"/2026-07-31-build-model-compare/0-spec.md", E+"/2026-07-31-build-model-compare/fixture"),
 (E+"/2026-07-31-spec-ablation-cherny/full/0-spec.md", E+"/2026-07-31-spec-ablation-cherny/fixture"),
 (E+"/2026-07-31-spec-ablation-cherny/minimal/0-spec.md", E+"/2026-07-31-spec-ablation-cherny/fixture"),
 (E+"/2026-07-31-spec-ablation-cherny-2/full/0-spec.md", E+"/2026-07-31-spec-ablation-cherny-2/fixture"),
 (E+"/2026-07-31-spec-ablation-cherny-2/minimal/0-spec.md", E+"/2026-07-31-spec-ablation-cherny-2/fixture"),
 (E+"/2026-07-31-spec-model-compare/opus/0-spec.md", ROOT),
 (E+"/2026-07-31-spec-model-compare/sonnet/0-spec.md", E+"/2026-07-31-spec-model-compare"),
]
MARK=re.compile(r"^>\s*Spec-ticket:.*$", re.M)
FIRSTH2=re.compile(r"^ {0,3}## ", re.M)
log=open("/tmp/t35/validator-matrix.log","w")
HEAD="/tmp/t35/validate_spec_HEAD.py"
rows=[]
for path,root in targets:
    txt=open(path,encoding="utf-8").read()
    m=FIRSTH2.search(txt); pre = txt[:m.start()] if m else txt
    pm=MARK.findall(pre); body=MARK.findall(txt[m.start():]) if m else []
    if pm and len(pm)==1 and re.match(r"^>\s*Spec-ticket:\s*https?://\S+\s*$",pm[0]): marker="yes"
    elif pm or body: marker="partial/misplaced"
    else: marker="no"
    p=subprocess.run([sys.executable,V,path,root],capture_output=True,text=True)
    out=p.stdout+p.stderr
    fails=len([l for l in out.splitlines() if l.startswith("FAIL")])
    warns=len([l for l in out.splitlines() if l.startswith("WARN")])
    rel=os.path.relpath(path,ROOT)
    log.write("$ python3 workflow/kestra-build/scripts/validate_spec.py %s %s\n"%(rel,os.path.relpath(root,ROOT) or "."))
    log.write(out if out.strip() else "(no output)\n")
    log.write("exit=%d\n\n"%p.returncode)
    ph=subprocess.run([sys.executable,HEAD,path,root],capture_output=True,text=True)
    oh=ph.stdout+ph.stderr
    hf=len([l for l in oh.splitlines() if l.startswith("FAIL")]); hw=len([l for l in oh.splitlines() if l.startswith("WARN")])
    log.write("  [HEAD validator, same args] FAIL=%d WARN=%d exit=%d\n\n"%(hf,hw,ph.returncode))
    rows.append((rel,marker,fails,warns,p.returncode,hf,hw,ph.returncode))
log.close()
for r in rows: print("| `%s` | %s | %d | %d | %d | HEAD:%d/%d/%d |"%r)
print("TOTALS files=%d fails=%d warns=%d nonzero_exit=%d"%(len(rows),sum(r[2] for r in rows),sum(r[3] for r in rows),sum(1 for r in rows if r[4]!=0)))
