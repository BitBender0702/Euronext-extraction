import time
from datetime import timedelta
import psycopg2
import psycopg2.extras

class Database:

    def __init__(self):

        self.connection_details = {'database': '****', 'user': '****', 'password': '****', 
                           'host': '****.****.****.****.****.****.****.****', 'port': '****'}
        self.connection = psycopg2.connect(**self.connection_details)
        self.cursor = self.connection.cursor()
        self.SuppressExceptions()
        self.CreateTables()

    def Reconnect(self, exception):

        backoff = 1        
        while 1:
            message = '%sReconnecting to database after %s...' % (exception, timedelta(seconds=backoff))
            print(message.replace('\t', ''))
            time.sleep(backoff)

            try:
                self.connection = psycopg2.connect(**self.connection_details)
                self.cursor = self.connection.cursor()
                break

            except psycopg2.OperationalError as e:
                exception = str(e)
                backoff *= 2

    def SuppressExceptions(self):

        def wrapper(func):

            def new_func(*args, **kwargs):

                while 1:
                    try:
                        return func(*args, **kwargs)
                    except psycopg2.OperationalError as e:
                        self.Reconnect(str(e))

            return new_func 
        
        for name in dir(self):
           if not name.startswith('__') and name not in ['Reconnect', 'SuppressExceptions']:
              attr = getattr(self, name)
              if callable(attr):
                  setattr(self, name, wrapper(attr))

    def CreateStatementsTable(self):

        self.cursor.execute('SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)', ('euronext_statements',))
        if not self.cursor.fetchone()[0]:
            self.cursor.execute('CREATE TABLE euronext_statements (symbol VARCHAR NOT NULL, isin VARCHAR NOT NULL, '
                                'registrant_name VARCHAR NOT NULL, market VARCHAR NOT NULL, market_full_name VARCHAR, '
                                'address_line VARCHAR, address_city VARCHAR, address_country VARCHAR, phone_number VARCHAR, '
                                'website VARCHAR, is_annual_report BOOLEAN, fiscal_year VARCHAR, fiscal_period VARCHAR NOT NULL, '
                                'fiscal_year_end_date VARCHAR, auditor_name VARCHAR, date VARCHAR NOT NULL, '
                                'units VARCHAR NOT NULL, revenue FLOAT, operating_income FLOAT, '
                                'non_operating_income_expense FLOAT, pretax_income FLOAT, tax_provision FLOAT, '
                                'earnings_from_equity_interest FLOAT, discontinued_operations FLOAT, '
                                'consolidated_net_income FLOAT, non_controlling_interests FLOAT, net_income FLOAT, '
                                'basic_earnings_per_share FLOAT, diluted_earnings_per_share FLOAT, current_assets FLOAT, '
                                'non_current_assets FLOAT, total_assets FLOAT, current_liabilities FLOAT, '
                                'non_current_liabilities FLOAT, total_liabilities FLOAT, non_current_provisions FLOAT, '
                                'total_equity FLOAT, common_stock_equity FLOAT, operating_cash_flow FLOAT, '
                                'investing_cash_flow FLOAT, financing_cash_flow FLOAT, change_in_cash FLOAT, '
                                'beginning_cash_position FLOAT, end_cash_position FLOAT, issuance_of_debt FLOAT, '
                                'repayment_of_debt FLOAT, html_data VARCHAR NOT NULL, raw_data VARCHAR NOT NULL, '
                                'json_data VARCHAR NOT NULL, json_result VARCHAR NOT NULL, url VARCHAR NOT NULL, '
                                's3_url VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, PRIMARY KEY (symbol, fiscal_period, date))')

            self.cursor.execute('CREATE INDEX euronext_statements_symbol ON euronext_statements(symbol)')
            self.cursor.execute('CREATE INDEX euronext_statements_updated_at ON euronext_statements(updated_at)')

        self.connection.commit()

    def CreateUrlsTable(self):

        self.cursor.execute('SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)', ('euronext_urls',))
        if not self.cursor.fetchone()[0]:
            self.cursor.execute('CREATE TABLE euronext_urls (symbol VARCHAR NOT NULL, market VARCHAR NOT NULL, '
                                'market_full_name VARCHAR NOT NULL, fiscal_year VARCHAR NOT NULL, fiscal_period VARCHAR NOT NULL, '
                                'url VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, PRIMARY KEY (symbol, fiscal_year, ' 
                                'fiscal_period, url))')

        self.connection.commit()

    def CreateUrlsCacheTable(self):

        self.cursor.execute('SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)', ('euronext_urls_cache',))
        if not self.cursor.fetchone()[0]:
            self.cursor.execute('CREATE TABLE euronext_urls_cache (symbol VARCHAR NOT NULL, url VARCHAR NOT NULL, '
                                'PRIMARY KEY (url))')

            self.cursor.execute('CREATE INDEX euronext_urls_cache_symbol ON euronext_urls_cache(symbol)')

        self.connection.commit()

    def CreateFeedTable(self):

        self.cursor.execute('SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s)', ('euronext_feed',))
        if not self.cursor.fetchone()[0]:
            self.cursor.execute('CREATE TABLE euronext_feed (symbol VARCHAR NOT NULL, registrant_name VARCHAR NOT NULL, '
                                'fiscal_period VARCHAR NOT NULL, date VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, '
                                'PRIMARY KEY (symbol, fiscal_period, date))')

            self.cursor.execute('CREATE INDEX euronext_feed_symbol ON euronext_feed(symbol)')
            self.cursor.execute('CREATE INDEX euronext_feed_updated_at ON euronext_feed(updated_at)')

        self.connection.commit()

    def CreateTables(self):

        self.CreateStatementsTable()
        self.CreateUrlsTable()
        self.CreateUrlsCacheTable()
        self.CreateFeedTable()

    def AddStatementsData(self, data):

        query = 'INSERT INTO euronext_statements (symbol, isin, registrant_name, market, market_full_name, address_line, ' \
                'address_city, address_country, phone_number, website, is_annual_report, fiscal_year, fiscal_period, ' \
                'fiscal_year_end_date, auditor_name, date, units, revenue, operating_income, non_operating_income_expense, ' \
                'pretax_income, tax_provision, earnings_from_equity_interest, discontinued_operations, consolidated_net_income, ' \
                'non_controlling_interests, net_income, basic_earnings_per_share, diluted_earnings_per_share, current_assets, ' \
                'non_current_assets, total_assets, current_liabilities, non_current_liabilities, total_liabilities, ' \
                'non_current_provisions, total_equity, common_stock_equity, operating_cash_flow, investing_cash_flow, ' \
                'financing_cash_flow, change_in_cash, beginning_cash_position, end_cash_position, issuance_of_debt, ' \
                'repayment_of_debt, html_data, raw_data, json_data, json_result, url, s3_url, updated_at) VALUES %s ' \
                'ON CONFLICT (symbol, fiscal_period, date) DO UPDATE SET (isin, registrant_name, market, market_full_name, ' \
                'address_line, address_city, address_country, phone_number, website, is_annual_report, fiscal_year, ' \
                'fiscal_year_end_date, auditor_name, units, revenue, operating_income, non_operating_income_expense, ' \
                'pretax_income, tax_provision, earnings_from_equity_interest, discontinued_operations, consolidated_net_income, ' \
                'non_controlling_interests, net_income, basic_earnings_per_share, diluted_earnings_per_share, current_assets, ' \
                'non_current_assets, total_assets, current_liabilities, non_current_liabilities, total_liabilities, ' \
                'non_current_provisions, total_equity, common_stock_equity, operating_cash_flow, investing_cash_flow, ' \
                'financing_cash_flow, change_in_cash, beginning_cash_position, end_cash_position, issuance_of_debt, ' \
                'repayment_of_debt, html_data, raw_data, json_data, json_result, url, s3_url, updated_at) = (excluded.isin, ' \
                'excluded.registrant_name, excluded.market, excluded.market_full_name, excluded.address_line, ' \
                'excluded.address_city, excluded.address_country, excluded.phone_number, excluded.website, ' \
                'excluded.is_annual_report, excluded.fiscal_year, excluded.fiscal_year_end_date, excluded.auditor_name, ' \
                'excluded.units, excluded.revenue, excluded.operating_income, excluded.non_operating_income_expense, ' \
                'excluded.pretax_income, excluded.tax_provision, excluded.earnings_from_equity_interest, ' \
                'excluded.discontinued_operations, excluded.consolidated_net_income, excluded.non_controlling_interests, ' \
                'excluded.net_income, excluded.basic_earnings_per_share, excluded.diluted_earnings_per_share, ' \
                'excluded.current_assets, excluded.non_current_assets, excluded.total_assets, excluded.current_liabilities, ' \
                'excluded.non_current_liabilities, excluded.total_liabilities, excluded.non_current_provisions, ' \
                'excluded.total_equity, excluded.common_stock_equity, excluded.operating_cash_flow, excluded.investing_cash_flow, ' \
                'excluded.financing_cash_flow, excluded.change_in_cash, excluded.beginning_cash_position, ' \
                'excluded.end_cash_position, excluded.issuance_of_debt, excluded.repayment_of_debt, excluded.html_data, ' \
                'excluded.raw_data, excluded.json_data, excluded.json_result, excluded.url, excluded.s3_url, excluded.updated_at)'
        psycopg2.extras.execute_values(self.cursor, query, data, page_size=1000) 
        self.connection.commit()

    def AddUrlsData(self, data):

        query = 'INSERT INTO euronext_urls (symbol, market, market_full_name, fiscal_year, fiscal_period, url, updated_at) ' \
                'VALUES %s ON CONFLICT (symbol, fiscal_year, fiscal_period, url) DO UPDATE SET (market, market_full_name, ' \
                'updated_at) = (excluded.market, excluded.market_full_name, excluded.updated_at)'
        psycopg2.extras.execute_values(self.cursor, query, data, page_size=1000) 
        self.connection.commit()

    def AddCachedUrlsData(self, data):

        query = 'INSERT INTO euronext_urls_cache (symbol, url) VALUES %s ON CONFLICT (url) DO UPDATE SET symbol = excluded.symbol'
        psycopg2.extras.execute_values(self.cursor, query, data, page_size=1000) 
        self.connection.commit()

    def AddFeedData(self, data):

        query = 'INSERT INTO euronext_feed (symbol, registrant_name, fiscal_period, date, updated_at) VALUES %s ' \
                'ON CONFLICT (symbol, fiscal_period, date) DO UPDATE SET (registrant_name, updated_at) = ' \
                '(excluded.registrant_name, excluded.updated_at)'
        psycopg2.extras.execute_values(self.cursor, query, data, page_size=1000) 
        self.connection.commit()

    def GetCachedUrls(self, symbol):

        query = 'SELECT url FROM euronext_urls_cache WHERE symbol = %s'
        self.cursor.execute(query, (symbol,))
        result = [item[0] for item in self.cursor.fetchall()]
        self.connection.commit()

        return result

    def GetLastUpdateTime(self):

        query = 'SELECT MAX(updated_at) FROM euronext_statements'
        self.cursor.execute(query)
        result = self.cursor.fetchone()
        self.connection.commit()

        return result[0] if result else None

    def StatementsDataExist(self):

        query = 'SELECT COUNT(*) FROM euronext_statements'
        self.cursor.execute(query)
        result = self.cursor.fetchone()
        self.connection.commit()

        return result[0]

   