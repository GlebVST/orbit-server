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
        r = requests.get(page_url,proxies={"http": proxy, "https": proxy})
        #r = requests.get(page_url)

        #print(response.json())

    except:
        #Most free proxies will often get connection errors. You will have retry the entire request using another proxy to work. 
        #We will just skip retries as its beyond the scope of this tutorial and we are only downloading a single url 
        print("Skipping " + page_url + ". Connnection error with proxy " + str(proxy))
        page_url_deque.appendleft((page_title, page_url))
        
        return []

    soup = BeautifulSoup(r.content, features="lxml")

    header_title = soup.find_all("h1", class_=["header-title"])

    if len(header_title) == 0:
        print("Did not load page " + page_url + " properly, could not find header")
        page_url_deque.appendleft((page_title, page_url))
        return []

    #title = soup.title.text

    #suffix_idx = title.find("|")
    #title = title[:suffix_idx]

    print(page_url)

    h4_diff_diag = soup.select("#nav_differential-diagnosis")
    if len(h4_diff_diag) == 0:
        return
    else:
        h4_diff_diag = h4_diff_diag[0]

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
                    #print(url)
            else:
                for link in links:
                    url = "https://radiopaedia.org" + link.get('href')
                    file_pointer.writerow([page_url, page_title, link.string, url])
                    link_added = True
                    #print(url)

            #if new_line_idx > 0:
            #    print(text[:new_line_idx])
            #else:
            #    print(text)
            
            if link_added == False:
                file_pointer.writerow([page_url, page_title, description, ""])
            
            #print("tada")
        ul_iter = ul_iter.find_next_sibling("ul")
'''
#url = 'https://radiopaedia.org/articles/acute-pyelonephritis-1?lang=us'
f = csv.writer(open("ddx_links.csv", "w"))
f.writerow(["Page Url", "Page Title", "Bullet text", "Link"])

#url = 'https://radiopaedia.org/articles/acute-coronary-syndrome?lang=us'

#extractDdx(url, f)
#print(extractUrl("https://radiopaedia.org/encyclopaedia/all/urogenital"))

starting_idx_urls = {"https://radiopaedia.org/encyclopaedia/all/urogenital": 11, 
                     "https://radiopaedia.org/encyclopaedia/all/vascular": 13,
                     "https://radiopaedia.org/encyclopaedia/artificial-intelligence/all?lang=us": 1,
                     "https://radiopaedia.org/encyclopaedia/physics/all": 7}

for starting_url in starting_idx_urls:
    
    page_urls = extractUrl(starting_url)

    for page_url in page_urls:
        extractDdx(page_url, f)
'''
#proxies = get_proxies()
#print(proxies)

#proxies = ['216.158.89.114:8088', '103.250.166.4:6666']#['132.255.92.35:53281', '23.97.53.135:44355', '45.77.231.240:31764']#, '216.158.89.114:8088', '103.250.166.4:6666']

