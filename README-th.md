# Claude Code skills

*[Read in English](README.md)*

repo นี้เก็บ Claude Code skill รวมกันเป็นกลุ่มเล็กๆ ตามโฟลเดอร์ repo นี้*คือ* skill ทั้งหมดนี้เอง —
clone แล้วรัน `install.sh` ครั้งเดียวเพื่อติดตั้งทุก skill ในนี้ (ไม่มีตัวเลือกติดตั้งแค่ตัวเดียว —
ติดตั้งทั้งชุดในครั้งเดียว)

## กลุ่ม skill

| กลุ่ม | Skill | ใช้ทำอะไร |
|---|---|---|
| [`workflow/`](workflow/README-th.md) | `kestra-spec`, `kestra-build`, `kestra-run`, `kestra-exam` | ตัวลับ spec + ตัวสร้าง + ตัวรัน "stage machine" แบบล็อก TDD — `kestra-spec` แปลง ticket บน tracker ที่คนตรวจ (vet) แล้ว (โหมด in-chain: สองคอมมิต — ตัว ticket แบบ verbatim แล้วค่อย raise) หรือไอเดียที่เขียนเองที่ลับคมแล้ว (โหมด standalone: คอมมิตเดียว) เป็น `0-spec.md` พร้อมสร้าง (AC เขียนแบบ Given-When-Then/BDD ได้ บวก test seam, เงื่อนไขหยุด, runtime invariants และ reality constraints ของ dependency ภายนอก), `kestra-build` แปลงเป็น `workflow.yaml`/`state.json` แล้ว `kestra-run` รันจริง ตรวจสอบทุกขั้นตอนแบบ mechanical (ไม่ใช้วิจารณญาณของ AI) นอกจากนี้ `kestra-build` ยัง *fold* ชุด ticket ที่ถูกซอยและคนตรวจ (vet) แล้วเข้าไปในเวิร์กโฟลว์ได้ (copy ตัว ticket แบบ verbatim และผูก hash ไว้กับคอมมิต raise) ส่วน `kestra-exam` ซึ่งเป็นแบบ opt-in จะสร้าง exam ที่ผ่านการ red-proof จาก spec เดียวกันนั้น — หนึ่ง check ต่อหนึ่ง acceptance criterion — เพื่อให้การตัดสินงานที่ส่งมอบอ้างจากสิ่งที่ถูกสั่งไว้ ไม่ใช่จากรายงานของ AI เอง |
| [`meta/`](meta/README.md) | `meta-designer`, `meta-dev`, `meta-qa`, `meta-test-review`, `meta-review`, `meta-security`, `meta-devops`, `meta-debug` | 8 skill ตามบทบาทงานส่งมอบ (designer, dev, QA, ตรวจ test double, code review, security, devops, บวก 4-mantra debugging discipline) — เรียกใช้ตัวเดียวโดยตรง chain เอง หรือระบุชื่อใน stage brief ของ `kestra-build` ก็ได้ ส่วนบทบาท spec/plan ที่เคยอยู่กลุ่มนี้ ตอนนี้ `kestra-spec` ทำให้ในตัวแล้ว |
| [`productivity/`](productivity/README.md) | `givename` | ช่วยตั้งชื่อ (ตัวแปร, ไฟล์, branch, commit, โปรเจกต์/skill ใหม่) โดยหา naming convention จริงที่มีอยู่รอบๆ ก่อน |

รายละเอียดเต็มของแต่ละ skill อยู่ใน README ของกลุ่มนั้นๆ — มันทำอะไร ใช้ยังไง และเอกสารอ้างอิง
กลุ่มใหม่ในอนาคตก็จะได้โฟลเดอร์ระดับบนสุดของตัวเองแบบเดียวกัน (ดู "เพิ่ม skill ใหม่" ด้านล่าง)

## การติดตั้ง

Clone repo แล้วรัน `install.sh` เพื่อ copy (หรือ symlink) ทุกโฟลเดอร์ skill ไปยังที่ที่ Claude Code
auto-discover skill ได้ — ไม่ว่าจะแบบ global (`~/.claude/skills/`, ใช้ได้ทุกโปรเจกต์) หรือเฉพาะ
โปรเจกต์เดียว (`<project>/.claude/skills/`)

