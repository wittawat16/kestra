# workflow/ — kestra-spec, kestra-build, kestra-run & kestra-exam

*[Read in English](README.md)*

สี่ skill นี้ทำงานร่วมกันเป็น **ตัวลับ spec + ตัวสร้าง + ตัวรัน** สำหรับสร้างและรัน "stage machine"
ที่บังคับ TDD จริงๆ (ไม่ใช่แค่ขอให้ AI เขียนเทสต์ก่อนแบบสุภาพๆ) มันจะ freeze เทสต์เมื่อเขียนเสร็จแล้ว
จำกัดว่าแต่ละ stage แก้ไฟล์ไหนได้บ้าง และ commit ทีละ stage เพื่อให้ rollback หรือ resume ได้เสมอ

```
ticket บน tracker ที่คน vet แล้ว (in-chain)  ·  หรือไอเดียที่ลับคมจาก /grilling (standalone)
                                              (/wayfinder ก่อน ถ้างานใหญ่เกินหนึ่ง session)
   │
   ▼
┌─────────────┐   in-chain: เช็ค vet → commit ตัว ticket แบบ verbatim → raise เป็น 0-spec.md
│ kestra-spec  │   ในคอมมิตที่สอง · standalone: ซักถามหนึ่งรอบ คอมมิตเดียว
└──────┬──────┘   ทั้งสองโหมด: AC ที่ทดสอบได้, flag needs_*, External Interface, Exit Criteria,
       │          business rules, design notes, การสำรวจโค้ดจริงที่ verify แล้ว — ในรอบเดียว
       │
       ├───────────▶ kestra-exam (opt-in, เฉพาะเมื่อ mode ด้านล่างเป็น `full`): สร้าง check
       │             หนึ่งตัวต่อหนึ่ง AC จาก 0-spec.md แล้ว red-proof ก่อนจะมีโค้ดใดๆ
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

skill เหล่านี้ไม่ได้ผูกติดกับ skill อื่นแบบ hard dependency — ถ้า brief ของ stage ไหนอยากแนะนำ
skill เฉพาะทาง (เช่น skill สำหรับ implement, skill สำหรับ review) มันจะปรากฏแค่เป็น "คำแนะนำ"
ในเนื้อหา brief เท่านั้น ตัวที่ถูก spawn มาทำงาน stage นั้นยังทำงานได้ปกติแม้ skill นั้นจะไม่ได้ติดตั้งไว้ ส่วน `kestra-exam` คือ
skill ตัวที่สี่ในโฟลเดอร์นี้ซึ่งเป็นแบบ opt-in: มันอ่านจาก mode ที่ `kestra-build` บันทึกไว้แล้ว
(`full` ⇒ ทำ exam, `lite` ⇒ ตั้งใจไม่ทำ) และอ้างถึงอีกสามตัวในฐานะคำแนะนำเท่านั้น

---

## kestra-spec — ตัวลับ spec

**ที่อยู่:** [`kestra-spec/`](kestra-spec/) · รายละเอียดเพิ่มเติม: [`kestra-spec/SKILL.md`](kestra-spec/SKILL.md)

### มันทำอะไร

สร้าง `0-spec.md` ไฟล์เดียวในรอบเดียว: acceptance criteria ที่ทดสอบได้, error state ที่ชัดเจน,
flag `needs_ba`/`needs_ui`/`needs_sa`/`needs_devops` ที่ `kestra-build` จะอ่านต่อ, test seam
(**External Interface**), เงื่อนไขหยุด (**Exit Criteria**), business rules (ถ้า `needs_ba: true`),
design notes (ถ้า `needs_ui: true`), การตัดสินใจด้าน solution architecture (ถ้า `needs_sa: true`),
และการสำรวจโค้ดจริงที่ path ทุกอันถูก verify ว่ามีจริง

ในขณะที่กลุ่ม `meta/` แบ่งงานชุดเดียวกันนี้ออกเป็นห้า skill ห้าไฟล์ `kestra-spec` ทำเป็นรอบเดียว
ต่อเนื่อง ไฟล์เดียว — เพื่อไม่ต้องจำว่าต้อง chain ห้า skill เอง และ stage agent ของ `kestra-build`
ก็ไม่ต้องเดาช่องว่างที่หลุดตอน handoff

### สองโหมด input ตัดสินแบบ mechanical

เป็นโหมด **in-chain** ก็ต่อเมื่อคำสั่งที่เรียกใช้ระบุ ticket บน tracker มาด้วย (เป็น URL หรือ `#N`
บวกชื่อ repo) นอกนั้นคือ **standalone** มันจะไม่ไปไล่หา ticket ที่ไม่มีใครระบุมาเด็ดขาด — การที่ไม่มี
ticket ถูกระบุ*คือ*สัญญาณของ standalone และการเดาเอาเองคือช่องทางที่ intent ซึ่งยังไม่ถูก vet จะหลุดเข้ามา

| | In-chain | Standalone |
|---|---|---|
| intent มาจาก | ticket ที่ระบุ ซึ่งคน vet แล้ว | ไอเดียที่เขียนเองหรือผลจาก `/grilling` บวกการซักถามใน session นี้ |
| vetted gate | บังคับ — ไม่มี vet ไม่ทำงาน | ไม่มี |
| จำนวนคอมมิต | สอง: ตัว ticket แบบ verbatim แล้วค่อย raise | หนึ่ง: การ raise |
| บรรทัด `> Spec-ticket:` / `> Vetted:` ใน preamble | เขียน | ไม่เขียนเด็ดขาด |
| `needs_ba` ที่ ticket เงียบเรื่อง intent | เด้งกลับต้นทาง (bounce) | ถามคนตรงนั้นเลย แล้วอ้างอิงคำตอบเป็น `Q<n>` |
| validator ตอนจบรอบ | การเช็ค template ห้าข้อเป็น `FAIL` | ห้าข้อเดียวกันขึ้น `WARN` |

**standalone เป็นเส้นทางชั้นหนึ่ง ไม่ใช่เส้นทางที่ด้อยกว่า** vetted gate มีอยู่เพราะในโหมด in-chain
ไม่มีใครเฝ้าดูจังหวะที่ intent ถูกคิดขึ้นมาเอง ส่วน standalone มีมนุษย์อยู่ในลูปโดยธรรมชาติ — เขาเป็น
คนเรียกใช้เอง ใน session นี้ และเป็นคนตอบคำถามเอง พฤติกรรมเดียวกัน แต่หลักประกันคนละแบบ standalone
ยังเก็บการซักถามไว้ครบ: คำขอหยาบๆ ("เพิ่ม CSV export") ยังต้องผ่านการซักถามสั้นๆ เรื่องขอบเขต
error state และจุดคลุมเครือก่อนจะเขียนอะไรลงไป

### vetted gate และการ raise แบบสองคอมมิต (in-chain)

