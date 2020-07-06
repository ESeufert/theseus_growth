# # # # # # # # # # #
#  functions pertaining to the different curve functions that can be applied to the data
# # # # # # # # # # #
import numpy as np
from scipy.interpolate import interp1d
from scipy.interpolate import InterpolatedUnivariateSpline
import warnings


processes = ['log', 'exp', 'linear', 'quad', 'weibull', 'power']


def log_func(x, a, b, c):
    np.seterr(all='ignore')
    return -a * np.log2(b + x) + c


def exp_func(x, a, b, c):
    warnings.filterwarnings('ignore')
    np.seterr(all='ignore')
    return a * exp(-b * x) + c


def poly_func(x, a, b, c, d):
    np.seterr(all='ignore')
    return a * x**3 + b * x**2 + c * x + d


def linear_func(x, a, b):
    np.seterr(all='ignore')
    return a * x + b


def quad_func(x, a, b, c):
    np.seterr(all='ignore')
    return a * x**2 + b * x + c


def weibull_func(x, k, l):
    np.seterr(all='ignore')
    return (k/l) * ((x/l) ** (k - 1)) * exp(- (x/l) ** k)


def power_func(x, a, b):
    np.seterr(all='ignore')
    return a * x ** -b


def get_interpolation_values(profile):
    values = {}
    values['x'] = np.unique(np.array(profile['x'])).tolist()
    values['y'] = []

    for i, v in enumerate(values['x']):
        # get indices from original X for this value
        this_y = [profile['y'][i] for i, v2 in enumerate(values['x']) if v2 == v]
        values['y'].append(round(np.average(this_y), 2))

    # add the collapsed (averaged) values to the profile
    profile['y_collapsed'] = values['y']
    profile['x_collapsed'] = values['x']
    return values


def interpolate(profile):
    interpolation_values = get_interpolation_values(profile)
    profile['interpolation_f'] = interp1d(interpolation_values['x'], interpolation_values['y'])
    profile['interpolation_s'] = InterpolatedUnivariateSpline(interpolation_values['x'], interpolation_values['y'], k=1)
    return None
