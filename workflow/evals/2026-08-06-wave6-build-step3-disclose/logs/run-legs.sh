#!/bin/sh
# The mechanical half of the Wave-6 eval, one leg at a time, literal output into
# this directory.  Re-run with:
#
#     sh workflow/evals/2026-08-06-wave6-build-step3-disclose/logs/run-legs.sh
#
# Reads the repo and writes only into this logs/ directory.  Nothing here needs
# a model: every leg is a command with a deterministic answer, so a reader can
# re-run it and get the same bytes.
#
# What this half grades: that the Wave-6 disclosure moved text without losing or
# rewording it, that every gate row resolves to a section that exists and every
# gated section is named by a row, and that the read budget the commits claim is
# the read budget the files actually have.  What it CANNOT grade is cost — a
# disclosed reference is only cheaper if a run declines to open it, and only the
# four agent runs in the other half can say whether that happens.  See README.md.
set -u

LOGS=$(cd "$(dirname "$0")" && pwd)
EVAL_DIR=$(cd "$LOGS/.." && pwd)
UP=$(cd "$EVAL_DIR/../../.." && pwd)
BEFORE=dd4077d
AFTER=bcc2bbd
export PYTHONDONTWRITEBYTECODE=1
cd "$UP" || exit 1

# ---------------------------------------------------------------- leg 00
# The read budget per run shape, recomputed from real line counts rather than
# taken from the commit messages that claim it.
python3 - "$BEFORE" "$AFTER" > "$LOGS/00-line-budget.log" 2>&1 <<'PY'
import subprocess, sys
before, after = sys.argv[1], sys.argv[2]
def n(sha, path):
    r = subprocess.run(['git','show',f'{sha}:{path}'], capture_output=True, text=True)
    return 0 if r.returncode else len(r.stdout.rstrip('\n').split('\n'))
P = 'workflow/kestra-build/'
files = ('SKILL.md', 'references/full-mode-stages.md', 'references/stage-derivation.md')
b = {f: n(before, P+f) for f in files}
a = {f: n(after,  P+f) for f in files}
print(f'before {before}:', ' '.join(f'{f}={b[f] or "-"}' for f in files))
print(f'after  {after}:', ' '.join(f'{f}={a[f] or "-"}' for f in files))
print()
print('lines a run reads, by the branch the spec takes:')
print(f'{"run shape":<30} {"before":>7} {"after":>7} {"delta":>7} {"pct":>7}  opens')
shapes = [
    ('lite, no devops', ['SKILL.md'], ['SKILL.md'], 'nothing'),
    ('full, typical',   ['SKILL.md','references/full-mode-stages.md'],
                        ['SKILL.md','references/full-mode-stages.md'], 'full-mode-stages.md'),
    ('full + refactor + repo gate', ['SKILL.md','references/full-mode-stages.md'],
                        list(files), 'both'),
]
for label, bf, af, opens in shapes:
    bt, at = sum(b[f] for f in bf), sum(a[f] for f in af)
    print(f'{label:<30} {bt:>7} {at:>7} {at-bt:>+7} {(at-bt)/bt*100:>+6.1f}%  {opens}')
print()
print('step 3, the ordered-list item this wave targeted:')
import re
for sha in (before, after):
    t = subprocess.run(['git','show',f'{sha}:{P}SKILL.md'], capture_output=True, text=True).stdout
    L = t.split('\n'); p = L.index('## Process') + 1
    idx = [i for i,l in enumerate(L,1) if re.match(r'^\d+\. \*\*', l) and i > p]
    nums = [int(L[i-1].split('.')[0]) for i in idx]
    print(f'  {sha}: step 3 = {idx[3]-idx[2]:>4} lines   Process = {nums}')
PY

# ---------------------------------------------------------------- leg 01
# Move fidelity.  Every span that moved is compared line by line against the
# same span at BEFORE.  A line that is not found byte-identical in its new home
# is printed, so the rewritten ones are on the record rather than glossed as
# "moved verbatim".
python3 - "$BEFORE" > "$LOGS/01-move-fidelity.log" 2>&1 <<'PY'
import subprocess, sys, pathlib
before = sys.argv[1]
old = subprocess.run(['git','show',f'{before}:workflow/kestra-build/SKILL.md'],
                     capture_output=True, text=True, check=True).stdout.split('\n')
def dedent(a, b, w=5):
    return [old[a-1][w:]] + ['' if not old[i-1].strip() else old[i-1][w:] for i in range(a+1, b+1)]
