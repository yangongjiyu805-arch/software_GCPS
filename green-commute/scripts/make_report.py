"""Generate formal Chinese course report from the same source docs shipped with code."""
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_LINE_SPACING
from docx.enum.table import WD_ROW_HEIGHT_RULE
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'GreenGo-软件工程课程完整实验报告.docx'
doc=Document()
sec=doc.sections[0]
sec.top_margin=Cm(2.2);sec.bottom_margin=Cm(2.1)
sec.left_margin=Cm(2.35);sec.right_margin=Cm(2.15)
sec.header_distance=Cm(1);sec.footer_distance=Cm(1.1)
styles=doc.styles
normal=styles['Normal'];normal.font.name='Noto Sans CJK SC';normal.font.size=Pt(10)
normal.font.color.rgb=RGBColor(43,57,50)
normal._element.rPr.rFonts.set(qn('w:eastAsia'),'Noto Sans CJK SC')
normal.paragraph_format.line_spacing=1.30
normal.paragraph_format.space_after=Pt(6)
for level,size in [(1,16),(2,13),(3,11)]:
    st=styles[f'Heading {level}'];st.font.name='Noto Sans CJK SC';st._element.rPr.rFonts.set(qn('w:eastAsia'),'Noto Sans CJK SC')
    st.font.size=Pt(size);st.font.bold=True;st.font.color.rgb=RGBColor(32,105,76)
    st.paragraph_format.space_before=Pt(18 if level==1 else 11)
    st.paragraph_format.space_after=Pt(7)
    st.paragraph_format.keep_with_next=True
code_style=styles.add_style('Source Code',WD_STYLE_TYPE.PARAGRAPH)
code_style.font.name='Consolas';code_style.font.size=Pt(8);code_style.font.color.rgb=RGBColor(34,85,63)
code_style.paragraph_format.left_indent=Cm(.35);code_style.paragraph_format.space_after=Pt(2)

header=sec.header.paragraphs[0]
header.text='青行 GreenGo  |  城市绿色出行积分系统  ·  软件工程课程实验'
header.alignment=WD_ALIGN_PARAGRAPH.RIGHT
for r in header.runs:r.font.size=Pt(8);r.font.color.rgb=RGBColor(113,140,122)
foot=sec.footer.paragraphs[0];foot.alignment=WD_ALIGN_PARAGRAPH.CENTER
foot.add_run('课程实验报告  ·  实际测试数据见附录  |  第 ')
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');foot._p.append(field)
for r in foot.runs:r.font.size=Pt(8);r.font.color.rgb=RGBColor(121,143,130)

def p(txt='',style=None):
    paragraph=doc.add_paragraph(style=style)
    txt=txt.strip().replace('**','').replace('`','')
    paragraph.add_run(txt)
    return paragraph

def table(rows):
    if not rows:return
    n=max(len(row) for row in rows)
    t=doc.add_table(rows=1,cols=n)
    t.style='Table Grid'
    t.alignment=WD_TABLE_ALIGNMENT.CENTER
    hdr=t.rows[0]
    for i,v in enumerate(rows[0]):hdr.cells[i].text=v
    for j,row in enumerate(rows[1:]):
        cells=t.add_row().cells
        for i,v in enumerate(row[:n]):cells[i].text=v
    for j,row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        if j==0:
            ppr=row._tr.get_or_add_trPr()
            repeat=OxmlElement('w:tblHeader');repeat.set(qn('w:val'),'true');ppr.append(repeat)
        for i,c in enumerate(row.cells):
            c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for pg in c.paragraphs:
                pg.paragraph_format.space_after=Pt(2);pg.paragraph_format.space_before=Pt(2)
                for run in pg.runs:
                    run.font.size=Pt(8.25)
                    if j==0:run.bold=True;run.font.color.rgb=RGBColor(30,89,63)
            tcpr=c._tc.get_or_add_tcPr()
            shd=OxmlElement('w:shd');shd.set(qn('w:fill'),'EAF4EB' if j==0 else ('F8FAF8' if j%2==0 else 'FFFFFF'));tcpr.append(shd)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)

def picture(path,width=15.3,caption=''):
    pp=doc.add_paragraph();pp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    pp.add_run().add_picture(str(path),width=Cm(width))
    if caption:
        c=doc.add_paragraph(caption);c.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for r in c.runs:r.font.size=Pt(9);r.font.color.rgb=RGBColor(104,120,108)

