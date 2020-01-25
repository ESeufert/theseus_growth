# # # #
#  Projection Functions
# # # #

import pandas as pd
from scipy.stats import linregress


def build_cohort(cohorts, date, cohort_size):
    cohort = pd.DataFrame(columns=['date', 'cohort_size'])

    cohort.loc[0] = [date, cohort_size]
    return cohort


def add_cohort(cohorts, date, cohort_size):
    this_cohort = build_cohort(cohorts, date, cohort_size)
    cohorts = cohorts.append(this_cohort)
    return cohorts


def create_cohorts(cohorts_DNU, start_date=None):
    # cohorts DNU is a list of ints
    # these are the cohorts of NEW users

    cohorts = pd.DataFrame()
    if start_date < 0:
        raise Exception("Invalid start date")

    if start_date is None or start_date == 0:
        start_date = 1
    this_date = start_date
    for i, cohort_size in enumerate(cohorts_DNU):
        cohort = build_cohort(cohorts, (this_date), cohort_size)
        cohorts = cohorts.append(cohort)
        this_date += 1
    return cohorts


def build_DAU_trajectory(start_DAU, end_DAU, periods):
    x = [1, periods]
    y = [start_DAU, end_DAU]

    model = linregress(x, y)

    return model


def project_cohort(cohort, profile, periods):

    # the function name for the best fit
    # if profile['retention_profile'] == 'best_fit':
    #    form = profile[profile['retention_profile']]
    # else:
    #     form = profile['retention_profile']
    # this_func = form + '_func' # never used?
    # this_params = profile['params'][form] # never used?

    # this iterates through the retention values list up through the #  of periods being projected out
    # if the period number is > the max x value that was used to build the retention projection, it gives 0
    this_cohort = [
        int(cohort * profile['retention_projection'][1][i]/100)
        if i <= max(profile['retention_projection'][0]) else 0 for i in range(0, periods)
    ]

    return this_cohort


def build_forward_DAU(profile, forward_DAU, cohort, periods, start_date):
    # # #  this function takes a set of cohorts (which is a list of DNU)
    # # #  and a retention profile and projects out what the DAU will be
    # # #  based on the retention to some map_length
    # # #  forward_DAU is either a blank dataframe or it contains data for some cohorts
    # # #  whatever the case, so long as the list of cohorts contains 2 or more values,
    # # #  we add this projected cohort to the end of the forward_DAU dataframe and
    # # #  recurse with one less cohort sent. If there's just one cohort left, we return dataframe.

    # the function name for the best fit
    # if profile['retention_profile'] == 'best_fit':
    #     form = profile[profile['retention_profile']]
    # else:
    #     form = profile['retention_profile']
    # this_func = form + '_func'
    # this_params = profile['params'][form]

    # build the cohort out by periods
    this_cohort = project_cohort(cohort, profile, periods)

    # need to insert 0s to the beginning depending on where it goes in the lifetime
    # eg if it's the first cohort, no zeroes
    # second cohort, 1 zero, etc.
    delta_count = len(forward_DAU)
    if start_date == 1:
        this_cohort = [len(forward_DAU)] + ([0] * (delta_count)) + this_cohort
    else:
        this_cohort = [len(forward_DAU)] + ([0] * (delta_count + 1)) + this_cohort
    # now remove that many values from the end
    if delta_count > 0:
        del this_cohort[-delta_count:]

    # add this_cohort to forward_DAU
    forward_DAU.loc[len(forward_DAU)] = this_cohort
    forward_DAU = forward_DAU.fillna(0)

    return forward_DAU


def DAU_total(forward_DAU):
    if not isinstance(forward_DAU, pd.DataFrame) or len(forward_DAU) < 2:
        raise Exception('Forward DAU Projection is malformed. Must be a dataframe with at least 2 rows.')

    # get the sums of the columns
    total_series = forward_DAU.sum()

    DAU_total = pd.DataFrame(columns=['DAU'] + forward_DAU.columns.tolist()).set_index('DAU')
    DAU_total.loc[len(DAU_total)] = total_series

    # change the index name
    DAU_total.index.names = ['Value']
    # set the index value to "DAU"
    DAU_total.rename(index={list(DAU_total.index)[0]: 'DAU'}, inplace=True)

    return DAU_total


