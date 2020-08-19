import csv

split = 7000
with open("radiopaedia-articles-all.csv", "r") as infile:
    first_split = open("radiopaedia-articles-all-first.csv", "w")
    second_split = open("radiopaedia-articles-all-second.csv", "w")

    read_csv = csv.DictReader(infile)

    header = ["articleTitle_articleName", "articleTitle_articleURL"]
    first_csv = csv.DictWriter(first_split, fieldnames=header)
    first_csv.writeheader()
    second_csv = csv.DictWriter(second_split, fieldnames=header)
    second_csv.writeheader()

    for idx, row in enumerate(read_csv):
        if idx < 7000:
            first_csv.writerow(row)
        else:
            second_csv.writerow(row)