def from_md(path):
    lines=Path(path).read_text(encoding='utf8').splitlines();i=0
    while i<len(lines):
        line=lines[i].rstrip()
        if not line.strip():i+=1;continue
        if line.startswith('```'):
            i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                doc.add_paragraph(lines[i],style='Source Code');i+=1
            i+=1;continue
        if line.startswith('|'):
            cells=[]
            while i<len(lines) and lines[i].startswith('|'):
                parts=[s.strip().replace('**','').replace('`','') for s in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-{3,}:?',v) for v in parts): cells.append(parts)
                i+=1
            table(cells);continue
        h=re.match(r'^(#{1,3})\s+(.*)$',line)
        if h:
            doc.add_heading(h.group(2),level=min(3,len(h.group(1))));i+=1;continue
        if re.match(r'^\d+\.\s+',line) or line.startswith('- '):
            # use simple text lines rather than Word auto bullets for consistent East Asian layout
            pp=doc.add_paragraph();pp.paragraph_format.left_indent=Cm(.5)
            pp.add_run(line.replace('**','').replace('`',''))
            i+=1;continue
        p(line);i+=1

# Cover
for _ in range(2):doc.add_paragraph()
a=doc.add_paragraph('软件工程课程综合实验报告')
a.alignment=WD_ALIGN_PARAGRAPH.CENTER
for r in a.runs:r.font.size=Pt(25);r.bold=True;r.font.color.rgb=RGBColor(24,87,57)
b=doc.add_paragraph('《碳中和主题的城市绿色出行积分系统》')
b.alignment=WD_ALIGN_PARAGRAPH.CENTER
for r in b.runs:r.font.size=Pt(18);r.bold=True;r.font.color.rgb=RGBColor(55,104,73)
doc.add_paragraph()
sub=doc.add_paragraph('青行 GreenGo  |  完整课程实验项目')
sub.alignment=WD_ALIGN_PARAGRAPH.CENTER
for r in sub.runs:r.font.size=Pt(12);r.font.color.rgb=RGBColor(115,142,124)
doc.add_paragraph()
meta=doc.add_table(rows=6,cols=2);meta.style='Table Grid'
labels=['课程名称','小组编号','组长及成员（4—5人）','学院 / 班级','指导教师','报告日期']
values=['软件工程综合实验','（请小组填写）','（请根据真实人员情况填写）','（请填写）','（请填写）','2026年10月（具体提交日期请填写）']
for i,(label,val) in enumerate(zip(labels,values)):
    meta.cell(i,0).text=label;meta.cell(i,1).text=val
    for c in meta.rows[i].cells:
        for para in c.paragraphs:
            for r in para.runs:r.font.size=Pt(10)
cover=p('提交说明：本报告包含可运行程序的实现说明、可编辑UML源码索引、实际执行的自动化测试结果及HTTP业务链证据；团队成员的真实协作和个人贡献须按实际补录。')
cover.paragraph_format.space_before=Pt(20)
for r in cover.runs:r.font.color.rgb=RGBColor(136,103,77)
doc.add_page_break()

doc.add_heading('摘  要',level=1)
p('围绕城市碳中和主题，本项目开发一套可实际启动的绿色出行积分教学原型。居民可模拟上报出行数据，系统依据固定教学排放因子计算二氧化碳当量节约量，并将积分以交易台账形式发放；居民可兑换积分商城商品，商户可核销订单，管理员可查看运营统计并进行模拟积分清算。')
p('技术实现采用 FastAPI、SQLAlchemy、SQLite（本地）/MySQL（部署示例），前端采用响应式单页界面；引入事务型Outbox实现行程积分发放及订单清算的事件解耦。核心积分以整数计量，余额与库存使用数据库条件更新保证事务一致性。')
p('实际验证：16项pytest测试全部通过，另运行HTTP端到端业务链，保存真实API响应。限制：碳因子未经官方核证，未接入实际出行数据或支付；Docker环境与自动浏览器截图没有在本制作环境完成测试。')
p('关键词：绿色出行；软件工程；UML；敏捷开发；事务型Outbox；积分账本；FastAPI')
doc.add_heading('报告目录',level=1)
for chapter in ['一、实验一：需求分析与迭代规划','二、实验二：系统设计与技术选型','三、实验三：系统原型构建与实现','四、实验四：软件测试与部署','五、工程协作、AI使用与提交核对','附录：实际运行证据与模型目录']:
    p(chapter)
doc.add_page_break()

chapters=[('01-需求分析与迭代规划.md',None),('02-系统设计与技术选型.md','design'),('03-原型构建与实现.md',None),('04-测试与部署.md',None)]
for fname,kind in chapters:
    from_md(ROOT/'docs'/fname)
    if kind=='design':
        doc.add_heading('设计图示（与源码模型对应）',level=2)
        picture(ROOT/'docs/figures/architecture-vertical.png',width=9.0,caption='图1  模块化后端与事件处理部署视图（结构化预览）')
        picture(ROOT/'docs/figures/entities-vertical.png',width=9.2,caption='图2  主要实体及关联关系（结构化预览）')
        p('说明：上述预览图由Graphviz绘制；符合UML表述的可编辑用例图、类图、时序图、状态图、组件图源文件位于 docs/uml/。')
    if fname!='04-测试与部署.md':doc.add_page_break()

doc.add_heading('五、工程协作、AI使用与提交核对',level=1)
doc.add_heading('1. 真实团队分工与Git记录（提交前必填）',level=2)
p('以下表格是课程互评模板，不代表本交付已经由4—5名学生协作完成，也不是基于真实Git数据的评分。请根据实际GitHub/Gitee提交与Issue/PR记录补全。')
table([['成员（真实姓名）','负责模块/任务','Git提交与PR证据','组内评分（待评）'],['组长：待填','待填','待填','待填'],['成员2：待填','待填','待填','待填'],['成员3：待填','待填','待填','待填'],['成员4：待填','待填','待填','待填'],['成员5（可选）','待填','待填','待填']])
p('提交依据：Git仓库URL、真实commit哈希及时间、Sprint看板截图、同伴评语和任务验收记录。不得把AI生成的本地示例提交归功于虚构成员。')
doc.add_heading('2. AI使用情况及后续人工审核计划',level=2)
table([['开发环节','AI辅助内容（已发生）','已进行的机器验证','人工检查/修改（小组待填）'],['需求分析','功能点、用户故事及范围界定初稿','文档结构与代码对照','逐条复核需求'],['UML与设计','模型文字草图及PlantUML源文件','校对实体与数据库字段','人工审图并修订'],['代码实现','后端、前端和数据表原型','16项pytest通过、HTTP链实测','逐行审核核心逻辑、重构'],['测试','正向/反向/并发测试用例','pytest结果存档','补充遗漏场景及测试记录'],['部署与报告','说明文档及容器配置建议','本地API验证','部署到小组实际环境并记录截图']])
doc.add_heading('3. 最终验收与交付清单',level=2)
for x in ['[已提供] 前后端可运行源码和静态资源','[已提供] 数据表与ORM结构及演示数据库','[已提供] 6份可编辑PlantUML模型与图示预览','[已提供] 敏捷Sprint计划、需求分析、设计说明、测试报告','[已提供] 16项自动测试与真实HTTP请求证据','[已提供] Dockerfile / Compose配置（未在本环境实际执行）','[需组员补全] 真实协作Git仓库及分工互评','[需组员补全] 实际Sprint评审与小组答辩记录']:
    p('• '+x)
doc.add_heading('附录：实际运行证据与模型目录',level=1)
doc.add_heading('A. 自动化测试输出',level=2)
for line in (ROOT/'docs/evidence/pytest-output.txt').read_text().splitlines():
    doc.add_paragraph(line,style='Source Code')
doc.add_heading('B. HTTP业务链测试数据',level=2)
import json
data=json.loads((ROOT/'docs/evidence/demo_flow.json').read_text(encoding='utf8'))
rows=[['步骤','接口','HTTP状态']]
for e in data['steps']:
    rows.append([e['step'],e['method']+' '+e['path'],str(e['status'])])
table(rows)
p(f'实际本次模拟公交行程获得 {data["this_trip_issued"]} 积分，兑换支出 {data["this_redemption_cost"]} 积分；运行时账户余额 {data["balance_after"]} 分，当前账本记录累计差额 {data["ledger_net"]} 分。原始请求响应存储于 docs/evidence/demo_flow.json。运行时账户余额包含先前的演示操作，不能误读为单笔出行所得。')
doc.add_heading('C. UML源文件索引',level=2)
for f in sorted((ROOT/'docs/uml').glob('*.puml')):
    p('• docs/uml/'+f.name)
doc.add_heading('D. 重要真实性说明',level=2)
p('测试结论只描述本次本地执行结果，不能推断在线支付、真实碳核证、真实团队协作、Docker部署或生产级安全符合要求。对于课程最终验收，应安排各组员在自己的设备上运行、复测、审查、补全报告的个人贡献及使用情况。')

doc.core_properties.title='城市绿色出行积分系统—软件工程综合实验报告'
doc.core_properties.subject='课程实验一至实验四：需求分析、系统设计、原型实现、测试部署'
doc.core_properties.author='GreenGo课程项目示例（待团队署名）'
doc.save(OUT)
print(OUT)