proxies = ['51.75.162.18:9999']#['187.130.139.197:8080', '200.106.55.125:80', '81.201.60.130:80']#['200.106.55.125:80', '81.201.60.130:80', '80.187.140.74:8080'] #['23.97.53.135:44355', '144.217.101.245:3129', '46.151.108.6:41171']#['175.139.179.65:42580'] #['36.89.99.98:44030']#['178.72.74.40:31372']
proxy_pool = cycle(proxies)
'''
f = csv.writer(open("ddx_links_tmp.csv", "w"))
f.writerow(["ToC Section", "Page Url", "Page Title", "Bullet text", "Link"])

page_urls_deque = collections.deque(["https://radiopaedia.org/articles/dysembryoplastic-neuroepithelial-tumour?lang=us"])
extractDdx(page_urls_deque, f, proxy_pool, "dummy")

'''
'''
starting_url = "https://radiopaedia.org/encyclopaedia/interventional-radiology/all"
start_page_url = collections.deque([starting_url + "?lang=us&page=1"])   

while start_page_url:
    toc_title, page_urls = extractUrl(start_page_url, proxy_pool)

prefix = toc_title.find('|')
suffix = toc_title.find('|', prefix + 1)

toc_title = toc_title[(prefix + 1):suffix]
count = 158
f = csv.writer(open("ddx_links" + str(count) + ".csv", "w"))
f.writerow(["ToC Section", "Page Url", "Page Title", "Bullet text", "Link"])
count += 1

page_urls_deque = collections.deque(page_urls)
#for page_url in page_urls:
while page_urls_deque:
    extractDdx(page_urls_deque, f, proxy_pool, toc_title)
'''
starting_idx_urls = {"https://radiopaedia.org/encyclopaedia/all/urogenital": 11, 
                     "https://radiopaedia.org/encyclopaedia/all/vascular": 13,
                     "https://radiopaedia.org/encyclopaedia/artificial-intelligence/all?lang=us": 1,
                     "https://radiopaedia.org/encyclopaedia/physics/all": 7, 
                     "https://radiopaedia.org/encyclopaedia/anatomy/all": 32, 
                     "https://radiopaedia.org/encyclopaedia/approach/all": 5,
                     "https://radiopaedia.org/encyclopaedia/classifications/all": 6, 
                     "https://radiopaedia.org/encyclopaedia/gamuts/all": 10, 
                     "https://radiopaedia.org/encyclopaedia/interventional-radiology/all": 2, 
                     "https://radiopaedia.org/encyclopaedia/mnemonics/all": 3, 
                     "https://radiopaedia.org/encyclopaedia/pathology/all": 3, 
                     "https://radiopaedia.org/encyclopaedia/radiography/all": 5, 
                     "https://radiopaedia.org/encyclopaedia/signs/all": 11, 
                     "https://radiopaedia.org/encyclopaedia/staging/all?lang=us": 1, 
                     "https://radiopaedia.org/encyclopaedia/syndromes/all": 7, 
                     "https://radiopaedia.org/encyclopaedia/all/breast": 4, 
                     "https://radiopaedia.org/encyclopaedia/all/cardiac": 7,
                     "https://radiopaedia.org/encyclopaedia/all/central-nervous-system": 28}#,
''' 
starting_idx_urls = {"https://radiopaedia.org/encyclopaedia/all/chest": 19, 
                     "https://radiopaedia.org/encyclopaedia/all/forensic?lang=us": 1, 
                     "https://radiopaedia.org/encyclopaedia/all/gastrointestinal": 14, 
                     "https://radiopaedia.org/encyclopaedia/all/gynaecology": 7, 
                     "https://radiopaedia.org/encyclopaedia/all/haematology": 3, 
                     "https://radiopaedia.org/encyclopaedia/all/head-neck": 18, 
                     "https://radiopaedia.org/encyclopaedia/all/hepatobiliary": 7,
                     "https://radiopaedia.org/encyclopaedia/all/interventional": 3, 
                     "https://radiopaedia.org/encyclopaedia/all/musculoskeletal": 37, 
                     "https://radiopaedia.org/encyclopaedia/all/obstetrics": 9, 
                     "https://radiopaedia.org/encyclopaedia/all/oncology": 9, 
                     "https://radiopaedia.org/encyclopaedia/all/paediatrics": 13, 
                     "https://radiopaedia.org/encyclopaedia/all/spine": 7,
                     "https://radiopaedia.org/encyclopaedia/all/trauma": 6}
'''

page_urls_deque = collections.deque()

with open("radiopaedia-articles-all-first.csv") as infile:
    read_csv = csv.DictReader(infile)
    for row in read_csv:
        title = row["articleTitle_articleName"]
        url = row["articleTitle_articleURL"]
        if url[:18] == "https://radiopaedi":
            page_urls_deque.append((title, url))

total = len(page_urls_deque)
count_to_pop = 0
for i in range(count_to_pop):
    page_urls_deque.popleft()

#for page_url in page_urls:
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
