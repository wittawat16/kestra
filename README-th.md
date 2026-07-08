# Claude Code skills

*[Read in English](README.md)*

repo นี้เก็บ Claude Code skill รวมกันเป็นกลุ่มเล็กๆ ตามโฟลเดอร์ repo นี้*คือ* skill ทั้งหมดนี้เอง —
clone แล้วรัน `install.sh` ครั้งเดียวเพื่อติดตั้งทุก skill ในนี้ (ไม่มีตัวเลือกติดตั้งแค่ตัวเดียว —
ติดตั้งทั้งชุดในครั้งเดียว)

## กลุ่ม skill

| กลุ่ม | Skill | ใช้ทำอะไร |
|---|---|---|
| [`workflow/`](workflow/README-th.md) | `kestra-build`, `kestra-run` | ตัวสร้าง + ตัวรัน "stage machine" แบบล็อก TDD — แปลง spec ของฟีเจอร์เป็น `workflow.yaml`/`state.json` แล้วรันจริง ตรวจสอบทุกขั้นตอนแบบ mechanical (ไม่ใช้วิจารณญาณของ AI) |
| [`meta/`](meta/README.md) | `meta-pm`, `meta-ba`, `meta-designer`, `meta-sa`, `meta-architect`, `meta-dev`, `meta-qa`, `meta-review`, `meta-security`, `meta-devops` | 10 skill ตามบทบาทสำหรับ spec→plan→build→review (PM, BA, designer, solution architect, architect, dev, QA, review, security, devops) — เรียกใช้ตัวเดียวโดยตรง หรือ chain เองก็ได้ ไม่มี orchestrator ตายตัว |
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
dependency ภายนอกที่ต้องติดตั้งเพิ่ม — สคริปต์ dry-run ของ `kestra-build` (`validate_workflow.py`)
ต้องการแค่ `python3` เปล่าๆ ไม่ต้องมี PyYAML หรือ package ภายนอกใดๆ ส่วน skill อื่นไม่ต้องมี
dependency อะไรเลย

## เพิ่ม skill ใหม่

แต่ละกลุ่มคือโฟลเดอร์ระดับบนสุดที่มี skill directory อยู่ข้างใน (`<กลุ่ม>/<ชื่อ skill>/SKILL.md`)
ถ้าจะเพิ่ม skill ใหม่ในกลุ่มที่มีอยู่แล้ว วางไว้ในโฟลเดอร์นั้นแล้วเพิ่ม path (เช่น
`productivity/new-skill-name`) ลงใน array `SKILLS` ใน `install.sh` — สคริปต์จะติดตั้งแต่ละรายการ
แบบแบนตาม basename ของมัน ดังนั้นโฟลเดอร์กลุ่มมีไว้จัดระเบียบ repo นี้เท่านั้น ไม่ได้เป็นส่วนหนึ่ง
ของ layout ที่ติดตั้งจริง ถ้าจะสร้างกลุ่มใหม่ ก็แค่สร้างโฟลเดอร์ระดับบนสุดใหม่แล้วทำตาม pattern
เดียวกัน

## สัญญาอนุญาต

ดูที่ [LICENSE](LICENSE)
