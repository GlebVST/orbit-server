import copy
import os
import string
import StringIO
import logging
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

logger = logging.getLogger('api.pdf')

SAMPLE_CERTIFICATE_NAME = "Sample Only - Start Subscription to Receive Official CME"
# files in settings.PDF_TEMPLATES_DIR
BLANK_FILE = 'blank.pdf'

FONT_CHARACTER_TABLES = {}
for font_file in glob('{0}/fonts/*.ttf'.format(settings.PDF_TEMPLATES_DIR)):
    font_name = os.path.basename(os.path.splitext(font_file)[0])
    ttf = TTFont(font_name, font_file)
    FONT_CHARACTER_TABLES[font_name] = ttf.face.charToGlyph.keys()
    pdfmetrics.registerFont(TTFont(font_name, font_file))

SHORTEST_DATE_FORMAT = 'n/j/y' # day/month without leading zeroes
LONG_DATE_FORMAT = 'd F Y' # full month name

WIDTH = 297  # width in mm (A4)
HEIGHT = 210  # hight in mm (A4)

class BaseCertificate(object):

    def __init__(self, certificate):
        """
        certificate: Certificate instance
        """
        self.certificate = certificate
        # overlayBuffer is overlaid on the template certificate.
        self.overlayBuffer = StringIO.StringIO()
        self.tplfileName = None
        # common styles
        addMapping('OpenSans-Light', 0, 0, 'OpenSans-Light')
        addMapping('OpenSans-Light', 0, 1, 'OpenSans-LightItalic')
        addMapping('OpenSans-Light', 1, 0, 'OpenSans-Bold')
        addMapping('OpenSans-Regular', 0, 0, 'OpenSans-Regular')
        addMapping('OpenSans-Regular', 0, 1, 'OpenSans-Italic')
        addMapping('OpenSans-Regular', 1, 0, 'OpenSans-Bold')
        addMapping('OpenSans-Regular', 1, 1, 'OpenSans-BoldItalic')
        self.styleOpenSans = ParagraphStyle(name="opensans-regular", leading=10, fontName='OpenSans-Bold')
        self.styleOpenSansLight = ParagraphStyle(name="opensans-light", leading=10, fontName='OpenSans-Regular')

    def makeCmeCertificate(self):
        """Generate CME certificate by merging self.overlayBuffer with
            an existing PDF template.
    """
        tplfilePath = os.path.join(settings.PDF_TEMPLATES_DIR, self.tplfileName)
        blankfilePath = os.path.join(settings.PDF_TEMPLATES_DIR, BLANK_FILE)
        output = StringIO.StringIO()
        try:
            overlayReader = PdfFileReader(self.overlayBuffer, strict=False)
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

    def cleanup(self):
        self.overlayBuffer.close()

    def makeCmeCertOverlay(self):
        """This method should be implemented by a subclass"""
        raise NotImplementedError

