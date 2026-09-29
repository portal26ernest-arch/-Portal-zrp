"""Unicode A4 PDF rendering for immutable PORTAL invoice and closed payroll records."""
import os
from pathlib import Path
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_ENV='PORTAL_PDF_FONT'
FONT_CANDIDATES=(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    'C:/Windows/Fonts/arial.ttf',
)

def _font():
    for raw in (os.environ.get(FONT_ENV,''),)+FONT_CANDIDATES:
        if raw and Path(raw).is_file():
            if 'PortalUnicode' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('PortalUnicode',raw))
            return 'PortalUnicode'
    raise RuntimeError('Unicode PDF font unavailable; configure PORTAL_PDF_FONT')

def _write(title, rows):
    font=_font();out=BytesIO();page_w,page_h=A4
    doc=canvas.Canvas(out,pagesize=A4,pageCompression=1,invariant=1)
    doc.setTitle(title);y=page_h-52
    doc.setFont(font,16);doc.drawString(46,y,title);y-=34
    for label,value in rows:
        value='' if value is None else ''.join(ch if ord(ch)>=32 else ' ' for ch in str(value))
        if y<70: doc.showPage();y=page_h-52
        doc.setFont(font,9);doc.setFillColorRGB(.30,.34,.40);doc.drawString(46,y,label[:100]);y-=14
        doc.setFont(font,11);doc.setFillColorRGB(.08,.10,.14)
        while value:
            line=''
            while value and pdfmetrics.stringWidth(line+value[0],font,11)<=page_w-92:
                line+=value[0];value=value[1:]
            if not line: line,value=value[0],value[1:]
            doc.drawString(46,y,line);y-=16
            if y<58:doc.showPage();y=page_h-52;doc.setFont(font,11)
        y-=8
    doc.save();return out.getvalue()

def _requisites(data):
    names=(('legal_name','\u042e\u0440\u0438\u0434\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435'),
      ('inn','\u0418\u041d\u041d'),('kpp','\u041a\u041f\u041f'),('ogrn','\u041e\u0413\u0420\u041d'),
      ('legal_address','\u042e\u0440\u0438\u0434\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0430\u0434\u0440\u0435\u0441'),
      ('settlement_account','\u0420\u0430\u0441\u0447\u0451\u0442\u043d\u044b\u0439 \u0441\u0447\u0451\u0442'),
      ('bank_name','\u0411\u0430\u043d\u043a'),('bik','\u0411\u0418\u041a'),('correspondent_account','\u041a\u043e\u0440\u0440\u0435\u0441\u043f\u043e\u043d\u0434\u0435\u043d\u0442\u0441\u043a\u0438\u0439 \u0441\u0447\u0451\u0442'),
      ('phone','\u0422\u0435\u043b\u0435\u0444\u043e\u043d'),('email','Email'),
      ('tax_info','\u041d\u0430\u043b\u043e\u0433\u043e\u043e\u0431\u043b\u043e\u0436\u0435\u043d\u0438\u0435'),
      ('director','\u0420\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c'),
      ('contact_person','\u041a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u043e\u0435 \u043b\u0438\u0446\u043e'))
    return [(label,data.get(key,'')) for key,label in names]

def invoice_pdf(company,client,invoice,operations):
    rows=[('\u0418\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c',company.get('name',''))]+_requisites(company)
    rows += [('\u041a\u043b\u0438\u0435\u043d\u0442',client.get('name',''))]+_requisites(client)
    rows.append(('\u0414\u0430\u0442\u0430',str(invoice.get('created_at',''))[:10]))
    if invoice.get('due_at'): rows.append(('\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c \u0434\u043e',str(invoice['due_at'])[:10]))
    for n,line in enumerate(invoice.get('lines',[]),1):
        operation=line.get('operation_name') or operations.get(line.get('operation_id'),'')
        price=line['client_rate']/100
        amount=line['amount']/100
        rows.append((f'\u041f\u043e\u0437\u0438\u0446\u0438\u044f {n}',f'{operation} \u00d7 {line["quantity"]} \u00d7 {price:.2f} = {amount:.2f} RUB'))
    rows.append(('\u0418\u0442\u043e\u0433\u043e, RUB',f'{invoice["amount"]/100:.2f}'))
    return _write('\u0421\u0447\u0451\u0442 \u043d\u0430 \u043e\u043f\u043b\u0430\u0442\u0443',rows)

def payroll_slip_pdf(company,period,employee,summary,issue_date):
    start,end=period['period_start'],period['period_end']
    rows=[('\u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f',company.get('name','')),
      ('\u0420\u0430\u0441\u0447\u0451\u0442\u043d\u044b\u0439 \u043b\u0438\u0441\u0442',''),
      ('\u041f\u0435\u0440\u0438\u043e\u0434 / \u0433\u043e\u0434',f'{start} \u2014 {end} / {start[:4]}'),
      ('\u0424\u0418\u041e',employee.get('display_name','')),
      ('\u0418\u0442\u043e\u0433\u043e\u0432\u0430\u044f \u0441\u0443\u043c\u043c\u0430, RUB',f'{summary["balance"]/100:.2f}'),
      ('\u0414\u0430\u0442\u0430',issue_date),
      ('\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0435\u0439','____________________________'),
      ('\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439 \u043f\u043e\u0434\u0440\u0430\u0437\u0434\u0435\u043b\u0435\u043d\u0438\u0435\u043c','____________________________'),
      ('\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a','____________________________')]
    return _write('\u0420\u0430\u0441\u0447\u0451\u0442\u043d\u044b\u0439 \u043b\u0438\u0441\u0442',rows)
