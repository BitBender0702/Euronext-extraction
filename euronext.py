import re
import time
import requests
from lxml.html import document_fromstring
from browser import Browser

class Euronext:

    def __init__(self):

        self.browser = Browser()
        self.headers = self.GetHeaders()
        self.languages = set(['bg', 'cs', 'da', 'de', 'nl', 'el', 'et', 'fi', 'fr', 'hr', 'hu', 'is', 'it', 
                              'lv', 'lt', 'lb', 'mt', 'no', 'pl', 'pt', 'ro', 'sk', 'sl', 'es', 'sv'])
        self.language_regex, self.page_regex, self.file_regex = self.GetRegexes()

    def __del__(self):
        
        self.browser.Quit()

    def GetHeaders(self):

        return {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,'
                          '*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'accept-language': 'en-US;q=0.8,en;q=0.7',
	            'cache-control': 'max-age=0',
	            'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
	            'sec-ch-ua-mobile': '?1',
	            'sec-ch-ua-platform': 'Android',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
	            'sec-fetch-user': '?1',
                'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Mobile Safari/537.36'}
        
    def GetRegexes(self):

        language_regex = r'(?<=\/)(%s)(?=\/|$)' % '|'.join(self.languages)
        language_regex = re.compile(language_regex, re.IGNORECASE)

        page_regex = r'invest|finan[sc]|regulat|réglement|document'
        page_regex = re.compile(page_regex, re.IGNORECASE)

        file_regex = r'statement|report|filing|result|déclaration|rapport|résultat|jaarverslag|(?:reference|registration)' \
                     r'[\s_-]*document|document[\s_-]*(?:de|d’)?[\s_-]*(?:référence|d’enregistrement|reference)' \
                     r'|(?:hy|fy|q\d|ra|rs|rfa|rfs|udr|urd)[\s_-]*(?:19|20)\d{2}'
        file_regex = re.compile(file_regex, re.IGNORECASE)

        return language_regex, page_regex, file_regex

    def ExtractCompanies(self, html):

        root = document_fromstring(html)
        rows = root.cssselect('table[id="stocks-data-table-es"] tbody tr')
        companies = []

        for row in rows:
            columns = row.cssselect('td')
            texts = [column.text_content().strip() for column in columns[1:5]]
            if all(texts):
                registrant_name, isin, symbol, market = texts
                quotes_link = columns[1].cssselect('a')[0]
                quotes_url = 'https://live.euronext.com%s' % quotes_link.attrib['href']

                match = re.search(r'^.+equities\/[^\/]+\/', quotes_url)
                if match is not None:
                    info_url = match.group() + 'company-information'
                    companies.append((symbol, isin, registrant_name, market, info_url))

        return companies

    def GetCompanies(self):

        self.browser.LoadPage('https://live.euronext.com/en/products/equities/list')
        accept_button = self.browser.WaitForElement('div[id="popup-buttons"] button', timeout=10)
        if accept_button is not None:
            accept_button.click()
            time.sleep(1)

        companies, last_company = set(), None
        while 1:
            self.browser.WaitForElement('table[id="stocks-data-table-es"] tbody tr')
            new_companies = self.ExtractCompanies(self.browser.PageSource())
            if new_companies[-1] == last_company:
                time.sleep(1)
                continue

            last_company = new_companies[-1]
            companies |= set(new_companies)
            next_button = self.browser.GetElement('a[id="stocks-data-table-es_next"]')
            class_name = next_button.get_attribute('class')
            if 'disabled' in class_name:
                companies = sorted(companies, key=lambda company: company[2])
                break

            self.browser.ScrollIntoView(next_button)
            time.sleep(1)
            next_button = self.browser.GetElement('a[id="stocks-data-table-es_next"]')
            next_button.click()
            time.sleep(1)

        return companies

    def GetCompanyInfo(self, info_url):

        if self.browser.Url() != info_url:
            self.browser.LoadPage(info_url)

        description_element = self.browser.WaitForElement('p[class^="address__text"]')
        market_full_name = description_element.text.split('\n')[0].strip() if description_element else None

        address_elements = self.browser.GetElement('address[id] > div:nth-of-type(1) > div:not(:first-of-type)', multiple=True)
        if len(address_elements) >= 3:
            address_line = address_elements[0].text.strip()
            address_city = address_elements[-2].text.strip()
            address_country = address_elements[-1].text.strip()
        else:
            address_line, address_city, address_country = None, None, None

        phone_element = self.browser.GetElement('address[id] a[href^="tel"]')
        phone_number = phone_element.text.replace(' ', '').strip() if phone_element else None
        website_element = self.browser.GetElement('address[id] a[href^="http"]')
        website = website_element.text.strip() if website_element else None

        return market_full_name, address_line, address_city, address_country, phone_number, website

    def ExtractWebsite(self):

        links = self.browser.GetElement('a[data-toggle]', multiple=True)
        for link in links:
            if not link.is_displayed():
                continue

            link.click()
            dialog = self.browser.WaitForElement('div[id="block-company-press-releases-block-off-canvas"] div[role="document"]', 
                                                 timeout=10)
            if dialog is not None:
                text = dialog.text.strip()
                match = re.search(r'\w+\.(?:com|net|org)', text)
                if match is not None:
                    website = 'https://%s' % match.group()
                    return website
         
            close_buttons = self.browser.GetElement('button[data-dismiss]', multiple=True)
            for close_button in close_buttons:
                if close_button.is_displayed():
                    close_button.click()
                    break

        return None
    
    def GetEnglishUrl(self, url):

        english_url = self.language_regex.sub('en', url)
        if english_url != url:
            response = requests.get(english_url, headers=self.headers)
            if response.status_code == 200:
                return english_url

        return None

    def GetUrls(self):

        url = self.browser.Url()
        html = self.browser.PageSource()
        root = document_fromstring(html)

        root.make_links_absolute(url)
        links = root.cssselect('a[href]')
        invalid_start_regex = re.compile(r'^(?:javascript|mailto)', re.IGNORECASE)

        urls = set()
        for link in links:
            url = link.attrib['href']
            if url and not invalid_start_regex.search(url):
                text = link.text_content().strip()
                urls.add((url, text))

        return urls

    def ExtractPageUrls(self, page_url):

        components = requests.utils.urlparse(page_url)
        path = components.path.strip('/')
        is_home_page = path == '' or path in self.languages

        page_url = self.GetEnglishUrl(page_url) or page_url
        page_url = page_url.strip('/')
        if not self.browser.LoadPage(page_url):
            return set()

        self.browser.WaitForElement('body')
        urls = self.GetUrls()
        page_urls = set([] if is_home_page else [page_url])

        for url, text in urls:
            if url and re.search(r'\.html?|\/[^.]+$', url):
                if (not is_home_page and url.startswith(page_url)) or self.page_regex.search(url) or self.page_regex.search(text):
                    url = re.split(r'#|\?', url)[0].strip('/')
                    page_urls.add(url)
                    
        slash_regex = re.compile(r'(?<!:)\/\/')
        for url in list(page_urls):
            url_without_prefix = slash_regex.sub('/', self.language_regex.sub('', url))
            if url_without_prefix != url and url_without_prefix in page_urls:
                page_urls.discard(url)               

        return page_urls

    def GetPageUrls(self, info_url):

        if self.browser.Url() != info_url:
            self.browser.LoadPage(info_url)

        page_link = self.browser.WaitForElement('address a[target="_blank"]')
        if page_link is None:
            email_link = self.browser.GetElement('a[href^="mailto"]')
            if email_link is None:
                page_url = self.ExtractWebsite()
            else:
                email_url = email_link.get_attribute('href')
                page_url = 'https://%s' % email_url.split('@')[-1]
        else:
            page_url = page_link.get_attribute('href')
            if not page_url.startswith('http'):
                page_url = 'https://%s' % page_url
       
        if page_url is None:
            page_urls = set()
        else:
            page_urls = self.ExtractPageUrls(page_url)            

        return list(page_urls)

    def GetUniqueSelector(self, element):

        path = []
        while 1:
            parent = element.getparent()
            if parent is None:
                break

            tag = element.tag
            siblings = [child for child in parent.getchildren() if child.tag == tag]
            if len(siblings) > 1:
                idx = siblings.index(element)
                tag += ':nth-of-type(%d)' % (idx + 1)

            path.append(tag)
            element = parent

        path = path[::-1]
        selector = ' > '.join(path).lower()

        return selector

    def FindLists(self):

        html = self.browser.PageSource()
        root = document_fromstring(html)
        list_item_selectors = ['ul > li', 'ol > li', 'div > a', 'div > div']

        list_items_map = {}
        for list_item_selector in list_item_selectors:
            lists_items = root.cssselect(list_item_selector)
            for list_item in lists_items:
                list = list_item.getparent()
                if list in list_items_map:
                    list_items_map[list].append(list_item)
                else:
                    list_items_map[list] = [list_item]

        selectors = []
        for list_items in list_items_map.values():
            if len(list_items) < 2:
                continue

            texts = [list_item.text_content().strip() for list_item in list_items]
            number_texts = [text for text in texts if text.isdigit()]
            number_ratio = len(number_texts) / len(texts)

            if number_ratio >= 0.5:
                unique_selector = self.GetUniqueSelector(list_items[0])
                unique_selector = unique_selector.rsplit(':nth-of-type', maxsplit=1)[0]
                selectors = [selector for selector in selectors if selector not in unique_selector]
                if all(unique_selector not in selector for selector in selectors):
                    selectors.append(unique_selector)

        return selectors

    def IterateList(self, list_item_selector):

        urls, previous_texts, texts = set(), set(), []
        while 1:
            list_items = self.browser.GetElement(list_item_selector, multiple=True) or []
            if not list_items:
                text = next((text for text in texts if text.isdigit() and text not in previous_texts), None)
                if text is not None:
                    tag = list_item_selector.rsplit(' > ', maxsplit=1)[-1]
                    list_item = self.browser.GetElementByText(text, tag)
                    if list_item is not None:
                        list_item_selector = self.browser.GetSelector(list_item)
                        list_item_selector = list_item_selector.rsplit(':nth-of-type', maxsplit=1)[0] 
                        list_items = self.browser.GetElement(list_item_selector, multiple=True) or []

            texts = [list_item.text.strip() for list_item in list_items]
            idx = next((idx for idx, text in enumerate(texts) if text.isdigit() and text not in previous_texts), None)
            if idx is None:
                break

            list_item, text = list_items[idx], texts[idx]
            previous_texts.add(text)
            selector = self.browser.GetSelector(list_item)
            self.browser.ScrollIntoView(list_item)
            time.sleep(1)
            list_item = self.browser.GetElement(selector)

            try:
                self.browser.RemoveOverlappingElements(list_item)
                list_item.click()
                time.sleep(1)
                urls |= self.GetUrls()
            except:
                pass

        return urls

    def CheckLists(self):     
       
        urls, list_item_selectors = set(), self.FindLists()
        for list_item_selector in list_item_selectors:
            list_selector = list_item_selector.rsplit(' > ', maxsplit=1)[0]
            list = self.browser.GetElement(list_selector)
            if list is None:
                continue

            list_parent = list.find_element_by_xpath('..')
            list_parent_class = list_parent.get_attribute('class')
            if 'dropdown' in list_parent_class:
                self.browser.SetAttribute(list, 'style', 'display: block !important; opacity: 1 !important')

            urls |= self.IterateList(list_item_selector)                       

        return urls

    def SelectOptions(self):

        urls = set()
        options = self.browser.GetElement('select option', multiple=True) or []
        option_selectors = [self.browser.GetSelector(option) for option in options[:60]]

        for option_selector in option_selectors:
            option = self.browser.GetElement(option_selector)
            if option is not None:
                text = option.text
                if re.search(r'(?:19|20)\d{2}', text):
                    select = option.find_element_by_xpath('..')
                    self.browser.SelectOption(select, text)
                    time.sleep(1)

                    idx = option_selector.rfind('form')
                    if idx != -1:
                        input_selector = option_selector[:idx + 4] + ' input[type="submit"]'
                        input = self.browser.GetElement(input_selector)
                        if input is not None:
                            try:
                                self.browser.ScrollIntoView(input)
                                time.sleep(1)
                                self.browser.RemoveOverlappingElements(input)
                                input.click()

                                while 1:
                                    time.sleep(1)
                                    disabled = input.get_attribute('disabled')
                                    if disabled is None:
                                        break                                        
                            except:
                                pass

                    urls |= self.GetUrls()
                    urls |= self.CheckLists()

        return urls

    def ExtractStatementUrls(self, page_url):

        if not self.browser.LoadPage(page_url):
            return set()

        self.browser.WaitForElement('body')
        link = self.browser.GetElement('head > link[rel="alternate"][hreflang="en"]')
        if link is not None:
            english_url = link.get_attribute('href')
            if english_url != page_url and self.browser.LoadPage(english_url):
                self.browser.WaitForElement('body')

        self.browser.ScrollToBottom()
        time.sleep(1)
        urls = self.GetUrls()
        urls |= self.CheckLists()
        urls |= self.SelectOptions()
               
        statement_urls = set()
        for url, text in urls:
            if url and re.search(r'\.pdf(\?|$)', url):
                if self.file_regex.search(url) or self.file_regex.search(text):
                    statement_urls.add(url)

        return statement_urls

    def GetStatementUrls(self, info_url):

        urls = ['*://*googlesyndication.com/*', '*://*doubleclick.net/*', '*://*googletagmanager.com/*', 
                '*://*google-analytics.com/*', '*://*cloudflare.com/*', '*://*facebook.net/*', 
                '*://*cookiebot.com/*', '*://*cookieinformation.com/*', '*://*consentframework.com/*', 
                '*://*cookielaw.org/*', '*://*privacy-center.org/*']
        self.browser.BlockUrls(urls)

        try:
            page_urls = self.GetPageUrls(info_url)
        except:
            return []

        statement_urls = set()
        for page_url in page_urls:
            try:
                statement_urls |= self.ExtractStatementUrls(page_url)
            except:
                continue

        return list(statement_urls)