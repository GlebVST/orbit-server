import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

import collections

def calc_cdf(amount_arr):
    """
       calculates the cumulative count dictionary       

       Parameters:
       amount_arr: an array of counts or amount
       where resident i has done amount_arr[i] 

       Returns:
       a dictionary with key as the count/amount and value as 
       cumulative count of residents(number of residents with at most that
       count/amount)
    """

    num_bins = max(amount_arr)

    counts, bin_edges = np.histogram (amount_arr, bins=num_bins, range=(0, num_bins), density=False)
    cdf_range = np.cumsum (counts)
    cdf = {bin_edges[i + 1] : cdf_range[i] for i in range(len(cdf_range))}    

    return cdf

def plot_cdf(cdf, fname):
    '''
        Plots the cdf into a png file using matplotlib

        Parameters:
        cdf_counter: A dictionary where key is, for 
        example, the number of articles visited, and the
        value is the number of residents who have visited
        number of articles or less

        fname: Name of file before the ".png" part. 
        fname.png and fname_normalized.png will be the
        names of the plots outputted

        Return:
        None. Just saves plots into png files
    '''

    bin_edges = list(cdf.keys())
    cdf_range = list(cdf.values())

    # calculate the normalized cdf
    max_cdf = max(cdf_range)
    normalized_cdf_range = [i/max_cdf for i in cdf_range]

    # plot and save the cdf as a step function
    cum_figure, cum_ax = plt.subplots()
    cum_ax.step(bin_edges, cdf_range)
    plt.xlabel("Cumulative articles visited")
    plt.ylabel("Cumulative residents count")
    cum_figure.savefig(fname + "_articles.png")
    plt.close(cum_figure)

    # plot and save the normalized cdf as a step function
    norm_cum_figure, norm_cum_ax = plt.subplots()
    norm_cum_ax.step(bin_edges, normalized_cdf_range)
    plt.xlabel("Cumulative articles visited")
    plt.ylabel("Normalized cumulative residents count")
    norm_cum_figure.savefig(fname + "_articles_normalized.png")
    plt.close(norm_cum_figure)

def combine_cdf(cdf1, cdf2):
    '''
        Combines two dictionaries of cumulative counts
        into one newly created dictionary and returns it
    '''
    new_cdf = collections.Counter()
    cdf1_bins = cdf1.keys()
    cdf2_bins = cdf2.keys()

    new_min_bin = int(min(min(cdf1_bins), min(cdf2_bins)))
    new_max_bin = int(max(max(cdf1_bins), max(cdf2_bins)))

    new_bins = [i for i in range(new_min_bin, new_max_bin + 1)]

    cum_count = 0
    prev_cdf1_count = 0
    prev_cdf2_count = 0
    for b in new_bins:
        if b in cdf1:
            cum_count += max(cdf1[b] - prev_cdf1_count, 0)
            prev_cdf1_count = cdf1[b]
        if b in cdf2:
            cum_count += max(cdf2[b] - prev_cdf2_count, 0)
            prev_cdf2_count = cdf2[b]
        new_cdf[b] = cum_count

    return new_cdf

# compute cdf as a function of time from a given reference point

if __name__ == "__main__":
    # this data can represent number of
    # articles read by person i in first month
    # so for example, person 3 read 8 articles in first month
    data = [5, 2, 8, 1, 15, 4, 23]
    #cumulative, bins = calc_cdf(data))
    first_cdf = calc_cdf(data)

    #for q in range(0, 110, 10):
    #    print ("{}%% percentile: {}".format (q, stats.scoreatpercentile(data, q)))

    # gets the percentile of 8 in data
    #print(stats.percentileofscore(data, 8))

    max_cdf = max(first_cdf.values())

    for q in range(0, 110, 10):
        print("{} percentile : {}".format(q, stats.scoreatpercentile(data, q))) 

    # gets the percentile of 8 in the data
    print("percentile of 8 is: " + str(first_cdf[9]/max_cdf))

    plot_cdf(first_cdf, "first_batch")

    additional_data = [3, 30, 8]
    second_cdf = calc_cdf(additional_data)

    plot_cdf(second_cdf, "second_batch")

    overall_cdf = combine_cdf(first_cdf, second_cdf)

    plot_cdf(overall_cdf, "overall")   

