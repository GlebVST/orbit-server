import os, glob
import csv

pubmed_tags = {}
with open("pathology_outlines_pubmed.csv", "r") as infile:
    read_csv = csv.reader(infile)
    next(read_csv, None)
    for row in read_csv:
        pubmed = row[2]
        left_bracket = 0
        left_bracket_idx = 0
        for idx, c in enumerate(pubmed):
            if c == "[":
                left_bracket = 1
                left_bracket_idx = idx
            elif c == "]" and left_bracket == 1:
                left_bracket = 0
                t = pubmed[(left_bracket_idx + 1):idx]
                if t not in pubmed_tags:
                    pubmed_tags[t] = pubmed
print(pubmed_tags)

tag_csv = csv.writer(open("pubmed_tags1.csv", "w"))
header = ["Tag", "Example"]
for k in pubmed_tags:
    tag_csv.writerow([k, pubmed_tags[k]])