`kestra-spec` เป็น **read-only บน tracker** — ไม่คอมเมนต์ ไม่ติด label ไม่แก้ ไม่ปิด ticket ดังนั้น
มันอนุมัติ input ของตัวเองไม่ได้ สัญญาณ vet คือคอมเมนต์บน ticket ที่บรรทัดแรกเป็น
`VETTED-FOR-KESTRA: <sha256 ของ body ของ ticket ณ ตอน vet>` ซึ่งคนสร้างขึ้นครั้งเดียวแล้ววางไว้
คอมเมนต์ล่าสุดที่ match ชนะ และ hash ต้องตรงกับ hash ของ body ปัจจุบัน การผูกการอนุมัติเข้ากับ
content hash คือสิ่งที่ทำให้มันแปลว่า *vet **ข้อความชุดนี้*** — body ที่ถูกแก้หลัง vet จะถูกจับได้
และ ticket บางๆ จะฟอกตัวเองผ่าน URL ที่อ้างอิงได้ไม่ได้ ข้อจำกัดที่ระบุไว้ตรงๆ: token ก็โพสต์
คอมเมนต์นั้นได้ มันจึงไม่ได้พิสูจน์ว่ามนุษย์เป็นคนพิมพ์ สิ่งที่ได้จริงคือ `kestra-spec` ไม่เคยเขียนมันเอง
การอนุมัติระบุข้อความที่แน่นอน และตัว artifact มองเห็นได้ มีชื่อคน มีวันที่

ไม่มี vet หรือ vet เก่าไม่ตรง → หยุดก่อนเริ่มทำงาน ไม่ commit อะไรเลย และพิมพ์บรรทัดให้คนเอาไปวาง
เป็นคอมเมนต์ ถ้าตัว ticket เองบางหรือยังไม่มี `to-spec` คือเครื่องมือที่ *แนะนำ* ให้ใช้เขียน — เป็นแค่
คำแนะนำ ไม่ใช่ข้อบังคับ กติกาเดียวกับการอ้างถึง skill อื่นทุกที่ในเอกสารนี้

เมื่อมี vet แล้ว มันจะทำ commit สองอันพอดี โดยห้ามมีอะไรถูก commit คั่นกลาง:

| คอมมิต | subject | บรรจุอะไร |
|---|---|---|
| 1 | `spec(<feature-id>): materialize vetted ticket verbatim` | body ของ ticket เขียนลง `0-spec.md` แบบไม่แก้อะไรเลย บวกสำเนา `requirement_surface.py` และ `validate_spec.py` ของ run นี้เอง ข้อความคอมมิตบันทึก `Spec-ticket: <url>` และ `Ticket-body-sha256: <hex>` |
| 2 | `spec(<feature-id>): raise vetted ticket into 0-spec.md` | แตะ path เดียวเป๊ะๆ — `0-spec.md` ที่ raise แล้วเขียนทับ body แบบ verbatim ทำให้การ raise เป็น `git diff` อันเดียวจริงๆ ข้อความคอมมิตบันทึก `Spec-ticket:` และ `Vetted-by:` |

`tr -d '\r'` คือการ normalize อย่างเดียวที่ประกาศไว้ (GitHub คืน body ที่เขียนผ่านเว็บมาเป็น CRLF)
นอกนั้นไม่ normalize อะไรอีก เพราะยิ่งทำเพิ่มยิ่งทำให้คำว่า "verbatim" ต่อรองได้ หลังคอมมิตที่ 2
มันจะดึง ticket มาใหม่แล้ว `diff` เทียบกับไฟล์ในคอมมิตที่ 1 — ถ้า diff ไม่ว่างคือ **หยุดทันที ไม่
handoff** และมีทางแก้ที่ซื่อสัตย์แค่สองทาง: materialize ใหม่ตั้งแต่ต้น หรือ bounce เพราะ ticket
เปลี่ยนจริงระหว่างรอบ ส่วนการแก้ไฟล์ verbatim ที่ commit ไปแล้ว หรือ amend คอมมิตที่ 1 นั้น **ห้าม**
— นั่นคือ "แก้เทสต์ให้เข้าข้างโค้ดที่พัง" ในคราบของ spec ส่วนคำถามว่าคอมมิตไหนคือ *ตัว* raise ใช้
กติกา match ได้อันเดียวเป๊ะ (การ raise ใหม่ไปแทนที่อันเดิม ไม่ใช่ซ้อนทับกัน) ดูรายละเอียดที่
[`kestra-spec/references/chain-provenance.md`](kestra-spec/references/chain-provenance.md)

### Bounce — ความเงียบเรื่อง intent เด้งกลับต้นทาง

ในโหมด in-chain ถ้า ticket ไม่ได้บอกว่า *ผลลัพธ์ไหนถูก* สำหรับแขนงที่ฟีเจอร์นี้ต้องเลือก
`kestra-spec` จะ **bounce** แทนที่จะเขียน business rule ขึ้นมาเอง: มันทำทั้งสองคอมมิตให้จบ (งานไม่หาย
และตรวจสอบย้อนได้) ตั้งบรรทัด status เป็น `BLOCKED_ON_INTENT` เขียนรายการ `BOUNCE-<n>` รูปแบบตายตัว
ไว้ใต้ **Open Items** ระบุแขนงที่ยังไม่ตัดสิน AC ที่ถูกบล็อก และใครเป็นคนตัดสิน — แล้วไม่ handoff ให้
`kestra-build`

ตัวแยกแยะนี้แคบโดยตั้งใจ การขาดตัวเลข threshold ชื่อ ข้อความ copy หรือชื่อไฟล์ **ไม่ใช่** bounce:
เลือกค่า default ที่สมเหตุสมผล ทำเครื่องหมายบรรทัดนั้นว่า `⚠ inferred` บันทึกเป็น `OI-n` แบบไม่บล็อก
แล้วทำต่อ มีเฉพาะ *แขนง* ที่ยังไม่ถูกตัดสินจริงๆ เท่านั้นที่หยุดรอบการทำงาน ส่วนการ "ติดธงไว้แล้วทำต่อ"
ไม่ใช่ทางเลือก เพราะ workflow ค่าเริ่มต้นมี `human_approval` stage เป็นศูนย์ ธงนั้นจึงไม่มีใครอ่าน และ
build จะเดินหน้าต่อบน intent ที่ถูกคิดขึ้นเอง

### กติกา provenance

ทุกบรรทัดที่เป็น intent ซึ่งรอบการลับ spec เพิ่มเข้ามา ต้องอ้างอิงแหล่งที่มา หรือไม่ก็ติด
`⚠ inferred` — "บรรทัด intent" คือบรรทัดใดก็ตามที่ยืนยันว่าระบบต้องทำอะไร (bullet ของ FR, edge case,
แถวใน invariant, AC, แถวใน **AC Coverage Map**, operation ใน External Interface) แหล่งที่มาที่ใช้ได้
คือ `US-n` (user story), `ID§x` (Implementation Decisions ของ ticket), `TD`/`FN`/`OOS`/`PS`,
`IDEA§x` / `Q<n>` (โหมด standalone: หัวข้อในไอเดีย หรือคำตอบจากการซักถามใน session นี้) หรือ
`verified:<probe>` สำหรับสิ่งที่ยืนยันด้วยการรันโค้ดจริง บรรทัดที่ไม่มีทั้งแหล่งที่มาและ `⚠ inferred`
คือ defect ไม่ใช่แค่เรื่องสไตล์ — คอลัมน์ `Source` ที่เพิ่มเข้ามาใน AC Coverage Map ถ้าไม่มีกติกานี้
หนุนหลัง ก็เป็นแค่คอลัมน์ที่เขียวแบบโกหก

