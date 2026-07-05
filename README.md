# kestra-build / kestra-run — TDD-locked workflow pipeline

สอง skill นี้ทำงานคู่กันเป็น **generator + orchestrator** สำหรับสร้างและรัน "stage machine"
ที่บังคับ TDD จริง ๆ (ไม่ใช่แค่ขอให้ AI เขียนเทสต์ก่อนโค้ดเฉย ๆ) โดยมีการ freeze เทสต์,
จำกัดขอบเขตไฟล์ที่แต่ละ stage แก้ได้, และ commit ทีละ stage เพื่อ rollback/resume ได้เสมอ

```
spec (0-spec.md)
   │
   ▼
┌─────────────┐   เขียนไฟล์ workflow.yaml + state.json แล้วหยุด
│ kestra-build │   ไม่รันอะไร ไม่เขียนโค้ด ไม่ commit
└──────┬──────┘
       │
       ▼
┌─────────────┐   อ่าน state.json → spawn subagent ทีละ stage
│ kestra-run   │ → ตรวจผลด้วยคำสั่งจริง (git diff / exit code / sha256sum)
└─────────────┘ → commit ทีละ stage ที่ผ่าน → หยุดเมื่อเจอ stop condition
```

ทั้งสอง skill ไม่ได้ผูกกับ skill อื่นเป็น hard dependency ใด ๆ — ถ้า brief ของ stage ไหน
อยากแนะนำ skill เฉพาะทาง (เช่น skill implement, skill review) ก็จะเขียนไว้เป็น "คำแนะนำ"
ในเนื้อ brief เท่านั้น ถ้าไม่มี skill นั้นติดตั้งอยู่ ผู้ที่ถูก spawn มาทำ stage ก็ยังทำงานต่อได้ปกติ

## การติดตั้ง

Repo นี้คือตัว skill เอง — clone แล้วรัน `install.sh` เพื่อคัดลอก (หรือ symlink) โฟลเดอร์
`kestra-build/` และ `kestra-run/` ไปวางไว้ในตำแหน่งที่ Claude Code auto-discover skill ให้เอง
ไม่ต้องแก้ config อะไรเพิ่ม:

```bash
git clone <this-repo-url> kestra-workflow-skills
cd kestra-workflow-skills

./install.sh                        # ติดตั้งแบบ global — ใช้ได้ทุกโปรเจกต์ (~/.claude/skills/)
./install.sh --project ~/code/app   # ติดตั้งเฉพาะโปรเจกต์เดียว (<path>/.claude/skills/)
./install.sh --link                 # symlink แทนการ copy — เวลา git pull repo นี้ skill จะอัปเดตตามทันที
./install.sh --force                # เขียนทับถ้ามีติดตั้งอยู่แล้ว
./install.sh --uninstall            # ถอนการติดตั้ง (ใส่ --project เดียวกับตอนติดตั้ง ถ้าไม่ใช่ global)
```

รันแล้ว restart Claude Code (หรือเปิด session ใหม่) เพื่อให้ skill ใหม่ถูกโหลด ไม่มี dependency
ภายนอกอะไรต้องติดตั้งเพิ่ม — สคริปต์ dry-run ของ kestra-build (`validate_workflow.py`) ใช้แค่
`python3` มาตรฐาน (ไม่ต้องมี PyYAML หรือ third-party package ใด ๆ)

---

## kestra-build — ตัวสร้าง workflow

**อยู่ที่:** [`kestra-build/`](kestra-build/) · อ่านเพิ่ม: [`kestra-build/README.md`](kestra-build/README.md), [`kestra-build/SKILL.md`](kestra-build/SKILL.md)

### ทำอะไร

รับ feature spec (ที่มี acceptance criteria ชัดเจน หรือ prose คร่าว ๆ ที่ยอมให้ช่วยลับให้คมก่อน)
แล้วผลิตไฟล์ 2 ไฟล์:

| ไฟล์ | คืออะไร |
|---|---|
| `workflow.yaml` | แผนงานแบบ stage-by-stage เฉพาะของ feature นั้น — แต่ละ stage ระบุว่าแก้ไฟล์ตรงไหนได้ (`write_scope`), เช็คผ่านยังไง (`exit_criteria`), ถ้าพังทำอะไรต่อ (`on_fail`) |
| `state.json` | สถานะเริ่มต้น — ทุก stage เป็น `pending`, test hash ยังเป็น `null` |

**ไม่รันอะไรทั้งสิ้น** — เขียนไฟล์เสร็จก็หยุด ถ้าอยากรันจริงต้องส่งต่อให้ `kestra-run`

### หลักการที่ยึดถือ (สำคัญมาก อ่านก่อนแก้ workflow ที่ generate มา)

