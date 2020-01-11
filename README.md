# Theseus

## Theseus provides straightforward tools for cohort analysis and general marketing performance analysis. Theseus was created by [Eric Benjamin Seufert](https://www.twitter.com/eric_seufert) of [Heracles](https://www.hrcls.co).

Theseus is an open source library that provides a set of common functions for use in doing analysis related to product growth: building retention profiles, projecting DAU levels, combining cohorts, segmenting cohorts by age, etc. Theseus can be used for marketing budgeting planning, scenario analysis, marketing campaign analysis, revenue projections, and in a media mix model.

Theseus is designed to be used for standalone analysis projects as well as in programmatic business intelligence environments.

Theseus is provided as open source software under the [MIT](https://choosealicense.com/licenses/mit/) license.

## Documentation

You can find the full Theseus documentation on QuantMar.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install foobar.

```bash
pip install theseus_growth
```

## Usage

Include the theseus_growth library

```python
import theseus_growth
```

Instantiate a Theseus object
```python
th = theseus()
```

Working with Theseus involves using retention profiles to build cohort projections. To get started with analysis, you'll first build a retention profile using `days` and `retention` values, where each day value corresponds to a retention value, starting from Day 1 (ie. the day after a user has entered the product). Retention values should be provided as whole numbers (not decimals), eg. 30% retention for some given day would be represented as 30 and not .30. 

The retention and day values are provided as lists, the lengths of which must match. Theseus uses the index of the values in the `days` list to associate with a value from the `retention` list, so no need to order the lists.

Here's an example:

```python
x_data = [ 1, 3, 7, 14, 30, 60, 90, 180 ]
y_data = [ 80, 70, 55, 50, 30, 22, 10, 8 ]

facebook = th.create_profile( days = x_data, retention_values = y_data, profile_max = 365 )
```

In this example, Day 1 retention is set to 80, Day 3 retention is set to 70, Day 7 retention is set to 55, etc. Then, using these lists are supplied to the `create_profile` function to generate a retention profile (in this case, for Facebook, as per the variable name).

If you `print` the `facebook` variable, the output will reveal a number of pieces of information about the retention profile:

```python
print( facebook )

{'x': [1, 3, 7, 14, 30, 60, 90, 180], 'y': [80, 70, 55, 50, 30, 22, 10, 8], 'y_collapsed': [80.0, 70.0, 55.0, 50.0, 30.0, 22.0, 10.0, 8.0], 'x_collapsed': [1, 3, 7, 14, 30, 60, 90, 180], 'interpolation_f': <scipy.interpolate.interpolate.interp1d object at 0x10c6234f8>, 'interpolation_s': <scipy.interpolate.fitpack2.InterpolatedUnivariateSpline object at 0x10c638588>, 'params': {'log': array([11.69432981,  0.85932489, 91.18858849]), 'exp': array([6.81055507e+01, 4.01937193e-02, 1.00786302e+01]), 'linear': array([-0.36314103, 58.10116222]), 'quad': array([ 4.23356783e-03, -1.09641452e+00,  6.94411850e+01]), 'weibull': array([136.70664663,   0.99893803]), 'power': array([88.3002565,  0.3123284]), 'interpolate': None}, 'errors': {'log': 61.1068291195336, 'exp': 101.38898207577283, 'linear': 1412.367783723572, 'quad': 364.49321231183075, 'weibull': 12824.82253493541, 'power': 440.6176923037875}, 'best_fit': 'log', 'retention_profile': 'best_fit', 'retention_projection': (array([  1,   2,   3,   4,   5,   6,   7,   8,   9,  10,  11,  12,  13,
        14,  15,  16,  17,  18,  19,  20,  21,  22,  23,  24,  25,  26,
        27,  28,  29,  30,  31,  32,  33,  34,  35,  36,  37,  38,  39,
        40,  41,  42,  43,  44,  45,  46,  47,  48,  49,  50,  51,  52,
        53,  54,  55,  56,  57,  58,  59,  60,  61,  62,  63,  64,  65,
        66,  67,  68,  69,  70,  71,  72,  73,  74,  75,  76,  77,  78,
        79,  80,  81,  82,  83,  84,  85,  86,  87,  88,  89,  90,  91,
        92,  93,  94,  95,  96,  97,  98,  99, 100, 101, 102, 103, 104,
       105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
       118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130,
       131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143,
       144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156,
       157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169,
       170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180]), [100.0, 80.72474913359267, 73.46379035522745, 68.40395854720839, 64.51667685670971, 61.35945860038563, 58.70096154455828, 56.40491084756263, 54.384231538266555, 52.579888860453295, 50.95000745540398, 49.46380467615453, 48.097988591666066, 46.834508880262675, 45.65909322498185, 44.56026139229167, 43.52864131907821, 42.55648257398489, 41.63730255356898, 40.76562419809498, 39.936778210530946, 39.14675163202042, 38.392070317383634, 37.669706592412716, 36.97700588336105, 36.3116278251625, 35.67149854953705, 35.054771699032194, 34.459796319341784, 33.88509022316152, 33.32931774346239, 32.79127103579817, 32.269854271186304, 31.764070199363758, 31.273008668265803, 30.79583676761319, 30.331790328468763, 29.88016656089222, 29.440317651599635, 29.01164517522338, 28.593595198171947, 28.185653974577036, 27.78734415043222, 27.398221405576763, 27.017871474283382, 26.645907494353807, 26.281967642193266, 25.92571301762287, 25.576825747436132, 25.235007281103094, 24.899976855723068, 24.57147011044914, 24.24923783325221, 23.933044825140172, 23.622668868865617, 23.317899790794513, 23.01853860601659, 22.724396737987817, 22.43529530504138, 22.15106446700662, 21.87154282596005, 21.59657687581418, 21.326020496044592, 21.059734485374676, 20.79758613169244, 20.539448814872614, 20.285201639528808, 20.034729095029036, 19.787920740381438, 19.544670911838594, 19.30487845128266, 19.06844645364413, 18.835282031775264, 18.605296097351072, 18.378403156503964, 18.154521119018952, 17.933571120024055, 17.715477353206225, 17.500166914670615, 17.287569656638155, 17.07761805024684, 16.870247056785416, 16.66539400674492, 16.462998486125443, 16.263002229482055, 16.065349019235967, 15.86998459081596, 15.676856543229135, 15.485914254692815, 15.297108802987182, 15.11039289021575, 14.925720771683615, 14.743048188626403, 14.562332304542082, 14.383531644896777, 14.206606039992167, 14.031516570797578, 13.858225517564094, 13.686696311050966, 13.516893486206541, 13.34878263815699, 13.18233038036621, 13.01750430483952, 12.854272944252656, 12.692605735895398, 12.53247298732623, 12.373845843641718, 12.216696256270339, 12.060996953206299, 11.90672141060432, 11.753843825661477, 11.602339090716569, 11.452182768502269, 11.30335106848878, 11.15582082426181, 11.009569471881221, 10.86457502916953, 10.720816075882823, 10.578271734719507, 10.436921653124443, 10.296745985849213, 10.157725378230722, 10.019840950153323, 9.883074280660807, 9.747407393187231, 9.612822741376846, 9.47930319546505, 9.346832029194132, 9.215392907238623, 9.084969873116748, 8.955547337565534, 8.827110067358433, 8.69964317454533, 8.573132106096097, 8.447562633929394, 8.322920845309952, 8.199193133597916, 8.076366189334905, 7.954426991652241, 7.833362799987498, 7.713161146095985, 7.5938098263449945, 7.475296894278529, 7.357610653441469, 7.240739650452227, 7.124672668313735, 7.009398719952898, 6.8949070419793514, 6.781187088654434, 6.668228526062208, 6.556021226474144, 6.444555262900209, 6.33382090381852, 6.223808608077022, 6.114509019960167, 6.005912964414506, 5.898011442426906, 5.790795626549496, 5.684256856566179, 5.578386635294848, 5.473176624520619, 5.368618641055164, 5.264704652917132, 5.16142677562982, 5.058777268631218, 4.95674853179267, 4.8553331020422945, 4.754523650089098, 4.65431297724453, 4.554694012337748, 4.455659808721521, 4.357203541365507, 4.259318504033715, 4.161998106543535, 4.065235872103301, 3.969025434725765, 3.873360536714898, 3.778235026223541, 3.6836428548796363, 3.5895780754783857])}
```

You won't ever actually interact directly with a retention profile variable, but you can see that it contains:
+ The original X and Y (the `days` and `retention` lists) data provided;
+ A projection (in the `retention_projection` variable);
+ Two `_collapsed` variables that contain the average values for each of the `days` and `retention` lists (in this example, only one value was provided for each day, so the `y_collapsed` list is the same as the `y` list, which was provided);
+ A `params` dict that contains coefficients for a number of different shape functions;
+ Some other miscellaneous data, like interpolation models;

(**_Note that this example represents a very simple retention profile construction. `create_profile` can take many more inputs -- for a more in-depth explanation of the Theseus library, see the documentation on QuantMar_**)

With the Facebook retention profile created, cohort projections can be generated from it. First, the profile can be visualized with the `plot_retention` function:

```python
th.plot_retention( facebook )
```

Which should output a graph that looks like this:

![alt text](https://mobiledevmemo.com/wp-content/uploads/2020/01/fb_retention.png "Facebook retention profile graph")

Now a cohort projection can be generated. First, we'll create a list of cohorts, meaning a list containing the numbers of new users that joined the product on a daily basis, with each number representing a sequential day.

Then, the `project_cohorted_DAU` function can be used to create a Pandas DataFrame containing the number of DAU present in the product, given the new users that joined via the cohorts, on the basis of the `facebook` retention profile. In this example, the function will take 4 inputs (although it can take many more; see the Documentation for more information):

+ `profile`: the retention profile to use;
+ `periods`: the number of periods to project forward
+ `cohorts`: a list of new user values 
+ `start_date`: the date at which the cohorts are added and from which the projection is made

```python
#cohorts are daily new user values, eg. the number of new users
#joining the product on a given day
cohorts = [1000, 1000, 1000, 1000, 1000 ]

facebook_DAU = th.project_cohorted_DAU( profile = facebook, periods = 50, 
    cohorts = cohorts, start_date = 1 )

print( facebook_DAU )
```

The output of this should look like:

```python
                1     2     3     4     5    6    7    8    9   10  ...   41  \
cohort_date                                                         ...        
1            1000   807   734   684   645  613  587  564  543  525  ...  285   
2               0  1000   807   734   684  645  613  587  564  543  ...  290   
3               0     0  1000   807   734  684  645  613  587  564  ...  294   
4               0     0     0  1000   807  734  684  645  613  587  ...  298   
5               0     0     0     0  1000  807  734  684  645  613  ...  303   

              42   43   44   45   46   47   48   49   50  
cohort_date                                               
1            281  277  273  270  266  262  259  255  252  
2            285  281  277  273  270  266  262  259  255  
3            290  285  281  277  273  270  266  262  259  
4            294  290  285  281  277  273  270  266  262  
5            298  294  290  285  281  277  273  270  266  

[5 rows x 50 columns]
```

This DataFrame table shows how many of the original cohorts are present on any given day; the cohort numbers run down the Y axis and the days run across the X axis.

To see this as a total, the `DAU_total` function can be used:

```python
facebook_total = th.DAU_total( facebook_DAU )

print( facebook_total )
```

The output of which should look like:

```python
        1     2     3     4     5     6     7     8     9    10  ...    41  \
DAU                                                              ...         
0    1000  1807  2541  3225  3870  3483  3263  3093  2952  2832  ...  1470   

       42    43    44    45    46    47    48    49    50  
DAU                                                        
0    1448  1427  1406  1386  1367  1348  1330  1312  1294  

[1 rows x 50 columns]
```

This table represents the total number of DAU present in the product from those five cohorts over the course of a 50-period timeline.


The `project_cohorted_DAU` can be used to project DAU out given some set of cohorts and a retention profile, but it can also be used to generate the number of new users, given some existing set of cohorts, to reach some DAU target over a timeline.

In this example, the `cohorts` list contains five cohorts of 1000 new users each. If a marketing analyst wanted to know how many _additional_ cohorts, and of what size, would be needed in order to get the user base to 10,000 DAU, then they could use `project_cohorted_DAU` to do that by adding two parameters: `DAU_target` and `DAU_target_timeline`. `DAU_target` is the targeted number of DAU, and `DAU_target_timeline` is the number of days (which must be less than or equal to the number of `periods` being projected) over which the additional new users will be added.

In action:

```python
facebook_DAU = th.project_cohorted_DAU( profile = facebook, periods = 50, cohorts = cohorts, 
    DAU_target = 10000, DAU_target_timeline = 10, start_date = 1 )

print( facebook_DAU )
```

Should produce the following output:

```python
                1     2     3     4     5     6     7     8     9    10  ...  \
cohort_date                                                              ...   
1            1000   807   734   684   645   613   587   564   543   525  ...   
2               0  1000   807   734   684   645   613   587   564   543  ...   
3               0     0  1000   807   734   684   645   613   587   564  ...   
4               0     0     0  1000   807   734   684   645   613   587  ...   
5               0     0     0     0  1000   807   734   684   645   613  ...   
6               0     0     0     0     0  1613  1302  1184  1103  1040  ...   
7               0     0     0     0     0     0  1757  1418  1290  1201  ...   
8               0     0     0     0     0     0     0  1853  1495  1361  ...   
9               0     0     0     0     0     0     0     0  1934  1561  ...   
10              0     0     0     0     0     0     0     0     0  2005  ...   

              41   42   43   44   45   46   47   48   49   50  
cohort_date                                                    
1            285  281  277  273  270  266  262  259  255  252  
2            290  285  281  277  273  270  266  262  259  255  
3            294  290  285  281  277  273  270  266  262  259  
4            298  294  290  285  281  277  273  270  266  262  
5            303  298  294  290  285  281  277  273  270  266  
6            496  489  481  474  467  461  454  448  441  435  
7            549  541  532  524  517  509  502  495  488  481  
8            588  579  570  562  553  545  537  529  522  514  
9            624  614  604  595  586  577  569  561  553  545  
10           657  647  636  627  617  608  599  590  581  573  

[10 rows x 50 columns]
```

This table reveals that the additional DNU needed to get to 10,000 overall DAU within the 10-period timeframe is: 1613, 1757, 1853, 1934, 2005. _Note that this approach seeks to minimize the number of total DNU added on any given day within the timeline_.

Since the `facebook_DAU` variable is a pandas DataFrame, manipulating it to query data is fairly straightforward. For instance, to get only the DNU values, the following can be done:

```python
#get DNU from a DAU projection
DNU = [ facebook_DAU.iloc[ x, x ] for x in range( 0, min( facebook_DAU.shape ) ) ]
print( "All DNU: " + str( DNU ) )
print( "Additional DNU: " + str( DNU[ len( cohorts ): ] ) )
```

The output of which is:

```python
All DNU: [1000, 1000, 1000, 1000, 1000, 1613, 1757, 1853, 1934, 2005]
Additional DNU: [1613, 1757, 1853, 1934, 2005]
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)