### การเช็คเชิงกลไกตอนจบรอบ

ก่อนจะ commit การ raise `kestra-spec` จะรัน `validate_spec.py` และ `requirement_surface.py` กับ
`0-spec.md` ของตัวเอง โดยใช้สำเนาที่มันเขียนไว้ในโฟลเดอร์ของ run นั้น เหตุผล: `spec-review` ทำงาน
หลังจาก `kestra-build` ยุบ spec เป็น stage แล้วเท่านั้น และโหมด `lite` ก็ยุบ `spec-review` เข้าไปใน
`generate-tests` อีกที ดังนั้น run แบบ `lite` จะเรียก validator ศูนย์ครั้ง และทุกอย่างที่ต่อยอดจากการ
raise ก็จะถูกสร้างบน surface ที่ยังไม่ถูกตรวจ นี่คือจุดตรวจ**เพิ่ม**ที่มาก่อน ไม่ได้มาแทน stage
`spec-review`

ข้อบังคับด้าน template ห้าข้อถูกเช็คแบบ **มีเงื่อนไข** โดยดูจาก chain marker (บรรทัด
`> Spec-ticket:` บรรทัดเดียวใน preamble ซึ่งเขียนโดยคอมมิต raise เท่านั้น ไม่มีที่อื่นเขียน): ต้องมี
คอลัมน์ `Source` ใน AC Coverage Map, ต้องมีหัวข้อ `## External Interface` ที่มีเนื้อหาจริง, ต้องมี
mode-prediction fact บรรทัดเดียวเป๊ะ, ต้องมีหัวข้อ `## Exit Criteria` พร้อมบรรทัด stop condition
กับ `progress:` fragment และต้องผ่าน delimiter precondition มี marker ⇒ `FAIL`,
ไม่มี ⇒ `WARN` เพราะ spec ที่มี marker คือ spec ที่ skill ของ repo นี้เองสร้างจาก ticket ที่ vet แล้ว
template ของมันจึงเป็นสัญญา ส่วน spec ที่ไม่มี marker คือ spec ที่เขียนมือ เป็น standalone หรือมาจาก
ที่อื่น การขาดหัวข้อเดียวกันจึงไม่ได้พิสูจน์อะไร — และการเช็คเดิมทุกข้อที่มีอยู่ก่อนแล้วทำงานเหมือนกัน
ทั้งสองโหมด ถ้าหาสำเนาสคริปต์ไม่เจอเลยสักที่ มันจะพิมพ์ `WARN` หนึ่งอัน ตรวจ checklist ด้วยตัวเอง
แล้วทำต่อ เพราะ `kestra-spec` ต้องไม่ hard-depend กับการที่ `kestra-build` ถูกติดตั้งไว้ แต่ต้องคัดลอก
**ทั้งสองสคริปต์ หรือไม่ก็ไม่ต้องคัดลอกเลย**: ถ้ามี `validate_spec.py` แต่ไม่มี `requirement_surface.py`
วางข้างกัน การเช็ค delimiter จะรันไม่ได้เลย และ *รันไม่ได้* ก็รายงานผ่านเงื่อนไขเดียวกัน — มี marker ⇒
`FAIL`, ไม่มี ⇒ `WARN` การที่เช็คไม่ได้รัน ไม่เท่ากับผ่าน

### ก่อนหน้านี้ใช้อะไร: `/grilling` และ `/wayfinder` เมื่องานใหญ่กว่านั้น

ในโหมด in-chain ต้นทางคือตัว ticket ที่ vet แล้วนั่นเอง ซึ่งเขียนด้วย `to-spec` ได้ถ้ามี (เป็นคำแนะนำ
ไม่ใช่ข้อบังคับ) ส่วนโหมด standalone `kestra-spec` คาดหวังว่าความคลุมเครือถูกกำจัดไปเกือบหมดแล้ว —
มันอ่านสิ่งที่ตกลงกันไว้ ไม่รื้อใหม่ มีสอง skill ต้นทางที่พาไปถึงจุดนั้น และทั้งสองใช้ **ซ้อนกัน**
ไม่ใช่แทนกัน

* **`/grilling`** — สัมภาษณ์ต่อเนื่องครั้งเดียว ทีละคำถาม ไล่ลงไปตาม design tree แก้ dependency
  ระหว่างการตัดสินใจไปทีละอัน อันนี้คือทางเข้าปกติ เพราะ `0-spec.md` หนึ่งไฟล์อธิบายหนึ่งฟีเจอร์
  ซึ่งปกติเป็นปริมาณการตัดสินใจของหนึ่ง session พอดี
* **`/wayfinder`** — สำหรับงานที่ *ใหญ่เกินหนึ่ง session และยังมีหมอกบังอยู่* คือยังบอกไม่ได้ด้วยซ้ำ
  ว่ามีกี่ฟีเจอร์ หรือการตัดสินใจไหนบล็อกอันไหน มันไม่ตอบคำถามเอง แต่วาดคำถามเหล่านั้นเป็นแผนที่
  ของ ticket บน issue tracker แล้วทยอยเคลียร์ทีละใบข้าม session — และ `/grilling` เป็นหนึ่งใน
  ticket สี่ประเภทของมัน แถมเป็นประเภท default ด้วย ดังนั้นการใช้ wayfinder ไม่ใช่การข้าม grilling
  แต่คือการจัดคิว grilling หลายรอบ

wayfinder ระบุปลายทางของแต่ละงานเอง และหนึ่งในรูปแบบที่มันบอกไว้คือ "spec ที่ส่งต่อไปทำต่อได้" —
ซึ่งคือจุดเชื่อมเข้า `kestra-spec` พอดี หลักคร่าวๆ: ถ้าบอกได้แล้วว่าฟีเจอร์นี้ *คืออะไร* เหลือแค่
ลับรายละเอียด → grill แล้วเข้ามาเลย แต่ถ้ายังไม่รู้ว่ามันจะกลายเป็นกี่สเปก → ชาร์ตก่อน แล้วค่อยเอา
แต่ละชิ้นที่ตกผลึกแล้วเข้ามาทีละอัน

### Runtime invariants และ reality constraints

เทสต์ที่ผ่านพิสูจน์ได้แค่เคสที่มีคนคิดถึงเท่านั้น เพราะเทสต์ถูกสร้างจาก spec และ spec คือที่ที่คำว่า
"คิดถึงแล้ว" ถูกตรึงไว้ สองหัวข้อนี้มีไว้ครอบส่วนที่เหลือ