1. **Write-scope allowlist** — บังคับตอน apply จริง ไม่ใช่ขอ AI ดี ๆ ว่าอย่าไปแตะไฟล์อื่น
   ถ้า diff ของ stage ไหนหลุดออกนอก `write_scope` ที่ประกาศไว้ → orchestrator revert ทิ้งทันที
2. **Test-hash freeze** — จุดที่เขียนเทสต์เสร็จ (`generate-tests`, มี `freeze_after: true`)
   จะ snapshot hash ของไฟล์เทสต์ทั้งหมดเก็บไว้ใน `state.json` ทุก stage หลังจากนั้นต้องเช็ค hash
   นี้ก่อนเริ่มงาน ถ้า hash ไม่ตรง (มีคนไปแก้เทสต์นอกกระบวนการ) → หยุดทันที ไม่ใช่แค่ retry
3. **Commit ต่อ stage** — stage ไหนผ่านจะ commit โค้ด + `state.json` พร้อมกันในคอมมิทเดียว
   ไม่มีการ tag แยก เพราะตัวคอมมิทเองคือจุด rollback (`git reset --hard <sha>`) อยู่แล้ว

**ทำไม TDD ต้องมาก่อนเสมอ:** ถ้าเขียนเทสต์พร้อมกับหรือหลังโค้ด false positive จะย้ายไปซ่อนอยู่ใน
เทสต์แทน (green build ปลอม ๆ ที่ assertion หลวมเกินไป อันตรายกว่า red ตรง ๆ เพราะดูเหมือนมี
หลักฐานรองรับ) พอ freeze เทสต์ก่อนเขียนโค้ด implement ก็ไม่มีทางลัดไปทำเทสต์ให้ผ่านง่าย ๆ ได้
(ข้อจำกัดที่ TDD **ไม่** แก้ให้: ถ้า spec เองมองข้าม edge case ไป เทสต์ก็จะมองข้ามเหมือนกัน —
ความเสี่ยงนี้เป็นหน้าที่ของขั้นตอน spec review ไม่ใช่ stage machine)

**ทำไม fixing ต้อง "เลื่อนขั้นขึ้น" ไม่ใช่ "เบี่ยงข้าง":** เทสต์ failed มีทางแก้ที่ซื่อสัตย์แค่ 2
ทาง — แก้โค้ด หรือยอมรับว่า spec/เทสต์ที่ freeze ไว้ผิด ไม่มีทางที่ 3 ที่จะไปแก้เทสต์ให้ตรงกับ
โค้ดที่พังอยู่ ดังนั้น stage สถานะ `fixing` แก้ได้แค่ไฟล์นอกเทสต์เท่านั้น พอ retry ครบ
(`max_attempts`) หรือวนซ้ำ diff เดิม (no progress ตาม `escalate_at`) ทางออกทางเดียวที่ถูกต้องคือ
`reworking` — ปลดล็อกให้เขียนเทสต์ใหม่ได้ วนกลับไป spec-review หรือ generate-tests ใหม่
freeze ใหม่ รีเซ็ต attempt counter

### ขั้นตอนการทำงานของ kestra-build (ย่อจาก SKILL.md)

1. อ่าน/ลับ spec ให้มี acceptance criteria ชัดเจนก่อน
2. เติมตาราง flag เชิงกล (`needs_ui`, `needs_ba`, `needs_sa`, `needs_devops`, ...) → ใช้ตัดสินว่า
   ต้องเพิ่ม stage อะไรบ้าง (เช่น `needs_ui: true` → ต้องมี stage `design` ก่อน `generate-tests`)
3. ออกแบบ stage list จาก spec จริง ไม่ใช่ template ตายตัว โครงพื้นฐานที่สุดคือ:
   `spec-review → generate-tests (🔒 freeze) → implement[-per-component] → {verify, review} → done`
   - component ที่เป็นอิสระต่อกัน (เช่น backend/frontend) → เป็น sibling stage แยกกัน ไม่ chain ต่อกัน
     เพื่อให้ kestra-run รันขนานกันได้จริง
   - `verify` กับ `review` เป็น sibling กันเสมอ (ทั้งคู่ `depends_on` stage implement โดยตรง)
   - ค่าเริ่มต้นคือ **ไม่มี** `human_approval` stage เลย — มนุษย์เข้ามาเกี่ยวจุดเดียวคือตอน
     `fixing → reworking` เท่านั้น (ดู "Default HITL posture" ใน `references/design-principles.md`)
   - `review` เป็น stage บังคับเสมอ (เช็ค correctness/security ที่เทสต์เฉย ๆ ไม่ครอบคลุม)
   - ถ้า spec มีเรื่อง deploy (env var, migration, feature flag) → เพิ่ม stage `deploy-readiness`
   - จบด้วย stage `done` แบบ mechanical (เขียนสรุปแล้วจบ ไม่ใช่ waiting_approval)
