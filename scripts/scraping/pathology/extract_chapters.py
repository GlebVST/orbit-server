from lxml.html import fromstring
import requests
from itertools import cycle
import traceback
from bs4 import BeautifulSoup
import csv
import collections

def extractChapters(url_deque, file_pointer, proxy_pool):
    page_url = url_deque.popleft()

    proxy = next(proxy_pool)
    try:
        r = requests.get(page_url, proxies={"http": proxy, "https": proxy})

    except:
        # most free proxies will often get connection errors. So, if this happens,
        # we retry the entire request by adding the url back into the page_url_deque
        print("Skipping " + page_url + ". Connnection error with proxy " + str(proxy))
        url_deque.appendleft(page_url)

        return []

    soup = BeautifulSoup(r.content, features="lxml")

    print(r.content)
    header_title = soup.find_all("div", class_=["home_content clearfix"])

    print(header_title)

    # if the page did not load properly, that means maybe the page only partially
    # loaded, or the web server was unavailable. So, we retry the entire request by
    # adding the url back into the page_url_deque.
    if len(header_title) == 0:
        print("Did not load page " + page_url + " properly, could not find header")
        url_deque.appendleft(page_url)
        return []

    print(page_url)

    print(header_title[0].find_all("a"))

    chapters = header_title[0].find_all("a")

    for chapter in chapters:
        file_pointer.writerow([chapter.text, chapter.get("href")])

if __name__=="__main__":

    # this is a list of proxies. You can get a list of proxies from 
    # http://free-proxy.cz/en/proxylist/country/all/https/ping/level1
    # there is a very high chance that the below proxy will not work in the future
    # try to choose an elite/high anonymity proxy. If none are available, try to 
    # choose an anonymous proxy
    proxies = ['144.217.101.245:3129']
    proxy_pool = cycle(proxies)

    page_urls_deque = collections.deque(['https://www.pathologyoutlines.com/'])

    f = csv.writer(open("pathology_outline_chapters.csv", "w"))
    f.writerow(["Chapter Name", "Chapter Url"])

    while page_urls_deque:
        extractChapters(page_urls_deque, f, proxy_pool)
