# workflow/ — kestra-build & kestra-run

*[Read in English](README.md)*

สอง skill นี้ทำงานร่วมกันเป็น **ตัวสร้าง + ตัวรัน** สำหรับสร้างและรัน "stage machine" ที่บังคับ
TDD จริงๆ (ไม่ใช่แค่ขอให้ AI เขียนเทสต์ก่อนแบบสุภาพๆ) มันจะ freeze เทสต์เมื่อเขียนเสร็จแล้ว
จำกัดว่าแต่ละ stage แก้ไฟล์ไหนได้บ้าง และ commit ทีละ stage เพื่อให้ rollback หรือ resume ได้เสมอ

```
spec (0-spec.md)
   │
   ▼
┌─────────────┐   เขียน workflow.yaml + state.json แล้วหยุด
│ kestra-build │   ไม่รัน stage, ไม่เขียนโค้ด, ไม่ commit
└──────┬──────┘
       │
       ▼
┌─────────────┐   อ่าน state.json → spawn subagent ต่อ stage
│ kestra-run   │ → ตรวจสอบแบบ mechanical (git diff / exit code / sha256sum)
└─────────────┘ → commit ทุก stage ที่ผ่าน → หยุดเมื่อเจอเงื่อนไขหยุดจริง
```

ทั้งสอง skill ไม่ได้ผูกติดกับ skill อื่นแบบ hard dependency — ถ้า brief ของ stage ไหนอยากแนะนำ
skill เฉพาะทาง (เช่น skill สำหรับ implement, skill สำหรับ review) มันจะปรากฏแค่เป็น "คำแนะนำ"
ในเนื้อหา brief เท่านั้น ตัวที่ถูก spawn มาทำงาน stage นั้นยังทำงานได้ปกติแม้ skill นั้นจะไม่ได้ติดตั้งไว้

---

## kestra-build — ตัวสร้างเวิร์กโฟลว์

**ที่อยู่:** [`kestra-build/`](kestra-build/) · รายละเอียดเพิ่มเติม: [`kestra-build/README.md`](kestra-build/README.md), [`kestra-build/SKILL.md`](kestra-build/SKILL.md)

### มันทำอะไร

รับ spec ของฟีเจอร์ (ที่มี acceptance criteria ชัดเจนอยู่แล้ว หรือเป็นแค่คำอธิบายหยาบๆ ที่จะช่วย
ทำให้ชัดเจนขึ้นก่อน) แล้วสร้างไฟล์สองไฟล์:

| ไฟล์ | คืออะไร |
|---|---|
| `workflow.yaml` | แผนแบบ stage-by-stage ที่ปรับเฉพาะฟีเจอร์นั้น — แต่ละ stage ประกาศว่าแก้ไฟล์ไหนได้ (`write_scope`), เช็คยังไงว่าผ่าน (`exit_criteria`), และทำอะไรถ้าล้มเหลว (`on_fail`) |
| `state.json` | สถานะเริ่มต้น — ทุก stage เป็น `pending`, test hash ยังเป็น `null` |

**มันไม่รันอะไรเลย** — แค่เขียนไฟล์แล้วหยุด ถ้าอยากรันจริง ต้องส่งต่อให้ `kestra-run`

### หลักการที่มันยึดถือ (สำคัญ — อ่านก่อนแก้ไข workflow ที่สร้างมา)

1. **Write-scope allowlist** — บังคับใช้ตอน apply จริง ไม่ใช่แค่ขอ AI สุภาพๆ ไม่ให้แตะไฟล์อื่น
   ถ้า diff ของ stage ไหนหลุดออกนอก `write_scope` ที่ประกาศไว้ orchestrator จะ revert ทันที
2. **Test-hash freeze** — พอเทสต์เสร็จ (`generate-tests`, ที่มี `freeze_after: true`) hash ของ
   ไฟล์เทสต์ทุกไฟล์จะถูก snapshot เก็บไว้ใน `state.json` ทุก stage หลังจากนั้นต้องเช็ค hash ก่อน
   ทำอะไรเสมอ ถ้าไม่ตรงกัน (มีคนแก้เทสต์นอกกระบวนการ) จะหยุดทันที — ไม่ใช่แค่ retry
3. **Commit ทีละ stage** — stage ที่ผ่านจะ commit โค้ด + `state.json` พร้อมกันในคอมมิตเดียว
   ไม่มี tag แยก — ตัว commit เองคือจุด rollback (`git reset --hard <sha>`)

