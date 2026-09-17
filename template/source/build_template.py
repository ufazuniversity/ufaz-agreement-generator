"""Fillable (AcroForm) version of the UFAZ IT Device Issuance Agreement."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Flowable)
from reportlab.platypus import Image as RLImage
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from PIL import Image as PILImage
import sys

OUT = sys.argv[1]
LOGO = sys.argv[2]

# ---------- Fonts ----------
LIB = "/usr/share/fonts/truetype/liberation/"
pdfmetrics.registerFont(TTFont("Sans", LIB + "LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Sans-B", LIB + "LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Sans-I", LIB + "LiberationSans-Italic.ttf"))
pdfmetrics.registerFont(TTFont("Sans-BI", LIB + "LiberationSans-BoldItalic.ttf"))
registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans-I", boldItalic="Sans-BI")

# ---------- Colours ----------
NAVY = colors.HexColor("#1F3A5F")
GREY = colors.HexColor("#5A5A5A")
LINE = colors.HexColor("#9AA5B1")
FILL = colors.HexColor("#EEF2F6")
FIELD_FILL = colors.HexColor("#F5F8FC")
FIELD_LINE = colors.HexColor("#8A96A3")

# ---------- Styles ----------
base = ParagraphStyle("base", fontName="Sans", fontSize=8.8, leading=11, textColor=colors.black)
small = ParagraphStyle("small", parent=base, fontSize=7.8, leading=9.6, textColor=GREY)
label = ParagraphStyle("label", parent=base, fontName="Sans-B", fontSize=8.6, leading=10.6, textColor=NAVY)
cell = ParagraphStyle("cell", parent=base, fontSize=8.6, leading=10.8)
title = ParagraphStyle("title", parent=base, fontName="Sans-B", fontSize=15, leading=18, textColor=NAVY, alignment=TA_LEFT)
meta = ParagraphStyle("meta", parent=base, fontSize=8.6, leading=12, alignment=TA_RIGHT)
sec = ParagraphStyle("sec", parent=base, fontName="Sans-B", fontSize=9.2, leading=11.5, textColor=NAVY, spaceBefore=7, spaceAfter=3)
term = ParagraphStyle("term", parent=base, fontSize=8.6, leading=10.8, leftIndent=14, firstLineIndent=-14, spaceAfter=1.5)
sig_lbl = ParagraphStyle("siglbl", parent=base, fontName="Sans-B", fontSize=9, leading=11.5, textColor=NAVY)
sig_line = ParagraphStyle("sigline", parent=base, fontSize=8.6, leading=11, textColor=GREY)

P = Paragraph
FH = 13          # text field height
CB = 9.5         # checkbox size

# ---------- Form-field flowables ----------
class TextField(Flowable):
    def __init__(self, name, width, height=FH, tooltip=None, multiline=False, fontSize=9, maxlen=200):
        super().__init__()
        self.name, self.width, self.height = name, width, height
        self.tooltip, self.multiline, self.fontSize, self.maxlen = tooltip, multiline, fontSize, maxlen
    def wrap(self, aw, ah):
        return self.width, self.height
    def draw(self):
        self.canv.acroForm.textfield(
            name=self.name, tooltip=self.tooltip or self.name,
            x=0, y=0, relative=True, width=self.width, height=self.height,
            fontName="Helvetica", fontSize=self.fontSize, textColor=colors.black,
            fillColor=FIELD_FILL, borderColor=FIELD_LINE, borderWidth=0.6, borderStyle="underlined",
            fieldFlags="multiline" if self.multiline else "", annotationFlags="print", maxlen=self.maxlen)

class CheckBox(Flowable):
    def __init__(self, name, tooltip=None, size=CB):
        super().__init__(); self.name, self.tooltip, self.size = name, tooltip, size
    def wrap(self, aw, ah):
        return self.size, self.size
    def draw(self):
        self.canv.acroForm.checkbox(
            name=self.name, tooltip=self.tooltip or self.name, x=0, y=0, relative=True, size=self.size,
            buttonStyle="check", borderColor=FIELD_LINE, borderWidth=0.8, fillColor=colors.white,
            textColor=colors.black, fieldFlags="", annotationFlags="print")

class Radio(Flowable):
    def __init__(self, group, value, tooltip=None, size=CB):
        super().__init__(); self.group, self.value, self.tooltip, self.size = group, value, tooltip, size
    def wrap(self, aw, ah):
        return self.size, self.size
    def draw(self):
        self.canv.acroForm.radio(
            name=self.group, value=self.value, tooltip=self.tooltip or self.value, x=0, y=0, relative=True,
            size=self.size, buttonStyle="check", shape="square", borderColor=FIELD_LINE, borderWidth=0.8,
            fillColor=colors.white, textColor=colors.black, fieldFlags="noToggleToOff radio",
            annotationFlags="print")

def tight(t, valign="MIDDLE"):
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("VALIGN", (0,0), (-1,-1), valign),
    ]))
    return t

import re
def tw(text, style=cell):
    plain = re.sub(r"<[^>]+>", "", text).replace("&amp;", "&")
    return stringWidth(plain, style.fontName, style.fontSize)

def labeled(text, name, avail, tooltip=None, height=FH, style=cell, multiline=False, maxlen=200):
    """'Label: [text field filling the rest of avail]'"""
    lw_ = tw(text, style) + 4
    return tight(Table([[P(text, style), TextField(name, avail - lw_, height, tooltip, multiline, maxlen=maxlen)]],
                       colWidths=[lw_, avail - lw_]))

def options(avail, items, other=None, gap=12, prefix=None):
    """Row of [widget label] pairs; items = list of (widget, label). other=(label, fieldname) adds a trailing text field."""
    cells, widths = [], []
    if prefix:
        cells.append(P(prefix, cell)); widths.append(tw(prefix) + 4)
    for w, lab in items:
        cells += [w, P(lab, cell)]
        widths += [CB + 3, tw(lab) + gap]
    if other:
        lab, name = other
        cells += [P(lab, cell)]; widths += [tw(lab) + 4]
        rest = avail - sum(widths)
        cells.append(TextField(name, rest, tooltip=lab)); widths.append(rest)
    else:
        widths[-1] = avail - sum(widths[:-1])   # let the last label absorb slack
    return tight(Table([cells], colWidths=widths))

# ---------- Document ----------
doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    leftMargin=16*mm, rightMargin=16*mm, topMargin=11*mm, bottomMargin=11*mm,
    title="Device Issuance Agreement — UFAZ IT Department",
    author="UFAZ IT Department", subject="Device issuance and return agreement (fillable form)",
)
W = A4[0] - doc.leftMargin - doc.rightMargin
story = []

# Header ---------------------------------------------------------------
iw, ih = PILImage.open(LOGO).size
logo_h = 15*mm
logo_w = logo_h * iw / ih
logo_col = logo_w + 5*mm
logo = RLImage(LOGO, width=logo_w, height=logo_h)

RW = W*0.30
hdr_right = tight(Table([
    [P("Agreement No.:", meta), TextField("agreement_no", 80, tooltip="Agreement number")],
    [P("Date:", meta), TextField("agreement_date", 80, tooltip="Date (DD/MM/YYYY)")],
], colWidths=[RW - 80 - 4, 80 + 4]))
hdr_right.setStyle(TableStyle([("BOTTOMPADDING", (0,0), (-1,0), 3), ("LEFTPADDING", (1,0), (1,-1), 4)]))

hdr = Table([[logo, P("DEVICE ISSUANCE AGREEMENT", title), hdr_right]],
            colWidths=[logo_col, W*0.70 - logo_col, RW])
hdr.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LINEBELOW", (0,0), (-1,0), 1.2, NAVY),
]))
story.append(hdr)
story.append(Spacer(1, 4))
story.append(P(
    "This Agreement is made between the <b>IT Department of the French-Azerbaijani University</b> "
    "(the “Department”) and the person named below (the “Receiver”) for the temporary issuance of "
    "university-owned IT equipment (the “Device”).", base))

# 1. Parties --------------------------------------------------------------
story.append(P("1. PARTIES", sec))
half = W/2 - 10   # cell width minus paddings
parties = Table([
    [P("ISSUER — IT Department, UFAZ", label), P("RECEIVER", label)],
    [labeled("Representative (name):", "issuer_name", half, "Issuer representative — full name"),
     labeled("Full name:", "receiver_name", half, "Receiver — full name")],
    [labeled("Position:", "issuer_position", half, "Issuer representative — position"),
     options(half, [(Radio("receiver_status", "staff", "Staff"), "Staff"),
                    (Radio("receiver_status", "teacher", "Teacher"), "Teacher"),
                    (Radio("receiver_status", "student", "Student"), "Student")], prefix="Status:")],
    [labeled("Phone / e-mail:", "issuer_contact", half, "Issuer representative — phone / e-mail"),
     labeled("Employee / Student ID No.:", "receiver_id", half, "Receiver — employee or student ID number")],
    [P("", cell), labeled("Faculty / Department:", "receiver_faculty", half, "Receiver — faculty / department")],
    [P("", cell), labeled("Phone / e-mail:", "receiver_contact", half, "Receiver — phone / e-mail")],
], colWidths=[W/2, W/2])
parties.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), FILL),
    ("BOX", (0,0), (-1,-1), 0.6, LINE),
    ("LINEBELOW", (0,0), (-1,0), 0.6, LINE),
    ("LINEAFTER", (0,0), (0,-1), 0.6, LINE),
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING", (0,0), (-1,-1), 2.0), ("BOTTOMPADDING", (0,0), (-1,-1), 2.0),
    ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(parties)

# 2. Device details ----------------------------------------------------------
story.append(P("2. DEVICE DETAILS", sec))
lw = 38*mm
avail = W - lw - 10
DATE_W = 78
dates_row = tight(Table([[
    P("Issued on:", cell), TextField("issue_date", DATE_W, tooltip="Issue date (DD/MM/YYYY)"),
    P("Return by:", cell), TextField("return_date", DATE_W, tooltip="Return date (DD/MM/YYYY)"),
    P("", cell)]],
    colWidths=[tw("Issued on:") + 4, DATE_W, tw("Return by:") + 20, DATE_W,
               avail - (tw("Issued on:") + 4 + DATE_W + tw("Return by:") + 20 + DATE_W)]))
dates_row.setStyle(TableStyle([("LEFTPADDING", (2,0), (2,0), 16)]))

dev = Table([
    [P("Device type", label),
     options(avail, [(Radio("device_type", "laptop", "Laptop"), "Laptop"),
                     (Radio("device_type", "desktop", "Desktop PC"), "Desktop PC"),
                     (Radio("device_type", "monitor", "Monitor"), "Monitor"),
                     (Radio("device_type", "other", "Other"), "Other:")],
             other=("", "device_type_other"))],
    [P("Brand &amp; model", label), TextField("device_model", avail, tooltip="Brand and model")],
    [P("Serial / Inventory No.", label), TextField("device_serial", avail, tooltip="Serial number / inventory tag")],
    [P("Accessories included", label),
     options(avail, [(CheckBox("acc_charger", "Charger"), "Charger"),
                     (CheckBox("acc_bag", "Bag"), "Bag"),
                     (CheckBox("acc_mouse", "Mouse"), "Mouse"),
                     (CheckBox("acc_keyboard", "Keyboard"), "Keyboard"),
                     (CheckBox("acc_other", "Other accessory"), "Other:")],
             other=("", "acc_other_text"))],
    [P("Condition on issue", label),
     [options(avail, [(Radio("condition", "new", "New"), "New"),
                      (Radio("condition", "good", "Good"), "Good"),
                      (Radio("condition", "used", "Used"), "Used")],
              other=("<font color='#5A5A5A'>Notes (scratches, defects, missing parts):</font>", "condition_notes"))]],
    [P("Issue date / Return by", label),
     [dates_row,
      Spacer(1, 3),
      options(avail, [(CheckBox("return_until_end", "Until the end of employment / studies"), "until the end of employment / studies"),
                      (CheckBox("return_on_request", "Upon the Department's request"), "upon the Department's request")],
              prefix="or")]],
], colWidths=[lw, W - lw])
dev.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (0,-1), FILL),
    ("GRID", (0,0), (-1,-1), 0.6, LINE),
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(dev)

# 3. Terms -----------------------------------------------------------------
story.append(P("3. TERMS AND CONDITIONS", sec))
terms = [
    "The Device remains the property of UFAZ at all times and is issued solely for work, teaching or study purposes related to the University.",
    "The Receiver confirms having received the Device, with the accessories listed, in the condition recorded in Section 2, and undertakes to <b>return it in the same condition</b>, allowing only for normal wear and tear from proper use.",
    "The Receiver shall take reasonable care of the Device, keep it secure, and shall not lend, transfer, sell, disassemble or modify it (including removing university software, security settings or asset labels) without the Department's written consent.",
    "Any loss, theft, damage or malfunction must be reported to the IT Department within <b>one (1) working day</b>. In case of theft, a copy of the police report must also be provided.",
    "If the Device or its accessories are lost, stolen, or damaged beyond normal wear and tear through the Receiver's negligence or misuse, the Receiver shall bear the cost of repair or replacement at current market value, as determined by the Department.",
    "The Device and all accessories shall be returned by the return date, upon the Department's request, or on termination of the Receiver's employment or studies, whichever occurs first. Unreturned equipment may be treated as lost under clause 5.",
    "Use of the Device is subject to the University's IT and acceptable-use policies. The Receiver is responsible for backing up personal data; the Department may erase all data on the Device upon its return.",
]
for i, t in enumerate(terms, 1):
    story.append(P(f"{i}.&nbsp;&nbsp;{t}", term))

# 4. Signatures -------------------------------------------------------------
story.append(P("4. SIGNATURES", sec))
story.append(P("By signing below, both parties confirm that the Device was issued and received as described in Section 2 and agree to the terms above.", small))
story.append(Spacer(1, 3))

sig_avail = W/2 - 14
def sig_block(heading, name_lbl, key):
    return [
        P(heading, sig_lbl),
        Spacer(1, 4),
        labeled(f"{name_lbl}:", f"sig_{key}_name", sig_avail, f"{heading} — name", style=sig_line),
        Spacer(1, 15),
        P("Signature: _______________________________________", sig_line),
        Spacer(1, 4),
        tight(Table([[P("Date:", sig_line), TextField(f"sig_{key}_date", DATE_W, tooltip="Date (DD/MM/YYYY)"), P("", cell)]],
                    colWidths=[tw("Date:", sig_line) + 4, DATE_W, sig_avail - DATE_W - tw("Date:", sig_line) - 4])),
    ]

sig = Table([[sig_block("ISSUED BY — IT Department (Giver)", "Name, position", "issuer"),
              sig_block("RECEIVED BY — Receiver", "Name", "receiver")]],
            colWidths=[W/2, W/2])
sig.setStyle(TableStyle([
    ("BOX", (0,0), (-1,-1), 0.6, LINE),
    ("LINEAFTER", (0,0), (0,-1), 0.6, LINE),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
]))
story.append(sig)

# 5. Approval ---------------------------------------------------------------
story.append(P("5. APPROVAL", sec))
story.append(P("This Agreement takes effect upon approval by the University management.", small))
story.append(Spacer(1, 3))

appr_left = [
    P("APPROVED BY", sig_lbl),
    Spacer(1, 3),
    P("Acting Executive Director:", sig_line),
    Spacer(1, 2),
    P("<b><font color='black' size='9.5'>Dr. Vazeh Asgarov, assoc. prof.</font></b>", sig_line),
]
appr_right = [
    Spacer(1, 19),
    P("Signature: _______________________________________", sig_line),
    Spacer(1, 4),
    tight(Table([[P("Date:", sig_line), TextField("approval_date", DATE_W, tooltip="Approval date (DD/MM/YYYY)"), P("", cell)]],
                colWidths=[tw("Date:", sig_line) + 4, DATE_W, sig_avail - DATE_W - tw("Date:", sig_line) - 4])),
]
appr = Table([[appr_left, appr_right]], colWidths=[W/2, W/2])
appr.setStyle(TableStyle([
    ("BOX", (0,0), (-1,-1), 0.6, LINE),
    ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F9FB")),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
]))
story.append(appr)

# Footer ---------------------------------------------------------------
def footer(canv, d):
    canv.saveState()
    canv.setFont("Sans", 7)
    canv.setFillColor(GREY)
    canv.drawString(d.leftMargin, 7*mm, "UFAZ IT Department — Device Issuance Agreement. One copy is kept by the IT Department and one by the Receiver.")
    canv.drawRightString(A4[0] - d.rightMargin, 7*mm, "Page 1 of 1")
    canv.restoreState()

doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("written", OUT)