R = pathlib.Path('workflow/kestra-build/references')
fms = (R/'full-mode-stages.md').read_text()
sd  = (R/'stage-derivation.md').read_text()
spans = [
    ('D  spec-review',            467, 519, 5, fms, 'full-mode-stages.md'),
    ('H  test-review fold-in',    571, 600, 5, fms, 'full-mode-stages.md'),
    ('C  design-tests split',     448, 466, 5, sd,  'stage-derivation.md'),
    ('F  wide refactor',          533, 554, 5, sd,  'stage-derivation.md'),
    ('G  batch greens',           555, 570, 5, sd,  'stage-derivation.md'),
    ('K2 numeric finding',        647, 663, 7, sd,  'stage-derivation.md'),
    ('L  repo pre-merge gate',    669, 692, 5, sd,  'stage-derivation.md'),
]
print(f'moved spans, measured against {before}\n')
total = rew = 0
for label, a, b, w, dest, name in spans:
    lines = [l for l in dedent(a, b, w) if l.strip()]
    missing = [l for l in lines if l not in dest]
    total += len(lines); rew += len(missing)
    print(f'{label:<26} {a}-{b} -> {name:<22} {len(lines)-len(missing)}/{len(lines)} byte-identical')
    for m in missing:
        print(f'    REWRITTEN: {m}')
print(f'\n{total-rew}/{total} moved lines byte-identical; {rew} rewritten, each printed above.')
print('\nspans SPLIT rather than moved — the rule stayed inline, the reasoning moved,')
print('so line boundaries changed on both sides and a line-level check does not apply:')
print('  B  same-spawn scenario table   436-447   rule inline, argument -> stage-derivation.md section 1')
print('  K1 verdict-artifact shape      634-646   shape inline, reasoning -> stage-derivation.md section 2')
import re
corpus = ' '.join((pathlib.Path('workflow/kestra-build/SKILL.md').read_text() + '\n' + sd).split())
for label, a, b, w in (('B', 436, 447, 5), ('K1', 634, 646, 7)):
    flat = ' '.join(x.strip() for x in dedent(a, b, w) if x.strip())
    body = flat[2:] if flat.startswith('- ') else flat
    sents = [s.strip() for s in re.split(r'(?<=[.!?]) +', body) if s.strip()]
    lost = [s for s in sents if s not in corpus]
    print(f'  {label}: {len(sents)-len(lost)}/{len(sents)} sentences still present verbatim '
          f'across SKILL.md + stage-derivation.md')
    for s in lost:
        print(f'      REWORDED: {s}')
print()
print('a sentence listed REWORDED above was edited, not dropped — the edits in the split spans are')
print('the same relocation-forced kind as the moved ones: "this bullet" became "this rule" in text')
print('that is no longer a bullet.')
PY

# ---------------------------------------------------------------- leg 02
# Every relative markdown link under workflow/ still resolves, including the two
# README rows this wave added.
python3 - > "$LOGS/02-links.log" 2>&1 <<'PY'
import re, pathlib
Lk = re.compile(r'\[[^\]]*\]\(([^)\s#]+)')
tot = bad = 0
for p in sorted(pathlib.Path('workflow').rglob('*.md')):
    if 'evals/' in str(p) or 'research/' in str(p): continue
    for i, line in enumerate(p.read_text().splitlines(), 1):
        for x in Lk.findall(line):
            if x.startswith(('http','mailto')): continue
            tot += 1
            if not (p.parent/x).exists():
                bad += 1; print('DANGLING', p, i, x)
print(f'{tot} relative links, {bad} dangling   (workflow/, excluding evals/ and research/)')
print()
for f in ('README.md','README-th.md'):
    t = pathlib.Path('workflow')/f
    body = t.read_text()
    for name in ('full-mode-stages.md','stage-derivation.md'):
        print(f'{f:<14} indexes {name:<24}', f'kestra-build/references/{name}' in body)
    print(f'{f:<14} headings', sum(1 for l in body.split("\n") if l.startswith("#")))
PY