**ทำไม TDD ต้องมาก่อนเสมอ:** ถ้าเขียนเทสต์พร้อมกับหรือหลังโค้ด false positive จะแค่ย้ายไปอยู่ใน
เทสต์เอง (build เขียวปลอมๆ ที่มี assertion หลวมๆ อันตรายกว่าการแดงตรงๆ เพราะดูเหมือนมีหลักฐาน
รองรับ) การ freeze เทสต์ก่อน implementation จะตัดทางลัดที่ทำให้เทสต์ผ่านง่ายๆ ออกไป (สิ่งที่ TDD
*ไม่ได้* แก้: ถ้า spec เองพลาดเคสขอบ เทสต์ก็จะพลาดเคสนั้นด้วย — ความเสี่ยงนี้เป็นเรื่องของ spec
review ไม่ใช่ของ stage machine)

**ทำไม "fixing" ต้อง escalate ขึ้นบน ไม่ใช่ไปด้านข้าง:** เทสต์ที่ fail มีทางแก้ที่ซื่อสัตย์แค่สองทาง
— แก้โค้ด หรือยอมรับว่า spec/test ที่ freeze ไว้ผิด ไม่มีทางเลือกที่สามที่จะแก้เทสต์ให้ตรงกับโค้ด
ที่พัง ดังนั้น stage `fixing` แก้ได้แค่ไฟล์ที่ไม่ใช่เทสต์เท่านั้น เมื่อ retry หมด (`max_attempts`)
หรือ diff เดิมโผล่มาซ้ำๆ (ไม่มีความคืบหน้า ตาม `escalate_at`) ทางเดียวที่ถูกต้องคือ `reworking`
— ปลดล็อกการเขียนเทสต์อีกครั้ง กลับไป spec-review หรือสร้างเทสต์ใหม่ freeze ใหม่ แล้วรีเซ็ต
ตัวนับ attempt

### kestra-build ทำงานยังไง (สรุปย่อจาก SKILL.md)

1. อ่าน spec หรือทำให้ชัดเจนขึ้นจนกว่าจะมี acceptance criteria ที่ชัด
2. กรอกตาราง flag แบบ mechanical (`needs_ui`, `needs_ba`, `needs_sa`, `needs_devops`, ...) เพื่อ
   ตัดสินว่าต้องมี stage ไหนบ้าง (เช่น `needs_ui: true` → ต้องเพิ่ม stage `design` ก่อน
   `generate-tests`)
3. สร้างรายการ stage จาก spec จริง ไม่ใช่ template ตายตัว โครงขั้นต่ำคือ:
   `spec-review → generate-tests (🔒 freeze) → implement[-per-component] → {verify, review} → done`
   - component ที่เป็นอิสระต่อกัน (เช่น backend/frontend) จะเป็น stage พี่น้องกัน ไม่ใช่ chain
     เพื่อให้ kestra-run รันขนานกันได้จริง
   - `verify` กับ `review` เป็นพี่น้องกันเสมอ (ทั้งคู่ `depends_on` stage implement โดยตรง)
   - ค่าเริ่มต้นมี `human_approval` stage เป็น **ศูนย์** — จุดเดียวที่มนุษย์เข้ามาเกี่ยวข้องเสมอคือ
     `fixing → reworking` (ดู "Default HITL posture" ใน `references/design-principles.md`)
   - `review` เป็น stage บังคับเสมอ (มันจับปัญหา correctness/security ที่เทสต์อย่างเดียวจับไม่ได้)
   - ถ้า spec เกี่ยวข้องกับเรื่อง deployment (env vars, migration, feature flags) จะเพิ่ม stage
     `deploy-readiness`
   - จบด้วย stage `done` แบบ mechanical (เขียนสรุปแล้วหยุด — ไม่ใช่ `waiting_approval`)
4. กรอกทุกฟิลด์ของแต่ละ stage: `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`,
   `on_fail`, `freeze_after`
