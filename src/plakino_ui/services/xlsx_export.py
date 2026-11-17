"""Small streaming OOXML workbook writer using only the standard library.

Cells are inline strings, including formula-like user values, so exports cannot
turn plate/camera names into spreadsheet formulas. No text shaping is applied.
"""
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import re

_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_INVALID_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def write_xlsx(path, rows):
    count = 0
    with ZipFile(path,'w',compression=ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''')
        archive.writestr('_rels/.rels','''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr('xl/workbook.xml',f'''<workbook xmlns="{_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="گزارش تردد" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr('xl/_rels/workbook.xml.rels','''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''')
        archive.writestr('xl/styles.xml',f'''<styleSheet xmlns="{_NS}"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF4BD0D0"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" readingOrder="2"/></xf><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment horizontal="center" readingOrder="2"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        with archive.open('xl/worksheets/sheet1.xml','w') as sheet:
            sheet.write(f'''<worksheet xmlns="{_NS}"><sheetViews><sheetView workbookViewId="0" rightToLeft="1"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="8" width="24" customWidth="1"/></cols><sheetData>'''.encode())
            for number, values in enumerate(rows,1):
                if number > 1_048_576:
                    raise ValueError('تعداد نتایج از ظرفیت یک فایل اکسل بیشتر است؛ بازه زمانی را محدود کنید')
                cells = []
                for column,value in enumerate(values):
                    text = escape(_INVALID_XML.sub('',str(value)))
                    cells.append(f'<c r="{chr(65+column)}{number}" t="inlineStr" s="{1 if number==1 else 0}"><is><t xml:space="preserve">{text}</t></is></c>')
                sheet.write((f'<row r="{number}">' + ''.join(cells) + '</row>').encode())
                count = number
            sheet.write(f'</sheetData><autoFilter ref="A1:H{max(1,count)}"/></worksheet>'.encode())
    return max(0,count-1)
