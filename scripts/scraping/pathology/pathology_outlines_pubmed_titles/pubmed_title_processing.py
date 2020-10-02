import os, glob
import pandas as pd
import csv
import re

path = ""
'''
all_files = glob.glob(os.path.join(path, "ddx_links*.csv"))

all_csv = (pd.read_csv(f, sep=',') for f in all_files)
df_merged   = pd.concat(all_csv, ignore_index=True)
df_merged.to_csv( "merged.csv")
'''

dividers = ["[AND]", "[mh]", "[Title]", "[tilte]", "[SB]", "[MH]", "[all fields]", 
            "[PDat]", "[pathology]", "[sb]", "[ptyp]", "[TIAB]", "[ALL]", "[Mesh]", 
            "[Arthritis]", "[PT]", "[title]", "[TI]", "[ti]"]

write_csv = csv.writer(open("pathology_outlines_pubmed_revised_09_27.csv", "w"), quoting=csv.QUOTE_ALL)
header = ["Page Url", "Page Title", "Original Pubmed Title", "Revised Pubmed Title Version 1", "Revised Pubmed Title Version 2"]
write_csv.writerow(header)

pubmed_tags = {}
with open("pathology_outlines_pubmed.csv", "r") as infile:
#with open("dumdum.csv", "r") as infile:
    read_csv = csv.reader(infile)
    next(read_csv, None)
    for row in read_csv:
        pubmed = row[2]
        left_bracket = 0
        left_quote = 0
        left_paren = 0
        cur_str = ""
        left_bracket_idx = 0

        regexPattern = '|'.join(map(re.escape, dividers))
        phrases = re.split(regexPattern, pubmed)

        revised_pubmed = ""
        revised_pubmed2 = ""
        title = ""
        title2 = ""
        for idx, phrase in enumerate(phrases):
            idx = pubmed.find(phrase)
            idx += len(phrase)

            #print(pubmed, phrase)            
            first_bracket_idx = idx
            if first_bracket_idx < len(pubmed) and pubmed[first_bracket_idx] == "[":
                second_bracket_idx = pubmed.index("]", first_bracket_idx)

                delimiter = pubmed[(first_bracket_idx + 1):second_bracket_idx]

                if title != "":
                    revised_pubmed += "{"

                if delimiter in ["AND", "mh", "Title", "tilte", "MH", "all fields", \
                                 "pathology", "TIAB", "ALL", "Mesh", "Arthritis", \
                                 "title", "TI", "ti"]:
                    revised_pubmed += phrase + " "
                elif delimiter in ["sb", "SB"]:
                    quote_idx = phrase.find("\"")
                    if quote_idx == -1:
                        revised_pubmed += phrase + " "
                    else:
                        revised_pubmed += phrase[:quote_idx] + " "

                if title != "":
                    revised_pubmed += "}"
                    title = ""

                if delimiter in ["Title", "tilte", "title", "TI", "ti"]:
                    title = phrase

                if delimiter in ["AND", "mh", "MH", "all fields", \
                                 "pathology", "TIAB", "ALL", "Mesh", "Arthritis"]:
                    revised_pubmed2 += phrase + " "
                elif delimiter in ["sb", "SB"]:
                    quote_idx = phrase.find("\"")
                    if quote_idx == -1:
                        revised_pubmed2 += phrase + " "
                    else:
                        revised_pubmed2 += phrase[:quote_idx] + " "
                

                if title2 != "":
                    revised_pubmed2 += title2
                    title2 = ""

                if delimiter in ["Title", "tilte", "title", "TI", "ti"]:
                    title2 += phrase

            else:
                if title != "":
                    revised_pubmed += "{" + phrase + "}"
                else:
                    revised_pubmed += phrase

                revised_pubmed2 += phrase + " "

                if title2 != "":
                    revised_pubmed2 += title2
                    title2 = ""

        print(revised_pubmed)
        print(revised_pubmed2)

        revised_pubmed = revised_pubmed.replace("AND", "")
        revised_pubmed = revised_pubmed.replace("OR", "")
        revised_pubmed = revised_pubmed.replace("(", "")
        revised_pubmed = revised_pubmed.replace(")", "")
        revised_pubmed = revised_pubmed.replace('"', '')
        remove_whitespace_str = " ".join(revised_pubmed.split())

        if remove_whitespace_str == "":
            for c in pubmed:
                if c in "[\"(":
                    break
                else:
                    revised_pubmed += c

        revised_pubmed = revised_pubmed.replace("AND", "")
        revised_pubmed = revised_pubmed.replace("OR", "")
        revised_pubmed = revised_pubmed.replace("(", "")
        revised_pubmed = revised_pubmed.replace(")", "")
        revised_pubmed = revised_pubmed.replace('"', '')
        revised_pubmed = revised_pubmed.replace("full text", "")
        revised_pubmed = revised_pubmed.replace("pathology free", "pathology")
        revised_pubmed = revised_pubmed.replace("features to report", "")
        revised_pubmed = revised_pubmed.replace("loattrfree", "") 

        revised_pubmed = revised_pubmed.replace("{}", "")
        revised_pubmed = revised_pubmed.replace("{  ", "(")
        revised_pubmed = revised_pubmed.replace("  }", ")")
        revised_pubmed = revised_pubmed.replace("{ ", "(")
        revised_pubmed = revised_pubmed.replace(" }", ")")
        revised_pubmed = revised_pubmed.replace("{", "(")
        revised_pubmed = revised_pubmed.replace("}", ")")

        #remove_whitespace_str = " ".join(revised_pubmed.split())

        phrase_arr = revised_pubmed.split()
        for idx, phrase in enumerate(phrase_arr):
            if phrase.isupper():
                continue
            else:
                phrase_arr[idx] = phrase.lower()

        if len(phrase_arr) > 0:
            phrase_arr[0] = phrase_arr[0].capitalize()

        remove_whitespace_str = " ".join(phrase_arr)

        revised_pubmed2 = revised_pubmed2.replace("AND", "")
        revised_pubmed2 = revised_pubmed2.replace("OR", "")
        revised_pubmed2 = revised_pubmed2.replace("(", "")
        revised_pubmed2 = revised_pubmed2.replace(")", "")
        revised_pubmed2 = revised_pubmed2.replace('"', '')
        remove_whitespace_str2 = " ".join(revised_pubmed2.split())

        if remove_whitespace_str2 == "":
            for c in pubmed:
                if c in "[\"(":
                    break
                else:
                    revised_pubmed2 += c

        revised_pubmed2 = revised_pubmed2.replace("AND", "")
        revised_pubmed2 = revised_pubmed2.replace("OR", "")
        revised_pubmed2 = revised_pubmed2.replace("(", "")
        revised_pubmed2 = revised_pubmed2.replace(")", "")
        revised_pubmed2 = revised_pubmed2.replace('"', '')
        revised_pubmed2 = revised_pubmed2.replace("full text", "")
        revised_pubmed2 = revised_pubmed2.replace("pathology free", "pathology")
        revised_pubmed2 = revised_pubmed2.replace("features to report", "")
        revised_pubmed2 = revised_pubmed2.replace("loattrfree", "") 

        phrase_arr2 = revised_pubmed2.split()
        for idx, phrase in enumerate(phrase_arr2):
            if phrase.isupper():
                continue
            else:
                phrase_arr2[idx] = phrase.lower()

        if len(phrase_arr2) > 0:
            phrase_arr2[0] = phrase_arr2[0].capitalize()

        remove_whitespace_str2 = " ".join(phrase_arr2)

        row.append(remove_whitespace_str)
        row.append(remove_whitespace_str2)

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
