import argparse
import json
import re
import shutil
import requests
import os
from bs4 import BeautifulSoup
import img2pdf
import tqdm

PATH = os.path.dirname(os.path.realpath(__file__))
COOKIES_FILE = os.path.join(PATH, "cookies.json")


def load_cookie():
    cookie = json.load(open(COOKIES_FILE))
    if isinstance(cookie, list):
        cookie_list = cookie
        cookie = {}
        for item in cookie_list:
            cookie[item["name"]] = item["value"]
    return cookie


class StoryBeeCrawler:
    BASE_URL = "https://www.storybee.space/"
    BASE_URL_V1 = "http://books.storybee.space/books/"
    SLIDE_URL = "http://books.storybee.space/books/{}/files/large/"
    LOGIN_ENTRY_URL = ""
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": LOGIN_ENTRY_URL,
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/90.0.4430.212 Safari/537.36"
    }

    def __init__(self, bookurl: str):
        print(bookurl)
        self.session = requests.session()
        self.session.headers.update(self.HEADERS)
        self.session.cookies.update(load_cookie())
        if bookurl.startswith(self.BASE_URL_V1):
            self.book = re.search(r"books/(\w+)/#", bookurl).group(1)
        else:
            self.book = bookurl.split("/")[-1]
        self.v2 = not bookurl.startswith(self.BASE_URL_V1)
        self.book_dir = os.path.join(PATH, "Books")

        if not os.path.exists(self.book_dir):
            os.makedirs(self.book_dir)

        self.process_current_book()

    def process_current_book(self):
        book_dir = os.path.join(PATH, self.book)
        if not os.path.exists(book_dir):
            os.makedirs(book_dir)

        book_url = os.path.join(self.BASE_URL, self.book)
        if not self.v2:
            book_url = os.path.join(self.BASE_URL_V1, self.book)
        response = self.request_provider(book_url)
        soup = BeautifulSoup(response.content, features="html.parser")
        slide_list = soup.find_all("figure", class_="gallery-slideshow-item")

        images = []

        if len(slide_list) == 0:
            config_js = soup.find("script", src=re.compile(r"config.js"))
            query_id = config_js["src"].split("?")[-1]
            response = self.request_provider(book_url + "/" + config_js["src"])
            js_content = str(response.content, encoding="utf-8")
            result = re.match(r"var\shtmlConfig\s=\s(\{.*});", js_content, re.S | re.VERBOSE)
            json_str = result.group(1)
            json_content = json.loads(json_str)
            slide_list = json_content["fliphtml5_pages"]
            book_id = self.book
            self.book = json_content["meta"]["title"]
            print("Start collecting book slide info: {} with {} slides".format(self.book, len(slide_list)))
            for slide_item in slide_list:
                img_name = slide_item["n"][0]
                img_src = self.SLIDE_URL.format(book_id) + img_name + "?" + query_id
                full_img_name = os.path.join(book_dir, img_name)
                images.append((img_src, full_img_name))
        else:
            print("Start collecting book slide info: {} with {} slides".format(self.book, len(slide_list)))
            for slide_item in slide_list:
                img_src = slide_item.find("img")['src']
                img_name = img_src.split("/")[-1]
                full_img_name = os.path.join(book_dir, img_name)
                images.append((img_src, full_img_name))

        count = len(images)
        print("Start downloading slides")
        with tqdm.tqdm(total=count) as bar:
            for img_src, local_path in images:
                if os.path.exists(local_path):
                    bar.update(1)
                    continue
                img_response = self.request_provider(img_src)
                with open(local_path, "wb") as img:
                    for chunk in img_response.iter_content(1024):
                        img.write(chunk)
                    bar.update(1)
        print("Generating the pdf file")
        with open(os.path.join(self.book_dir, self.book + ".pdf", ), "wb") as pdf:
            pdf.write(img2pdf.convert([img for _, img in images]))
        print("Done")
        # shutil.rmtree(book_dir)

    def request_provider(self, url, method="get", data=None, perform_redirect=True, **kwargs):
        response = None
        try:
            response = getattr(self.session, method)(
                url,
                data=data,
                allow_redirects=False,
                **kwargs
            )
        except (requests.ConnectionError, requests.ConnectTimeout, requests.RequestException) as request_exception:
            print(request_exception)

        if response.is_redirect and perform_redirect:
            return self.request_provider(response.next.url, method, None, perform_redirect)
        return response


def main(args):
    StoryBeeCrawler(args.bookurl)


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(prog="StoryBeeCrawler.py",
                                        description="Download and Generate pdf of your favorite books"
                                                    " from storybee.space",
                                        add_help=False,
                                        allow_abbrev=False)
    arguments.add_argument("bookurl", metavar="<Book name>", help="The full url of you favorite book")

    main(arguments.parse_args())
