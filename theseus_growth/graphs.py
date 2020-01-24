# # # #
#  Graphing Functions
# # # #

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as pltcolors
from matplotlib import cm
import numpy as np
import random
import math


def plot_retention(profile, show_average_values=True):

    retention_projection = profile['retention_projection']
    profile_label = profile['retention_profile'] + ' function'

    fig, ax = plt.subplots(figsize=(25, 15))
    plt.plot(profile['x'], profile['y'], 'ro', label="Original Data", markersize=6)
    plt.plot(retention_projection[0], retention_projection[1], 'm--', label=profile_label, linewidth=4)

    if show_average_values:
        plt.plot(
            profile['x_collapsed'],
            profile['y_collapsed'],
            'yo',
            label='Average Values',
            markersize=12
        )

    plt.xticks(fontsize=20)
    plt.xticks(rotation=45)
    plt.yticks(fontsize=20)

    plt.axhline(y=0, color='r', linestyle='--')

    ax.get_yaxis().set_major_formatter(
        ticker.FuncFormatter(lambda y, _: '{:.0%}'.format(y/100))
    )

    plt.legend()
    plt.show()

    return None


def stacked_bar(data, series_labels, category_labels=None,
                show_values=False, value_format="{}", y_label=None,
                grid=True, reverse=False, show_totals_values=False, totals=[]):
    """Plots a stacked bar chart with the data and labels provided.

    Keyword arguments:
    data            -- 2-dimensional numpy array or nested list
                       containing data for each series in rows
    series_labels   -- list of series labels (these appear in
                       the legend)
    category_labels -- list of category labels (these appear
                       on the x-axis)
    show_values     -- If True then numeric value labels will
                       be shown on each bar
    value_format    -- Format string for numeric value labels
                       (default is "{}")
    y_label         -- Label for y-axis (str)
    grid            -- If True display grid
    reverse         -- If True reverse the order that the
                       series are displayed (left-to-right
                       or right-to-left)
    """

    cmap = cm.get_cmap('tab20', 100)    # PiYG, create a color map
    colors = [pltcolors.rgb2hex(cmap(i)[:3]) for i in range(cmap.N)]

    fig, ax = plt.subplots(figsize=(25, 15))

    ny = len(data[0])
    ind = list(range(ny))

    axes = []
    cum_size = np.zeros(ny)

    data = np.array(data)

    if reverse and category_labels is not None:
        data = np.flip(data, axis=1)
        category_labels = reversed(category_labels)

    for i, row_data in enumerate(data):
        if colors:
            axes.append(plt.bar(ind, row_data, bottom=cum_size,
                                label=series_labels[i], color=random.choice(colors)))
        else:
            axes.append(plt.bar(ind, row_data, bottom=cum_size,
                                label=series_labels[i]))
        cum_size += row_data

    if category_labels:
        category_font_size = 20 if len(category_labels) <= 15 else 16
        plt.xticks(ind, category_labels, fontsize=category_font_size)
        plt.xticks(rotation=45)
        label_skip = 7  # Keeps every 7th label
        [l.set_visible(False) for (i, l) in enumerate(ax.xaxis.get_ticklabels()) if i % label_skip != 0]

    if y_label:
        plt.ylabel(y_label, fontsize=20)
        plt.yticks(fontsize=20)
        ax.get_yaxis().set_major_formatter(
            ticker.FuncFormatter(lambda x, p: format(int(x), ','))
        )

    plt.legend(fontsize='xx-large')

    if grid:
        plt.grid()

    if show_values:
        for axis in axes:
            for bar in axis:
                w, h = bar.get_width(), bar.get_height()
                text_loc_x = bar.get_x() + w/2
                text_loc_y = bar.get_y() + h/2
                if h != 0:
                    plt.text(text_loc_x, text_loc_y,
                             h, ha="center",
                             va="center", fontsize=22)

    if show_totals_values:
        # show the total for each stacked bar chart
        # eg. the sum of the values for any given category
        if totals:
            if len(totals) == len(category_labels):
                count = 0
                for index, total in enumerate(totals):
                    totals_font = 26 if len(category_labels) <= 15 else 18
                    totals_rotate = 0 if len(category_labels) <= 15 else 45
                    totals_height = 3 if len(category_labels) <= 15 else 10
                    totals_skip = 5 if len(category_labels) >= 15 else 3
                    if count % totals_skip == 0 or count == 0:
                        plt.text(index, total + (totals_height/100 * sum(totals)/len(totals)),
                                 '{:,}'.format(math.floor(total)), ha="center",
                                 va="center", fontsize=totals_font, color="r",
                                 weight='bold', rotation=totals_rotate)
                    count += 1


def plot_forward_DAU_stacked(forward_DAU, forward_DAU_labels, forward_DAU_dates, show_values=False,
                             show_totals_values=False):
    transformed = forward_DAU.values.tolist()

    # I dont remember what the purpose of this was, but it broke the transformed list when I
    # re-indexed the forward_DAU df to start at 1
    # leaving it here just in case
    '''
    if len(forward_DAU.index) > 1:
        for index, value in enumerate(transformed):
            transformed[index] = value[1:]
    '''

    totals = [
        forward_DAU[column].sum() for column in forward_DAU.loc[:, forward_DAU.columns != 'cohort_date']
    ]

    stacked_bar(
        transformed, forward_DAU_labels,
        category_labels=forward_DAU_dates,
        show_values=show_values, value_format="{}", y_label='DAU',
        grid=True, reverse=False, show_totals_values=show_totals_values, totals=totals
    )

    return None
