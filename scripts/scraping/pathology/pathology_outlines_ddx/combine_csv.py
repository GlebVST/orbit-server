import os, glob
import pandas as pd
import csv
path = ""
'''
all_files = glob.glob(os.path.join(path, "ddx_links*.csv"))

all_csv = (pd.read_csv(f, sep=',') for f in all_files)
df_merged   = pd.concat(all_csv, ignore_index=True)
df_merged.to_csv( "merged.csv")
'''


write_csv = csv.writer(open("all_ddx_links_pathology_outlines.csv", "w"), quoting=csv.QUOTE_ALL)
header = ["Chapter Name", "Chapter Url", "Section Name", "Subsection Name", "Article Url", "Article Name", "Ddx Text", "Ddx Url"]
write_csv.writerow(header)

for count in range(65):
    with open("ddx_links" + str(count) + ".csv", "r") as infile:
        print(count)
        read_csv = csv.reader(infile)
        next(read_csv, None)
        for row in read_csv:
                
            write_csv.writerow(row)

'''
#write_csv = csv.writer(open("all_pathology_outline_articles.csv", "w"))
header = ["Chapter Name", "Chapter Url", "Section Name", "Subsection Name", "Article Name", "Article Url"]
#write_csv.writerow(["Chapter Name", "Chapter Url", "Section Name", "Subsection Name", "Article Name", "Article Url"])
outfile = open("all_pathology_outline_articles.csv", "w")
write_csv = csv.DictWriter(outfile, fieldnames=header)

for count in range(62):
    with open("pathology_outline_articles" + str(count) + ".csv", "r") as infile:
        print(count)
        #read_csv = csv.reader(infile)
        read_csv = csv.DictReader(infile)
        #next(read_csv, None)
        for row in read_csv:
            #print(row)
            section_name = row["Section Name"]
            colon_idx = section_name.find(":")
            if colon_idx != -1:
                row["Section Name"] = row["Section Name"][:colon_idx]

            subsection_name = row["Subsection Name"]
            colon_idx = subsection_name.find(":")
            if colon_idx != -1:
                row["Subsection Name"] = row["Subsection Name"][:colon_idx]
                
            write_csv.writerow(row)
'''