* **Runtime Invariants** — เงื่อนไขที่ต้องเป็นจริง *ทุกครั้งที่ระบบทำงาน* บังคับใช้ตอนรันจริง
  ไม่ใช่ตรวจครั้งเดียวในเทสต์ แต่ละข้อระบุ: เงื่อนไขคืออะไร, ตรวจจับตอนรันยังไง, และเกิดอะไรขึ้น
  เมื่อถูกละเมิด — หยุด, ปฏิเสธ, หรือแจ้งเตือน ส่วนการแค่ log แล้วทำงานต่อไม่นับ เพราะนั่นคือ
  พฤติกรรมที่หัวข้อนี้มีไว้ป้องกันโดยตรง
* **Reality Constraints** — โลกภายนอกทำอะไรจริงบ้าง ซึ่งคือมาตรฐานที่ test double จะถูกตัดสิน
  เทียบกับมัน: ลำดับการเรียกที่ dependency บังคับ, type ที่มันคืนมาจริง, และ (คอลัมน์ที่คนมักเว้น)
  ความครบถ้วนหรือความสอดคล้องที่มัน **ไม่** รับประกัน; คู่ของ code path ที่ต้องให้ผลตรงกัน เพราะ
  parity check เขียนไม่ได้ถ้าไม่มีใครประกาศคู่นั้นไว้; และ input ที่ไม่ deterministic — clock,
  randomness, timezone, network, filesystem, environment — ข้อไหนต้อง pin ในเทสต์ ข้อไหนปล่อยได้

ที่มาของความเสี่ยงเหล่านี้: [`kestra-build/references/test-quality-taxonomy-research.md`](kestra-build/references/test-quality-taxonomy-research.md)
เชื่อมโยงกับวรรณกรรมด้าน testing ที่มีอยู่จริง (hermetic tests, test-double fidelity,
consumer-driven contract testing, characterization/golden-master) — เป็นจุดตั้งต้นที่มีที่มา
**ไม่ใช่รายการที่ครบถ้วน** data pipeline เจอ schema drift เป็นหลัก เว็บแอปเจอเรื่อง authorization
ซึ่งทั้งคู่ไม่มีอยู่ในนั้น

### Acceptance criteria แบบ Given-When-Then / BDD

AC ที่บรรยาย *พฤติกรรมภายใต้เงื่อนไข* (ไม่ใช่แค่ threshold หรือรูปร่างข้อมูล) เขียนเป็น
Given-When-Then แทน prose ได้ — สำคัญที่สุดตอน `needs_ba: true` เพราะบังคับให้แต่ละแขนงของ
business rule กลายเป็นบรรทัดที่ชัดเจน แทนที่จะซ่อนอยู่ใน requirement บรรทัดเดียว stage
`generate-tests` ของ `kestra-build` ก็ทำแบบเดียวกัน: ถ้า AC ของ spec เขียนเป็น Given-When-Then
เทสต์ที่ freeze จะเขียนเป็น BDD scenario (Gherkin หรือ `describe`/`it` ที่จัดโครงเป็น
Given/When/Then) ที่ map 1:1 กับมัน — เป็นแค่ทางเลือกด้าน format เท่านั้น `freeze_after` และ
test-hash invariant ทำงานเหมือนเดิมทุกประการ ดูตัวอย่างจริงได้ที่
[`workflow/runs/order-cancellation-refund/`](runs/order-cancellation-refund/) — spec ตัวนั้นตั้งใจ
คงรูปแบบ template *ก่อน*มีสองโหมดไว้ เพราะมันคือตัวอย่างของ spec แบบ standalone/มาจากที่อื่นที่ไม่มี
marker และการเช็คแบบมีเงื่อนไขทั้งห้าข้อจะขึ้น `WARN` กับมัน ซึ่งคือสัญญาของโหมด standalone ที่สาธิต
บนไฟล์จริง ส่วน template ปัจจุบันอยู่ใน [`kestra-spec/SKILL.md`](kestra-spec/SKILL.md)

**มันไม่เขียนโค้ดและไม่รัน stage ใดๆ** — แค่เขียน `0-spec.md`, commit (สองคอมมิตในโหมด in-chain,
คอมมิตเดียวในโหมด standalone) แล้วหยุด และเป็น read-only บน tracker ตลอดทั้งรอบ จากนั้นส่งต่อให้
`kestra-build` — ยกเว้นบรรทัด status เป็น `BLOCKED_ON_INTENT` กรณีนั้นให้ส่งกลับต้นทาง ไปหาคนที่เป็น
เจ้าของกติกาที่ ticket ยังไม่ได้ตัดสิน

### ตัวอย่างการใช้งาน

```
"raise this vetted ticket into 0-spec.md: https://github.com/acme/app/issues/123"
"materialize issue #123 into a spec"
"write the spec for kestra-build for CSV export"
"turn this idea into 0-spec.md"
```

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

1. อ่าน spec หรือทำให้ชัดเจนขึ้นจนกว่าจะมี acceptance criteria ที่ชัด มี input สามรูปแบบ ตัดสินแบบ
   mechanical ก่อนทำอะไรทั้งสิ้น: run folder ที่มี `0-spec.md` **บวกกับ** ชุด ticket ที่ถูกซอยและถูก
   ระบุชื่อมาให้ (*sliced fold* — เป็น ref ของ GitHub หรือไดเรกทอรีของ ticket ที่เป็นไฟล์ในเครื่อง);
   มี `0-spec.md` อย่างเดียว (*monolithic fold* เหมือนเดิม ไม่เปลี่ยน); หรือ spec ที่มี chain marker
   แต่ไม่ได้ระบุชุด ticket มา ซึ่งจะถาม **ครั้งเดียว** และ **ไม่ค้นหา ticket ที่ไม่มีใครระบุชื่อมาใน
   tracker เด็ดขาด** (การเดาชุด ticket คือช่องทางที่ scope ที่ยังไม่ถูก vet เล็ดลอดเข้ามา) ในแบบ
   sliced fold ทุก ticket จะถูก copy แบบ verbatim ไปที่ `<run>/tickets/<id>.md` (`tr -d '\r'` เท่านั้น
   ไม่มีอย่างอื่น — normalization ตัวเดียวกับที่ `kestra-spec` ใช้ เพื่อให้คำว่า "verbatim" หมายถึงสิ่ง
   เดียวกันทั้งสองปลายของ chain), ฝังไว้ใน brief ของ stage ระหว่าง delimiter ที่มี sha256 และถูกลง
   รายการใน map `tickets:` ที่ผูกกับคอมมิต raise ส่วน Source label ของแต่ละ AC ที่ถูกซอยจะถูก resolve
   จาก `## AC Coverage Map` ของ spec เอง ไม่ใช่ไปตรวจกับคำศัพท์อีกชุด และ AC ที่ไม่ match แถวไหนใน map
   เลยจะทำให้การ fold ถูกปฏิเสธ นี่คือจุดเดียวในทั้งรอบการทำงานที่มีการอ่าน tracker
