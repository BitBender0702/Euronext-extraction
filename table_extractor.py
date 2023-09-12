import re
import fitz
import unicodedata
from collections import OrderedDict
from datetime import datetime, timedelta
from dateutil import parser

class TableExtractor:

    def __init__(self):

        self.units_map = {'€': 'EUR', 'eur': 'EUR', 'euro': 'EUR', 'euros': 'EUR', 'd\'euros': 'EUR', 'd´euros': 'EUR', 
                          'd’euros': 'EUR', 'd‘euros': 'EUR', '$': 'USD', 'us$': 'USD', 'usd': 'USD', 'dollar': 'USD', 
                          'dollars': 'USD', 'us dollar': 'USD', 'us dollars': 'USD', '£': 'GBP', 'gbp': 'GBP', 
                          'pound': 'GBP', 'pounds': 'GBP', 'nok': 'NOK', 'norwegian krone': 'NOK', 'kroner': 'NOK', 
                          'kr': 'NOK', 'dkk': 'DKK', 'sek': 'SEK', 'pln': 'PLN', '¥': 'JPY', 'jpy': 'JPY', 'yen': 'JPY', 
                          'yens': 'JPY', 'japanese yen': 'JPY', 'japanese yens': 'JPY'}
        self.multipliers_map = {'million': 1e6, 'millions': 1e6, 'milli ons': 1e6, 'miljoen': 1e6, 'm': 1e6, 'thousand': 1e3, 
                                'thousands': 1e3, 'millier': 1e3, 'milliers': 1e3, 'mille': 1e3, 'duizend': 1e3, 'tusen': 1e3, 
                                'tusenvis': 1e3, 'k': 1e3, '\'000': 1e3, '´000': 1e3, '’000': 1e3, '‘000': 1e3, '1,000': 1e3, 
                                '1 000': 1e3, '1000': 1e3, '000': 1e3}
        self.date_regex, self.units_regex, self.parser_info = self.CreateRegexes()
        fitz.TOOLS.mupdf_display_errors(False)

    def CreateRegexes(self):

        month_names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 
                       'November', 'December', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 
                       'Nov', 'Dec', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 
                       'Octobre', 'Novembre', 'Décembre']
        class ParserInfo(parser.parserinfo):
            MONTHS = list(zip(month_names[:12], month_names[12:24], month_names[24:]))

        month_names = '|'.join(month_names)
        date_regexes = ['(?:1er|2[eè]me)\s+semestre\s+20\d{2}', '20\d{2}\s+(?:1er|2[eè]me)\s+semestre', 
                        '(?:1st|first|2nd|second)\s+half[-\s]+year\s+20\d{2}', '20\d{2}\s+(?:1st|first|2nd|second)\s+half[-\s]+year', 
                        '[SHQ]\d\s+20\d{2}', '20\d{2}\s+[SHQ]\d', '20\d{2}[\/.-]\d{1,2}[\/.-]\d{1,2}', 
                        '\d{1,2}[\/.-]\d{1,2}[\/.-]20\d{2}', '\d{2}[\s,]+(?:%s)[\s,]+20\d{2}' % month_names, 
                        '(?:%s)[\s,]+\d{2}[\s,]+20\d{2}' % month_names, '20\d{2}[\s,]+(?:%s)[\s,]+\d{2}' % month_names, 
                        '\d{1,2}\/\d{1,2}\/\d{2}', '20\d{2}[\/.-]\d{2}', '\d{2}[\/.-]20\d{2}', '20\d{2}']
        date_regex = r'|'.join(r'\b%s\b' % date_regex for date_regex in date_regexes)
        date_regex = re.compile(date_regex, re.IGNORECASE)

        units = '|'.join(re.escape(units) for units in self.units_map.keys())
        multipliers = '|'.join(re.escape(multiplier) for multiplier in self.multipliers_map.keys())
        units_regex = r'(?:\W|^)(%s)(?:\s*of)?\s*(%s)(?:\W|$)|(?:\W|^)(%s)(?:\)|\s+x|\s+in)?\s*(%s)(?:\W|$)|(?:\W|^)(%s)(?:\W|$)' \
                      % (multipliers, units, units, multipliers, units)
        units_regex = re.compile(units_regex, re.IGNORECASE)

        return date_regex, units_regex, ParserInfo()

    def MergeLines(self, lines):

        idx = 1
        while idx < len(lines):
            prev_y0, prev_y1, prev_words = lines[idx - 1]
            y0, y1, words = lines[idx]
            line_height = ((prev_y1 - prev_y0) + (y1 - y0)) / 2
            overlap_ratio = (prev_y1 - y0) / line_height if line_height else 0.0

            if prev_y0 <= y0 and y1 <= prev_y1 or overlap_ratio > 0.5:
                prev_y0, prev_y1 = min(prev_y0, y0), max(prev_y1, y1)
                lines[idx - 1] = [prev_y0, prev_y1, prev_words + words]
                lines.pop(idx)
            else:
                idx += 1

        for idx, line in enumerate(lines):
            y0, y1, words = line
            words = sorted(set(words), key=lambda word: word[0])
            lines[idx] = [y0, y1, words]

        return lines

    def RemoveOverlappingWords(self, lines):

        for line_idx, line in enumerate(lines):
            y0, y1, words = line
            word_idx = 0
            
            while word_idx < len(words):
                x0, x1, text = words[word_idx]
                other_words = words[word_idx + 1:]

                word_indices = set()
                for other_word_idx, other_word in enumerate(other_words):
                    other_x0, other_x1, other_text = other_word
                    if text == other_text:
                        max_x0, min_x1 = max(x0, other_x0), min(x1, other_x1)
                        overlap = max(0, min_x1 - max_x0)
                        overlap_ratio = overlap / (x1 - x0) if x1 - x0 else 0.0
                        if overlap_ratio > 0.9:
                            word_indices.add(word_idx + 1 + other_word_idx)

                words = [word for word_idx, word in enumerate(words) if word_idx not in word_indices]
                word_idx += 1

            word_idx = 0
            while word_idx < len(words):
                x0, x1, text = words[word_idx]
                other_words = words[word_idx + 1:]

                word_indices = set()
                for other_word_idx, other_word in enumerate(other_words):
                    other_x0, other_x1, other_text = other_word
                    if x0 == other_x0:
                        if text.startswith(other_text):
                            word_indices.add(word_idx + 1 + other_word_idx)
                        elif other_text.startswith(text):
                            word_indices.add(word_idx)

                words = [word for word_idx, word in enumerate(words) if word_idx not in word_indices]
                word_idx += 1

            lines[line_idx] = [y0, y1, words]

        return lines

    def MergeWords(self, lines):

        number_regex = re.compile('^[\d.,]+')
        for line_idx, line in enumerate(lines):
            y0, y1, words = line
            word_idx = 1

            while word_idx < len(words):
                prev_x0, prev_x1, prev_text = words[word_idx - 1]
                x0, x1, text = words[word_idx]
                if prev_text == '-' and number_regex.search(text) and 0 < x0 - prev_x1 < 5:
                    words[word_idx - 1] = prev_x0, x1, prev_text + text
                    words.pop(word_idx)
                else:
                    word_idx += 1

            lines[line_idx] = [y0, y1, words]

        return lines 

    def ExtractSeparators(self, page, lines):

        paths, rects = page.get_drawings(), []
        for path in paths:
            fill_opacity, rect = path['fill_opacity'], path['rect']
            if fill_opacity > 0.9:
                rects.append(rect)

        for idx, line in enumerate(lines):
            y0, y1, words = line
            line_height, separators = y1 - y0, []

            for rect in rects:
                max_y0, min_y1 = max(y0, rect.y0), min(y1, rect.y1)
                overlap = max(0, min_y1 - max_y0)
                overlap_ratio = overlap / line_height if line_height else 0
                if overlap_ratio > 0.66:
                    separators.append(rect.x0)
                    separators.append(rect.x1)

            lines[idx] = words, separators
        
        return lines

    def ExtractLines(self, page):

        whitespace_regex = re.compile(r'\s+')
        lines, words = {}, page.get_text('words')

        for word in words:
            x0, y0, x1, y1, text = word[:5]
            text = whitespace_regex.sub(' ', text)
            text = ''.join(char for char in text if unicodedata.category(char) != 'Co')
            if not text:
                continue

            key = round(y0, 1), round(y1, 1)
            word = round(x0, 1), round(x1, 1), text
            if key in lines:
                lines[key].append(word)
            else:
                lines[key] = [word]

        lines = [[*key, value] for key, value in lines.items()]
        lines = sorted(lines, key=lambda line: line[0])
        lines = self.MergeLines(lines)
        lines = self.RemoveOverlappingWords(lines)
        lines = self.MergeWords(lines)
        lines = self.ExtractSeparators(page, lines)

        return lines

    def ExtractBlocks(self, line):

        words, separators = line
        text_length, char_count = 0, 0
        for x0, x1, text in words:
            text_length += x1 - x0
            char_count += len(text)

        average_char_width = text_length / char_count if char_count else 1e5
        double_char_width = 2 * average_char_width

        groups = [[]]
        for idx, word in enumerate(words):
            groups[-1].append(word)
            if idx == len(words) - 1:
                gap, has_separator = 0, False
            else:
                next_word = words[idx + 1] 
                gap = next_word[0] - word[1]
                has_separator = any(word[1] < separator < next_word[0] for separator in separators)

            if gap > double_char_width or has_separator:
                groups.append([])

        blocks = []
        for group in groups:
            first_word, last_word = group[0], group[-1]
            x0, x1 = first_word[0], last_word[1]
            text = ' '.join(word[2] for word in group)
            blocks.append((x0, x1, text))

        return blocks

    def AlignSingleBlock(self, block, gaps):

        x0, x1 = block[:2]
        non_aligned = lambda gap: (x0 < gap[0] and gap[1] < x1) or (gap[0] < x0 and x1 < gap[1])
        non_aligned_gaps = sum(1 for gap in gaps if non_aligned(gap))
        if non_aligned_gaps > 0:
            return None

        end_found = False
        aligned_blocks = [None] * (len(gaps) + 1)
        for idx, gap in enumerate(gaps):
            if x0 < gap[0]:
                aligned_blocks[idx] = block

            if x1 < gap[1]:
                end_found = True
                break

        if not end_found:
            aligned_blocks[-1] = block

        return aligned_blocks

    def AlignMultipleBlocks(self, less_blocks, more_blocks, less_block_gaps, more_block_gaps):

        start_idx, indices = 0, []
        for block_gap in less_block_gaps:
            x0, x1 = block_gap
            overlaps = []

            for other_block_gap in more_block_gaps[start_idx:]:
                other_x0, other_x1 = other_block_gap
                max_x0, min_x1 = max(x0, other_x0), min(x1, other_x1)
                overlap = max(0, min_x1 - max_x0)
                overlaps.append(overlap)

            if overlaps:
                idx, overlap = max(enumerate(overlaps), key=lambda item: item[1])
                if overlap > 0:
                    indices.append(start_idx + idx)
                    start_idx += idx + 1

        if len(indices) != len(less_block_gaps):
            return None

        aligned_blocks = [None] * len(more_blocks)		
        for idx, other_idx in enumerate(indices + [-1]):
            x0, x1, text = less_blocks[idx]
            prev_other_idx = 0 if idx == 0 else indices[idx - 1] + 1 
            other_blocks = more_blocks[prev_other_idx:] if other_idx == -1 else more_blocks[prev_other_idx:other_idx + 1]
            
            if len(other_blocks) == 1:
                aligned_blocks[other_idx] = x0, x1, text
            else:
                start_idx = min(enumerate(other_blocks), key=lambda item: abs(x0 - item[1][0]))[0]
                end_idx = min(enumerate(other_blocks[start_idx:]), key=lambda item: abs(x1 - item[1][1]))[0]
                start_idx, end_idx = prev_other_idx + start_idx, prev_other_idx + start_idx + end_idx
                
                new_blocks_count = end_idx - start_idx + 1
                new_block_length = (x1 - x0) / new_blocks_count
                new_x0 = lambda block_idx: x0 + block_idx * new_block_length
                new_x1 = lambda block_idx: x0 + block_idx * new_block_length + new_block_length

                new_blocks = [(new_x0(block_idx), new_x1(block_idx), text) for block_idx in range(new_blocks_count)]
                aligned_blocks[start_idx:end_idx + 1] = new_blocks

        return aligned_blocks

    def AlignBlocks(self, blocks, other_blocks):

        block_gaps = [(block[1], next_block[0]) for block, next_block in zip(blocks, blocks[1:])]
        other_block_gaps = [(block[1], next_block[0]) for block, next_block in zip(other_blocks, other_blocks[1:])]

        if len(blocks) <= len(other_blocks):
            less_blocks, more_blocks = blocks, other_blocks
            less_block_gaps, more_block_gaps = block_gaps, other_block_gaps
        else:
            less_blocks, more_blocks = other_blocks, blocks
            less_block_gaps, more_block_gaps = other_block_gaps, block_gaps

        if len(less_blocks) == 1:
            return self.AlignSingleBlock(less_blocks[0], more_block_gaps)

        return self.AlignMultipleBlocks(less_blocks, more_blocks, less_block_gaps, more_block_gaps)

    def CorrectBlocks(self, blocks, most_blocks):

        x0, x1 = blocks[0][0], blocks[-1][1]
        text = ''.join(block[-1] for block in blocks)
        regex = re.compile(r'(?:1st|first|2nd|second)\s+half[-\s]+year', re.IGNORECASE)
        boundaries = [match.span() for match in regex.finditer(text)]
        if not boundaries:
            return blocks

        width, texts = x1 - x0, {}
        for start, end in boundaries:
            new_x0 = x0 + start / len(text) * width
            new_x1 = x0 + end / len(text) * width
            new_midx = new_x0 + (new_x1 - new_x0) / 2
            new_text = text[start:end]

            differences = []
            for block in most_blocks:
                block_midx = block[0] + (block[1] - block[0]) / 2
                difference = abs(new_midx - block_midx)
                differences.append(difference)
            
            idx = min(enumerate(differences), key=lambda item: item[1])[0]
            texts[idx] = new_text

        texts = list(texts.items())
        blocks = [most_blocks[idx][:2] + (text,) for idx, text in texts]

        return blocks

    def CorrectTable(self, table, first_idx, lines):

        lines = lines[:first_idx][::-1]
        most_blocks = max(table, key=lambda item: len(item))
        prev_aligned_blocks = self.AlignBlocks(table[0], most_blocks)
        prev_aligned_blocks = prev_aligned_blocks or [None] * len(most_blocks)
        sentence_regex = re.compile(r'^.+[.:]\s*$')

        table_extension = []
        for line in lines:
            blocks = self.ExtractBlocks(line)
            blocks = self.CorrectBlocks(blocks, most_blocks)
            aligned_blocks = self.AlignBlocks(blocks, most_blocks)

            if aligned_blocks is None or len(aligned_blocks) != len(prev_aligned_blocks):
                line_valid = False
            else:
                is_sentence = aligned_blocks[0] is not None and bool(sentence_regex.search(aligned_blocks[0][-1]))
                other_blocks_empty = all(aligned_block is None for aligned_block in aligned_blocks[1:])
                if is_sentence and other_blocks_empty:
                    line_valid = False
                else:
                    block_indices = [idx for idx, aligned_block in enumerate(aligned_blocks) if aligned_block is not None]
                    line_valid = all(prev_aligned_blocks[idx] is not None for idx in block_indices)

                    if not line_valid:
                        text = ' '.join(aligned_block[-1] for aligned_block in aligned_blocks if aligned_block is not None)
                        has_units, has_dates = bool(self.units_regex.search(text)), bool(self.date_regex.search(text))
                        if has_units and has_dates:
                            first_third_of_table = table_extension[::-1] + table[:len(table) // 3]
                            text = lambda blocks: ' '.join(block[-1] for block in blocks[1:] if block is not None)
                            first_third_of_table = [text(blocks) for blocks in first_third_of_table]
                            has_previous_dates = bool(self.date_regex.search(' '.join(first_third_of_table)))
                            if not has_previous_dates:
                                line_valid = True

            if line_valid:
                table_extension.append(blocks)
                first_idx -= 1
                prev_aligned_blocks = aligned_blocks
            else:
                break

        return table_extension[::-1] + table, first_idx

    def ExtractTables(self, lines):

        tables = [[]]
        for idx, line in enumerate(lines):
            blocks = self.ExtractBlocks(line)
            if tables[-1]:
                most_blocks = max((item[-1] for item in tables[-1]), key=lambda item: len(item))
                aligned_blocks = self.AlignBlocks(blocks, most_blocks)
                if aligned_blocks is None:
                    tables.append([[idx, blocks]] if len(blocks) > 1 else [])
                else:
                    tables[-1].append([idx, blocks])

            elif len(blocks) > 1:
                tables[-1].append([idx, blocks])

        tables = tables if tables[-1] else tables[:-1]       
        for table_idx, table in enumerate(tables):
            first_idx, last_idx = table[0][0], table[-1][0]
            table = [item[-1] for item in table]
            table, first_idx = self.CorrectTable(table, first_idx, lines)

            most_blocks = max(table, key=lambda item: len(item))
            for row_idx, blocks in enumerate(table):
                blocks = self.AlignBlocks(blocks, most_blocks)
                if blocks is None:
                    row = [''] * len(most_blocks)
                else:
                    row = ['' if block is None else block[-1] for block in blocks]

                table[row_idx] = row

            tables[table_idx] = [first_idx, last_idx, table]

        return tables

    def FilterTables(self, tables):

        numbers_regex = re.compile(r'^[\s\d.,\-+%()]+$')
        number_gaps_regex = re.compile(r'(?<=\b\d)\s(?=\d\/)')
        repeating_numbers_regex = re.compile(r'[SHQ]\d\s+20\d(\d)(\1+)', re.IGNORECASE)
        ellipsis_regex = re.compile(r'[\d\s.,]+$')
        substitution = lambda match: match.string.replace(match.group(2), '')

        filtered_tables = []
        for first_idx, last_idx, rows in tables:
            if len(rows) < 3:
                continue

            columns = [list(column) for column in zip(*rows)]
            columns, other_columns = columns[:1], columns[1:]
            for column in other_columns:
                column = [repeating_numbers_regex.sub(substitution, number_gaps_regex.sub('', cell)) for cell in column]
                first_third_of_column = column[:len(column) // 3]
                date_idx = next((idx for idx, cell in enumerate(first_third_of_column) if self.date_regex.search(cell)), -1)
                if date_idx != -1:
                    number_idx = next((idx for idx, cell in enumerate(column[date_idx + 1:]) if numbers_regex.search(cell)), -1)
                    if number_idx != -1:
                        columns.append(column)

            if len(columns) > 1:
                columns = columns[:4]
                columns[0] = [ellipsis_regex.sub('', cell) for cell in columns[0]]
                rows = [list(row) for row in zip(*columns)]
                filtered_tables.append([first_idx, last_idx, rows])

        return filtered_tables

    def IdentifyHeader(self, tables):

        letters_regex = re.compile(r'[A-Za-z]')
        values_regex = re.compile(r'^[\s\d.,\-+%()]+$|^\s*(?:-|n\.a)?\s*$', re.IGNORECASE)

        new_tables = []
        for table in tables:
            first_idx, last_idx, rows = table
            date_idx = next(idx for idx, row in enumerate(rows) if self.date_regex.search(' '.join(row[1:])))

            header_idx = date_idx
            for row in rows[date_idx + 1:]:
                has_letters = bool(letters_regex.search(row[0]))
                has_units = bool(self.units_regex.search(row[0])) or bool(self.units_regex.search(row[1]))
                has_values = bool(values_regex.search(row[1]))

                if has_letters and not has_units and has_values:
                    break
                else:
                    header_idx += 1

            header_rows, value_rows = rows[:header_idx + 1], rows[header_idx + 1:]
            if header_rows and value_rows:
                header_idx = first_idx + header_idx
                new_tables.append([header_idx, last_idx, header_rows, value_rows])

        return new_tables

    def MergeRows(self, rows, idx):

        uppercase_regex = re.compile(r'^\s*[A-Z]')
        colon_regex = re.compile(r':\s*$')
        uppercase_ratio = lambda text: sum(1 if char.isupper() else 0 for char in text) / len(text) if len(text) else 0

        previous_row = rows[idx - 1] if idx > 0 else None
        current_row = rows[idx]
        next_row = rows[idx + 1] if idx < len(rows) - 1 else None

        if all(not cell for cell in current_row[1:]):
            next_row_not_capitalized = next_row is not None and not bool(uppercase_regex.search(next_row[0]))
            current_row_not_capitalized = not bool(uppercase_regex.search(current_row[0]))
            previous_row_hasno_colon = previous_row is not None and not bool(colon_regex.search(previous_row[0]))

            if next_row_not_capitalized:
                if uppercase_ratio(current_row[0]) < 0.5 and uppercase_ratio(next_row[0]) < 0.5:
                    rows[idx + 1][0] = '%s %s' % (current_row[0], next_row[0])
                    rows.pop(idx)
                    return rows, True

            elif current_row_not_capitalized and previous_row_hasno_colon:
                if uppercase_ratio(previous_row[0]) < 0.5 and uppercase_ratio(current_row[0]) < 0.5:
                    rows[idx - 1][0] = '%s %s' % (previous_row[0], current_row[0]) 
                    rows.pop(idx)
                    return rows, True

        return rows, False

    def CleanRows(self, tables):

        letters_regex = re.compile(r'[A-Za-z]')
        row_valid = lambda row: bool(letters_regex.search(row[0])) and all(row[1:])
        new_tables = []

        for table in tables:
            header_idx, last_idx, header_rows, value_rows = table
            idx = next((idx for idx, row in enumerate(value_rows[::-1]) if row_valid(row)), len(value_rows))
            value_rows, idx = value_rows[:len(value_rows) - idx], 0
            while idx < len(value_rows):
                value_rows, was_merged = self.MergeRows(value_rows, idx)
                if not was_merged:
                    idx += 1

            value_rows = [row for row in value_rows if row_valid(row)]
            if value_rows:
                header_columns = [list(dict.fromkeys(column)) for column in zip(*header_rows)]
                header_row = [' '.join(column).strip() for column in header_columns]
                rows = [header_row] + value_rows
                new_tables.append([header_idx, last_idx, rows])

        return new_tables

    def ExtractTitle(self, lines, tables):

        titles = []
        for idx, table in enumerate(tables):
            header_idx, last_idx, rows = table
            first_idx = tables[idx - 1][1] + 1 if idx > 0 else 0
            lines_slice = lines[first_idx:header_idx + 1]

            title = []
            for line in lines_slice:
                words, separators = line
                text = ' '.join(word[-1] for word in words)
                title.append(text)

            titles.append(title)

        for idx, table in enumerate(tables):
            header_idx, last_idx, rows = table
            tables[idx] = [titles[idx], rows]

        return tables

    def ExtractDate(self, text):

        match, date = self.date_regex.search(text), None
        if match is not None:
            date = match.group()
            match = re.search(r'(?:1er|2[eè]me)\s+semestre|(?:1st|first|2nd|second)\s+half[-\s]+year|[SHQ]\d', date, re.IGNORECASE)

            try:
                if match is not None:
                    period = match.group()
                    year = date.replace(period, '').strip()
                    if len(period) == 2:
                        month = int(period[1]) * (3 if period[0].upper() == 'Q' else 6)
                    else:
                        month = 6 if re.search(r'1|first', period, re.IGNORECASE) else 12

                    if month == 12:
                        year, month = int(year) + 1, 1
                    else:
                        year, month = int(year), month + 1

                    date = datetime(year=year, month=month, day=1)
                    date -= timedelta(days=1)    
                else:
                    if re.search(r'^20\d{2}$', date):
                        date = datetime(year=int(date), month=12, day=31)

                    elif re.search(r'^(20\d{2}[\/.-]\d{2}|\d{2}[\/.-]20\d{2})$', date):
                        numbers = [int(token) for token in re.split(r'[\/.-]', date)]
                        numbers = numbers if numbers[0] > numbers[1] else numbers[::-1]
                        year, month = numbers
                        if month == 12:
                            year, month = year + 1, 1
                        else:
                            year, month = year, month + 1

                        date = datetime(year=year, month=month, day=1)
                        date -= timedelta(days=1)  

                    else:
                        date = parser.parse(date, parserinfo=self.parser_info)

                date = date.strftime('%Y-%m-%d')
            except:
                date = None

        return date

    def ExtractUnits(self, text):

        units, multiplier = '', 1
        match = self.units_regex.search(text)
        if match is not None:
            groups = match.groups()
            if groups[0] and groups[1]:
                units, multiplier = groups[1].lower(), groups[0].lower()
                units, multiplier = self.units_map[units], self.multipliers_map[multiplier]

            elif groups[2] and groups[3]:
                units, multiplier = groups[2].lower(), groups[3].lower()
                units, multiplier = self.units_map[units], self.multipliers_map[multiplier]

            elif groups[4]:
                units = groups[4].lower()
                units, multiplier = self.units_map[units], 1

        return units, multiplier

    def ParseNumber(self, text):

        text = re.sub(r'\s+|\+', '', text)
        text = re.sub(r'\([\d.,]+\)', lambda match: '-%s' % match.group()[1:-1], text)
        text = re.sub(r'[,.](?=\d{3})', '', text)
        text = text.replace(',', '.').strip()

        try:
            number = float(text)
        except:
            number = None

        return number

    def FormatRows(self, page, title, rows):

        keys, dates = rows[0][1:], []
        for idx, key in enumerate(keys):
            date = self.ExtractDate(key)
            if date is not None and all(date != item[1] for item in dates):
                dates.append((idx + 1, date))

        if not dates:
            return [], '', 1
       
        title = ' '.join(title[::-1])
        keys = ' '.join(row[0] for row in rows[1:] if not re.search(r'(?:per|par)\s+(share|action)', row[0], re.IGNORECASE))
        units_and_multipliers = [self.ExtractUnits(text) for text in (title, keys)]
        units_and_multipliers = sorted(units_and_multipliers, key=lambda item: (item[1], item[0]), reverse=True)
        units, multiplier = units_and_multipliers[0]

        formatted_rows, html_data = [], page.get_text('html')
        for idx, date in dates:
            formatted_row, contain_values = OrderedDict(date=date, units=units), False
            for row in rows[1:]:
                key, value = row[0], row[idx]
                value = self.ParseNumber(value)
                if value is not None:
                    contain_values = True
                    if not re.search(r'(?:per|par)\s+(share|action)', key, re.IGNORECASE):
                        value *= multiplier

                formatted_row[key] = value

            if contain_values:
                formatted_row['html_data'] = html_data
                formatted_row['raw_data'] = rows
                formatted_rows.append(formatted_row)

        return formatted_rows, units, multiplier

    def FormatTables(self, page, lines, tables, most_common_units, most_common_multiplier):

        formatted_tables, unit_counts = [], {}
        for title, rows in tables:
            rows, units, multiplier = self.FormatRows(page, title, rows)
            if rows:
                formatted_table = OrderedDict(title=' '.join(title), body=rows)
                formatted_tables.append(formatted_table)

                if units:
                    key = units, multiplier
                    unit_counts[key] = unit_counts.get(key, 0) + 1

        tables = formatted_tables
        if tables and not unit_counts:
            for line in lines:
                text = ' '.join(word[-1] for word in line[0])
                if not re.search(r'(?:per|par)\s+(share|action)', text, re.IGNORECASE):
                    units, multiplier = self.ExtractUnits(text)
                    if units:
                        key = units, multiplier
                        unit_counts[key] = unit_counts.get(key, 0) + 1

            if not unit_counts and most_common_units:
                key = most_common_units, most_common_multiplier
                unit_counts[key] = unit_counts.get(key, 0) + 1

        if not unit_counts:
            return []

        units, multiplier = max(unit_counts.keys(), key=lambda item: unit_counts[item])
        for table_idx, table in enumerate(tables):
            title, rows = table['title'], table['body']
            if rows[0]['units']:
                continue

            for row_idx, row in enumerate(rows):
                row['units'] = units
                for key, value in row.items():
                    if isinstance(value, float) and not re.search(r'(?:per|par)\s+(share|action)', key, re.IGNORECASE):
                        row[key] *= multiplier

                rows[row_idx] = row
                
            tables[table_idx] = OrderedDict(title=title, body=rows)

        return tables

    def __call__(self, document):
        
        document = fitz.open(stream=document, filetype='pdf')
        units_and_multipliers = [self.ExtractUnits(page.get_text()) for page in document]
        units_and_multipliers = [item for item in units_and_multipliers if item[0]]
        if units_and_multipliers:
            units, multiplier = max(units_and_multipliers, key=lambda item: units_and_multipliers.count(item))
        else:
            units, multiplier = '', 1

        tables = []
        for page in document:
            lines = self.ExtractLines(page)
            tables_slice = self.ExtractTables(lines)  
            tables_slice = self.FilterTables(tables_slice)
            tables_slice = self.IdentifyHeader(tables_slice)

            tables_slice = self.CleanRows(tables_slice)
            tables_slice = self.ExtractTitle(lines, tables_slice)
            tables_slice = self.FormatTables(page, lines, tables_slice, units, multiplier)
            tables.extend(tables_slice)

        return tables