class MDCertificate(BaseCertificate):
    """Handles both MD/DO certificate (via verified) and participation certificate for non-verified.
    Note: NurseCertificate should be used for nurses (RN/NP).
    """

    # files in settings.PDF_TEMPLATES_DIR
    CERT_TEMPLATE_VERIFIED = 'cme-certificate-verified.pdf'
    CERT_TEMPLATE_PARTICIPATION = 'cme-certificate-participation.pdf'

    PARTICIPATION_TEXT_TEMPLATE = string.Template("""This activity was designated for ${numCredits} <i>AMA PRA Category 1 Credits<sup>TM</sup></i>. This activity has been planned and implemented in<br/> accordance with the accreditation requirements and policies of the Accreditation Council for Continuing Medical Education<br/> (ACCME) through the joint providership of Tufts University School of Medicine (TUSM) and Orbit. TUSM is accredited by the<br/> ACCME to provide continuing education for physicians. Activity Original Release Date: ${releaseDate}, Activity Expiration Date: ${expireDate}.""")

    VERIFIED_TEXT_TEMPLATE = string.Template("""This activity has been planned and implemented in accordance with the accreditation requirements and policies of the<br/> Accreditation Council for Continuing Medical Education (ACCME) through the joint providership of Tufts University<br/> School of Medicine (TUSM) and Orbit. TUSM is accredited by the ACCME to provide continuing medical education for<br/> physicians. Activity Original Release Date: ${releaseDate}, Activity Expiration Date: ${expireDate}.""")

    CREDIT_TEXT_VERIFIED_TEMPLATE = string.Template("${numCredits} <i>AMA PRA Category 1 Credits<sup>TM</sup></i> Awarded")
    SPECIALTY_CREDIT_TEXT_VERIFIED_TEMPLATE = string.Template("${numCredits} <i>AMA PRA Category 1 Credits<sup>TM</sup></i> Awarded in ${tag}")

    CREDIT_TEXT_PARTICIPATION_TEMPLATE = string.Template("${numCredits} Hours of Participation Awarded")
    SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE = string.Template("${numCredits} Hours of Participation Awarded in ${tag}")

    def __init__(self, certificate, verified):
        """
        verified: bool  If True: use verified template, else use participation template.
        """
        BaseCertificate.__init__(self, certificate)
        self.verified = verified
        if verified:
            self.tplfileName = self.__class__.CERT_TEMPLATE_VERIFIED
        else:
            self.tplfileName = self.__class__.CERT_TEMPLATE_PARTICIPATION
        self.releaseDate = settings.CERT_ORIGINAL_RELEASE_DATE
        self.expireDate = settings.CERT_EXPIRE_DATE

    def getCreditText(self):
        """Returns string for credit text"""
        if self.certificate.tag:
            if self.verified:
                tpl = self.__class__.SPECIALTY_CREDIT_TEXT_VERIFIED_TEMPLATE
            else:
                tpl = self.__class__.SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE
            return tpl.substitute({
                'numCredits': self.certificate.credits,
                'tag': self.certificate.tag.description
                })
        else:
            if self.verified:
                tpl = self.__class__.CREDIT_TEXT_VERIFIED_TEMPLATE
            else:
                tpl = self.__class__.CREDIT_TEXT_PARTICIPATION_TEMPLATE
            return tpl.substitute({
                'numCredits': self.certificate.credits
                })

    def makeCertNameParagraph(self):
        """If self.certificate.name == SAMPLE_CERTIFICATE_NAME, then write it as a link,
        else write it normal text
        Returns: Paragraph object to be drawn on the overlay
        """
        if self.certificate.name == SAMPLE_CERTIFICATE_NAME:
            self.styleOpenSans.textColor = colors.Color(0, 0, 0.9) # blue
            text = """<u><a href="https://{0}{1}">{0}</a></u>""".format(
                    settings.SERVER_HOSTNAME,
                    settings.UI_LINK_SUBSCRIPTION,
                    self.certificate.name)
            paragraph = Paragraph(text, self.styleOpenSans)
        else:
            paragraph = Paragraph(self.certificate.name, self.styleOpenSans)
        return paragraph

    def makeCmeCertOverlay(self):
        """Populate self.overlayBuffer"""
        pdfCanvas = canvas.Canvas(self.overlayBuffer, pagesize=landscape(A4))
        # initialize font styles
        self.styleOpenSans.fontSize = 20
        self.styleOpenSans.leading = 10
        self.styleOpenSans.textColor = colors.Color(0, 0, 0)
        self.styleOpenSans.alignment = TA_LEFT

        self.styleOpenSansLight.fontSize = 12
        self.styleOpenSansLight.leading = 10
        self.styleOpenSansLight.textColor = colors.Color(
            0.1, 0.1, 0.1)
        self.styleOpenSansLight.alignment = TA_LEFT

        # CERT NAME
        paragraph = self.makeCertNameParagraph()
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12 * mm, 120 * mm)
        # return color to normal in case it was changed
        self.styleOpenSans.textColor = colors.Color(0, 0, 0)

        # dates
        paragraph = Paragraph("Total credits earned between {0} - {1}".format(
            DateFormat(self.certificate.startDate).format(LONG_DATE_FORMAT),
            DateFormat(self.certificate.endDate).format(LONG_DATE_FORMAT)),
            self.styleOpenSansLight)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 65 * mm)

        # credits
        self.styleOpenSans.fontSize = 14
        creditText = self.getCreditText()
        paragraph = Paragraph(creditText, self.styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 53.83 * mm)

        # issued
        self.styleOpenSans.fontSize = 9
        paragraph = Paragraph("Issued: {0}".format(
            DateFormat(self.certificate.created).format(LONG_DATE_FORMAT)), self.styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 12 * mm)

        # Link to this certificate
        certUrl = self.certificate.getAccessUrl()
        paragraph = Paragraph(certUrl, self.styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 127.5 * mm, 12 * mm)

        # Large description text block with variable substitutions
        self.styleOpenSansLight.fontSize = 10.5
        self.styleOpenSansLight.leading = 15
        self.styleOpenSansLight.textColor = colors.Color(
            0.6, 0.6, 0.6)
        if not self.verified:
            descriptionText = self.__class__.PARTICIPATION_TEXT_TEMPLATE.substitute({
                'numCredits': self.certificate.credits,
                'releaseDate': DateFormat(self.releaseDate).format(SHORTEST_DATE_FORMAT),
                'expireDate': DateFormat(self.expireDate).format(SHORTEST_DATE_FORMAT)
                })
        else:
            descriptionText = self.__class__.VERIFIED_TEXT_TEMPLATE.substitute({
                'releaseDate': DateFormat(self.releaseDate).format(SHORTEST_DATE_FORMAT),
                'expireDate': DateFormat(self.expireDate).format(SHORTEST_DATE_FORMAT)
            })
        paragraph = Paragraph(descriptionText, self.styleOpenSansLight)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 24 * mm)

        pdfCanvas.showPage()
        pdfCanvas.save() # write to overlayBuffer