2. กรอกตาราง flag แบบ mechanical (`needs_ui`, `needs_ba`, `needs_sa`, `needs_devops`, ...) เพื่อ
   ตัดสินว่าต้องมี stage ไหนบ้าง (เช่น `needs_ui: true` → ต้องเพิ่ม stage `design` ก่อน
   `generate-tests`)
3. เลือก **mode** — `lite` หรือ `full` — ก่อนจะสร้าง stage ใดๆ โดยอ่านจากตารางเงื่อนไขตายตัว ไม่ใช่
   จากความรู้สึกว่างานนี้ควรเข้มแค่ไหน ข้อใดข้อหนึ่งต่อไปนี้บังคับให้เป็น `full`: มี component
   อิสระตั้งแต่ 2 ตัวขึ้นไป, Reality Constraints ระบุ external dependency หรือคู่ path ที่ต้องให้ผล
   ตรงกัน, `needs_devops: true`, มี runtime invariant ที่ถ้าถูกละเมิดแล้วจะเงียบใน production, หรือ
   ผู้ใช้ขอมาเอง ถ้าไม่เข้าข้อไหนเลย → `lite` และถ้าก้ำกึ่งให้เลือก `full` เพราะ `lite` ที่ผิดคือ
   ข้อผิดพลาดที่หลุดไป ส่วน `full` ที่ผิดแค่ทำให้รันช้าลง
   `lite` คือ `generate-tests → freeze-tests (🔒) → implement → {verify, review} → done` — เครื่อง
   ตัวเดิมที่ตัดเฉพาะ stage ที่ไม่มีอะไรให้ตรวจบน spec นี้ **ไม่ใช่การตัดกลไกกันพลาด**: write-scope
   allowlist, การ freeze, commit-per-stage และ `review` ยังอยู่ครบ สิ่งที่หายไปคือ `test-review` กับ
   `deploy-readiness` (ซึ่งเงื่อนไขของ `lite` เองรับประกันแล้วว่าไม่มีอะไรให้ทั้งคู่ตรวจ) ส่วน
   `spec-review` ถูกยุบเข้าไปใน brief ของ `generate-tests` ไม่ได้หายไป โดยทั่วไปเหลือ stage ที่ต้อง
   spawn subagent 3 ตัว แทนที่จะเป็น 6-7 ตัว mode ที่เลือกถูกบันทึกเป็น `mode: lite | full` ใน
   `workflow.yaml` — เป็นบันทึกว่าทำไม stage นั้นถึงไม่อยู่ ไม่ใช่สวิตช์ที่มีอะไรอ่านตอนรัน
4. สร้างรายการ stage จาก spec จริง ไม่ใช่ template ตายตัว โครงของ `full` คือ:
   `spec-review → generate-tests → [test-review] → freeze-tests (🔒) → implement[-per-component] →
   {verify, review} → done`
   - การเขียนเทสต์กับการ freeze เป็น **คนละ stage** เพราะ freeze มีไว้กัน *implementation* แก้เทสต์
     ให้เข้าข้างโค้ดที่พัง แต่ตอนเขียนเทสต์เสร็จใหม่ๆ ยังไม่มี implementation อยู่เลย — ล็อกตอนนั้น
     จึงไม่ได้ป้องกันอะไร แต่เสียโอกาสเดียวที่จะแก้ข้อผิดพลาด *ในตัวเทสต์เอง* แบบถูกๆ ไป ก่อนล็อก
     มันคือ retry แบบมีขอบเขต หลังล็อกทางเดียวที่ทำได้คือ `reworking` ซึ่งคือจุดหยุดที่ต้องใช้คนเสมอ
   - `test-review` อยู่ในช่วงนั้น และจะถูกสร้าง **เฉพาะเมื่อ Reality Constraints ของ spec บอกว่า
     เทสต์จะมี test double** — คือมี external dependency หรือมีคู่ path ที่ต้องให้ผลตรงกัน ฟีเจอร์ที่
     ไม่ได้ fake อะไรเลยเกิดข้อผิดพลาดกลุ่มนี้ไม่ได้ การไม่ใส่จึงไม่ใช่การลดคุณภาพ มันตรวจตามตาราง
     ความเสี่ยง 6 แถว (ลำดับการเรียก, ความสมจริงของ response, type drift, path parity, การ mock
     logic ของตัวเอง, non-determinism) ไม่ได้เป็นเจ้าของไฟล์ไหน และสั่งแก้ย้อนกลับไปที่
     `generate-tests` ด้วยกลไกเดียวกับที่ `review` สั่งกลับไป `implement-*`
   - `spec-review` เป็น gate จริง ไม่ใช่พิธีกรรม — มันตรวจ runtime invariants และ reality
     constraints ของ spec ว่ามีช่องโหว่หรือขัดแย้งกันเองไหม แล้วเขียน verdict artifact แบบเดียวกับ
     `review` เป็นจุดที่ถูกที่สุดในไฟล์ทั้งหมดสำหรับจับข้อผิดพลาด: แก้เอกสารใบเดียว เทียบกับการ
     `reworking` หลังจาก freeze เทสต์ไปแล้ว
   - component ที่เป็นอิสระต่อกัน (เช่น backend/frontend) จะเป็น stage พี่น้องกัน ไม่ใช่ chain
     เพื่อให้ kestra-run รันขนานกันได้จริง
   - `verify` กับ `review` เป็นพี่น้องกันเสมอ (ทั้งคู่ `depends_on` stage implement โดยตรง)
   - ค่าเริ่มต้นมี `human_approval` stage เป็น **ศูนย์** — จุดเดียวที่มนุษย์เข้ามาเกี่ยวข้องเสมอคือ
     `fixing → reworking` (ดู "Default HITL posture" ใน `references/design-principles.md`)
   - `review` เป็น stage บังคับเสมอ (มันจับปัญหา correctness/security ที่เทสต์อย่างเดียวจับไม่ได้)
   - ถ้า spec เกี่ยวข้องกับเรื่อง deployment (env vars, migration, feature flags) จะเพิ่ม stage
     `deploy-readiness`
   - จบด้วย stage `done` แบบ mechanical (เขียนสรุปแล้วหยุด — ไม่ใช่ `waiting_approval`)
5. brief ของ `implement-*` ต้องสั่งให้ลง runtime invariants ของ spec เป็น guard จริงด้วย — เทสต์ที่
   freeze ไว้มาจากเคสที่คิดถึงแล้ว ส่วน guard มีไว้สำหรับเคสที่คิดไม่ถึง ดังนั้น implementation ที่
   ไม่มี guard เลยก็ยังผ่านเทสต์หมด และไม่มีการตรวจเชิงกลไกจุดไหนในไฟล์ที่จะจับได้ — จึงต้องสั่งใน
   brief เท่านั้น จากนั้นกรอกทุกฟิลด์ของแต่ละ stage: `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`,
   `on_fail`, `freeze_after`
