from lxml.html import fromstring
import requests
from itertools import cycle
import traceback
from bs4 import BeautifulSoup
import csv
import collections


def extractDdx(page_url_deque, file_pointer, proxy_pool):

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

    header_title = soup.find_all("h1", class_=["header-title"])

    # if the page did not load properly, that means maybe the page only partially
    # loaded, or the web server was unavailable. So, we retry the entire request by
    # adding the url back into the page_url_deque.
    if len(header_title) == 0:
        print("Did not load page " + page_url + " properly, could not find header")
        page_url_deque.appendleft((page_title, page_url))
        return []

    print(page_url)

    # look for the header for differential diagnosis
    h4_diff_diag = soup.select("#nav_differential-diagnosis")
    if len(h4_diff_diag) == 0:
        return
    else:
        h4_diff_diag = h4_diff_diag[0]

    # we want to find the next "ul" that is not
    # under "Differential Diagnosis". We have to do this
    # because the bullet points that are ddx are not actually 
    # under the h4 differential diagnosis, but instead will be its siblings
    # so, we look for the next h4 header.
    # if the next h4 header does not exist, try next div
    # if next div does not exist, try next li
    # example is https://radiopaedia.org/articles/abnormally-thickened-endometrium-differential-1?lang=us
    # else, there are no other possible bullet points that are next
    # to h4 differential diagnosis that are not ddx

    # there might be a possibility that we only need to look at the li's under the ul that is the
    # next sibling of the h4 ddx header
    # TODO: look into this to maybe shorten the code
    ending_next_li = None
    ending_next_ul = None
    ending = h4_diff_diag.find_next_sibling("h4")

    if ending is None:
        ending = h4_diff_diag.find_next_sibling("div")

    if ending is not None:
        ending_next_li = ending.find_next_sibling("li")
        ending_next_ul = ending.find_next_sibling("ul")

    ul_iter = h4_diff_diag.find_next_sibling("ul")

    while ul_iter:
        if ul_iter == ending_next_ul:
            return
        li_list = ul_iter.find_all("li")

        for li in li_list:
            text = li.text
            # some of the entries have a newline as the
            # first character. We want to search for newline
            # after this
            new_line_idx = text.find("\n", 1)

            # check if inner li has this link or not
            links = li.find_all("a")
            inner_li = li.find_all("li")

            if new_line_idx > 0:
                description = text[:new_line_idx]
            else:
                description = text

            link_added = False
            # if there is another bullet, we don't want to accidentally
            # grab the link of that next bullet and claim that this bullet has that
            # link. Further this bullet may have multiple links, which is why we have 
            # a for loop
            if len(inner_li) > 0:
                inner_li_links = inner_li[0].find_all("a")
                for link in links:
                    if len(inner_li_links) > 0 and link == inner_li_links[0]:
                        break
                    url = "https://radiopaedia.org" + link.get('href')
                    file_pointer.writerow([page_url, page_title, link.string, url])
                    link_added = True
            else:
                for link in links:
                    url = "https://radiopaedia.org" + link.get('href')
                    file_pointer.writerow([page_url, page_title, link.string, url])
                    link_added = True

            if link_added == False:
                file_pointer.writerow([page_url, page_title, description, ""])
            
        ul_iter = ul_iter.find_next_sibling("ul")

if __name__=="__main__":

    # this is a list of proxies. You can get a list of proxies from 
    # http://free-proxy.cz/en/proxylist/country/all/https/ping/level1
    # there is a very high chance that the below proxy will not work in the future
    # try to choose an elite/high anonymity proxy. If none are available, try to 
    # choose an anonymous proxy.
    # other helpful sites are 
    # http://www.freeproxylists.net/?c=&pt=&pr=HTTPS&a%5B%5D=0&a%5B%5D=1&a%5B%5D=2&u=70
    proxies = ['51.75.162.18:9999']
    proxy_pool = cycle(proxies)

    page_urls_deque = collections.deque()

    # collect the page urls that we are going to scrape over for ddx
    # note that this is called radiopaedia-articles-all-first.csv . This
    # is the first half of radiopaedia-articles-all.csv and was generated from
    # split_article.py . This is so we can run web scraper over multiple machines
    # so that it is faster.
    with open("radiopaedia-articles-all-first.csv") as infile:
        read_csv = csv.DictReader(infile)
        for row in read_csv:
            title = row["articleTitle_articleName"]
            url = row["articleTitle_articleURL"]
            # make sure that this url is a radiopaedia url
            if url[:18] == "https://radiopaedi":
                page_urls_deque.append((title, url))

    # this is so if our scraper dies in the middle, we don't have to
    # start from the beginning. Every 100 urls this scraper goes through, it
    # saves the results in a csv file. So, let's say the scraper dies after
    # processing 732 urls. We can then set count_to_pop to 700 and begin
    # the scraper again.
    total = len(page_urls_deque)
    count_to_pop = 0
    for i in range(count_to_pop):
        page_urls_deque.popleft()

    # Every 100 urls processed, we save the results in a csv file.
    # for each url, we call function extractDdx.
    while page_urls_deque:
        print("length of page_urls_deque: " + str(len(page_urls_deque)))
        count_processed = total - len(page_urls_deque)
        if count_processed == 100:
            break
        print("count processed: " + str(count_processed))
        if count_processed % 100 == 0:
            f = csv.writer(open("ddx_links" + str(count_processed//100) + ".csv", "w"))
            f.writerow(["Page Url", "Page Title", "Bullet text", "Link"])
        extractDdx(page_urls_deque, f, proxy_pool)
