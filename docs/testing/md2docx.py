"""md2docx.py <template.docx> <in.md> <out.docx>

  python docs/testing/md2docx.py docs/testing/RockLocalCPUWithFAN.docx \
      docs/testing/RockLocalNPU.md docs/testing/RockLocalNPU.docx

Builds a .docx in the same format as the earlier Rock results docx: reuses its
styles, numbering and package parts, and writes document.xml from the Markdown
(headings, paragraphs, bullet/numbered lists, tables, **bold**, `code`, links)."""
import re
import sys
import zipfile
from xml.sax.saxutils import escape

TEMPLATE, SRC, OUT = sys.argv[1:4]
CODE = '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
BORDER = ''.join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
                 for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))


def runs(text, size=None, bold_all=False):
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links -> their text.
    out = []
    for part in re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', text):
        if not part:
            continue
        rpr = ''
        if part.startswith('**') and part.endswith('**'):
            part, rpr = part[2:-2], '<w:b/>'
        elif part.startswith('`') and part.endswith('`'):
            part, rpr = part[1:-1], CODE
        if bold_all and '<w:b/>' not in rpr:
            rpr = '<w:b/>' + rpr
        if size:
            rpr += f'<w:sz w:val="{size}"/>'
        out.append(f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return ''.join(out)


def para(text, style=None, after=60, num=None):
    ppr = f'<w:pStyle w:val="{style}"/>' if style else ''
    if num:
        ppr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
    elif not style:
        ppr += f'<w:spacing w:before="0" w:after="{after}"/>'
    return f'<w:p><w:pPr>{ppr}</w:pPr>{runs(text)}</w:p>'


def table(lines):
    cells = [[c.strip() for c in l.strip().strip('|').split('|')] for l in lines]
    head, align, body = cells[0], cells[1], cells[2:]
    right = [a.endswith(':') and not a.startswith(':') for a in align]
    center = [a.startswith(':') and a.endswith(':') for a in align]
    n = len(head)
    plain = lambda s: re.sub(r'[*`]', '', s)
    weight = [max(8, min(60, max(len(plain(r[i])) for r in cells[:1] + body))) for i in range(n)]
    widths = [int(9360 * w / sum(weight)) for w in weight]
    widths[-1] += 9360 - sum(widths)
    grid = ''.join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    xml = [f'<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblBorders>{BORDER}</w:tblBorders>'
           '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="40" w:type="dxa"/>'
           '<w:left w:w="80" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/>'
           f'<w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
    for ri, row in enumerate([head] + body):
        xml.append('<w:tr><w:trPr><w:tblHeader/></w:trPr>' if ri == 0 else '<w:tr>')
        for i, c in enumerate(row):
            shd = '<w:shd w:val="clear" w:color="auto" w:fill="E7ECF2"/>' if ri == 0 else ''
            jc = ('<w:jc w:val="right"/>' if right[i] else '<w:jc w:val="center"/>' if center[i]
                  else '') if ri else ''
            xml.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[i]}" w:type="dxa"/>{shd}</w:tcPr>'
                       f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/>{jc}</w:pPr>'
                       f'{runs(c, 18, bold_all=ri == 0)}</w:p></w:tc>')
        xml.append('</w:tr>')
    xml.append('</w:tbl><w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr></w:p>')
    return ''.join(xml)


lines = open(SRC, encoding='utf-8').read().splitlines()
body, i = [], 0
while i < len(lines):
    line = lines[i]
    if not line.strip():
        i += 1
    elif line.startswith('|'):
        block = []
        while i < len(lines) and lines[i].startswith('|'):
            block.append(lines[i]); i += 1
        body.append(table(block))
    elif line.startswith('```'):
        i += 1
        while i < len(lines) and not lines[i].startswith('```'):
            body.append(f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:ind w:left="720"/></w:pPr>'
                        f'<w:r><w:rPr>{CODE}<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">'
                        f'{escape(lines[i])}</w:t></w:r></w:p>')
            i += 1
        i += 1
    else:
        m = re.match(r'(#{1,3}) (.*)', line)
        if m:
            body.append(para(m[2], {1: 'Title', 2: 'Heading1', 3: 'Heading2'}[len(m[1])]))
        elif re.match(r'\s*- ', line):
            body.append(para(re.sub(r'\s*- ', '', line, 1), 'ListParagraph', num=1))
        elif re.match(r'\d+\. ', line):
            body.append(para(re.sub(r'\d+\. ', '', line, 1), 'ListParagraph', num=2))
        else:
            body.append(para(line))
        i += 1

doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document '
       'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
       + ''.join(body) + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" '
       'w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
       '</w:sectPr></w:body></w:document>')
with zipfile.ZipFile(TEMPLATE) as t, zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in t.namelist():
        z.writestr(name, doc if name == 'word/document.xml' else t.read(name))
print(f'Wrote {OUT}: {len(body)} blocks')
