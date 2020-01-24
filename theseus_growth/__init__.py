'''

Theseus Growth
Author: Eric Benjamin Seufert, Heracles LLC (eric@mobiledevmemo.com)

Copyright 2020 Heracles LLC

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

'''

import numbers
from theseus_growth import cohort_projections
from theseus_growth import aged_DAU_projections
from theseus_growth import graphs
from theseus_growth import retention_profile
from theseus_growth import theseus_io
from theseus_growth import curve_functions


class theseus():

    # retention_profile = {
    #      x: [], 'y': [], 'errors': {}, 'best_fit': '', 'retention_profile' = ''
    # }
    #

    # # # #
    #  Utility Functions
    # # # #

    def __init__(self):

        return None

    def create_profile(self, days, retention_values, form='best_fit', profile_max=None):

        if self.test_retention_profile(days, retention_values):
            profile = {'x': days, 'y': retention_values}

        if profile_max is not None and (not isinstance(profile_max, int) or profile_max < max(days)):
            raise Exception("profile_max must be an integer greater than or equal to maximum value of Days data")

        #  build the params attribute, which contains profile function curve shape parameters
        #  if the best fit function is requested, use teh get_retention_projection_best_fit method
        #  which iterates through all curve functions and finds the best fit (least squared error)
        #  if a single form was provided, just get that
        profile = retention_profile.get_retention_projection_best_fit(profile, profile_max)
        if form == 'best_fit' or form == '' or form is None:
            profile['retention_profile'] = 'best_fit'
        else:
            if form in curve_functions.processes or form == 'interpolate':
                profile['retention_profile'] = form
            else:
                raise Exception('Invalid retention curve function provided')

        profile['retention_projection'] = retention_profile.generate_retention_profile(profile, profile_max)
        return profile

    def test_retention_profile(self, x_data, y_data):
        # do both lists have the same number of elements?
        if len(x_data) != len(y_data):
            raise Exception('X and Y have differing numbers of data points')
        if not all(isinstance(x, numbers.Real) for x in x_data):
            raise Exception('X data can only contain integers')
        if not all(isinstance(y, (int, float)) for y in y_data):
            raise Exception('Y data can only contain integers and floats')
        if not all((float(y) <= 100 and float(y) > 0) for y in y_data):
            raise Exception('Y data must be less than or equal to 100 and more than 0')
        if not all((x > 0) for x in x_data):
            raise Exception('X data must be more than 0')
        if x_data is None or y_data is None or len(x_data) < 2 or len(y_data) < 2:
            raise Exception('Insufficient retention data provided!')

        return True

    def plot_retention(self, profile, show_average_values=True):
        graphs.plot_retention(profile, show_average_values)

    def project_cohorted_DAU(self, profile, periods, cohorts, DAU_target=None, DAU_target_timeline=None, start_date=1):
        return cohort_projections.project_cohorted_DAU(
            profile, periods, cohorts, DAU_target, DAU_target_timeline, start_date
        )

    def DAU_total(self, forward_DAU):
        return cohort_projections.DAU_total(forward_DAU)

    def plot_forward_DAU_stacked(self, forward_DAU, forward_DAU_labels, forward_DAU_dates,
                                 show_values=False, show_totals_values=False):
        graphs.plot_forward_DAU_stacked(
            forward_DAU, forward_DAU_labels, forward_DAU_dates, show_values, show_totals_values
        )

    def combine_DAU(self, DAU_totals, labels=None):
        return cohort_projections.combine_DAU(DAU_totals, labels)

    def project_aged_DAU(self, profile, periods, cohorts, ages, start_date=1):
        return aged_DAU_projections.project_aged_DAU(profile, periods, cohorts, ages, start_date)

    def project_exact_aged_DAU(self, profile, periods, cohorts, ages, start_date=1):
        return aged_DAU_projections.project_exact_aged_DAU(profile, periods, cohorts, ages, start_date)

    def get_DNU(self, forward_DAU):
        return aged_DAU_projections.get_DNU(forward_DAU)

    def to_excel(self, df, file_name=None, sheet_name=None):
        theseus_io.to_excel(df, file_name, sheet_name)

    def to_json(self, df, file_name=None):
        theseus_io.to_json(df, file_name)
