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


def _clean(value):
    return '' if value is None else ''.join(ch if ord(ch)>=32 else ' ' for ch in str(value))


def _wrap(text,font,size,width):
    text=_clean(text).strip()
    if not text:return ['']
    words=text.split()
    lines=[];line=''
    for word in words:
        candidate=word if not line else line+' '+word
        if pdfmetrics.stringWidth(candidate,font,size)<=width:
            line=candidate
            continue
        if line:lines.append(line)
        if pdfmetrics.stringWidth(word,font,size)<=width:
            line=word
            continue
        part=''
        for ch in word:
            if part and pdfmetrics.stringWidth(part+ch,font,size)>width:
                lines.append(part);part=ch
            else:part+=ch
        line=part
    if line:lines.append(line)
    return lines or ['']


def _write(title, rows):
    font=_font();out=BytesIO();page_w,page_h=A4
    doc=canvas.Canvas(out,pagesize=A4,pageCompression=1,invariant=1)
    doc.setTitle(title);y=page_h-52
    doc.setFont(font,16);doc.drawString(46,y,title);y-=34
    for label,value in rows:
        value=_clean(value)
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
    names=(('legal_name','Юридическое наименование'),
      ('inn','ИНН'),('kpp','КПП'),('ogrn','ОГРН'),
      ('legal_address','Юридический адрес'),
      ('settlement_account','Расчётный счёт'),
      ('bank_name','Банк'),('bik','БИК'),('correspondent_account','Корреспондентский счёт'),
      ('phone','Телефон'),('email','Email'),
      ('tax_info','Налогообложение'),
      ('director','Руководитель'),
      ('contact_person','Контактное лицо'))
    return [(label,data.get(key,'')) for key,label in names]


def _invoice_party(data,fallback):
    name=data.get('legal_name') or data.get('name') or fallback
    parts=[name]
    inn=data.get('inn');kpp=data.get('kpp')
    if inn:parts.append('ИНН '+str(inn)+((' / КПП '+str(kpp)) if kpp else ''))
    if data.get('legal_address'):parts.append(str(data['legal_address']))
    bank=[]
    if data.get('bank_name'):bank.append(str(data['bank_name']))
    if data.get('bik'):bank.append('БИК '+str(data['bik']))
    if bank:parts.append(', '.join(bank))
    accounts=[]
    if data.get('settlement_account'):accounts.append('р/с '+str(data['settlement_account']))
    if data.get('correspondent_account'):accounts.append('к/с '+str(data['correspondent_account']))
    if accounts:parts.append(' · '.join(accounts))
    return parts


def _invoice_header(doc,font,page_w,page_h,invoice):
    margin=42;y=page_h-42
    doc.setFillColorRGB(.043,.369,.843)
    doc.roundRect(margin,y-34,page_w-margin*2,34,7,fill=1,stroke=0)
    doc.setFillColorRGB(1,1,1);doc.setFont(font,15)
    doc.drawString(margin+14,y-22,'PORTAL')
    doc.setFillColorRGB(.07,.11,.18);doc.setFont(font,17)
    number=_clean(invoice.get('number') or invoice.get('id') or '')
    created=str(invoice.get('created_at',''))[:10]
    title='Счёт на оплату'
    if number:title+=' № '+number
    if created:title+=' от '+created
    y-=58;doc.drawString(margin,y,title)
    return y-22


def _party_block(doc,font,page_w,y,label,data,fallback):
    margin=42;width=page_w-margin*2
    lines=_invoice_party(data,fallback)
    needed=24+sum(13*len(_wrap(line,font,9.5,width-20)) for line in lines)+8
    doc.setStrokeColorRGB(.83,.87,.92);doc.setFillColorRGB(.97,.98,1)
    doc.roundRect(margin,y-needed,width,needed,6,fill=1,stroke=1)
    doc.setFillColorRGB(.35,.42,.52);doc.setFont(font,8.5)
    doc.drawString(margin+10,y-16,label.upper())
    cy=y-31
    doc.setFillColorRGB(.08,.11,.17)
    for index,line in enumerate(lines):
        size=10.5 if index==0 else 9.5
        doc.setFont(font,size)
        for wrapped in _wrap(line,font,size,width-20):
            doc.drawString(margin+10,cy,wrapped);cy-=13
    return y-needed-10


def _table_header(doc,font,y,widths):
    margin=42;height=25
    doc.setFillColorRGB(.043,.369,.843)
    doc.rect(margin,y-height,sum(widths),height,fill=1,stroke=0)
    labels=('№','Услуга','Кол-во','Цена, ₽','Сумма, ₽')
    x=margin
    doc.setFillColorRGB(1,1,1);doc.setFont(font,8.5)
    for label,width in zip(labels,widths):
        doc.drawCentredString(x+width/2,y-16,label);x+=width
    return y-height


