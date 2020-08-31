from lxml.html import fromstring
import requests
from itertools import cycle
import traceback
from bs4 import BeautifulSoup
import csv
import collections
import re


def extractDdx(page_url_deque, file_pointer, proxy_pool, error_file_pointer):

    chapter_name, chapter_url, section_name, subsection_name, article_title, article_url, proxy_num = page_url_deque.popleft()

    print(proxy_num)
    if proxy_num >= 5:
        try:
            r = requests.get(article_url)
            print(r)
        except:
            print("BAD URL, SKIPPING " + article_url)
            return []
    else:
        proxy = next(proxy_pool)
        try:
            r = requests.get(article_url, proxies={"http": proxy, "https": proxy})

        except:
            # most free proxies will often get connection errors. So, if this happens,
            # we retry the entire request by adding the url back into the page_url_deque
            print("Skipping " + article_url + ". Connnection error with proxy " + str(proxy))
            page_url_deque.appendleft((chapter_name, chapter_url, section_name, subsection_name, article_title, article_url, proxy_num + 1))
            
            return []

    soup = BeautifulSoup(r.content, features="lxml")

    header_title = soup.find_all("div", class_=["table_of_contents"])

    # if the page did not load properly, that means maybe the page only partially
    # loaded, or the web server was unavailable. So, we retry the entire request by
    # adding the url back into the page_url_deque.
    if len(header_title) == 0:
        print("Did not load page " + article_url + " properly, could not find header")
        print(r)
        if proxy_num < 7:
            page_url_deque.appendleft((chapter_name, chapter_url, section_name, subsection_name, article_title, article_url, proxy_num + 1))
        else:
            print("BAD URL, SKIPPING chapter name " + chapter_name + " article_url " + article_url)
            error_file_pointer.write("BAD URL, SKIPPING chapter name " + chapter_name + " article_url " + article_url)
        return []

    print(article_url)

    div_diff_diag = soup.find_all("div", {"id": re.compile('differentialdiagnosis.*')})

    if len(div_diff_diag) == 0:
        f.writerow({"Chapter Name": chapter_name, "Chapter Url": chapter_url, 
            "Section Name": section_name, "Subsection Name": subsection_name, 
            "Article Name": article_title, "Article Url": article_url, 
            "Ddx Text": "", "Ddx Url": ""})
        return

    ddx_links = div_diff_diag[0].find_all("a")

    for ddx_link in ddx_links:
        ddx_link_text = ddx_link.text
        ddx_link_url = ddx_link.get("href")

        f.writerow({"Chapter Name": chapter_name, "Chapter Url": chapter_url, 
            "Section Name": section_name, "Subsection Name": subsection_name, 
            "Article Name": article_title, "Article Url": article_url, 
            "Ddx Text": ddx_link_text, "Ddx Url": ddx_link_url})

if __name__=="__main__":

    # this is a list of proxies. You can get a list of proxies from 
    # http://free-proxy.cz/en/proxylist/country/all/https/ping/level1
    # there is a very high chance that the below proxy will not work in the future
    # try to choose an elite/high anonymity proxy. If none are available, try to 
    # choose an anonymous proxy
    proxies = ['95.174.67.50:18080']#['81.201.60.130:80']#['198.50.163.192:3129']#['144.217.101.245:3129']#['51.75.162.18:9999']
    proxy_pool = cycle(proxies)

    page_urls_deque = collections.deque()

    # collect the page urls that we are going to scrape over for ddx
    # note that this is called radiopaedia-articles-all-first.csv . This
    # is the first half of radiopaedia-articles-all.csv and was generated from
    # split_article.py . This is so we can run web scraper over multiple machines
    # so that it is faster.
    with open("all_pathology_outline_articles.csv") as infile:
        read_csv = csv.DictReader(infile)
        for row in read_csv:
            chapter_name = row["Chapter Name"]
            chapter_url = row["Chapter Url"]
            section_name = row["Section Name"]
            subsection_name = row["Subsection Name"]
            article_title = row["Article Name"]
            article_url = row["Article Url"]
            # make sure that this url is a radiopaedia url
            if article_url[:34] == "https://www.pathologyoutlines.com/":
                page_urls_deque.append((chapter_name, chapter_url, section_name, subsection_name, article_title, article_url, 0))

    # this is so if our scraper dies in the middle, we don't have to
    # start from the beginning. Every 100 urls this scraper goes through, it
    # saves the results in a csv file. So, let's say the scraper dies after
    # processing 732 urls. We can then set count_to_pop to 700 and begin
    # the scraper again.
    total = len(page_urls_deque)
    print(total)
    count_to_pop = 1200
    for i in range(count_to_pop):
        page_urls_deque.popleft()

    # Every 100 urls processed, we save the results in a csv file.
    # for each url, we call function extractDdx.
    while page_urls_deque:
        print("length of page_urls_deque: " + str(len(page_urls_deque)))
        count_processed = total - len(page_urls_deque)
        #if count_processed == 100:
        #    break
        print("count processed: " + str(count_processed))
        if count_processed % 100 == 0:
            header = ["Chapter Name", "Chapter Url", "Section Name", "Subsection Name", "Article Url", "Article Name", "Ddx Text", "Ddx Url"]
            f = csv.DictWriter(open("ddx_links" + str(count_processed//100) + ".csv", "w"), fieldnames=header, quoting=csv.QUOTE_ALL)
            f.writeheader()

            g = open("failed_article_links" + str(count_processed//100) + ".txt", "w")
        extractDdx(page_urls_deque, f, proxy_pool, g)
