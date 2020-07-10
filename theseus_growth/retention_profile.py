# # # #
#  Core Retention Profile Functions
# # # #

import numpy as np
from scipy.optimize import curve_fit
from itertools import chain

from theseus_growth import curve_functions


def generate_retention_profile(profile, profile_max):
    y_data_projected = project_retention(profile, profile_max=profile_max)
    # push 1 onto the front of the list because day 0 retention is always 100
    y_data_projected = np.insert(y_data_projected, 0, 100)

    # get the occurances of all inf values
    inf_indices = [i for i, x in enumerate(y_data_projected) if x == float("inf")]
    # remove all inf values
    y_data_projected = [y for y in y_data_projected if y != float("inf")][:-1].copy()
    # add them back to the end
    to_add = [
        project_retention(
            profile, start=len(y_data_projected) + i, stop=len(y_data_projected) + i + 1
        ) for i, v in enumerate(inf_indices)
    ]

    # test to see if to_add is a nested list
    # if it is, un-nest it
    if any(isinstance(i, list) for i in to_add):
        to_add = list(chain(*to_add))
    y_data_projected = y_data_projected + to_add
    x_data_projected = np.arange(start=1, stop=len(y_data_projected) + 1, step=1)

    return (x_data_projected, y_data_projected)


def project_retention(profile, profile_max=None, start=None, stop=None):

    x2 = None

    if profile_max is None and start is None and stop is None:
        # no x2 x-axis values were passed
        # take the max x value from the profile and create a range from that
        x2 = np.arange(start=1, stop=max(profile['x']) + 1, step=1)
    elif profile_max is not None:
        # create a range from 0 to profile_max
        x2 = np.arange(start=1, stop=profile_max + 1, step=1)
    elif start is not None and stop is not None:
        # a start and end date were provided, so that's x2
        x2 = np.arange(start=start, stop=stop, step=1)
    else:
        raise Exception('Incorrect parameter set sent. Must include either profile_max or start and end points.')

    this_process = profile['retention_profile']

    #
    #  we have a process equation for the function, so now use that to project
    #  out DAU against x2
    #
    if this_process != 'interpolate':
        #  if the process isn't simply to just interpolate the points
        if this_process == 'best_fit':
            this_process = profile['best_fit']
        # get the retention projection for the appropriate process
        if this_process in curve_functions.processes:
            retention_projection = getattr(
                curve_functions, this_process + '_func'
                )(x2, *profile['params'][this_process])
        else:
            raise Exception('Invalid retention function provided: ' + this_process)
    else:
        #  create the retention projection for the interpolation
        if profile_max is None:
            #  no profile max was selected, so x2 is just the max value from the profile X values
            #  use the interpolation_f function which is the linear interpolation of the provided values
            retention_projection = [
                profile['interpolation_f'](z) for z in range(min(profile['x']), max(profile['x']) + 1)
            ]
        else:
            #  a profile_max was provided so we need to extrapolate the interpolation out
            #  use the interpolation_s function
            retention_projection = [profile['interpolation_s'](z) for z in range(min(profile['x']), max(x2) + 1)]
    retention_projection = [z if z > 0 else 0 for z in retention_projection]

    # replace all negative y values with 0
    retention_projection[1] = np.where(retention_projection[1] < 0, 0, retention_projection[1])

    return retention_projection


def generate_curve_coefficients(profile, process_value):
    if process_value in curve_functions.processes:
        x_data = profile['x']
        y_data = profile['y']
        this_func = process_value + '_func'
        try:
            popt, pcov = curve_fit(getattr(curve_functions, this_func), x_data, y_data)
        except Exception:
            # raise Exception('Unable to process retention curve with ' + process_value + ' function')
            print('Notice: Unable to process retention curve with ' + process_value + ' function')
            return None
        popt, pcov = curve_fit(getattr(curve_functions, this_func), x_data, y_data)
    elif process_value == 'interpolate':
        curve_functions.interpolate(profile)
        return None
    else:
        raise Exception(process_value + ' is not a valid retention curve function')
    return popt


def process_retention_profile_projection(profile):
    curve_fit_values = {}
    process_list = curve_functions.processes.copy() + ['interpolate']

    for process_value in process_list:
        curve_fit_values[process_value] = generate_curve_coefficients(profile, process_value)
        if curve_fit_values[process_value] is None:
            # couldn't fit a curve for this form so delete it from the process list
            if process_value in curve_fit_values:
                del curve_fit_values[process_value]
    return curve_fit_values


def get_retention_projection_best_fit(profile, profile_max=None):
    equations = {}
    errors = {}

    x_data = profile['x']
    y_data = profile['y']

    if profile_max is None:
        profile_max = max(x_data)

    x2 = np.arange(profile_max)

    if 'params' not in profile or not profile['params']:
        profile['params'] = process_retention_profile_projection(profile)

    for process_value in curve_functions.processes and process_value in profile['params']:
        if process_value not in profile['params']:
            pass
        this_func = process_value + '_func'
        this_params = profile['params'][process_value]
        equations[process_value] = getattr(curve_functions, this_func)(x2, *this_params)
        # calculate the summed squared error for this model based on the X values
        # that exist for this retention profile
        these_summed_squares = 0

        for i, x_projection in enumerate(x2):
            x_projection = int(x_projection)
            # loop through x2 and get all the y values for that x
            # since there can be multiple points per x value
            # the indices in x_data are the same for those values in y_data
            x_indices = [i for i, x in enumerate(x_data) if x == x_projection]
            y_values = [y_data[index] for index in x_indices]
            # get the projected value for this x value from equations
            projected_value = equations[process_value][x_projection]
            # sum up squared errors between all y values and the projected value
            this_ss = sum([abs(projected_value - this_value)**2 for this_value in y_values])
            # add the summed errors for the y values at this x value to the running total
            these_summed_squares += this_ss
        # assign the summed squares value to the errors for this process value
        errors[process_value] = these_summed_squares

    best_fit = str(min(errors, key=errors.get))
    profile['errors'] = errors
    profile['best_fit'] = best_fit

    return profile
