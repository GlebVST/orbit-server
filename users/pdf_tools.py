import copy
import os
import string
import StringIO
from glob import glob

from django.conf import settings
from django.utils.dateformat import DateFormat

from PyPDF2 import PdfFileWriter, PdfFileReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# files in settings.PDF_TEMPLATES_DIR
CERT_TEMPLATE_VERIFIED = 'cme-certificate-verified.pdf'
CERT_TEMPLATE_PARTICIPATION = 'cme-certificate-participation.pdf'
BLANK_FILE = 'blank.pdf'

PARTICIPATION_TEXT_TEMPLATE = string.Template("""This activity was designated for ${numCredits} <i>AMA PRA Category 1 Credit<sup>TM</sup></i>. This activity has been planned and implemented <br/>in accordance with the Essential Areas and policies of the Accreditation Council for Continuing Medical Education<br/> through the joint providership Tufts University School of Medicine (TUSM) and Orbit. <br/>TUSM is accredited with commendation by the ACCME to provide continuing education for physicians.""")

CREDIT_TEXT_VERIFIED = "<i>AMA PRA Category 1 Credits<sup>TM</sup></i> Awarded"
CREDIT_TEXT_PARTICIPATION = "Hours of Participation Awarded"

SAMPLE_CERTIFICATE_NAME = "Sample Only - Upgrade to Receive Official CME"

FONT_CHARACTER_TABLES = {}
for font_file in glob('{0}/fonts/*.ttf'.format(settings.PDF_TEMPLATES_DIR)):
    font_name = os.path.basename(os.path.splitext(font_file)[0])
    ttf = TTFont(font_name, font_file)
    FONT_CHARACTER_TABLES[font_name] = ttf.face.charToGlyph.keys()
    pdfmetrics.registerFont(TTFont(font_name, font_file))

def makeCmeCertOverlay(verified, certificate):
    """This file is overlaid on the template certificate.
        verified: bool  verified vs. participation
        certificate: Certificate instance
    Returns StringIO object
    """
    overlayBuffer = StringIO.StringIO()
    pdfCanvas = canvas.Canvas(overlayBuffer, pagesize=landscape(A4))
    addMapping('OpenSans-Light', 0, 0, 'OpenSans-Light')
    addMapping('OpenSans-Light', 0, 1, 'OpenSans-LightItalic')
    addMapping('OpenSans-Light', 1, 0, 'OpenSans-Bold')
    addMapping('OpenSans-Regular', 0, 0, 'OpenSans-Regular')
    addMapping('OpenSans-Regular', 0, 1, 'OpenSans-Italic')
    addMapping('OpenSans-Regular', 1, 0, 'OpenSans-Bold')
    addMapping('OpenSans-Regular', 1, 1, 'OpenSans-BoldItalic')
    styleOpenSans = ParagraphStyle(name="opensans-regular", leading=10, fontName='OpenSans-Bold')
    styleOpenSansLight = ParagraphStyle(name="opensans-light", leading=10, fontName='OpenSans-Regular')

    WIDTH = 297  # width in mm (A4)
    HEIGHT = 210  # hight in mm (A4)
    LEFT_INDENT = 49  # mm from the left side to write the text
    RIGHT_INDENT = 49  # mm from the right side for the CERTIFICATE
    # CLIENT NAME
    styleOpenSans.fontSize = 20
    styleOpenSans.leading = 10
    styleOpenSans.textColor = colors.Color(0, 0, 0)
    styleOpenSans.alignment = TA_LEFT

    styleOpenSansLight.fontSize = 12
    styleOpenSansLight.leading = 10
    styleOpenSansLight.textColor = colors.Color(
        0.1, 0.1, 0.1)
    styleOpenSansLight.alignment = TA_LEFT

    paragraph = Paragraph(certificate.name, styleOpenSans)
    paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
    paragraph.drawOn(pdfCanvas, 12 * mm, 120 * mm)

    # dates
    paragraph = Paragraph("{0} - {1}".format(
        DateFormat(certificate.startDate).format('d F Y'),
        DateFormat(certificate.endDate).format('d F Y')),
        styleOpenSansLight)
    paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
    paragraph.drawOn(pdfCanvas, 12.2 * mm, 65 * mm)

    # credits
    styleOpenSans.fontSize = 14
    creditText = CREDIT_TEXT_VERIFIED if verified else CREDIT_TEXT_PARTICIPATION
    paragraph = Paragraph("{0} {1}".format(certificate.credits, creditText), styleOpenSans)
    paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
    paragraph.drawOn(pdfCanvas, 12.2 * mm, 53.83 * mm)

    # issued
    styleOpenSans.fontSize = 9
    paragraph = Paragraph("Issued: {0}".format(DateFormat(certificate.created).format('d F Y')), styleOpenSans)
    paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
    paragraph.drawOn(pdfCanvas, 12.2 * mm, 12 * mm)

    # Link to this certificate
    certUrl = certificate.getAccessUrl()
    paragraph = Paragraph(certUrl, styleOpenSans)
    paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
    paragraph.drawOn(pdfCanvas, 127.5 * mm, 12 * mm)

    # Some extra text for participation
    if not verified:
        styleOpenSansLight.fontSize = 10.5
        styleOpenSansLight.leading = 15
        styleOpenSansLight.textColor = colors.Color(
            0.5, 0.5, 0.5)
        participationText = PARTICIPATION_TEXT_TEMPLATE.substitute({'numCredits': certificate.credits})
        paragraph = Paragraph(participationText, styleOpenSansLight)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 24 * mm)
    pdfCanvas.showPage()
    pdfCanvas.save() # write to overlayBuffer
    return overlayBuffer


def makeCmeCertificate(overlayBuffer, verified):
    """Generate CME certificate by merging the overlayBuffer with
        an existing PDF template.
        overlayBuffer: StringIO object
        verified: bool  If True: use verified template, else
            use participation template.
    """
    tplfileName = CERT_TEMPLATE_VERIFIED if verified else CERT_TEMPLATE_PARTICIPATION
    tplfilePath = os.path.join(settings.PDF_TEMPLATES_DIR, tplfileName)
    blankfilePath = os.path.join(settings.PDF_TEMPLATES_DIR, BLANK_FILE)
    output = StringIO.StringIO()
    try:
        overlayReader = PdfFileReader(overlayBuffer, strict=False)
        with open(tplfilePath, 'rb') as f_tpl, open(blankfilePath, 'rb') as f_blank:
            templateReader = PdfFileReader(f_tpl, strict=False)
            blankReader = PdfFileReader(f_blank, strict=False)
            # make copy of blank page
            mergedPage = copy.copy(blankReader.getPage(0))
            # add template
            mergedPage.mergePage(templateReader.getPage(0))
            # add overlay
            mergedPage.mergePage(overlayReader.getPage(0))
            # write to output
            writer = PdfFileWriter()
            writer.addPage(mergedPage)
            writer.write(output)
    except IOError, e:
        logger.exception('makeCmeCertificate IOError')
    except Exception, e:
        logger.exception('makeCmeCertificate exception')
    finally:
        return output.getvalue() # return empty str if no write