5. เขียน `workflow.yaml` + `state.json`
6. **dry-run เสมอก่อน**: `python3 kestra-build/scripts/validate_workflow.py <output-dir>` —
   การเช็คโครงสร้างแบบ zero-LLM (ไม่มี PyYAML ไม่มีการตัดสินใจของ AI) ที่จับ 7 เรื่องหลัก:
   - `on_fail.target` หายไปใน stage ที่ `write_scope: []` + `action: fixing`
   - `write_scope` ทับซ้อนกับ path ที่ freeze เป็นเทสต์ไปแล้ว
   - stage อิสระที่ `write_scope` ชนกัน (เสี่ยงจริงถ้ารันขนานกัน)
   - `freeze_after: true` หายไป หรือถูกตั้งไว้มากกว่าหนึ่ง stage
   - dependency วนลูป / stage ที่ไปไม่ถึง
   - `exit_criteria` หรือ `on_fail` ขาดฟิลด์ที่จำเป็น
   - `state.json` ไม่ตรงกับ stage id ใน `workflow.yaml`

   `FAIL` = ต้องแก้ก่อนโชว์ให้ผู้ใช้ดู, `WARN` = แจ้งไว้แต่ไม่บล็อก

7. โชว์ทั้งสองไฟล์พร้อมคำอธิบายลำดับ stage แบบภาษาธรรมดา เพื่อให้ผู้ใช้ตรวจสอบได้ก่อนถือว่า
   "freeze" แล้วจริงๆ

### ตัวอย่างการใช้งาน

```
"turn workflows/runs/csv-export/0-spec.md into a workflow.yaml"
```

---

## kestra-run — ตัวรันเวิร์กโฟลว์

**ที่อยู่:** [`kestra-run/`](kestra-run/) · รายละเอียดเพิ่มเติม: [`kestra-run/README.md`](kestra-run/README.md), [`kestra-run/SKILL.md`](kestra-run/SKILL.md)

### มันทำอะไร

รับ `workflow.yaml` + `state.json` ที่ kestra-build เขียนไว้ แล้ว "รัน" มันจริงๆ: อ่าน state →
spawn subagent มาทำ `brief` ของ stage → **ตรวจสอบผลลัพธ์ด้วยคำสั่งจริง** (ไม่เคยอ่าน diff แล้ว
เดาเอาเอง) → commit ถ้าผ่าน → ไปยัง stage ถัดไปโดยอัตโนมัติ

### กติกาข้อเดียวที่ทุกอย่างยึดตาม

> การตัดสินใจบังคับใช้ทุกครั้งต้องมาจากคำสั่งที่รันจริง ห้ามอ่าน diff แล้วตัดสินว่ามันดูโอเค

สิ่งอย่าง `git diff --name-only` เทียบกับ `write_scope`, `sha256sum` เทียบกับ hash ที่เก็บไว้,
exit code จริงของคำสั่งเทสต์ — นี่แหละคือเหตุผลที่ปลอดภัยที่จะให้ AI เป็น orchestrator ตรงนี้
เพราะทุกการตัดสินใจที่สำคัญเป็นแบบ mechanical ไม่ใช่ความเห็น

### ลูปการทำงาน (ต่อรอบ)

1. **เช็ค test hash** (ถ้า `state.json.test_hash` ไม่ใช่ `null`) — ถ้าไม่ตรงกันคือหยุดทันที
   ไม่ใช่ retry เพราะแปลว่ามีคนแก้เทสต์ที่ freeze ไว้นอกกระบวนการ
2. **ทำงานของ stage** — spawn subagent (หรือทำเองตรงๆ ถ้าเป็นแค่การเช็ค mechanical ที่ไม่ต้องใช้
   วิจารณญาณ เช่น stage `review`/`verify` ที่ `write_scope: []`) — stage `done` เขียนสรุปของตัวเอง
   ได้ตรงๆ จาก `state.json`/`git log` โดยไม่ต้อง spawn อะไร
3. **ตรวจสอบแบบ mechanical** เรียงลำดับเสมอ: `write_scope` (diff จริง, revert ถ้าหลุดขอบเขต) →
   `exit_criteria` (รันคำสั่งจริง / เช็ค artifact จริง)
4. ถ้า `exit_criteria.type` เป็น `human_approval` (มีเฉพาะตอนผู้ใช้ขอ manual milestone ไว้ล่วงหน้า)
   → หยุดถามจริงเสมอ ไม่เคย auto-approve
5. **ถ้าผ่าน** → stage กลายเป็น `passed`; ถ้าเป็น freeze stage ก็เก็บ test hash; commit (โค้ด +
   `state.json` ในคอมมิตเดียว); ไปยัง stage ถัดไปที่ dependency ครบแล้วโดยอัตโนมัติ
