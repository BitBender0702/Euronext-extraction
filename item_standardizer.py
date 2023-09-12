import re
import json
import fitz
from io import BytesIO
from collections import OrderedDict
from difflib import SequenceMatcher

class ItemStandardizer:

    def __init__(self):

        self.statement_names = ['income_statement', 'balance_sheet_statement', 'cash_flow_statement']
        self.title_regexes, self.item_regexes = self.CreateRegexes()

    def CreateRegexes(self):

        path = 'data/structures.json'
        with open(path, 'r', encoding='utf-8') as file:
           structures = json.load(file, object_pairs_hook=OrderedDict)

        title_regexes, item_regexes = {}, {}       
        for statement_name in self.statement_names:
            structure = structures[statement_name]
            titles, items = structure['titles'], structure['items']

            titles = [re.sub(r'\s+', '\s+', title) for title in titles]
            regex = r'%s' % '|'.join(titles)
            regex = re.compile(regex, re.IGNORECASE)
            title_regexes[statement_name] = regex

            regexes = OrderedDict()
            for item, names in items.items():
                for idx, name in enumerate(names):
                    name = re.split(r'\s+', name)
                    name = '.+?'.join('(%s)' % token for token in name)
                    names[idx] = name

                regex = r'%s' % '|'.join(names)
                regex = re.compile(regex, re.IGNORECASE)
                regexes[item] = regex

            item_regexes[statement_name] = regexes

        return title_regexes, item_regexes

    def GetKeyPages(self, document):

        try:
            document = fitz.open(stream=document, filetype='pdf')
        except:
            return None

        title_regexes = list(self.title_regexes.items())
        flags = dict.fromkeys(self.title_regexes.keys(), False)
        page_indices = []

        for idx, page in enumerate(document):
            text, is_key_page = page.get_text(), False
            for statement_name, title_regex in title_regexes:
                match = title_regex.search(text)
                if match is not None:
                    flags[statement_name] = True
                    is_key_page = True

            if not is_key_page:
                page_indices.append(idx)

        if all(flags.values()):
            try:
                if page_indices:
                    document.delete_pages(page_indices)
                return BytesIO(document.write(clean=True))
            except:
                pass

        return None

    def GetSimilarityRatio(self, x, y):

        x, y = x.lower(), y.lower()
        matcher = SequenceMatcher(None, x, y)
        similarity_ratio = matcher.ratio()

        return similarity_ratio

    def CorrectIncomeStatement(self, statement):

        if statement['pretax_income'] is None:
            operating_income = statement['operating_income']
            non_operating_income_expense = statement['non_operating_income_expense']
            if operating_income is not None and non_operating_income_expense is not None:
                statement['pretax_income'] = operating_income + non_operating_income_expense

        if statement['net_income'] is None:
            pretax_income = statement['pretax_income']
            tax_provision = statement['tax_provision']
            if pretax_income is not None and tax_provision is not None:
                statement['net_income'] = pretax_income - tax_provision

        return statement

    def CorrectBalanceSheetStatement(self, statement):

        if statement['current_assets'] is None:
            non_current_assets = statement['non_current_assets']
            total_assets = statement['total_assets']
            if non_current_assets is not None and total_assets is not None:
                statement['current_assets'] = total_assets - non_current_assets

        if statement['non_current_assets'] is None:
            current_assets = statement['current_assets']
            total_assets = statement['total_assets']
            if current_assets is not None and total_assets is not None:
                statement['non_current_assets'] = total_assets - current_assets

        if statement['total_assets'] is None:
            current_assets = statement['current_assets']
            non_current_assets = statement['non_current_assets']
            if current_assets is not None and non_current_assets is not None:
                statement['total_assets'] = current_assets + non_current_assets

        if statement['current_liabilities'] is None:
            non_current_liabilities = statement['non_current_liabilities']
            total_liabilities = statement['total_liabilities']
            if non_current_liabilities is not None and total_liabilities is not None:
                statement['current_liabilities'] = total_liabilities - non_current_liabilities

        if statement['non_current_liabilities'] is None:
            current_liabilities = statement['current_liabilities']
            total_liabilities = statement['total_liabilities']
            if current_liabilities is not None and total_liabilities is not None:
                statement['non_current_liabilities'] = total_liabilities - current_liabilities

        if statement['total_liabilities'] is None:
            current_liabilities = statement['current_liabilities']
            non_current_liabilities = statement['non_current_liabilities']
            if current_liabilities is not None and non_current_liabilities is not None:
                statement['total_liabilities'] = current_liabilities + non_current_liabilities

        return statement

    def CorrectCashFlowStatement(self, statement):

        if statement['change_in_cash'] is None:
            beginning_cash_position = statement['beginning_cash_position']
            end_cash_position = statement['end_cash_position']
            if beginning_cash_position is not None and end_cash_position is not None:
                statement['change_in_cash'] = end_cash_position - beginning_cash_position

        if statement['beginning_cash_position'] is None:
            change_in_cash = statement['change_in_cash']
            end_cash_position = statement['end_cash_position']
            if change_in_cash is not None and end_cash_position is not None:
                statement['beginning_cash_position'] = end_cash_position - change_in_cash

        if statement['end_cash_position'] is None:
            change_in_cash = statement['change_in_cash']
            beginning_cash_position = statement['beginning_cash_position']
            if change_in_cash is not None and beginning_cash_position is not None:
                statement['end_cash_position'] = beginning_cash_position + change_in_cash

        return statement

    def ExtractStatements(self, statement_name, statement_table):

        rows = [row.copy() for row in statement_table['body']]
        html_data = [row.pop('html_data') for row in rows][0]
        raw_data = [row.pop('raw_data') for row in rows][0]
        item_regexes, statements = self.item_regexes[statement_name], []

        for row in rows:
            keys = [key for key in row.keys() if key != 'date' and key != 'units']
            statement = OrderedDict([('date', row['date']), ('units', row['units'])])

            for item, regex in item_regexes.items():
                keys_and_ratios = []
                for key in keys:
                    match = regex.search(key) 
                    if match is not None:
                        tokens = match.groups()
                        name = ' '.join(token for token in tokens if token)
                        similarity_ratio = self.GetSimilarityRatio(key, name)
                        keys_and_ratios.append((key, similarity_ratio))

                if keys_and_ratios:
                    key = max(keys_and_ratios, key=lambda item: item[1])[0]
                    statement[item] = row[key]
                else:
                    statement[item] = None

            if statement_name == 'income_statement':
                statement = self.CorrectIncomeStatement(statement)
            elif statement_name == 'balance_sheet_statement':
                statement = self.CorrectBalanceSheetStatement(statement)
            elif statement_name == 'cash_flow_statement':
                statement = self.CorrectCashFlowStatement(statement)

            statement['html_data'] = html_data
            statement['raw_data'] = raw_data
            statement['json_data'] = rows
            statements.append(statement)

        return statements

    def __call__(self, tables):

        statements_map = OrderedDict()
        for statement_name in self.statement_names:
            title_regex, statements_and_counts = self.title_regexes[statement_name], []
            for table in tables:
                if title_regex.search(table['title']):
                    statements = self.ExtractStatements(statement_name, table)
                    count = max(sum(value is not None for value in statement.values()) for statement in statements)
                    statements_and_counts.append((statements, count))

            statements = max(statements_and_counts, key=lambda item: item[1])[0] if statements_and_counts else []
            statements_map[statement_name] = statements

        dates = [set(statement['date'] for statement in statements) for statements in statements_map.values()]
        common_dates = set.intersection(*dates)
        for statement_name, statements in statements_map.items():
            statements = [statement for statement in statements if statement['date'] in common_dates]
            statements = sorted(statements, key=lambda statement: statement['date'])
            statements_map[statement_name] = statements

        return statements_map