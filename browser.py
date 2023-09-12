import re
import sys
import time
import psutil
from contextlib import redirect_stdout, redirect_stderr
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
import selenium.webdriver.support.expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from multi_processing import Mutex

class Browser:

    def __init__(self, headless=True):

        self.headless = headless
        self.driver = self.CreateChromedriver(headless)
        self.window_handles = set()
        self.page_loads = 0
        if sys.platform == 'win32':
            import win32api
            win32api.SetConsoleCtrlHandler(lambda ctrl_type: Browser.CleanUp(), True)

    def CreateChromedriver(self, headless):

        options = Options()
        options.set_capability('unhandledPromptBehavior', 'dismiss')
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

        arguments = ['start-maximized', '--window-size=1920,1080', '--incognito', '--allow-running-insecure-content', 
                     '--ignore-certificate-errors', '--no-proxy-server', '--proxy-server="direct://"', '--proxy-bypass-list=*']      
        for argument in arguments:
            options.add_argument(argument)

        if headless:
            options.add_argument('--headless')

        with redirect_stdout(None), redirect_stderr(None), Mutex('browser'):
            driver = webdriver.Chrome(ChromeDriverManager().install(), chrome_options=options)
            driver.set_page_load_timeout(20)

        return driver

    def Restart(self):

        self.driver.quit()
        while 1:
            try:
                self.driver = self.CreateChromedriver(self.headless)
                self.window_handles = set()
                break
            except WebDriverException:
                continue

    def ApplyEvasions(self):

        window_handle = self.driver.current_window_handle
        if window_handle not in self.window_handles:
            self.window_handles.add(window_handle)
            user_agent = self.driver.execute_script('return navigator.userAgent')
            user_agent = user_agent.replace('HeadlessChrome', 'Chrome')
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {'userAgent': user_agent})

    def TabsCount(self):

        return len(self.driver.window_handles)

    def OpenTab(self, timeout=20):

        tabs_count = len(self.driver.window_handles)
        self.driver.execute_script('window.top.open("")')
        wait = WebDriverWait(self.driver, timeout)
        wait.until(lambda driver: len(driver.window_handles) == tabs_count + 1)

    def CloseTab(self, timeout=20):

        tabs_count = len(self.driver.window_handles)
        self.driver.close()
        wait = WebDriverWait(self.driver, timeout)
        wait.until(lambda driver: len(driver.window_handles) == tabs_count - 1)

    def SwitchToTab(self, idx):

        window_handle = self.driver.window_handles[idx]
        self.driver.switch_to.window(window_handle)

    def Url(self):

        try:
            url = self.driver.current_url
        except TimeoutException:
            url = ''

        return url

    def PageSource(self):

        try:
            page_source = self.driver.page_source
        except TimeoutException:
            page_source = ''

        return page_source

    def LoadPage(self, url, timeout=20, retries=3):

        if self.page_loads >= 300:
            self.Restart()
            self.page_loads = 0

        self.ApplyEvasions()
        wait = WebDriverWait(self.driver, timeout=timeout)
        for iteration in range(retries):
            try:
                self.driver.get(url)
            except WebDriverException:
                time.sleep(1)
                continue

            self.page_loads += 1
            try:
                wait.until(lambda driver: driver.execute_script('return document.readyState') == 'complete')
            except TimeoutException:
                time.sleep(1)
                continue

            return True

        return False

    def WaitForElement(self, selector, timeout=20, multiple=False):

        wait = WebDriverWait(self.driver, timeout=timeout)
        try:
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
        except TimeoutException:
            return None

        find_func = self.driver.find_elements_by_css_selector if multiple else self.driver.find_element_by_css_selector
        return find_func(selector)

    def GetElement(self, selector, multiple=False):
       
        find_func = self.driver.find_elements_by_css_selector if multiple else self.driver.find_element_by_css_selector
        try:
            element = find_func(selector)
        except:
            element = None

        return element

    def GetElementByText(self, text, tag=None, multiple=False):

        xpath = '//%s[text()="%s"]|//%s[*[text()="%s"]]' % (tag or '*', text, tag or '*', text)
        find_func = self.driver.find_elements_by_xpath if multiple else self.driver.find_element_by_xpath

        try:
            element = find_func(xpath)
        except:
            element = None

        return element

    def GetSelector(self, element):

        script = '''
                 var element = arguments[0], path = [];
                 while (1) 
                 {
                    var parent = element.parentNode;
                    if(!parent)
                    {
                        break;
                    }

                    var tag = element.tagName;
                    var children = Array.from(parent.children);
                    var siblings = children.filter(children => children.tagName == tag);
                    if(siblings.length > 1)
                    {
                        var idx = siblings.indexOf(element);
                        tag += `:nth-of-type(${idx + 1})`;
                    }
                    path.push(tag);
                    element = parent;
                };

                path = path.reverse();
                return path.join(' > ').toLowerCase();
                '''

        return self.driver.execute_script(script, element)

    def SetAttribute(self, element, attribute, value):

        script = 'arguments[0].setAttribute("%s", "%s")' % (attribute, value)
        self.driver.execute_script(script, element)

    def ScrollIntoView(self, element):

        script = 'arguments[0].scrollIntoView({ behavior: "auto", block: "center", inline: "center" })'
        self.driver.execute_script(script, element)

    def ScrollToBottom(self):

        while 1:
            script = 'return [window.pageYOffset, window.innerHeight, window.document.documentElement.scrollHeight]'
            y_offset, window_height, scroll_height = self.driver.execute_script(script)
            if y_offset + window_height >= scroll_height or scroll_height > 20000:
                break

            self.driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(0.1)

    def IsScrollAtBottom(self):

        script = 'return [window.pageYOffset, window.innerHeight, window.document.documentElement.scrollHeight]'
        y_offset, window_height, scroll_height = self.driver.execute_script(script)
        return y_offset + window_height >= scroll_height

    def SelectOption(self, element, text):

        select = Select(element)
        select.select_by_visible_text(text)

    def RemoveOverlappingElements(self, element):

        script = '''
                 var element = arguments[0];
                 var labels = Array.from(element.labels || []);
                 var rect = element.getBoundingClientRect();
                 var x = rect['x'] + rect['width'] / 2;
                 var y = rect['y'] + rect['height'] / 2;

                 while (1)
                 {
                     var top_element = document.elementFromPoint(x, y);
                     var is_same_node = element.isSameNode(top_element);
                     var contains = element.contains(top_element);
                     var is_label = labels.includes(top_element);

                     if(!top_element || is_same_node || contains || is_label)
                     {
                         break;
                     }
                     top_element.remove();
                 }
                 '''

        self.driver.execute_script(script, element)
           
    def GetAllStyles(self):

        script = '''
                 var styles = [];
                 for (var i = 0; i < document.styleSheets.length; ++i)
                 {
                     var sheet = document.styleSheets[i];
                     var rules = `cssRules` in sheet? sheet.cssRules : sheet.rules;
                     for (var j = 0; j < rules.length; ++j)
                     {
                         var rule = rules[j]; 
                         if (`cssText` in rule)
                         {
                             styles.push(rule.cssText);
                         }
                         else
                         {
                             styles.push(rule.selectorText + ` {\n` + rule.style.cssText + `\n}\n`);
                         }
                     }
                 }

                 return styles.join(`\n`);
                 '''

        return self.driver.execute_script(script)

    def GetScreenshot(self):

        script = 'return [document.body.parentNode.scrollWidth, document.body.parentNode.scrollHeight]'
        full_width, full_height = self.driver.execute_script(script)
        window_size = self.driver.get_window_size()

        self.driver.set_window_size(full_width, full_height)
        image = self.driver.find_element_by_tag_name('body').screenshot_as_png
        self.driver.set_window_size(window_size['width'], window_size['height'])

        return image

    def Back(self):

        self.driver.back()

    def Quit(self):

        self.driver.quit()

    def BlockUrls(self, urls):

        self.driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': urls})
        self.driver.execute_cdp_cmd('Network.enable', {})

    @staticmethod
    def CleanUp():

        for process in psutil.process_iter():
            try:
                if process.name() == 'chrome.exe' and '--headless' in process.cmdline():
                    process.kill()
            except psutil.NoSuchProcess:
                continue



