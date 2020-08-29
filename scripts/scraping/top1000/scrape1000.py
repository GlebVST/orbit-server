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
    proxies = ['95.174.67.50:18080', '81.201.60.130:80', '51.75.162.18:9999']#['81.201.60.130:80']#['198.50.163.192:3129']#['144.217.101.245:3129']#['51.75.162.18:9999']
    proxy_pool = cycle(proxies)

    header = ["numOffers", "url", "title", "topic_studytopic", "top_studytopic: wrong (x) or right (blank)", "top_3_studytopic", "top_3: wrong (x) or right (blank)", "reference_title", "reference_url", "keywords"]

    f = csv.DictWriter(open("top1000_withkey.csv", "w"), fieldnames=header, quoting=csv.QUOTE_ALL)
    f.writeheader()

    # collect the page urls that we are going to scrape over for ddx
    # note that this is called radiopaedia-articles-all-first.csv . This
    # is the first half of radiopaedia-articles-all.csv and was generated from
    # split_article.py . This is so we can run web scraper over multiple machines
    # so that it is faster.
    with open("top_1000.csv") as infile:
        read_csv = csv.DictReader(infile)
        for row in read_csv:
            num_offers = row["numOffers"]
            url = row["url"]
            title = row["title"]
            topic_studytopic = row["top_studytopic"]
            top_wrong_right = row["top_studytopic: wrong (x) or right (blank)"]
            top3_study = row["top_3_studytopic"]
            top3_wrong_right = row["top_3: wrong (x) or right (blank)"]
            ref_title = row["reference_title"]
            ref_url = row["reference_url"]

            keywords = ""

            num_tries = 0
           
            status = 0 
            while num_tries < 5 and status != 200:
                proxy = next(proxy_pool)
                try:
                    print(url)
                    r = requests.get(url, proxies={"http": proxy, "https": proxy})

                except:
                    # most free proxies will often get connection errors. So, if this happens,
                    # we retry the entire request by adding the url back into the page_url_deque
                    print("Skipping " + url + ". Connnection error with proxy " + str(proxy))
             
                status = r.status_code
                print(url + " has response code: " + str(r.status_code))
                num_tries += 1
                  

            keywords_str = ""
            if num_tries < 5 and r and r.status_code == 200:
                tags = ["keywords", "keyword", "citation_keyword", "citation_keywords", "DC.Subject", "eprints.keywords"]

                delimiters = [";", ","] 

                soup = BeautifulSoup(r.content, features="lxml")

                keywords = []
                for tag in tags:
                    meta_keywords = soup.find_all("meta", attrs={'name': tag})
                    delimiter = ","
                    for meta in meta_keywords:
                        content = meta.get("content")
                        for d in delimiter:
                            if d in content:
                                delimiter = d
                                break
                        keywords.extend(content.split(delimiter))

                if len(keywords) > 0:
                    keywords_str = ";".join(keywords)
                    
                print(url + " has keywords " + keywords_str)
            else:
                print(url + " unable to connect")

            f.writerow({"numOffers": num_offers, "url": url, "title": title, "topic_studytopic": topic_studytopic,
                        "top_studytopic: wrong (x) or right (blank)": top_wrong_right, 
                        "top_3_studytopic": top3_study,
                        "top_3: wrong (x) or right (blank)": top3_wrong_right,
                        "reference_title": ref_title, "reference_url": ref_url, "keywords": keywords_str}) 