def invoice_pdf(company,client,invoice,operations):
    font=_font();out=BytesIO();page_w,page_h=A4
    doc=canvas.Canvas(out,pagesize=A4,pageCompression=1,invariant=1)
    number=_clean(invoice.get('number') or invoice.get('id') or '')
    doc.setTitle(('Счёт на оплату '+number).strip())
    margin=42;usable=page_w-margin*2
    widths=(28,usable-28-64-78-88,64,78,88)

    def new_page(first=False):
        if not first:doc.showPage()
        y=_invoice_header(doc,font,page_w,page_h,invoice)
        return y

    y=new_page(True)
    y=_party_block(doc,font,page_w,y,'Исполнитель',company,'PORTAL')
    y=_party_block(doc,font,page_w,y,'Покупатель',client,'Клиент')
    if invoice.get('due_at'):
        doc.setFillColorRGB(.35,.42,.52);doc.setFont(font,9)
        doc.drawString(margin,y,'Срок оплаты: '+str(invoice['due_at'])[:10]);y-=20
    y=_table_header(doc,font,y,widths)

    lines=invoice.get('lines',[])
    for index,line in enumerate(lines,1):
        operation=line.get('operation_name') or operations.get(line.get('operation_id'),'')
        name_lines=_wrap(operation,font,9,widths[1]-12)
        row_h=max(28,10+13*len(name_lines))
        if y-row_h<115:
            y=new_page()
            y=_table_header(doc,font,y,widths)
        doc.setStrokeColorRGB(.84,.87,.91)
        doc.setFillColorRGB(1,1,1)
        doc.rect(margin,y-row_h,sum(widths),row_h,fill=1,stroke=1)
        x=margin
        for width in widths[:-1]:
            x+=width;doc.line(x,y,x,y-row_h)
        doc.setFillColorRGB(.08,.11,.17);doc.setFont(font,9)
        doc.drawCentredString(margin+widths[0]/2,y-17,str(index))
        x_name=margin+widths[0]+6;cy=y-16
        for wrapped in name_lines:
            doc.drawString(x_name,cy,wrapped);cy-=13
        x_qty=margin+widths[0]+widths[1]
        doc.drawRightString(x_qty+widths[2]-7,y-17,str(line['quantity']))
        x_price=x_qty+widths[2]
        doc.drawRightString(x_price+widths[3]-7,y-17,f'{line["client_rate"]/100:.2f}')
        x_sum=x_price+widths[3]
        doc.drawRightString(x_sum+widths[4]-7,y-17,f'{line["amount"]/100:.2f}')
        y-=row_h

    if y<125:
        y=new_page()
    y-=14
    total=invoice.get('amount',sum(line.get('amount',0) for line in lines))
    doc.setFillColorRGB(.08,.11,.17);doc.setFont(font,11)
    doc.drawRightString(page_w-margin-95,y,'Итого:')
    doc.setFont(font,13);doc.drawRightString(page_w-margin,y,f'{total/100:.2f} ₽')
    y-=24
    tax=_clean(company.get('tax_info'))
    if tax:
        doc.setFillColorRGB(.35,.42,.52);doc.setFont(font,9)
        for wrapped in _wrap(tax,font,9,usable):
            doc.drawString(margin,y,wrapped);y-=12
    y-=14
    doc.setStrokeColorRGB(.75,.79,.84);doc.line(margin,y,margin+190,y)
    doc.setFillColorRGB(.35,.42,.52);doc.setFont(font,8.5)
    responsible=company.get('director') or company.get('contact_person') or 'Ответственный'
    doc.drawString(margin,y-13,'Ответственный: '+_clean(responsible))
    doc.drawRightString(page_w-margin,y-13,'Сформировано в PORTAL')
    doc.save()
    return out.getvalue()


def payroll_slip_pdf(company,period,employee,summary,issue_date):
    start,end=period['period_start'],period['period_end']
    rows=[('Компания',company.get('name','')),
      ('Расчётный лист',''),
      ('Период / год',f'{start} — {end} / {start[:4]}'),
      ('ФИО',employee.get('display_name','')),
      ('Итоговая сумма, RUB',f'{summary["balance"]/100:.2f}'),
      ('Дата',issue_date),
      ('Управляющий компанией','____________________________'),
      ('Управляющий подразделением','____________________________'),
      ('Сотрудник','____________________________')]
    return _write('Расчётный лист',rows)
