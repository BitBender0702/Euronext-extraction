import re
import fitz
from datetime import datetime

class MetadataExtractor:

    def __init__(self):

        self.month_names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 
                            'November', 'December']
        self.regexes = self.GetRegexes()

    def GetRegexes(self):

        annual_report_regex = r'(?<!-)a\s?n\s?n\s?u\s?[ae]\s?l|(?<!-)year\s+end(?:ed|ing)|(?:12|twelve)\s+months\s+end(?:ed|ing)' \
                              r'|31\s+december|december\s+31|full(?:\s+|-)year|(?<!\w)årsrapport|(?<!\w)jaarverslag|fy'
        annual_report_regex = re.compile(annual_report_regex, re.IGNORECASE)

        halfyear_report_regex = r'half(?:\s+|-)year|semi(?:\s+|-)annual|(?:6|six)\s+months\s+end(?:ed|ing)|six-month\s+period' \
                                r'\s+ended|30\s+june|june\s+30|semestriel|halvårsrapport|halfjaarverslag|[12]h|h[12]'
        halfyear_report_regex = re.compile(halfyear_report_regex, re.IGNORECASE)

        quarter_report_regex = r'quarter|(?:3|three)\s+months\s+end(?:ed|ing)|trimestriel|kvartalsrapport|kwartaalrapport' \
                               r'|[1234]q|q[1234]'
        quarter_report_regex = re.compile(quarter_report_regex, re.IGNORECASE)

        month_names = '|'.join(self.month_names)
        year_end_regex = r'(?<!half\s)(?<!half-)(?:year|12\s+months?|twelve(?:\s+|-)months?)(?:\s+period)?\s+end(?:ed|ing)' \
                         r'(?:\s+on|\s+as\s+of)?[\s:]+(\d{1,2})\s+(%s)|(?<!half\s)(?<!half-)(?:year|12(?:\s+|-)months?' \
                         r'|twelve\s+months?)(?:\s+period)?\s+end(?:ed|ing)(?:\s+on|\s+as\s+of)?[\s:]+(%s)\s+(\d{1,2})' \
                         r'|year(?:\s+|-)end\s+(\d{1,2})[\/\-](\d{1,2})' % (month_names, month_names)
        year_end_regex = re.compile(year_end_regex, re.IGNORECASE)

        auditor_regex = r'Ernst\s+\&\s+Young|EY\s+Bedrijfsrevisoren|KPMG|Deloitte|PricewaterhouseCoopers|PwC|Grant\s+Thornton'
        auditor_regex = re.compile(auditor_regex, re.IGNORECASE)

        return annual_report_regex, halfyear_report_regex, quarter_report_regex, year_end_regex, auditor_regex

    def ExtractPeriodData(self, date, text):

        regexes, min_position, min_idx = self.regexes[:3], 1e6, 3
        for idx, regex in enumerate(regexes):
            match = regex.search(text)
            if match is not None:
                position = match.start()
                if position < min_position:
                    min_position, min_idx = position, idx

        report_type = ['annual', 'halfyear', 'quarter', None][min_idx]
        year, data = date.split('-')[0], [None, None, 'N/A']
        date = datetime.strptime(date, '%Y-%m-%d')
        days_elapsed = (date - datetime(date.year, 1, 1)).days

        if report_type == 'annual': 
            data = [True, year, 'FY']

        elif report_type == 'halfyear':
            period = 'H1' if 91 <= days_elapsed <= 273 else 'H2'
            data = [False, year, period]

        elif report_type == 'quarter':
            if 45 <= days_elapsed <= 136:
                period = 'Q1'
            elif 137 <= days_elapsed <= 228:
                period = 'Q2'
            elif 229 <= days_elapsed <= 319:
                period = 'Q3'
            else:
                period = 'Q4'

            data = [False, year, period]

        return data

    def ExtractYearEnd(self, text):

        year_end_regex = self.regexes[3]
        match = year_end_regex.search(text)
        if match is None:
            return None

        groups = match.groups()
        if groups[0] and groups[1]:
            year_end = '%s %s' % (groups[1].title(), groups[0])

        elif groups[2] and groups[3]:
            year_end = '%s %s' % (groups[2].title(), groups[3])

        elif groups[4] and groups[5]:
            numbers = int(groups[4]), int(groups[5])
            if 1 <= numbers[0] <= 12:
                month, day = self.month_names[numbers[0] - 1], numbers[1]
                year_end = '%s %s' % (month, day)

            elif 1 <= numbers[1] <= 12:
                month, day = self.month_names[numbers[1] - 1], numbers[0]
                year_end = '%s %s' % (month, day)

            else:
                year_end = None

        return year_end

    def ExtractAuditorName(self, text):

        auditor_regex = self.regexes[4]
        match = auditor_regex.search(text)
        if match is None:
            return None

        return match.group()

    def __call__(self, statement_url, document, date):

        metadata = [None] * 5
        try:
            document = fitz.open(stream=document, filetype='pdf')
        except:
            return metadata

        for page in document:
            text = page.get_text()
            if metadata[0] is None:
                metadata[0:3] = self.ExtractPeriodData(date, text)
            
            if metadata[3] is None:
                metadata[3] = self.ExtractYearEnd(text)

            if metadata[4] is None:
                metadata[4] = self.ExtractAuditorName(text)

            if all(item is not None for item in metadata):
                break

        if metadata[0] is None:
            metadata[0:3] = self.ExtractPeriodData(date, statement_url)

        return metadata
