import os
import re
import time
import json
import uuid
import traceback
import requests
import boto3
import botocore
from io import BytesIO
from collections import OrderedDict
from datetime import datetime, timedelta
from euronext import Euronext
from database import Database
from metadata_extractor import MetadataExtractor
from table_extractor import TableExtractor
from item_standardizer import ItemStandardizer
from multi_processing import StdOut, Value, Pool

class InternationalFinancials:

    def __init__(self):

        self.database = Database()
        self.metadata_extractor = MetadataExtractor()
        self.table_extractor = TableExtractor()
        self.item_standardizer = ItemStandardizer()
        self.s3_client = None
        self.last_update_time = None
        self.companies = self.GetCompanies()
        requests.packages.urllib3.disable_warnings()

    def GetCompanies(self):

        path = 'data/companies.json'
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as file:
                companies = json.load(file)
                companies = [tuple(company) for company in companies]
        else:
            euronext = Euronext()
            companies = euronext.GetCompanies()
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(companies, file, indent=2)

        return companies

    def GenerateData(self, *statements):

        html_data, raw_data, json_data = [], [], []
        for statement in statements:
            columns = [list(column) for column in zip(*statement[-2])]
            for idx, column in enumerate(columns):
                max_length = len(max(column, key=lambda cell: len(cell)))
                column = [cell.ljust(max_length, ' ') for cell in column]
                columns[idx] = column

            rows = [list(row) for row in zip(*columns)]
            line = ['_' * len(cell) for cell in rows[0]]
            rows = [line, rows[0], line, *rows[1:], line]
            rows = [' %s ' % '_'.join(row) if idx == 0 else '|%s|' % '|'.join(row) for idx, row in enumerate(rows)]

            html_data.append(statement[-3])
            raw_data.append('\n'.join(rows))
            json_data.append(statement[-1])

        html_data = '\n\n'.join(html_data)
        raw_data = '\n\n'.join(raw_data)
        json_data = json.dumps(json_data, ensure_ascii=False)

        return html_data, raw_data, json_data

    def GenerateJsonResult(self, statement):

        column_names = ['symbol', 'isin', 'registrant_name', 'market', 'market_full_name', 'address_line', 'address_city',
                        'address_country', 'phone_number', 'website', 'is_annual_report', 'fiscal_year', 'fiscal_period', 
                        'fiscal_year_end_date', 'auditor_name', 'date', 'units', 'revenue', 'operating_income', 
                        'non_operating_income_expense', 'pretax_income', 'tax_provision', 'earnings_from_equity_interest', 
                        'discontinued_operations', 'consolidated_net_income', 'non_controlling_interests', 'net_income', 
                        'basic_earnings_per_share', 'diluted_earnings_per_share', 'current_assets', 'non_current_assets', 
                        'total_assets', 'current_liabilities', 'non_current_liabilities', 'total_liabilities', 
                        'non_current_provisions', 'total_equity', 'common_stock_equity', 'operating_cash_flow', 
                        'investing_cash_flow', 'financing_cash_flow', 'change_in_cash', 'beginning_cash_position', 
                        'end_cash_position','issuance_of_debt','repayment_of_debt']

        word_start_regex = re.compile(r'(?:^|_)\w')
        substitution = lambda match: match.group()[-1].upper()
        column_names = [word_start_regex.sub(substitution, column_name) for column_name in column_names]
        statement = list(zip(column_names, statement))

        date = statement[15][1]
        doc_entity_info = OrderedDict(statement[:15] + statement[16:17])
        income_statement = OrderedDict(statement[17:29])
        balance_sheet_statement = OrderedDict(statement[29:38])
        cash_flow_statement = OrderedDict(statement[38:])

        face = [('doc_entity_info', doc_entity_info), ('income_statement', income_statement), 
                 ('balance_sheet_statement', balance_sheet_statement), ('cash_flow_statement', cash_flow_statement)]
        face = [(word_start_regex.sub(substitution, item[0]), item[1]) for item in face]
        json_result = [(date, OrderedDict(face=OrderedDict(face)))]
        json_result = json.dumps(OrderedDict(json_result), ensure_ascii=False)

        return json_result

    def UploadToS3(self, document, document_url):

        if self.s3_client is None:
            aws_keys = ('YOUR_ACCESS_KEY', 'YOUR_SECRET_KEY')
            anonymized_region = 'your-region'
            anonymized_bucket_name = 'your-bucket-name'
            s3_config = botocore.config.Config(max_pool_connections=20)
            self.s3_client = boto3.client('s3', region_name=anonymized_region, aws_access_key_id=aws_keys[0], 
                                          aws_secret_access_key=aws_keys[1], config=s3_config)

        file_name = '%s.pdf' % uuid.uuid5(uuid.NAMESPACE_X500, document_url)
        transfer_config = boto3.s3.transfer.TransferConfig(multipart_threshold=1024**2, multipart_chunksize=1024**2, 
                                                           max_concurrency=20, use_threads=True)
        self.s3_client.upload_fileobj(document, anonymized_bucket_name, file_name, Config=transfer_config)
        s3_url = f'https://{anonymized_bucket_name}.s3.amazonaws.com/{file_name}'

        return s3_url

    def ParseStatement(self, company_info, statement_url, headers):

        try:
            response = requests.get(statement_url, headers=headers, verify=False)
        except:
            return []

        document = BytesIO(response.content)
        key_pages = self.item_standardizer.GetKeyPages(document)
        if key_pages is None:
            return []

        tables = self.table_extractor(key_pages)
        separate_statements = self.item_standardizer(tables)
        separate_statements = list(separate_statements.values())
        statements = []

        for income_statement, balance_sheet_statement, cash_flow_statement in zip(*separate_statements):
            income_statement = list(income_statement.values())
            balance_sheet_statement = list(balance_sheet_statement.values())
            cash_flow_statement = list(cash_flow_statement.values())

            metadata = self.metadata_extractor(statement_url, document, income_statement[0])
            statement = company_info + metadata + income_statement[:-3] + balance_sheet_statement[2:-3] + cash_flow_statement[2:-3]
            html_data, raw_data, json_data = self.GenerateData(income_statement, balance_sheet_statement, cash_flow_statement)

            json_result = self.GenerateJsonResult(statement)
            statement += [html_data, raw_data, json_data, json_result, statement_url]
            statements.append(tuple(statement))

        if statements:
            s3_url = self.UploadToS3(document, statement_url)
            statements = [statement + (s3_url,) for statement in statements]

        return statements

    def SaveStatementsData(self, data):

        data_map = {}
        for item in data:
            key = item[0], item[12], item[15]
            if not (key[0] == 'EDF' and key[1][0] == 'Q'):
                if key in data_map:
                    data_map[key].append(item)
                else:
                    data_map[key] = [item]

        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        key = lambda item: sum(0 if value is None else 1 for value in item)
        data = [max(items, key=key) + (updated_at,) for items in data_map.values()]
        self.database.AddStatementsData(data)

        filter = lambda item: (item[0], item[3], item[4] or 'N/A', item[11] or 'N/A', item[12], item[-3], item[-1])
        filtered_data = list(set(filter(item) for item in data))
        self.database.AddUrlsData(filtered_data)

        filter = lambda item: (item[0], item[2], item[12], item[15], item[-1])
        filtered_data = list(set(filter(item) for item in data))
        self.database.AddFeedData(filtered_data)

    def ParseStatements(self):

        stdout = StdOut() 
        stdout.redirect()
        session = Value('parsing_session', 0)
        euronext = Euronext()

        while 1:
            with session:
                idx = session.Get()
                session.Set(idx + 1)
            
            if idx >= len(self.companies):
                break

            *company, info_url = self.companies[idx]
            print('Parsing statements for %s...' % company[2])
            company_info = company + list(euronext.GetCompanyInfo(info_url))
            statement_urls = euronext.GetStatementUrls(info_url)
            cached_urls = self.database.GetCachedUrls(company[0])
            statement_urls = sorted(set(statement_urls) - set(cached_urls))

            data = []
            for statement_url in statement_urls:
                try:
                    statements = self.ParseStatement(company_info, statement_url, euronext.headers)
                    if statements:
                        data += statements
                except:
                    print(traceback.format_exc())

            if data:
                self.SaveStatementsData(data)

            data = [(company[0], statement_url) for statement_url in statement_urls]
            if data:
                self.database.AddCachedUrlsData(data)

    def UpdateStatements(self):

        if self.last_update_time is None:
            last_update_time = self.database.GetLastUpdateTime()
            last_update_time = datetime.strptime(last_update_time, '%Y-%m-%d %H:%M:%S')
            self.last_update_time = last_update_time

        time_now = datetime.now()
        if time_now - self.last_update_time < timedelta(days=7):
            return

        print('Updating statements...')
        Value('parsing_session', 0).Set(0)
        pool = Pool()
        pool.Run(self.ParseStatements)

        print('All statements were updated')
        self.last_update_time = datetime.now()

    def Run(self):

        stdout = StdOut() 
        stdout.redirect()

        if not self.database.StatementsDataExist():
            pool = Pool()
            pool.Run(self.ParseStatements)
            print('All statements were parsed')

        while 1:
            self.UpdateStatements()
            time.sleep(10)

if Pool.IsMainProcess(): 
    international_financials = InternationalFinancials()
    international_financials.Run()