6. **ถ้าล้มเหลว** → เพิ่ม `attempt`, เช็คว่า diff ซ้ำหรือไม่ (`seen_diffs`):
   - ยังไม่ถึง `max_attempts` และไม่ใช่การซ้ำเกิน `escalate_at` → กลับไปข้อ 2 (resume subagent
     ตัวเดิมถ้าทำได้ แทนที่จะ spawn ใหม่ เพื่อไม่ต้องเสียเวลา orient ใหม่)
   - `max_attempts` หมด หรือ diff เดิมซ้ำเกิน `escalate_at` → **`reworking`** — เงื่อนไขหยุดเดียวที่
     รับประกันว่าจะดึงมนุษย์เข้ามาเสมอ

### เมื่อไหร่ที่มันหยุด

- `fixing → reworking` — retry หมด หรือ diff เดิมซ้ำโดยไม่มีความคืบหน้า (จุดหยุดที่รับประกันเสมอ)
- `blocked` — ต้องการมนุษย์มาปลดล็อก
- Test-hash ไม่ตรงกัน — มีคนแก้เทสต์ที่ freeze ไว้นอกกระบวนการ
- `human_approval` — เฉพาะ workflow ที่ผู้ใช้ขอ manual milestone ไว้ล่วงหน้าเท่านั้น (ไม่ใช่
  ค่าเริ่มต้น)

นอกเหนือจากนี้จะรันต่อเนื่องอัตโนมัติ — ไม่ถามซ้ำทุก stage เพราะถ้าเป็นแบบนั้นก็ไม่มีประโยชน์
ที่จะมี orchestrator

### ตัวอย่างการใช้งาน

```
/kestra-run csv-export
"run the workflow for inventory-sync"
"resume where csv-export left off"
```

ถ้ายังไม่มี `workflow.yaml` มันจะบอกให้รัน `kestra-build` ก่อน — จะไม่ด้นสดสร้างเองให้

### การ resume

ไม่มี "resume mode" แยกต่างหาก — `state.json` บวกกับ commit ของ stage ล่าสุดที่ผ่านแล้วก็คือ
checkpoint อยู่แล้ว แค่บอกให้ kestra-run ทำงานต่อ มันจะอ่าน `current_stage` ใหม่ทุกครั้ง

---

## เอกสารอ้างอิงเพิ่มเติม

| ไฟล์ | เนื้อหา |
|---|---|
| [`kestra-build/references/design-principles.md`](kestra-build/references/design-principles.md) | ที่มาของทุก state/transition, "Default HITL posture", ทำไมไม่มีการ replan กลางเวิร์กโฟลว์ |
| [`kestra-build/references/workflow-schema.md`](kestra-build/references/workflow-schema.md) | รายการฟิลด์เต็มของ `workflow.yaml` พร้อมตัวอย่างจริง (csv-export) |
| [`kestra-build/references/state-schema.md`](kestra-build/references/state-schema.md) | รายการฟิลด์ของ `state.json` |
| [`kestra-run/references/enforcement.md`](kestra-run/references/enforcement.md) | คำสั่งจริงที่ใช้เช็คทุกอย่าง (write_scope diff, test-hash, commit-per-stage, rollback) |
| [`kestra-run/references/efficiency-notes.md`](kestra-run/references/efficiency-notes.md) | ทำไมแต่ละทางลัดด้าน efficiency ถึงปลอดภัย (ไม่ spawn agent ใหม่ทุก stage, resume แทน respawn ฯลฯ) |

## สิ่งที่ตั้งใจ "ไม่ทำ"

- **kestra-build ไม่รันอะไรเลย** — ไม่เขียนโค้ดจริง ไม่ commit ไม่เรียก skill ใดๆ
- **kestra-run ไม่สร้างเวิร์กโฟลว์เอง** — ถ้าไฟล์ยังไม่มี มันจะบอกตรงๆ แทนที่จะด้นสดสร้างเอง
- **ทั้งสอง skill ไม่ hard-depend กับ skill/agent เฉพาะทางใดๆ** — ชื่อ skill ที่อาจถูกแนะนำใน
  `brief` ของ stage เป็นแค่คำแนะนำเสมอ ("ลองใช้ถ้ามี") ไม่ใช่ข้อบังคับ ทำให้ `workflow.yaml` ที่
  สร้างไว้ย้ายไปเครื่อง/session อื่นที่มี skill set ต่างกันได้และยังทำงานได้ปกติ
