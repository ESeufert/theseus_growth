# # # # # #
#  Project Aged DAU
#  Will project out the number of people that are at least X days old on a given day
# # # # # #

import pandas as pd
from theseus_growth import cohort_projections


def get_DNU(forward_DAU):
    # build a list out of the DNU values
    DNU_list = [forward_DAU.iloc[x, x] for x in range(0, min(forward_DAU.shape))]
    # copy the forward_DAU structure and change the index name
    DNU_df = pd.DataFrame().reindex_like(forward_DAU).reset_index()
    DNU_df.index.names = ['Value']
    # delete all of the rows from the DNU_df except for first one
    DNU_df = DNU_df[: (-1 * DNU_df.shape[0])]
    # insert the DNU list into the DNU df and add 0s to the end to match columns
    DNU_df.loc[len(DNU_df)] = DNU_list + ([0] * (len(list(DNU_df.columns)) - len(forward_DAU)))
    # rename the index to DNU
    DNU_df.rename(index={list(DNU_df.index)[0]: 'DNU'}, inplace=True)
    return DNU_df


def project_aged_DAU(profile, periods, cohorts, ages, start_date=1):
    if len(ages) == 0:
        raise Exception("Age values cannot be empty")

    if any(x <= 0 for x in ages):
        raise Exception("Age values cannot be less than 1")

    # create a list of dates
    if start_date == 0:
        start_date = 1
    dates = list(range(start_date, (start_date + periods)))
    dates = [str(x) for x in dates]
    # create the blank dataframe that will contain the forward_DAU
    aged_DAU = pd.DataFrame(columns=['age'] + dates).set_index('age')
    # remove any ages that are > the number of periods being projected out
    ages = [age for age in ages if age <= periods]
    for i, age in enumerate(ages):
        this_age = pd.DataFrame(columns=['age'] + dates).set_index('age')
        this_age.loc[age] = [0] * len(dates)
        aged_DAU = aged_DAU.append(this_age)

    # # # go through the cohorts and get the ages
    for i, cohort in enumerate(cohorts):
        this_cohort = cohort_projections.project_cohort(cohort, profile, periods)
        for j, age in enumerate(ages):
            temp_cohort = this_cohort.copy()
            this_age = aged_DAU.loc[[age]]
            if age > 0:
                # set 0s to the front of the cohort for each day that the cohort is less than age
                temp_cohort[0: (age - 1)] = [0] * (age - 1)
            if i > 0:
                # shift the cohort right by the number of cohorts this is
                temp_cohort = [0] * i + temp_cohort[: -i]
            cohort_age = pd.DataFrame(columns=['age'] + dates).set_index('age')
            cohort_age.loc[age] = temp_cohort
            aged_DAU.loc[[age]] = this_age.add(cohort_age, fill_value=0)

    return aged_DAU


# # # # # #
#  Project Exact Aged DAU
#  Will project out the number of people that are exactly X days old on a given day
# # # # # #
def project_exact_aged_DAU(profile, periods, cohorts, ages, start_date=1):
    # create a list of dates
    if len(ages) == 0:
        raise Exception("Age values cannot be empty")

    if start_date == 0:
        start_date = 1

    if any(x <= 0 for x in ages):
        raise Exception("Age values cannot be less than 1")

    dates = list(range(start_date, (start_date + periods)))
    dates = [str(x) for x in dates]
    # create the blank dataframe that will contain the forward_DAU
    aged_DAU = pd.DataFrame(columns=['age'] + dates).set_index('age')
    # remove any ages that are > the number of periods being projected out
    ages = [age for age in ages if age <= periods]
    for i, age in enumerate(ages):
        this_age = pd.DataFrame(columns=['age']+dates).set_index('age')
        this_age.loc[age] = [0] * len(dates)
        aged_DAU = aged_DAU.append(this_age)

    # # # go through the cohorts and get the ages
    for i, cohort in enumerate(cohorts):
        this_cohort = cohort_projections.project_cohort(cohort, profile, periods)
        for j, age in enumerate(ages):
            temp_cohort = this_cohort.copy()
            this_age = aged_DAU.loc[[age]]
            if age > 0:
                # set 0s to the front of the cohort for each day that the cohort is less than age
                temp_cohort[0: (age - 1)] = [0] * (age - 1)
                # set to 0 anything after the first day of the cohort
                temp_cohort[age:] = [0] * (len(temp_cohort) - age)
            if i > 0:
                # shift the cohort right by the number of cohorts this is
                temp_cohort = [0] * i + temp_cohort[: -i]
            cohort_age = pd.DataFrame(columns=['age'] + dates).set_index('age')
            cohort_age.loc[age] = temp_cohort
            aged_DAU.loc[[age]] = this_age.add(cohort_age, fill_value=0)

    return aged_DAU