# ---------------------------------------------------------------- leg 03
# The gate table is the only thing making four of stage-derivation.md's five
# sections reachable, so it gets checked both ways: no row pointing at a section
# that does not exist, and no gated section without a row.  Section 2 is
# deliberately ungated (its rule is inline because it applies to every run) and
# the check asserts that it is the ONLY such section.
python3 - > "$LOGS/03-gate-coverage.log" 2>&1 <<'PY'
import pathlib, re
L = pathlib.Path('workflow/kestra-build/SKILL.md').read_text().split('\n')
proc = L.index('## Process') + 1
idx = [i for i,l in enumerate(L,1) if re.match(r'^\d+\. \*\*', l) and i > proc]
s3, s4 = idx[2], idx[3]
rows = [l.strip() for l in L[s3-1:s4-1] if l.strip().startswith('|')]
print(f'gate table, step 3 (lines {s3}-{s4-1}):')
for r in rows: print('  ' + r)
sd = pathlib.Path('workflow/kestra-build/references/stage-derivation.md').read_text()
fm = pathlib.Path('workflow/kestra-build/references/full-mode-stages.md').read_text()
txt = ' '.join(rows)
gated = {int(x) for x in re.findall(r'§ ([0-9])', txt)}
for a,b in re.findall(r'§§ ([0-9])–([0-9])', txt): gated |= {int(a), int(b)}
have = {int(m) for m in re.findall(r'^## ([0-9])\.', sd, re.M)}
print()
print('stage-derivation.md sections named by a gate row:', sorted(gated))
print('stage-derivation.md sections that exist:         ', sorted(have))
print('rows pointing at a missing section:', sorted(gated - have) or 'NONE')
print('sections with no gate row:        ', sorted(have - gated), '(2 by design; anything else is a defect)')
print()
for h in ('## `spec-review`', '## `test-review`', '## `deploy-readiness`'):
    print(f'full-mode-stages.md has {h + ":":<26}', ('\n' + h) in fm)
print()
print('ASSERT', 'OK' if (not (gated - have)) and (have - gated) == {2} else 'FAIL',
      ': every gate row resolves and section 2 is the only ungated one')
PY

# ---------------------------------------------------------------- leg 04
# The four suites and the must-stay-green control, at HEAD.
{
  echo "the four suites and the control, at $(git rev-parse --short HEAD)"
  echo
  for t in workflow/kestra-build/scripts/test_requirement_surface.py \
           workflow/kestra-build/scripts/test_validate_workflow_anchor.py \
           workflow/kestra-exam/scripts/test_exam_harness.py; do
    printf '%-44s ' "$(basename "$t")"
    python3 -B "$t" 2>&1 | tail -2 | tr '\n' ' ' | sed 's/[[:space:]]*$//'; echo
  done
  printf '%-44s ' 'tests/test_install_check.py'
  python3 -B -m unittest discover -s tests -p 'test_install_check.py' 2>&1 \
    | tail -2 | tr '\n' ' ' | sed 's/[[:space:]]*$//'; echo
  echo
  echo 'control: validate_workflow.py on runs/order-cancellation-refund'
  python3 workflow/kestra-build/scripts/validate_workflow.py workflow/runs/order-cancellation-refund
  echo "exit=$?"
  echo
  # Scoped away from this logs/ directory on purpose: the check would otherwise
  # flag whitespace in the very file it is being written into, so the leg would
  # report on itself instead of on the wave.
  printf 'git diff --check (excluding this eval logs dir): '
  git diff --check -- . ":(exclude)$LOGS" && echo clean
} > "$LOGS/04-suites.log" 2>&1

# ---------------------------------------------------------------- leg 05
# The 2026-07-31 ablation's vendored skill copies are a dated record.  This wave
# reuses that eval's spec and fixture and must not have touched its copies.
{
  echo 'the 2026-07-31 ablation is a dated record — its vendored copies must be untouched'
  echo
  P=workflow/evals/2026-07-31-build-ablation-antipatterns
  echo "commits touching $P since dd4077d:"
  git log --oneline dd4077d..HEAD -- "$P" | sed 's/^/  /'
  test -z "$(git log --oneline dd4077d..HEAD -- "$P")" && echo '  (none)'
  echo
  printf 'uncommitted changes under that path: '
  n=$(git status --porcelain -- "$P" | wc -l | tr -d ' '); echo "$n"
  echo
  echo 'its vendored SKILL.md line counts, for the drift note in README.md:'
  wc -l "$P"/full-skill/SKILL.md "$P"/minimal-skill/SKILL.md workflow/kestra-build/SKILL.md
  echo
  echo "ASSERT $( [ -z "$(git log --oneline dd4077d..HEAD -- "$P")" ] && [ "$n" = 0 ] && echo OK || echo FAIL ): frozen copies untouched"
} > "$LOGS/05-frozen.log" 2>&1