4. เติมฟิลด์ทุก stage: `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`, `on_fail`,
   `freeze_after`
5. เขียน `workflow.yaml` + `state.json`
6. **Dry-run ก่อนเสมอ**: `python3 kestra-build/scripts/validate_workflow.py <output-dir>` —
   สคริปต์ตรวจโครงสร้างแบบ zero-LLM (ไม่ใช้ PyYAML, ไม่พึ่ง AI ตัดสิน) เช็ค 7 อย่างหลัก ๆ:
   - `on_fail.target` หายไปตอน `write_scope: []` + `action: fixing`
   - write_scope ไปทับ path ของเทสต์ที่ freeze ไว้แล้ว
   - stage ที่ independent กันแต่ `write_scope` ชนกัน (เสี่ยงชนกันตอนรันขนาน)
   - `freeze_after: true` ไม่ครบ 1 หรือเกิน 1 stage
   - dependency cycle / stage ที่ไปไม่ถึง (unreachable)
   - `exit_criteria` หรือ `on_fail` ที่ field จำเป็นหายไป
   - `state.json` ไม่ตรงกับ stage id ใน `workflow.yaml`

   ผลลัพธ์ `FAIL` = ต้องแก้ก่อนโชว์ผู้ใช้, `WARN` = แจ้งไว้เฉย ๆ ไม่ block

7. โชว์ทั้งสองไฟล์พร้อมอธิบายลำดับ stage เป็นภาษาคน ให้ผู้ใช้ตรวจก่อนถือว่า "frozen"

### ตัวอย่างการเรียกใช้

```
"turn workflows/runs/csv-export/0-spec.md into a workflow.yaml"
```

---

## kestra-run — ตัว orchestrator ที่รัน workflow

**อยู่ที่:** [`kestra-run/`](kestra-run/) · อ่านเพิ่ม: [`kestra-run/README.md`](kestra-run/README.md), [`kestra-run/SKILL.md`](kestra-run/SKILL.md)

### ทำอะไร

รับไฟล์ `workflow.yaml` + `state.json` ที่ kestra-build เขียนไว้ แล้ว "รัน" มันจริง ๆ:
อ่าน state → spawn subagent ให้ทำงานตาม `brief` ของ stage นั้น → **ตรวจผลด้วยคำสั่งจริง**
(ไม่ใช่อ่าน diff แล้วเดาว่าโอเค) → commit ถ้าผ่าน → เดินหน้า stage ถัดไปอัตโนมัติ

### กติกาข้อเดียวที่ทุกอย่างยึดตาม

> ทุกการตัดสินใจเรื่อง enforcement ต้องมาจากคำสั่งที่รันจริงเท่านั้น ห้ามอ่าน diff แล้วตัดสินเอาเอง

เช่น `git diff --name-only` เทียบกับ `write_scope`, `sha256sum` เทียบกับ hash ที่เก็บไว้,
exit code ของคำสั่งเทสต์จริง ๆ — นี่คือเหตุผลที่ให้ AI เป็น orchestrator ได้อย่างปลอดภัย เพราะ
จุดตัดสินใจที่สำคัญทั้งหมดเป็นกลไก ไม่ใช่ความเห็น

### ลูปการทำงาน (ต่อรอบ)

1. **เช็ค test-hash** (ถ้า `state.json.test_hash` ไม่ใช่ `null`) — hash ไม่ตรง = หยุดทันที
   ไม่ใช่ retry เพราะแปลว่ามีคนไปแก้เทสต์แช่แข็งนอกกระบวนการ
2. **ทำงานตาม brief** — spawn subagent (หรือทำเองถ้าเป็นแค่เช็คเชิงกลที่ไม่ต้องใช้ judgment
   เช่น stage `review`/`verify` ที่ `write_scope: []`) — stage `done` ก็เขียนสรุปเองได้เลยจาก
   `state.json`/`git log` โดยไม่ต้อง spawn ใหม่
3. **ตรวจเชิงกล** ตามลำดับเสมอ: `write_scope` (diff จริง, revert ถ้าหลุดขอบเขต) → `exit_criteria`
   (รันคำสั่งจริง/เช็ค artifact จริง)
4. ถ้า `exit_criteria.type` เป็น `human_approval` (มีเฉพาะกรณีผู้ใช้ขอ milestone แบบ manual
   ไว้ล่วงหน้าเท่านั้น) → หยุดถามจริง ๆ ทุกครั้ง ไม่ auto-approve