class NurseCertificate(BaseCertificate):
    """Used for Nurse certificate."""

    # files in settings.PDF_TEMPLATES_DIR
    CERT_TEMPLATE = 'nurse-cme-certificate.pdf'

    CREDIT_TEXT_PARTICIPATION_TEMPLATE = string.Template("${numCredits} Contact Hours / Hours of Participation Awarded")
    SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE = string.Template("${numCredits} Contact Hours / Hours of Participation Awarded in ${tag}")

    PARTICIPATION_TEXT_TEMPLATE = string.Template("""This activity is designated for ${numCredits} Contact Hours by ${companyName} (${companyCep}), 265 Cambridge Ave, #61224,<br />Palo Alto CA 94306. This certificate must be retained by the nurse licensee for a period of four years after the course ends.<br />This activity was designated for ${numCredits} <i>AMA PRA Category 1 Credits<sup>TM</sup></i>. This activity has been planned and implemented in accordance<br/> with the accreditation requirements and policies of the Accreditation Council for Continuing Medical Education (ACCME)<br/> through the joint providership of Tufts University School of Medicine (TUSM) and Orbit. TUSM is accredited by the ACCME to<br/> provide continuing education for physicians. Activity Original Release Date: ${releaseDate}, Activity Expiration Date: ${expireDate}.""")

    def __init__(self, certificate):
        super(NurseCertificate, self).__init__(certificate)
        self.tplfileName = self.__class__.CERT_TEMPLATE
        self.releaseDate = settings.CERT_ORIGINAL_RELEASE_DATE
        self.expireDate = settings.CERT_EXPIRE_DATE
        if not certificate.state_license:
            raise ValueError('NurseCertificate requires certificate to have non-null state_license.')

    def getCreditText(self):
        """Returns string for credit text"""
        if self.certificate.tag:
            tpl = self.__class__.SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE
            return tpl.substitute({
                'numCredits': self.certificate.credits,
                'tag': self.certificate.tag.description
                })
        else:
            tpl = self.__class__.CREDIT_TEXT_PARTICIPATION_TEMPLATE
            return tpl.substitute({
                'numCredits': self.certificate.credits
                })

    def makeCertNameParagraph(self):
        """If self.certificate.name == SAMPLE_CERTIFICATE_NAME, then write it as a link,
        else write it normal text
        Returns: Paragraph object to be drawn on the overlay
        """
        if self.certificate.name == SAMPLE_CERTIFICATE_NAME:
            self.styleOpenSans.textColor = colors.Color(0, 0, 0.9) # blue
            text = """<u><a href="https://{0}{1}">{0}</a></u>""".format(
                    settings.SERVER_HOSTNAME,
                    settings.UI_LINK_SUBSCRIPTION,
                    self.certificate.name)
        else:
            text = "{0} <font size=13>({1})</font>".format(
                    self.certificate.name,
                    self.certificate.state_license.getLabelForCertificate())
        paragraph = Paragraph(text, self.styleOpenSans)
        return paragraph


    def makeCmeCertOverlay(self):
        """Populate self.overlayBuffer"""
        pdfCanvas = canvas.Canvas(self.overlayBuffer, pagesize=landscape(A4))
        # initialize font styles
        self.styleOpenSans.fontSize = 20
        self.styleOpenSans.leading = 10
        self.styleOpenSans.textColor = colors.Color(0, 0, 0)
        self.styleOpenSans.alignment = TA_LEFT

        self.styleOpenSansLight.fontSize = 12
        self.styleOpenSansLight.leading = 10
        self.styleOpenSansLight.textColor = colors.Color(
            0.1, 0.1, 0.1)
        self.styleOpenSansLight.alignment = TA_LEFT

        # CERT NAME
        paragraph = self.makeCertNameParagraph()
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12 * mm, 120 * mm)
        # return color to normal in case it was changed
        self.styleOpenSans.textColor = colors.Color(0, 0, 0)

        # dates
        paragraph = Paragraph("Total credits earned between {0} - {1}".format(
            DateFormat(self.certificate.startDate).format(LONG_DATE_FORMAT),
            DateFormat(self.certificate.endDate).format(LONG_DATE_FORMAT)),
            self.styleOpenSansLight)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 75 * mm)

        # credits
        self.styleOpenSans.fontSize = 14
        creditText = self.getCreditText()
        paragraph = Paragraph(creditText, self.styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 63.83 * mm)

        # issued
        self.styleOpenSans.fontSize = 9
        paragraph = Paragraph("Issued: {0}".format(
            DateFormat(self.certificate.created).format(LONG_DATE_FORMAT)), self.styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.4 * mm, 12 * mm)

        # Link to this certificate
        certUrl = self.certificate.getAccessUrl()
        paragraph = Paragraph(certUrl, self.styleOpenSans)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 114.5 * mm, 12 * mm)

        # Large description text block with variable substitutions
        self.styleOpenSansLight.fontSize = 10.5
        self.styleOpenSansLight.leading = 15
        self.styleOpenSansLight.textColor = colors.Color(
            0.6, 0.6, 0.6)
        descriptionText = self.__class__.PARTICIPATION_TEXT_TEMPLATE.substitute({
            'numCredits': self.certificate.credits,
            'companyName': settings.COMPANY_NAME,
            'companyCep': settings.COMPANY_BRN_CEP,
            'releaseDate': DateFormat(self.releaseDate).format(SHORTEST_DATE_FORMAT),
            'expireDate': DateFormat(self.expireDate).format(SHORTEST_DATE_FORMAT)
        })
        paragraph = Paragraph(descriptionText, self.styleOpenSansLight)
        paragraph.wrapOn(pdfCanvas, WIDTH * mm, HEIGHT * mm)
        paragraph.drawOn(pdfCanvas, 12.2 * mm, 24 * mm)

        pdfCanvas.showPage()
        pdfCanvas.save() # write to overlayBuffer