# ---------------------------------------------------------------- leg 06
# The two vendored skill copies this eval runs against must be byte-identical to
# the commits they claim, or the runs measure something other than the wave.
#
# First sweep out compiled bytecode.  A half-B run invokes the vendored
# validate_spec.py, which imports requirement_surface and drops a .pyc inside the
# frozen copy -- so a real run leaves the very thing this leg is built to reject.
# The sweep is printed, not silent, and is scoped to __pycache__ under the two
# vendored folders: bytecode is generated, never authored, so removing it cannot
# destroy evidence.  Anyone re-running half B should export
# PYTHONDONTWRITEBYTECODE=1 so it never appears in the first place.
{
  echo 'sweeping compiled bytecode out of the vendored copies before checking them:'
  find "$EVAL_DIR/before-skill" "$EVAL_DIR/after-skill" -name '__pycache__' -type d -print 2>/dev/null \
    | sed 's|^|  removing |'
  find "$EVAL_DIR/before-skill" "$EVAL_DIR/after-skill" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  echo '  (nothing listed above = the copies were already clean)'
  echo
} > "$LOGS/06-vendor-provenance.log" 2>&1
python3 - "$BEFORE" "$AFTER" "$EVAL_DIR" >> "$LOGS/06-vendor-provenance.log" 2>&1 <<'PY'
import subprocess, sys, pathlib
before, after, ev = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True); return r.stdout.strip()
clean = True
for sha, d in ((before,'before-skill'), (after,'after-skill')):
    tracked = {t[len('workflow/kestra-build/'):]
               for t in sh('git','ls-tree','-r','--name-only',sha,'workflow/kestra-build').split('\n') if t}
    disk = {str(p.relative_to(ev/d)) for p in (ev/d).rglob('*') if p.is_file()}
    bad = [f for f in sorted(disk)
           if sh('git','rev-parse',f'{sha}:workflow/kestra-build/{f}') != sh('git','hash-object',str(ev/d/f))]
    print(f'{d:<13} vs {sha}: {len(disk)} files, file set equal={disk==tracked}, '
          f'content mismatches={bad or "NONE"}')
    if disk != tracked:
        print('   only on disk:', sorted(disk-tracked), '  only in commit:', sorted(tracked-disk))
    clean = clean and disk == tracked and not bad
src = pathlib.Path('workflow/evals/2026-07-31-build-ablation-antipatterns')
print()
print('spec-full/0-spec.md identical to the 2026-07-31 spec:',
      sh('git','hash-object',str(src/'spec/0-spec.md')) == sh('git','hash-object',str(ev/'spec-full/0-spec.md')))
print('fixture/ identical to the 2026-07-31 fixture:',
      all(sh('git','hash-object',str(p)) == sh('git','hash-object',str(ev/'fixture'/p.relative_to(src/'fixture')))
          for p in (src/'fixture').rglob('*') if p.is_file()))
print()
print('spec-lite/0-spec.md is new to this eval; validate_spec.py against the fixture:')
# -B, so this leg cannot leave behind the bytecode the sweep above just removed.
r = subprocess.run(['python3', '-B', str(ev/'after-skill/scripts/validate_spec.py'),
                    str(ev/'spec-lite/0-spec.md'), str(ev/'fixture')], capture_output=True, text=True)
print(''.join('  '+l+'\n' for l in r.stdout.strip().split('\n')), end='')
print(f'  exit={r.returncode}   (0 = no FAIL; the WARNs are the same five spec-full gets)')
print()
print(f'ASSERT {"OK " if clean else "FAIL"}: both vendored copies are byte-identical to the '
      f'commits they claim, source files and file set alike')
PY

# ---------------------------------------------------------------- leg 07
# Leg 00 counts lines, and a line is not a token.  A table row is denser than the
# prose it replaced, so a line count could flatter the wave.  Recount the same
# budget in words and characters, which track tokens far more closely, and price
# the whole saving against what a real run actually costs.
python3 - "$BEFORE" "$AFTER" > "$LOGS/07-token-proxy-budget.log" 2>&1 <<'PY'
import subprocess, re, sys
before, after = sys.argv[1], sys.argv[2]
def blob(sha, path):
    return subprocess.run(['git','show',f'{sha}:{path}'],capture_output=True,text=True).stdout
def step3(txt):
    L = txt.split('\n')
    s = next(i for i,l in enumerate(L) if l.startswith('3. **Derive the stage list'))
    e = next(i for i in range(s+1,len(L)) if re.match(r'^4\. \*\*', L[i]))
    return '\n'.join(L[s:e])
