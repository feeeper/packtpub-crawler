import requests
import re
from os.path import split
from utils import make_soup, wait, download_file
from logs import *
import sys

class Packpub(object):
    """
    """

    def __init__(self, config, dev):
        self.__config = config
        self.__dev = dev
        self.__delay = float(self.__config.get('delay', 'delay.requests'))
        self.__url_base = self.__config.get('url', 'url.base')
        self.__headers = self.__init_headers()
        self.__session = requests.Session()
        self.info = {
            'paths': []
        }
        # utf8 issue
        # reload(sys)
        # sys.setdefaultencoding('utf8')

    def __init_headers(self):
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2228.0 Safari/537.36'
        }

    def __log_response(self, response, method='GET', detail=False):
        print '[-] {0} {1} | {2}'.format(method, response.url, response.status_code)
        if detail:
            print '[-] cookies:'
            log_dict(requests.utils.dict_from_cookiejar(self.__session.cookies))
            print '[-] headers:'
            log_dict(response.headers)

    def __GET_login(self):
        url = self.__url_base
        if self.__dev:
            url += self.__config.get('url', 'url.loginGet')
        else:
            url += self.__config.get('url', 'url.login')

        response = self.__session.get(url, headers=self.__headers)
        self.__log_response(response)

        soup = make_soup(response)
        form = soup.find('form', {'id': 'packt-user-login-form'})
        self.info['form_build_id'] = form.find('input', attrs={'name': 'form_build_id'})['value']
        self.info['form_id'] = form.find('input', attrs={'name': 'form_id'})['value']

    def __POST_login(self):
        data = self.info.copy()
        data['email'] = self.__config.get('credential', 'credential.email')
        data['password'] = self.__config.get('credential', 'credential.password')
        data['op'] = 'Login'

        url = self.__url_base
        response = None
        if self.__dev:
            url += self.__config.get('url', 'url.loginPost')
            response = self.__session.get(url, headers=self.__headers, data=data)
            self.__log_response(response)
        else:
            url += self.__config.get('url', 'url.login')
            response = self.__session.post(url, headers=self.__headers, data=data)
            self.__log_response(response, 'POST', True)

        soup = make_soup(response)
        div_target = soup.find('div', {'id': 'deal-of-the-day'})

        title = div_target.select('div.dotd-title > h2')[0].text.strip()
        self.info['title'] = title.replace(':', ' ')
        self.info['filename'] = title.encode('ascii', 'ignore').replace(' ', '_')
        self.info['description'] = div_target.select('div.dotd-main-book-summary > div')[2].text.strip()
        self.info['url_image'] = 'https:' + div_target.select('div.dotd-main-book-image img')[0]['src']
        self.info['url_claim'] = self.__url_base + div_target.select('a.twelve-days-claim')[0]['href']
        # remove useless info
        self.info.pop('form_build_id', None)
        self.info.pop('form_id', None)

    def __GET_claim(self):
        if self.__dev:
            url = self.__url_base + self.__config.get('url', 'url.account')
        else:
            url = self.info['url_claim']

        response = self.__session.get(url, headers=self.__headers)
        self.__log_response(response)

        soup = make_soup(response)
        div_target = soup.find('div', {'id': 'product-account-list'})

        # only last one just claimed
        div_claimed_book = div_target.select('.product-line')[0]
        self.info['book_id'] = div_claimed_book['nid']
        self.info['author'] = div_claimed_book.find(class_='author').text.strip()

        source_code = div_claimed_book.find(href=re.compile('/code_download/*'))
        if source_code is not None:
            self.info['url_source_code'] = self.__url_base + source_code['href']

    def __GET_all(self):
        if self.__dev:
            url = self.__url_base + self.__config.get('url', 'url.account')
        else:
            url = self.info['url_claim']

        response = self.__session.get(url, headers=self.__headers)
        self.__log_response(response)

        soup = make_soup(response)
        div_target = soup.find('div', {'id': 'product-account-list'})

        div_claimed_books = div_target.select('.product-line')

        self.books = []
        for book in div_claimed_books:
            if 'nid' in book.attrs:
                # title = book['title'].replace(':', '').replace('.', '').replace("'", '').replace('\u2019', '')
                original_title = book['title'].replace(':', '').replace('.', '')
                title = ''.join([i if ord(i) < 128 else ' ' for i in original_title]).strip()
                nid = book['nid']
                cover = ('https:' + book.select('img')[0].attrs['src']) if ('src' in book.select('img')[0].attrs) else ''

                source_code = book.find(href=re.compile('/code_download/*'))
                if source_code is not None:
                    source_code = self.__url_base + source_code['href']

                self.books.append({
                    'title': title,
                    'nid': nid,
                    'cover': cover,
                    'sources': source_code})
        return

    def run(self):
        """
        """
        self.__GET_login()
        wait(self.__delay)
        self.__POST_login()
        wait(self.__delay)
        # self.__GET_claim()
        self.__GET_all()
        wait(self.__delay)

    def download_ebooks(self, types, nid=0, title=''):
        """
        """
        if nid == 0:
            nid = self.info['book_id']

        if title == '':
            title = self.info['filename']

        title = title.replace('[eBook]', '').strip()

        downloads_info = [dict(type=type,
            url=self.__url_base + self.__config.get('url', 'url.download').format(nid, type),
            filename=title + '.' + type)
            for type in types]

        directory = self.__config.get('path', 'path.ebooks')
        for download in downloads_info:
            fn = download['filename']
            directory = directory.format(fn.split('.')[0]).replace(' [eBook]', '')
            self.info['paths'].append(
                download_file(self.__session, download['url'], directory, fn))

    def download_all_ebooks(self, types, download_extras):
        total_books = len(self.books)
        downloaded_books_count = 0
        for book in self.books:
            self.download_ebooks(types, book['nid'], book['title'])

            if download_extras:
                self.download_extras(book['cover'], book['title'], book['sources'] if 'sources' in book else '')

            downloaded_books_count += 1
            print('[-] download books {0}/{1}'.format(downloaded_books_count, total_books))
        return

    def download_extras(self, img='', filename='', url_source_code=''):
        """
        """

        if img == '':
            img = self.info['url_image']

        if filename == '':
            filename = self.info['filename']

        filename = ''.join([i if ord(i) < 128 else '' for i in filename]).strip()

        if url_source_code == '':
            if 'url_source_code' in self.info:
                url_source_code = self.info['url_source_code']

        directory = self.__config.get('path', 'path.extras')
        filename_replace = filename.replace(' [eBook]', '').strip()
        directory = directory.format(filename_replace)

        url_image = img

        if url_image != '' and url_image is not None:
            self.info['paths'].append(download_file(self.__session, url_image, directory, filename_replace + '.' + url_image.split('.')[-1]))

        if url_source_code != '' and url_source_code is not None:
            self.info['paths'].append(download_file(self.__session,
                                                    url_source_code,
                                                    directory,
                                                    filename.split('.')[0].replace(' [eBook]', '') + '.zip'))

    def download_all_extras(self):
        #for book in self.books:
        book = self.books[1]
        print('cover: ' + book['cover'])
        print('title: ' + book['title'])
        print('sources: ' + book['sources'] if 'sources' in book else 'no sources')
        self.download_extras(book['cover'], book['title'], book['sources'] if 'sources' in book else '')
        return