6. เขียน `workflow.yaml` + `state.json`
7. **dry-run เสมอก่อน**: `python3 <run-folder>/validate_workflow.py <run-folder>` — ตัว validator กับ
   `requirement_surface.py` จะถูก emit ลงใน run folder ข้างๆ spec และ validator จะ import ไฟล์พี่น้อง
   ตัวนั้นโดยไม่มีการ setup path ใดๆ ทำให้ run folder ตรวจตัวเองได้ไม่ว่าจะถูก copy ไปไว้ที่ไหน
   เป็นการเช็คโครงสร้างแบบ zero-LLM (ไม่มี PyYAML ไม่มีการตัดสินใจของ AI) ที่จับเรื่องเหล่านี้:
   - `on_fail.target` หายไปใน stage ที่ `write_scope: []` + `action: fixing`
   - `write_scope` ทับซ้อนกับ path ที่ freeze เป็นเทสต์ไปแล้ว
   - stage อิสระที่ `write_scope` ชนกัน (เสี่ยงจริงถ้ารันขนานกัน)
   - `freeze_after: true` หายไป หรือถูกตั้งไว้มากกว่าหนึ่ง stage
   - dependency วนลูป / stage ที่ไปไม่ถึง
   - `exit_criteria` หรือ `on_fail` ขาดฟิลด์ที่จำเป็น
   - `state.json` ไม่ตรงกับ stage id ใน `workflow.yaml`
   - `spec_anchor` ทั้งสามค่า (`raise_commit` / `surface_hash` / `extractor_version`) — ถ้าไม่มี
     anchor เลยเป็น `WARN` (spec แบบ standalone หรือที่เขียนด้วยมือย่อมไม่มี anchor) ถ้ามี**ไม่ครบ**
     เป็น `FAIL` และถ้า `surface_hash` ที่บันทึกไว้ไม่ตรงกับ surface ของ spec ที่คำนวณใหม่ตอนนี้ ก็เป็น
     `FAIL` ที่บอกให้ re-fold ไม่ใช่ให้ไปแก้ anchor
   - ในแบบ sliced fold: เทียบ ticket block ที่ฝังไว้ทุกอันกับ `tickets/<id>.md` ด้วย sha256, เทียบ map
     `tickets:` กับ brief ของ stage ทั้งสองทาง และเทียบ `ac_hash` ของแต่ละ ticket กับ surface ที่คำนวณ
     ใหม่ — นี่คือสิ่งที่ทำให้ "การ fold ถูกปฏิเสธ" เป็น exit code จริง ไม่ใช่คำสัญญาของ agent

   `FAIL` = ต้องแก้ก่อนโชว์ให้ผู้ใช้ดู, `WARN` = แจ้งไว้แต่ไม่บล็อก

8. โชว์ทั้งสองไฟล์พร้อมคำอธิบายลำดับ stage แบบภาษาธรรมดา เพื่อให้ผู้ใช้ตรวจสอบได้ก่อนถือว่า
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
   ไม่ใช่ retry เพราะแปลว่ามีคนแก้เทสต์ที่ freeze ไว้นอกกระบวนการ บน workflow ที่มี anchor ก่อน
   งานทุกรอบให้คำนวณ requirement surface ฝั่ง working และ raise ใหม่ แล้วบังคับให้ทั้งคู่ตรงกับ
   anchor ที่บันทึกไว้ ถ้า anchor ผิดรูป/เข้าถึงไม่ได้, คำนวณไม่สำเร็จ หรือไม่ตรงกัน ให้ hard stop
   แบบ fail-closed ไม่ใช่ retry หรือ `reworking`
2. **ทำงานของ stage** — spawn subagent (หรือทำเองตรงๆ ถ้าเป็นแค่การเช็ค mechanical ที่ไม่ต้องใช้
   วิจารณญาณ เช่น stage `review`/`verify` ที่ `write_scope: []`) — stage `done` เขียนสรุปของตัวเอง
   ได้ตรงๆ จาก `state.json`/`git log` โดยไม่ต้อง spawn อะไร stage แบบ sliced ที่มี anchor จะได้
   slim pack (brief ของ ticket เดียวที่พิสูจน์ ownership แล้ว + provision layer และอ่าน spec ตาม
   ต้องการ) ต่อเมื่อ provenance กับ surface check ของรอบนี้ผ่านเท่านั้น stage ที่ไม่มี anchor,
   monolithic หรือกำกวมต้องได้ spec เต็มแบบ verbatim; anchored gate ที่ล้มเหลวจะหยุด ไม่ fallback
3. **ตรวจสอบแบบ mechanical** เรียงลำดับเสมอ: `write_scope` (diff จริง; snapshot path ที่ละเมิด
   ก่อน revert แล้วให้ scope check ล้มเหลว) → `exit_criteria` (รันคำสั่งจริง / เช็ค artifact จริง)
4. ถ้า `exit_criteria.type` เป็น `human_approval` (มีเฉพาะตอนผู้ใช้ขอ manual milestone ไว้ล่วงหน้า)
   → หยุดถามจริงเสมอ ไม่เคย auto-approve
5. **ถ้าผ่าน** → stage กลายเป็น `passed`; ถ้าเป็น freeze stage ก็เก็บ test hash; commit (โค้ด +
   `state.json` ในคอมมิตเดียว); ไปยัง stage ถัดไปที่ dependency ครบแล้วโดยอัตโนมัติ
6. **ถ้าล้มเหลว** → เพิ่ม `attempt`, เช็คว่า diff ซ้ำหรือไม่ (`seen_diffs`):
   - ถ้ามี `exit_criteria.progress` ให้วัด attempt 0 จาก criterion จริงก่อนงานรอบแรก และเก็บเป็น
     entry แรกใน `progress_history` — ห้ามใช้ baseline ที่เขียนไว้ใน prose จากนั้น append ค่าที่วัด
     ได้ของ failed attempt แต่ละรอบ; ถ้าค่าของ failed attempt ไม่ขยับเข้าเป้าติดต่อกันสองรอบ ให้
     เข้า `reworking` ก่อน attempt ถัดไป
   - ยังไม่ถึง `max_attempts` และไม่ใช่การซ้ำเกิน `escalate_at` → กลับไปข้อ 2 (resume subagent
     ตัวเดิมถ้าทำได้ แทนที่จะ spawn ใหม่ เพื่อไม่ต้องเสียเวลา orient ใหม่)
   - `max_attempts` หมด หรือ diff เดิมซ้ำเกิน `escalate_at` → **`reworking`** — เงื่อนไขหยุดเดียวที่
     รับประกันว่าจะดึงมนุษย์เข้ามาเสมอ

### เมื่อไหร่ที่มันหยุด

- `fixing → reworking` — retry หมด, diff เดิมซ้ำ หรือค่าของ failed progress ไม่ขยับเข้าเป้า
  ติดต่อกันสองรอบ (จุดหยุดที่รับประกันเสมอ)
- `blocked` — ต้องการมนุษย์มาปลดล็อก
- Test-hash ไม่ตรงกัน — มีคนแก้เทสต์ที่ freeze ไว้นอกกระบวนการ
- Anchored-surface mismatch — anchor ผิดรูป/เข้าถึงไม่ได้ หรือ surface ฝั่ง raise/current ไม่ตรงกัน;
  หยุดแบบ fail-closed ไม่เข้า `reworking`
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