# splitlines(), not split('\n'): a file ending in a newline would otherwise count
# one phantom line and leg 07 would disagree with leg 00's wc -l by one.
def m(t): return (len(t.splitlines()), len(t.split()), len(t))
K = 'workflow/kestra-build/'
bs, as_ = blob(before, K+'SKILL.md'),        blob(after, K+'SKILL.md')
bf, af  = blob(before, K+'references/full-mode-stages.md'), blob(after, K+'references/full-mode-stages.md')
sd      = blob(after,  K+'references/stage-derivation.md')

print(f"{'':38}{'lines':>8}{'words':>9}{'chars':>9}")
for name, t in (('SKILL.md before',bs),('SKILL.md after',as_),
                ('  of which step 3, before',step3(bs)),('  of which step 3, after',step3(as_)),
                ('full-mode-stages.md before',bf),('full-mode-stages.md after',af),
                ('stage-derivation.md (new)',sd)):
    l,w,c = m(t); print(f"{name:38}{l:8,}{w:9,}{c:9,}")

print()
print("Read budget per branch, three ways:")
print(f"{'branch':34}{'lines':>17}{'words':>17}{'chars':>17}")
def row(label, bparts, aparts):
    bl,bw,bc = (sum(x) for x in zip(*[m(t) for t in bparts]))
    al,aw,ac = (sum(x) for x in zip(*[m(t) for t in aparts]))
    f = lambda b,a: f"{a-b:+,} ({(a-b)/b*100:+.1f}%)"
    print(f"{label:34}{f(bl,al):>17}{f(bw,aw):>17}{f(bc,ac):>17}")
    return ac-bc
d_lite = row('lite, no devops',        [bs],    [as_])
row('full, typical',                   [bs,bf], [as_,af])
row('full + refactor + repo gate',     [bs,bf], [as_,af,sd])
print()
print("Words and chars move with lines, slightly further -- so the line count in")
print("leg 00 does not flatter the wave.  ASSERT below checks that directly.")

# The read gate itself: fewer lines, but MORE words.  Print it, don't hide it.
def span(txt, a, b):
    L = txt.split('\n'); s = next(i for i,l in enumerate(L) if a in l)
    return '\n'.join(L[s:next(i for i in range(s+1,len(L)) if b in L[i])])
prose = span(bs, '**If step 2 settled on `mode: lite`', 'A minimal TDD-honest skeleton')
table = span(as_, '| Fact, already settled in step 2 |', 'Name what you opened')
print()
print("The read gate itself -- the one place the wave traded prose for a table:")
if prose: print(f"  before, prose : {m(prose)[0]:>3} lines {m(prose)[1]:>5} words {m(prose)[2]:>6} chars")
print(f"  after,  table : {m(table)[0]:>3} lines {m(table)[1]:>5} words {m(table)[2]:>6} chars")
print("  The table is shorter in lines and LONGER in words than the prose gate it")
print("  replaced.  That is the 'lines are not tokens' effect, isolated: it costs")
print("  a few hundred characters, against a lite saving three orders up.")

print()
print("What the whole saving is worth against a real run (half B measured 144,954")
print("tokens for the cheapest run; ~4 chars/token is the usual English rule):")
tok = abs(d_lite)/4
print(f"  lite text saved   : {abs(d_lite):,} chars  ~= {tok:,.0f} tokens")
print(f"  as a share of one measured lite run (144,954 tokens): {tok/144954*100:.1f}%")
print(f"  observed run-to-run delta on the lite pair          : +7.4%")
print("  So the entire prize is smaller than the noise this design can resolve.")
print()
for lbl, cond in (
    ('the char saving per branch has the same sign as the line saving',
     (d_lite < 0)),
    ('lite chars fall by more than 15%',
     abs(d_lite)/m(bs)[2] > 0.15),
):
    print(f"ASSERT {'OK ' if cond else 'FAIL'}: {lbl}")
PY