#
# Orbit Story certificates
#

class MDStoryCertificate(MDCertificate):
    """Handles both MD/DO Orbit Story certificate (via verified) and participation certificate for non-verified.
    Note: NurseStoryCertificate should be used for nurses (RN/NP).
    """
    # files in settings.PDF_TEMPLATES_DIR
    CERT_TEMPLATE_VERIFIED = 'story-certificate-verified.pdf'
    CERT_TEMPLATE_PARTICIPATION = 'story-certificate-participation.pdf'

    SPECIALTY_CREDIT_TEXT_VERIFIED_TEMPLATE = string.Template("${numCredits} <i>AMA PRA Category 1 Credits<sup>TM</sup></i> Awarded in Self Assessment")
    SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE = string.Template("${numCredits} Hours of Participation Awarded in Self Assessment")

    def __init__(self, certificate, verified):
        """
        verified: bool  If True: use verified template, else use participation template.
        """
        MDCertificate.__init__(self, certificate, verified)
        self.releaseDate = settings.STORY_CERT_ORIGINAL_RELEASE_DATE
        self.expireDate = settings.STORY_CERT_EXPIRE_DATE

    def getCreditText(self):
        """Returns string for credit text"""
        if self.verified:
            tpl = self.__class__.SPECIALTY_CREDIT_TEXT_VERIFIED_TEMPLATE
        else:
            tpl = self.__class__.SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE
        return tpl.substitute({
            'numCredits': self.certificate.credits
        })


class NurseStoryCertificate(NurseCertificate):
    """Used for Nurse Orbit Story certificate."""

    # files in settings.PDF_TEMPLATES_DIR
    CERT_TEMPLATE = 'story-certificate-nurse.pdf'

    SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE = string.Template("${numCredits} Contact Hours / Hours of Participation Awarded in Self Assessment")

    def __init__(self, certificate):
        NurseCertificate.__init__(self, certificate)
        self.releaseDate = settings.STORY_CERT_ORIGINAL_RELEASE_DATE
        self.expireDate = settings.STORY_CERT_EXPIRE_DATE


    def getCreditText(self):
        """Returns string for credit text"""
        tpl = self.__class__.SPECIALTY_CREDIT_TEXT_PARTICIPATION_TEMPLATE
        return tpl.substitute({
            'numCredits': self.certificate.credits
        })
