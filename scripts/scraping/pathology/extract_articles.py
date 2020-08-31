from lxml.html import fromstring
import requests
from itertools import cycle
import traceback
from bs4 import BeautifulSoup
import csv
import collections

def extractArticles(page_url_deque, file_pointer, proxy_pool):
    page_title, page_url = page_url_deque.popleft()

    proxy = next(proxy_pool)
    try:
        r = requests.get(page_url, proxies={"http": proxy, "https": proxy})

    except:
        # most free proxies will often get connection errors. So, if this happens,
        # we retry the entire request by adding the url back into the page_url_deque
        print("Skipping " + page_url + ". Connnection error with proxy " + str(proxy))
        page_url_deque.appendleft((page_title, page_url))

        return []

    soup = BeautifulSoup(r.content, features="lxml")

    header_title = soup.find_all("div", class_=["page_content"])

    # if the page did not load properly, that means maybe the page only partially
    # loaded, or the web server was unavailable. So, we retry the entire request by
    # adding the url back into the page_url_deque.
    if len(header_title) == 0:
        print("Did not load page " + page_url + " properly, could not find header")
        page_url_deque.appendleft((page_title, page_url))
        return []

    print(page_url)

    toc_sections = soup.find_all("div", class_=["toc_section toc_links"])

    if len(toc_sections) == 0:
        toc_sections = soup.find_all("div", class_=["toc_links"])

        if len(toc_sections) > 0:
            #print(len(toc_sections))
            toc_section = toc_sections[0]
            section = toc_section.find_all("span", class_=["f12b"])

            itr_elem = section[0]
            section_name = section[0].text
            sub_section_name = ""

            while section_name != "Superpages:":
                itr_elem = itr_elem.next_element
                #print(itr_elem)
                if itr_elem.name == "a":
                    article = itr_elem
                    article_url = article.get("href")
                    article_text = article.text
                    if article_url[:34] == "https://www.pathologyoutlines.com/":
                        colon_idx = section_name.find(":")
                        if colon_idx != -1:
                            section_name = section_name[:colon_idx]
                        f.writerow({"Chapter Name": page_title, "Chapter Url": page_url, 
                                    "Section Name": section_name, "Subsection Name": sub_section_name, 
                                    "Article Name": article_text, "Article Url": article_url})
                elif itr_elem.name == "span":
                    section_name = itr_elem.text
                elif itr_elem.name in set(["b", "span"]) and itr_elem.text in set(["Superpages:", "Index (Alphabetical table of contents)"]):
                    break
            return

    for toc_section in toc_sections:
        section_name = ""
        sub_section_name = ""
        section = toc_section.find_all("span", class_=["toc_section_name"])
        if len(section) == 0:
            section = toc_section.find_all("div", class_=["toc_section_name"])
            if len(section) > 0:
                section_name = section[0].text
                colon_idx = section_name.find(":")
                if colon_idx != -1:
                    section_name = section_name[:colon_idx]
                sub_sections = toc_section.find_all("div", class_=["toc_subsection toc_links"])
                for sub_section in sub_sections:
                    sub_section_span = sub_section.find_all("span", class_=["toc_subsection_name"])
                    sub_section_name = sub_section_span[0].text 
                    colon_idx = sub_section_name.find(":")
                    if colon_idx != -1:
                        sub_section_name = sub_section_name[:colon_idx]

                    articles = sub_section.find_all("a")

                    for article in articles:
                        article_url = article.get("href")
                        article_text = article.text
                        if article_url[:34] == "https://www.pathologyoutlines.com/": 
                            f.writerow({"Chapter Name": page_title, "Chapter Url": page_url, 
                                        "Section Name": section_name, "Subsection Name": sub_section_name, 
                                        "Article Name": article_text, "Article Url": article_url})
                    
        else:
            section_name = section[0].text
            if section_name in set(["Superpages:", "A-E:"]):
                return
            colon_idx = section_name.find(":")
            if colon_idx != -1:
                section_name = section_name[:colon_idx]

            articles = toc_section.find_all("a")

            for article in articles:
                article_url = article.get("href")
                article_text = article.text
                if article_url[:34] == "https://www.pathologyoutlines.com/":
                    f.writerow({"Chapter Name": page_title, "Chapter Url": page_url, 
                                "Section Name": section_name, "Subsection Name": sub_section_name, 
                                "Article Name": article_text, "Article Url": article_url})

    
if __name__=="__main__":

    # this is a list of proxies. You can get a list of proxies from 
    # http://free-proxy.cz/en/proxylist/country/all/https/ping/level1
    # there is a very high chance that the below proxy will not work in the future
    # try to choose an elite/high anonymity proxy. If none are available, try to 
    # choose an anonymous proxy
    proxies = ['51.158.119.88:8811']# ['186.1.162.203:3128']#['189.33.93.88:3128']#['81.201.60.130:80']#['80.211.183.7:80']#['144.217.101.245:3129']
    proxy_pool = cycle(proxies)

    page_urls_deque = collections.deque()

    bad_urls = set([])#set(["https://www.pathologyoutlines.com/cdmarkers.html"])

    with open("pathology_outline_chapters.csv") as infile:
        read_csv = csv.DictReader(infile)
        for row in read_csv:
            name = row["Chapter Name"]
            url = row["Chapter Url"]
            if url not in bad_urls:
                page_urls_deque.append((name, url))

    total = len(page_urls_deque)
    count_to_pop = 0
    for i in range(count_to_pop):
        page_urls_deque.popleft()

    while page_urls_deque:
        count_processed = total - len(page_urls_deque)
        header = ["Chapter Name", "Chapter Url", "Section Name", "Subsection Name", "Article Name", "Article Url"]
        #f = csv.writer(open("pathology_outline_articles" + str(count_processed) + ".csv", "w"))
        f = csv.DictWriter(open("pathology_outline_articles" + str(count_processed) + ".csv", "w"), fieldnames=header, quoting=csv.QUOTE_ALL)
        f.writeheader()
        #f.writerow(['Chapter Name'.encode(encoding='UTF-8'), 'Chapter Url'.encode(encoding='UTF-8'), 'Section Name'.encode(encoding='UTF-8'), 'Subsection Name'.encode(encoding='UTF-8'), 'Article Name'.encode(encoding='UTF-8'), 'Article Url'.encode(encoding='UTF-8')])

        extractArticles(page_urls_deque, f, proxy_pool)