## kestra-exam — exam ที่สร้างจาก spec

**ที่อยู่:** [`kestra-exam/`](kestra-exam/) · รายละเอียดเพิ่มเติม: [`kestra-exam/SKILL.md`](kestra-exam/SKILL.md)

### มันทำอะไร

แปลง acceptance criteria ที่มีอยู่แล้วใน `0-spec.md` ให้เป็น exam ที่รันได้: หนึ่ง check ต่อหนึ่ง AC
ในไฟล์ `exam.py` ไฟล์เดียว บวก `manifest.md` ที่ map ทุก check กลับไปยัง AC ของมันและช่อง `Source`
ที่มันมาจาก ตัว exam จะถูก **red-proof** ก่อนที่จะมี implementation อยู่เลย — มันถูกรันใน clone ที่
ทิ้งได้ ณ คอมมิต raise ซึ่งทุก check ต้องล้มเหลวด้วยเหตุผลที่ถูกต้อง (ล้มเหลวเชิงพฤติกรรม ไม่ใช่เพราะ
import ไม่เจอ) เพื่อให้การเป็นสีเขียวในภายหลังไม่ใช่อุบัติเหตุของ harness

มันอ่านเฉพาะห้าหัวข้อที่อยู่ใน surface ของ spec (ชุดเดียวกับที่ `requirement_surface.py` สกัดออกมา)
และตั้งใจไม่อ่านแผน implementation, รายการไฟล์ หรือโค้ดเลย เพราะ exam ที่สร้างจากรูปร่างของ
implementation จะไม่ใช่การอนุมานจาก requirement อย่างเป็นอิสระอีกต่อไป

สิ่งที่มัน **ไม่ได้อ้าง**: มันครอบเฉพาะสิ่งที่ spec สั่งไว้ ไม่ใช่ runtime invariants หรือ guard ที่
บังคับ invariants เหล่านั้น (เจ้าของเรื่องนั้นคือ `kestra-build/references/design-principles.md`) และมัน
ไม่ใช่ทางแก้ hallucination คำอ้างของมันแคบกว่าและตรวจได้ — มันเปลี่ยนการเชื่อ AI ให้เป็นการเชื่อหลักฐาน

### เมื่อไหร่ที่มันทำงาน และเมื่อไหร่ที่ไม่ทำ

เป็นแบบ opt-in โดยอ่านจาก mode ที่ `kestra-build` บันทึกไว้แล้ว: `full` ⇒ สร้าง exam, `lite` ⇒ ตั้งใจ
ไม่มี exam ส่วน spec แบบ standalone (ไม่มี marker) ก็ใช้ได้ ไม่มีอะไรอื่นใน pipeline ที่ขึ้นอยู่กับมัน —
`kestra-spec`, `kestra-build` และ `kestra-run` ยังทำงานได้เหมือนเดิมในเครื่องที่ไม่ได้ติดตั้งมัน และมัน
อ้างถึงทั้งสามตัวในฐานะคำแนะนำเท่านั้น

### exam เก็บอยู่ที่ไหน

อยู่นอก repo ในไดเรกทอรี exams ระดับผู้ใช้ใต้ `~/.kestra/` โดยตั้งชื่อตาม origin และ slug ของฟีเจอร์
(`<origin-key>/<feature-slug>/`) และ `git init` แยกต่อหนึ่งฟีเจอร์ —
เพื่อให้ exam เป็นหลักฐาน *เกี่ยวกับ* งาน ไม่ใช่ไฟล์อีกไฟล์ที่ตัวงานแก้ได้เงียบๆ ค่า `<origin-key>` มา
จาก `git remote get-url origin`; repo ที่ไม่มี `origin` คือจุดหยุดตายตัว ไม่ใช่การใช้ชื่อสำรอง เพราะ
ไม่อย่างนั้น clone หรือ fork สองอันที่ชื่อโฟลเดอร์เหมือนกันจะถูกต่อสายเข้า exam dir เดียวกัน แต่ละ exam
มี pointer record ที่คงทนอันเดียว — ticket บน tracker ชื่อ `kestra-exam: <feature-slug>` หรือไฟล์
`.pointer` ในเครื่องสำหรับ repo ที่ไม่มี tracker — ซึ่งเก็บ hash ทั้งหมดไว้ มันถูกแก้ในที่เดิม และถ้า
match ได้มากกว่าหนึ่งอันคือ hard fail ที่ไม่ตัดสินด้วยการเลือกอันที่ใหม่กว่าเด็ดขาด

### การปฏิเสธเมื่อ exam เก่า

ทุกครั้งที่รัน มันจะเทียบสามค่า — surface hash ของ spec, คอมมิต raise, เวอร์ชันของ extractor — ข้าม
ระหว่าง manifest, pointer และ `exam.py` ถ้าไม่ตรงกันตรงไหน หมายความว่า **ไม่มีการให้ verdict ใดๆ เลย**:
มันจะพิมพ์ `REFUSED: exam is stale` และออกด้วย exit code ที่ไม่ใช่ศูนย์ แทนที่จะรายงานว่าผ่านหรือไม่ผ่าน
เทียบกับ spec ที่ขยับไปแล้ว การที่ spec เปลี่ยนต้องแก้ด้วยการ regenerate (แผน delta ที่ระบุชัดว่า check
ไหนต้องขยับ และ check ไหน carry over ไปได้โดยไม่ต้องแตะ) ไม่ใช่ด้วยการไปแก้ anchor

การสร้างตัว *runner* ของ gate — งานก่อนส่งมอบที่รัน exam — **ไม่ใช่** ส่วนหนึ่งของ skill นี้อย่างชัดเจน
เพื่อไม่ให้ใครไป implement gate ที่ไม่มีอยู่จริง

### ตัวอย่างการใช้งาน

```
"build the exam for workflows/runs/csv-export"
"is the csv-export exam still fresh?"
"the spec changed — regenerate the exam"
```

---

## เอกสารอ้างอิงเพิ่มเติม