```bash
git clone <this-repo-url> claude-skills
cd claude-skills

./install.sh                        # ติดตั้งแบบ global — ใช้ได้ทุกโปรเจกต์ (~/.claude/skills/)
./install.sh --project ~/code/app   # ติดตั้งเฉพาะโปรเจกต์เดียว (<path>/.claude/skills/)
./install.sh --link                 # symlink แทนการ copy — `git pull` ที่นี่จะอัปเดตทันที
./install.sh --force                # เขียนทับการติดตั้งเดิม
./install.sh --update               # ดึงโค้ดล่าสุด (git pull ที่นี่) แล้วรีเฟรชการติดตั้ง
./install.sh --uninstall            # ถอนการติดตั้ง (ใส่ flag --project เดียวกับตอนติดตั้ง)
```

แต่ละ skill จะถูกติดตั้งแบบ**แบน (flat)** ตามชื่อโฟลเดอร์ของมันเองใน target skills dir ไม่ว่าจะมา
จากกลุ่มไหนในนี้ — เพราะนั่นคือโครงสร้างที่ Claude Code discover ได้จริง ดังนั้น
`workflow/kestra-build/` จะกลายเป็น `~/.claude/skills/kestra-build/`, `productivity/givename/`
จะกลายเป็น `~/.claude/skills/givename/` และต่อๆ ไปแบบเดียวกัน

### อัปเดตให้เป็นเวอร์ชันล่าสุด

ถ้าติดตั้งด้วย **`--link`** — ไม่ต้องทำอะไรเพิ่ม แค่ `git pull` ใน repo นี้ symlink ก็ชี้มาที่นี่อยู่แล้ว

ถ้าติดตั้งแบบ **copy** (ค่าเริ่มต้น) — รัน `./install.sh --update` (ใส่ `--project <path>` ด้วยถ้า
ติดตั้งแบบเฉพาะโปรเจกต์): มันจะ `git pull` โค้ดล่าสุดใน repo นี้ก่อน (ข้ามขั้นตอนนี้ถ้า repo มีการ
แก้ไขที่ยังไม่ commit เพื่อไม่ให้ทับงานที่ทำค้างไว้) แล้วค่อย copy ทับการติดตั้งเดิม — ไม่ต้องใช้
`--force` หรือถอนการติดตั้งก่อน

รีสตาร์ท Claude Code (หรือเริ่ม session ใหม่) หลังจากนั้นเพื่อให้ skill ที่อัปเดตถูกโหลด ไม่มี
dependency ภายนอกที่ต้องติดตั้งเพิ่ม — ทุกสคริปต์ใน repo ต้องการแค่ `python3` เปล่าๆ ไม่ต้องมี
PyYAML หรือ package ภายนอกใดๆ ทั้งสคริปต์ dry-run ของ `kestra-build` (`validate_workflow.py`) และ
คู่ `validate_spec.py` + `requirement_surface.py` ที่ `kestra-spec` รันกับ `0-spec.md` ของตัวเอง
ก่อนจะ commit การ raise สคริปต์สี่ตัวของ `kestra-exam` กับ exam harness ที่มัน copy เข้าไปในทุก exam
ก็ใช้แค่ stdlib เหมือนกัน ส่วน skill อื่นไม่ต้องมี dependency อะไรเลย

## เพิ่ม skill ใหม่

แต่ละกลุ่มคือโฟลเดอร์ระดับบนสุดที่มี skill directory อยู่ข้างใน (`<กลุ่ม>/<ชื่อ skill>/SKILL.md`)
ถ้าจะเพิ่ม skill ใหม่ในกลุ่มที่มีอยู่แล้ว วางไว้ในโฟลเดอร์นั้นแล้วเพิ่ม path (เช่น
`productivity/new-skill-name`) ลงใน array `SKILLS` ใน `install.sh` — สคริปต์จะติดตั้งแต่ละรายการ
แบบแบนตาม basename ของมัน ดังนั้นโฟลเดอร์กลุ่มมีไว้จัดระเบียบ repo นี้เท่านั้น ไม่ได้เป็นส่วนหนึ่ง
ของ layout ที่ติดตั้งจริง ถ้าจะสร้างกลุ่มใหม่ ก็แค่สร้างโฟลเดอร์ระดับบนสุดใหม่แล้วทำตาม pattern
เดียวกัน

## สัญญาอนุญาต

ดูที่ [LICENSE](LICENSE)
