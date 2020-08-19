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

write_csv = csv.writer(open("all_ddx_links.csv", "w"))
write_csv.writerow(["ToC Section", "Page Url", "Page Title", "Bullet text", "Link"])

for count in range(156):
    with open("ddx_links" + str(count) + ".csv", "r") as infile:
        print(count)
        read_csv = csv.reader(infile)
        next(read_csv, None)
        for row in read_csv:
            write_csv.writerow(row)