| ไฟล์ | เนื้อหา |
|---|---|
| [`kestra-spec/references/chain-provenance.md`](kestra-spec/references/chain-provenance.md) | รูปแบบที่แน่นอนของ chain marker และเคสพิการต่างๆ, กติกา match ได้อันเดียวเป๊ะสำหรับหาคอมมิต raise, การ raise ใหม่หลัง bounce หรือหลัง re-vet, และการใช้ tracker ที่เป็นไฟล์ในเครื่องแทน GitHub |
| [`kestra-build/references/design-principles.md`](kestra-build/references/design-principles.md) | ที่มาของทุก state/transition, "Default HITL posture", ทำไมไม่มีการ replan กลางเวิร์กโฟลว์ |
| [`kestra-build/references/workflow-schema.md`](kestra-build/references/workflow-schema.md) | รายการฟิลด์เต็มของ `workflow.yaml` พร้อมตัวอย่างจริง (csv-export) |
| [`kestra-build/references/state-schema.md`](kestra-build/references/state-schema.md) | รายการฟิลด์ของ `state.json` |
| [`kestra-build/references/ticket-fold.md`](kestra-build/references/ticket-fold.md) | รายละเอียดเต็มของ sliced fold — input สามรูปแบบ, การ copy แบบ verbatim, การ resolve Source label จาก AC Coverage Map, ขั้นตอน F0–F5 ตอนเริ่ม fold พร้อมข้อความปฏิเสธที่แน่นอน และการตรวจจับการเปลี่ยนแปลงตอน re-fold |
| [`kestra-build/references/test-quality-taxonomy-research.md`](kestra-build/references/test-quality-taxonomy-research.md) | ทำไมเทสต์ผ่านแต่ production พัง — 6 รูปแบบความล้มเหลวด้าน test fidelity ที่เกิดซ้ำ เชื่อมโยงกับวรรณกรรมที่มีอยู่จริง พร้อมแหล่งอ้างอิง |
| [`kestra-run/references/enforcement.md`](kestra-run/references/enforcement.md) | คำสั่งจริงที่ใช้เช็คทุกอย่าง (write_scope diff, test-hash, commit-per-stage, rollback) |
| [`kestra-run/references/efficiency-notes.md`](kestra-run/references/efficiency-notes.md) | ทำไมแต่ละทางลัดด้าน efficiency ถึงปลอดภัย (ไม่ spawn agent ใหม่ทุก stage, resume แทน respawn ฯลฯ) |
| [`kestra-exam/references/exam-script-contract.md`](kestra-exam/references/exam-script-contract.md) | รูปร่างของ `exam.py` — `@check`, ตระกูล `expect*` (และทำไมห้ามใช้ `assert` เปล่าๆ), seam สามชนิด, ตัวแยกแยะ red แบบ behavioral กับ infrastructure, บันไดของ exit code และ schema ของ `--json` |
| [`kestra-exam/references/manifest-schema.md`](kestra-exam/references/manifest-schema.md) | เจ็ดหัวข้อของ `manifest.md` ตามลำดับตายตัว, ทุกคอลัมน์, ชุดคำ Red-proof แบบปิด, สูตร fingerprint และ verdict contract แบบ verbatim |
| [`kestra-exam/references/gate-procedure.md`](kestra-exam/references/gate-procedure.md) | gate ก่อนส่งมอบ — sweep ต่างๆ กับขอบเขตการยกเว้น, วินัยเรื่อง pointer และการเทียบ hash กับ pointer; การสร้างตัว runner เองอยู่นอกขอบเขต |
| [`kestra-exam/references/regeneration.md`](kestra-exam/references/regeneration.md) | อะไรขยับเมื่อ spec ขยับ — delta map, fingerprint, scope สี่แบบ, การ carry over และ commit subject ของ exam dir |

## สิ่งที่ตั้งใจ "ไม่ทำ"

- **kestra-spec ไม่แตะโค้ดและไม่รัน stage ใดๆ** — เขียน `0-spec.md`, commit, รันสคริปต์ validator
  สองตัวกับผลงานของตัวเอง แล้วหยุด แต่มันครอบงานฝั่ง spec→plan ทั้งหมดไว้ในตัวแล้ว จึงเป็นเหตุผลที่
  role skill เดิม (PM/BA/SA/architect) ถูกปลดระวางไป เหลือ `meta-designer` ตัวเดียวที่ยังอยู่ เพราะ
  มันสร้าง artifact ที่เปิดดูได้จริงซึ่ง skill นี้ไม่ได้ทำ
- **kestra-spec ไม่เขียนอะไรลง tracker เลย** — ไม่คอมเมนต์ ไม่ติด label ไม่แก้ ไม่ปิด ticket มันจึง
  vet input ของตัวเองไม่ได้ ถ้าไม่มี vet หรือ vet ไม่ตรง มันจะหยุดรอบการทำงานแทน
- **kestra-spec ไม่คิด business rule ที่ยังไม่ถูกตัดสินขึ้นมาเองในโหมด in-chain** — แขนงที่ ticket
  ไม่ได้ตัดสินจะเด้งกลับต้นทางเป็น `BLOCKED_ON_INTENT` ส่วนงาน `needs_ui` และ `needs_sa` ยังทำในตัว
  เหมือนเดิม มีเฉพาะความเงียบเรื่อง intent จริงๆ เท่านั้นที่ bounce
- **kestra-build ไม่รันอะไรเลย** — ไม่เขียนโค้ดจริง ไม่ commit ไม่เรียก skill ใดๆ
- **kestra-run ไม่สร้างเวิร์กโฟลว์เอง** — ถ้าไฟล์ยังไม่มี มันจะบอกตรงๆ แทนที่จะด้นสดสร้างเอง
- **kestra-build อ่าน tracker ครั้งเดียวเท่านั้น และอ่านอย่างเดียว** — ตอน fold เพื่อ copy ticket ที่
  *ถูกระบุชื่อมา* แบบ verbatim ลง run folder มันไม่แก้ ไม่คอมเมนต์ ไม่ปิด ไม่ซอย ticket ไม่ค้นหา ticket
  ที่ไม่มีใครระบุชื่อมา และไม่ re-fold กลางรอบการทำงาน — spec หรือ ticket ที่ขยับต้องแก้ด้วยการ fold ใหม่
  จากสถานะที่สะอาด ไม่ใช่การไป patch เวิร์กโฟลว์ที่กำลังรันอยู่
- **kestra-exam ไม่สร้างตัว gate runner และไม่ให้ verdict กับ spec ที่ขยับไปแล้ว** — มันเขียน exam,
  red-proof, บันทึก anchor สามค่า และวินาทีที่สำเนาทั้งสามชุดไม่ตรงกัน มันจะปฏิเสธทันที (ไม่บอกว่าผ่าน
  ไม่บอกว่าไม่ผ่าน) แล้วชี้ไปที่การ regenerate ทั้งยังไม่ได้ถูกเสนอว่าเป็นทางแก้ hallucination — คำอ้าง
  ที่แคบกว่าและตรวจได้คือ verdict อ้างจากหลักฐาน ไม่ใช่จากรายงานของ AI เอง
- **skill เหล่านี้ไม่ hard-depend กับ skill/agent เฉพาะทางใดๆ** — ชื่อ skill ที่อาจถูกแนะนำใน
  `brief` ของ stage หรือที่ถูกระบุว่าเป็นวิธีเขียน ticket ต้นทาง (`to-spec`) เป็นแค่คำแนะนำเสมอ
  ("ลองใช้ถ้ามี") ไม่ใช่ข้อบังคับ ทำให้ `workflow.yaml` ที่สร้างไว้ย้ายไปเครื่อง/session อื่นที่มี
  skill set ต่างกันได้และยังทำงานได้ปกติ และ `kestra-spec` ก็ยังรันได้ในเครื่องที่ไม่ได้ติดตั้ง
  `to-spec` และ `kestra-build`