def combine_DAU(DAU_totals, labels=None):

    if len(DAU_totals) < 2:
        raise Exception('Must provide at least two sets of DAU projections to combine.')

    if labels is not None and (len(DAU_totals) != len(labels)):
        raise Exception('Number of labels doesnt match number of DAU projections provided.')

    combined_DAU = DAU_totals[0]
    combined_DAU = combined_DAU.reset_index()
    if labels is not None:
        combined_DAU['profile'] = labels[0]

    i = 1
    for DAU_total in DAU_totals[1:]:
        if labels is not None:
            DAU_total['profile'] = labels[i]
            DAU_total.reset_index().set_index(['profile'])
        common = list(set(combined_DAU.columns.tolist()) & set(DAU_total.columns.tolist()))
        combined_DAU = pd.merge(combined_DAU, DAU_total, on=common, how='outer').fillna(0)
        i += 1

    # sort the columns
    columns = sorted(
        [int(c) for c in combined_DAU.columns if c not in ['DAU', 'profile', 'cohort_date', 'age', 'Value']]
    )
    columns = [str(c) for c in columns]
    if labels is not None:
        columns += ['profile']
    # combined_DAU = combined_DAU.reindex(
    #    sorted(combined_DAU.columns, key=lambda x: float(combined_DAU.columns)), axis=1
    # )
    combined_DAU = combined_DAU[columns]

    combined_DAU.reset_index()

    return combined_DAU.set_index('profile')


def project_targeted_DAU(profile, forward_DAU, periods, cohorts, DAU_target, DAU_target_timeline, start_date):
    if DAU_target_timeline is None:
        raise Exception('DAU Target Projections require a DAU Target Timeline')

    if DAU_target_timeline + len(cohorts) - 1 > periods:
        raise Exception('''
            DAU target timeline extends past the number of periods being projected.
            DAU target timeline must be less than or equal to the number of periods minus the number of cohorts.
        ''')

    tracker = len(cohorts) + 1

    # start projections
    start_DAU = forward_DAU.iloc[:, tracker - 1].sum()  # the current value of DAU

    #  this builds a list of DAU values needed to hit the DAU target over the timeline
    #  it uses a straight linear regression and just comes up with DAU values
    #  the reason it starts from tracker - 1 is that we want the model to project
    #  from the *current* value to target, not the day after the last cohort
    #  keep in mind that the entire timeline is projected out, which is why the
    #  tracker is needed in the first place (otherwise we could just use last column of df)
    model = build_DAU_trajectory(start_DAU, DAU_target, (DAU_target_timeline + 1 - len(cohorts)))

    #  get the DAU values that we need each day to linearly progress to the target DAU
    #  start from 2 because we want to exclude the first value,
    #  which is the last value of the existing cohorts
    DAU_values = [int(model[0] * i + model[1]) for i in range(1, (DAU_target_timeline + 2 - len(cohorts)))][1:]

    for DAU_target in DAU_values:

        if len(forward_DAU) > len(forward_DAU.columns.tolist()):
            forward_DAU[str(int(forward_DAU.columns.tolist()[-1]) + 1)] = [0] * (len(forward_DAU))

        # the current value of DAU is the sum of the last column of forward_DAU
        start_DAU = forward_DAU.iloc[:, tracker].sum()
        DAU_needed = (0 if DAU_target - start_DAU < 0 else DAU_target - start_DAU)

        forward_DAU = build_forward_DAU(profile, forward_DAU, DAU_needed, periods, start_date)

        tracker += 1

    return forward_DAU


def project_cohorted_DAU(profile, periods, cohorts, DAU_target=None,
                         DAU_target_timeline=None, start_date=1):

    if not isinstance(periods, int) or periods < 2:
        raise Exception("The periods parameter must be an integer greater than 1")

    if len(cohorts) < 1 or not all(isinstance(x, int) for x in cohorts) or not all(x >= 1 for x in cohorts):
        raise Exception("Must provide at least one cohort value, and all cohort values must be greater than 0")

    if DAU_target is not None and DAU_target_timeline is not None and DAU_target_timeline > periods:
        raise Exception("DAU target timeline is longer than the number of periods being projected")

    if start_date == 0 or start_date is None:
        start_date = 1

    # create a list of dates
    if start_date == 1:
        dates = list(range(start_date, (start_date + periods)))
    else:
        dates = list(range(start_date, (start_date + periods + 1)))

    dates = [str(x) for x in dates]

    # create the blank dataframe that will contain the forward_DAU
    forward_DAU = pd.DataFrame(columns=['cohort_date'] + dates)
    # build the initial forward DAU from the cohorts
    for cohort in cohorts:
        forward_DAU = build_forward_DAU(profile, forward_DAU, cohort, periods, start_date)

    # if DAU_target is set, it means we are trying to build to some target
    if DAU_target is not None:
        forward_DAU = project_targeted_DAU(
            profile, forward_DAU, periods, cohorts, DAU_target, DAU_target_timeline, start_date
        )

    forward_DAU['cohort_date'] = forward_DAU['cohort_date'] + 1

    return forward_DAU.set_index('cohort_date')