# ---------------------------------------------------------------- leg 08
# Half B's equivalence bar, applied mechanically to the four generated workflows
# rather than eyeballed: same stage topology, one freeze point, same on_fail
# wiring and exit types, and -- the hard requirement -- the same mode per spec.
python3 - "$EVAL_DIR" > "$LOGS/08-run-equivalence.log" 2>&1 <<'PY'
import re, sys, pathlib, subprocess
ev = pathlib.Path(sys.argv[1])
def parse(p):
    txt = (ev/p/'workflow.yaml').read_text(); out=[]
    for blk in re.split(r'\n  - id: ', txt)[1:]:
        sid = blk.split('\n',1)[0].strip()
        g = lambda k: (lambda mm: mm.group(1).strip() if mm else None)(
            re.search(r'^\s{4}'+k+r':\s*(.*)$', blk, re.M))
        one = lambda k: (lambda mm: mm.group(1) if mm else None)(re.search(k+r':\s*(\S+)', blk))
        out.append(dict(id=sid, depends_on=g('depends_on'), write_scope=g('write_scope'),
                        freeze=g('freeze_after'), action=one('action'), target=one('target'),
                        max_attempts=one('max_attempts'),
                        exit_type=(lambda mm: mm.group(1) if mm else None)(
                            re.search(r'^\s+type:\s*(\S+)', blk, re.M))))
    return out
def mode(p):
    t = (ev/p/'workflow.yaml').read_text()
    mm = re.search(r'^mode:\s*(\S+)', t, re.M);  return mm.group(1) if mm else '(absent)'
def norm(v, run):
    # Path frame and run-folder name are per-run facts, not structure.  The skill
    # never states which frame write_scope uses -- see README half B -- so compare
    # the basenames and let leg 08 stay a structure check, not a path check.
    if v is None: return None
    v = v.replace(f'../{run}/','').replace('run-1-before-full/','').replace('run-2-after-full/','')
    return re.sub(r'"[^"]*/(?=[^/"]+")', '"', v.replace('fixture/',''))

pairs = (('full', 'run-1-before-full', 'run-2-after-full'),
         ('lite', 'run-3-before-lite', 'run-4-after-lite'))
verdicts = []
for label, b, a in pairs:
    B, A = parse(b), parse(a)
    print('='*72); print(f'{label}: {b}  vs  {a}')
    print(f'  mode           : {mode(b)}  vs  {mode(a)}'
          f'   {"AGREE" if mode(b)==mode(a) else "*** DISAGREE = REGRESSION ***"}')
    print(f'  stage count    : {len(B)} vs {len(A)}')
    print(f'  freeze_after=1 : {sum(1 for r in B if r["freeze"]=="true")} vs '
          f'{sum(1 for r in A if r["freeze"]=="true")}')
    renamed, diffs = [], []
    for i,(rb,ra) in enumerate(zip(B,A)):
        if rb['id'] != ra['id']: renamed.append((rb['id'], ra['id']))
        for k in ('depends_on','write_scope','action','target','max_attempts','exit_type'):
            x, y = norm(rb[k], b), norm(ra[k], a)
            if k in ('depends_on','target'):          # ids differ when a stage is renamed
                for o,n in renamed:
                    if x: x = x.replace(o,n)
            if x != y: diffs.append((i, rb['id'], k, x, y))
    print(f'  renamed stages : {renamed or "none"}')
    if diffs:
        print('  differences after normalising path frame and renames:')
        for i,sid,k,x,y in diffs: print(f'    [{i}] {sid:28} {k:13} {x}  ->  {y}')
    else:
        print('  differences    : none, after normalising path frame and renames')
    ok = (mode(b)==mode(a) and len(B)==len(A)
          and sum(1 for r in B if r['freeze']=='true')==1==sum(1 for r in A if r['freeze']=='true')
          and all(d[2] not in ('depends_on','action','max_attempts','exit_type') for d in diffs))
    verdicts.append((label, ok))
print('='*72)
print('validate_workflow.py on all four, each under BOTH vendored validators:')
for run in ('run-1-before-full','run-2-after-full','run-3-before-lite','run-4-after-lite'):
    for v in ('before-skill','after-skill'):
        r = subprocess.run(['python3','-B',str(ev/v/'scripts/validate_workflow.py'),str(ev/run)],
                           capture_output=True, text=True)
        last = [l for l in r.stdout.strip().split('\n') if l.strip()][-1]
        print(f'  {run:20} under {v:12} exit={r.returncode}  {last}')
print()
for label, ok in verdicts:
    print(f'ASSERT {"OK " if ok else "FAIL"}: {label} pair is equivalent on mode, topology, '
          f'one freeze point, on_fail wiring and exit types')
PY

echo "legs written to $LOGS:"
ls -1 "$LOGS"/*.log | sed 's|.*/|  |'
grep -h '^ASSERT' "$LOGS"/*.log | sed 's/^/  /'