5. **ผ่าน** → stage เป็น `passed`, ถ้าเป็น freeze stage ก็เก็บ test_hash, commit
   (โค้ด + `state.json` ในคอมมิทเดียว), เลื่อนไป stage ถัดไปที่ dependency ครบแล้วอัตโนมัติ
6. **ไม่ผ่าน** → เพิ่ม `attempt`, เช็ค diff ซ้ำเดิมไหม (`seen_diffs`) →
   - ยัง `attempt < max_attempts` และไม่ใช่ diff ซ้ำเดิมเกิน `escalate_at` → กลับไป step 2 ใหม่
     (resume subagent ตัวเดิมถ้าทำได้ ดีกว่า spawn ใหม่ เพราะไม่ต้องเสียเวลา re-orient)
   - ครบ `max_attempts` หรือ diff ซ้ำเดิมเกิน `escalate_at` → **`reworking`** — จุดหยุดเดียวที่
     รับประกันว่ามีมนุษย์เข้ามาดูเสมอ

### หยุดเมื่อไหร่ (stop condition)

- `fixing → reworking` — retry หมดโควต้า หรือวนซ้ำ diff เดิมไม่คืบหน้า (จุดที่มี "เสมอ")
- `blocked` — ต้องมีคนมาปลดล็อก
- test-hash mismatch — มีคนแก้เทสต์แช่แข็งนอกกระบวนการ
- `human_approval` — เฉพาะ workflow ที่ผู้ใช้ขอ manual milestone ไว้ล่วงหน้าเท่านั้น (ไม่ใช่ default)

นอกเหนือจากนี้รันต่อเนื่องอัตโนมัติ ไม่ถามซ้ำทุก stage — เพราะงั้นถึงมี orchestrator

### ตัวอย่างการเรียกใช้

```
/kestra-run csv-export
"run the workflow for inventory-sync"
"resume where csv-export left off"
```

ถ้ายังไม่มี `workflow.yaml` จะบอกให้ไปรัน `kestra-build` ก่อน ไม่มโนสร้างเองให้

### Resume

ไม่มี "resume mode" แยกต่างหาก — `state.json` + คอมมิทของ stage ล่าสุดที่ผ่านคือจุด checkpoint
ในตัวอยู่แล้ว แค่บอกให้ kestra-run รันต่อ มันจะอ่าน `current_stage` สดใหม่ทุกครั้งเอง

---

## เอกสารอ้างอิงเพิ่มเติม

| ไฟล์ | เนื้อหา |
|---|---|
| [`kestra-build/references/design-principles.md`](kestra-build/references/design-principles.md) | ที่มาของทุก state/transition, "Default HITL posture", เหตุผลที่ไม่มี mid-workflow replanning |
| [`kestra-build/references/workflow-schema.md`](kestra-build/references/workflow-schema.md) | field reference ของ `workflow.yaml` ทุกตัว พร้อมตัวอย่างเต็มไฟล์ (csv-export) |
| [`kestra-build/references/state-schema.md`](kestra-build/references/state-schema.md) | field reference ของ `state.json` |
| [`kestra-run/references/enforcement.md`](kestra-run/references/enforcement.md) | คำสั่งจริงทุกอันที่ใช้เช็ค (write_scope diff, test-hash, commit-per-stage, rollback) |
| [`kestra-run/references/efficiency-notes.md`](kestra-run/references/efficiency-notes.md) | เหตุผลของทางลัดด้านประสิทธิภาพต่าง ๆ (ไม่ spawn agent ใหม่ทุก stage, resume แทน spawn ใหม่ ฯลฯ) |

## สิ่งที่ตั้งใจ "ไม่ทำ"

- **kestra-build ไม่รันอะไรเลย** ไม่เขียนโค้ดจริง ไม่ commit ไม่เรียก skill ไหนทั้งสิ้น
- **kestra-run ไม่ generate workflow เอง** ถ้ายังไม่มีไฟล์จะบอกให้ไปสร้างก่อน ไม่ improvise
- ทั้งสอง skill **ไม่ผูกกับ skill/agent เฉพาะทางตัวไหนเป็น hard dependency** — ชื่อ skill
  ที่อาจถูกแนะนำใน `brief` ของแต่ละ stage เป็นแค่คำแนะนำ ("ลองใช้ดูถ้ามี") ไม่ใช่ข้อบังคับ
  เพื่อให้ workflow.yaml ที่ generate ออกมาย้ายไปรันบนเครื่อง/session อื่นที่มี skill set
  ไม่เหมือนกันได้โดยไม่พัง

## License

ดู [LICENSE](LICENSE)