'''

Theseus Growth
Author: Eric Benjamin Seufert, Heracles LLC (eric@mobiledevmemo.com)

Copyright 2020 Heracles LLC

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), 
to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, 
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, 
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

'''

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.colors as pltcolors
from matplotlib.ticker import PercentFormatter
from matplotlib import colors as mcolors
from matplotlib import cm
import pandas as pd
import numpy as np
import random
from datetime import datetime
from datetime import timedelta
from scipy.stats import linregress
from scipy.optimize import curve_fit
from scipy.interpolate import interp1d
from scipy.interpolate import InterpolatedUnivariateSpline
import numbers
import warnings
import time
import math
import openpyxl
from itertools import chain
warnings.filterwarnings('ignore')

class theseus():
    
    processes = [ 'log', 'exp', 'linear', 'quad', 'weibull', 'power' ]
    
    #retention_profile = {
    #     x: [], 'y': [], 'errors': {}, 'best_fit': '', 'retention_profile' = '' 
    #}
    #

    ####
    # Utility Functions
    ####

    def __init__( self ):
        
        return None
    
    def create_profile( self, days = None, retention_values = None, form = 'best_fit', profile_max = None ):
        
        if self.test_retention_profile( days, retention_values ):
            profile = { 'x': days, 'y': retention_values }

        if profile_max != None and ( not isinstance( profile_max, int ) or profile_max < max( days ) ):
            raise Exception( "profile_max must be an integer greater than or equal to maximum value of Days data" )
        
        # build the params attribute, which contains profile function curve shape parameters
        # if the best fit function is requested, use teh get_retention_projection_best_fit method
        # which iterates through all curve functions and finds the best fit (least squared error)
        # if a single form was provided, just get that 
        profile = self.get_retention_projection_best_fit( profile, profile_max )
        if form == 'best_fit' or form == '' or form == None:
            profile[ 'retention_profile' ] = 'best_fit'
        else:
            if form in self.processes or form == 'interpolate':
                profile[ 'retention_profile' ] = form
            else:
                raise Exception( 'Invalid retention curve function provided' )
                
        profile[ 'retention_projection' ] = self.generate_retention_profile( profile, profile_max )
        return profile
    
    def log_func( self, x, a, b, c ):
        return -a * np.log2( b + x ) + c

    def exp_func( self, x, a, b, c ):
        return a * np.exp( -b * x ) + c

    def poly_func( self, x, a, b, c, d ):
        return a*x**3 + b*x**2 +c*x + d

    def linear_func( self, x, a, b ):
        return a * x + b

    def quad_func( self, x, a, b, c ):
        return a * x**2 + b * x + c
    
    def weibull_func( self, x, k, l ):
        return ( k / l) * ( ( x / l ) ** ( k - 1 ) ) * np.exp( - ( x / l ) ** k )
    
    def power_func( self, x, a, b ):
        return a * x ** -b

    def test_retention_profile( self, x_data, y_data ):
        #do both lists have the same number of elements?
        if len( x_data ) != len( y_data ):
            raise Exception( 'X and Y have differing numbers of data points' )
        if not all( isinstance( x, numbers.Real ) for x in x_data ):
            raise Exception( 'X data can only contain integers' )
        if not all( isinstance( y, ( int, float ) ) for y in y_data ):
            raise Exception( 'Y data can only contain integers and floats' )
        if not all( ( float( y ) <= 100 and float( y ) > 0 ) for y in y_data ):
            raise Exception( 'Y data must be less than or equal to 100 and more than 0' )
        if not all( ( x > 0 ) for x in x_data ):
            raise Exception( 'X data must be more than 0' )
        if x_data == None or y_data == None or len( x_data ) < 2 or len( y_data ) < 2:
            raise Exception( 'Insufficient retention data provided!' )

        return True
    
    def get_interpolation_values( self, profile ):
        values = {}
        values[ 'x' ] = np.unique( np.array( profile[ 'x' ] ) ).tolist()
        values[ 'y' ] = []

        for i, v in enumerate( values[ 'x' ] ):
            #get indices from original X for this value
            this_y = [ profile[ 'y' ][ i ] for i, v2 in enumerate( values[ 'x' ] ) if v2 == v ]
            values[ 'y' ].append( round( np.average( this_y ), 2 ) )
            
        #add the collapsed (averaged) values to the profile
        profile[ 'y_collapsed' ] = values[ 'y' ]
        profile[ 'x_collapsed' ] = values[ 'x' ]
        return values
    
    def interpolate( self, profile ):
        interpolation_values = self.get_interpolation_values( profile )
        profile[ 'interpolation_f' ] = interp1d( interpolation_values[ 'x' ], interpolation_values[ 'y' ] )
        profile[ 'interpolation_s' ] = InterpolatedUnivariateSpline( interpolation_values[ 'x' ], interpolation_values[ 'y' ], k=1 )
        return None
        
    ####
    # Projection Functions
    ####
    
    def build_cohort( self, cohorts, date, cohort_size ):
        cohort = pd.DataFrame( columns=[ 'date', 'cohort_size' ] )

        cohort.loc[ 0 ] = [ date, cohort_size ]
        return cohort
    
    def add_cohort( self, cohorts, date, cohort_size ):
        this_cohort = self.build_cohort( cohorts, date, cohort_size )
        cohorts = cohorts.append( this_cohort )
        return cohorts
    
    def create_cohorts( self, cohorts_DNU, start_date = None ):
        #cohorts DNU is a list of ints
        #these are the cohorts of NEW users
        
        cohorts = pd.DataFrame()
        if start_date < 0:
            raise Exception( "Invalid start date" )

        if start_date == None or start_date == 0:
            start_date = 1
        this_date = start_date
        for i, cohort_size in enumerate( cohorts_DNU ): 
            cohort = self.build_cohort( cohorts, ( this_date ) , cohort_size )
            cohorts = cohorts.append( cohort )
            this_date += 1
        return cohorts
    
    def build_DAU_trajecory( self, start_DAU, end_DAU, periods ):
        x = [ 1, periods ]
        y = [ start_DAU, end_DAU ]

        model = linregress( x, y )

        return model
    
    def project_cohort( self, cohort, profile, periods ):
        
        #the function name for the best fit
        if profile[ 'retention_profile' ] == 'best_fit':
            form = profile[ profile[ 'retention_profile' ] ]
        else:
            form = profile[ 'retention_profile' ]
        this_func = form + '_func'
        this_params = profile[ 'params' ][ form ]
        
        #this iterates through the retention values list up through the # of periods being projected out
        #if the period number is > the max x value that was used to build the retention projection, it gives 0
        this_cohort = [ int( cohort * profile[ 'retention_projection' ][ 1 ][ i ] / 100 ) 
            if i <= max( profile[ 'retention_projection' ][ 0 ] ) else 0 for i in range( 0, periods ) ]
        
        return this_cohort
    
    def build_forward_DAU( self, profile, forward_DAU, cohort, periods, start_date ):
        ### this function takes a set of cohorts (which is a list of DNU)
        ### and a retention profile and projects out what the DAU will be
        ### based on the retention to some map_length
        ### forward_DAU is either a blank dataframe or it contains data for some cohorts
        ### whatever the case, so long as the list of cohorts contains 2 or more values,
        ### we add this projected cohort to the end of the forward_DAU dataframe and
        ### recurse with one less cohort sent. If there's just one cohort left, we return dataframe.

        #the function name for the best fit
        if profile[ 'retention_profile' ] == 'best_fit':
            form = profile[ profile[ 'retention_profile' ] ]
        else:
            form = profile[ 'retention_profile' ]
        this_func = form + '_func'
        this_params = profile[ 'params' ][ form ]
        
        #build the cohort out by periods
        this_cohort = self.project_cohort( cohort, profile, periods )
        
        #need to insert 0s to the beginning depending on where it goes in the lifetime
        #eg if it's the first cohort, no zeroes
        #second cohort, 1 zero, etc.
        delta_count = len( forward_DAU )
        if start_date == 1:
            this_cohort = [ len( forward_DAU ) ] + ( [ 0 ] * ( delta_count ) ) + this_cohort
        else:
            this_cohort = [ len( forward_DAU ) ] + ( [ 0 ] * ( delta_count + 1 ) ) + this_cohort
        #now remove that many values from the end
        if delta_count > 0:
            del this_cohort[ -delta_count: ]
        
        #add this_cohort to forward_DAU
        forward_DAU.loc[ len( forward_DAU ) ] = this_cohort
        forward_DAU = forward_DAU.fillna( 0 )
        
        return forward_DAU
    
    def DAU_total( self, DAU_projection ):
        if not isinstance( DAU_projection, pd.DataFrame ) or len( DAU_projection ) < 2:
            raise Exception( 'DAU Projection is malformed. Must be a dataframe with at least 2 rows.' )
            
        #get the sums of the columns
        total_series = DAU_projection.sum()

        DAU_total = pd.DataFrame( columns = [ 'DAU' ] + DAU_projection.columns.tolist() ).set_index( 'DAU' )
        DAU_total.loc[ len( DAU_total ) ] = total_series
        
        return DAU_total
    
    def combine_DAU( self, DAU_totals, labels = None ):
        
        if len( DAU_totals ) < 2:
            raise Exception( 'Must provide at least two sets of DAU projections to combine.' )
            
        if labels != None and ( len( DAU_totals ) != len( labels ) ):
            raise Exception( 'Number of labels doesnt match number of DAU projections provided.' )
        
        combined_DAU = DAU_totals[ 0 ]
        combined_DAU = combined_DAU.reset_index( )
        if labels != None:
            combined_DAU[ 'profile' ] = labels[ 0 ]
            
        i = 1
        for DAU_total in DAU_totals[ 1: ]:
            if labels != None:
                DAU_total[ 'profile' ] = labels[ i ]
                DAU_total.reset_index().set_index( [ 'profile' ] )
            common = list( set( combined_DAU.columns.tolist() ) & set( DAU_total.columns.tolist() ) )
            combined_DAU = pd.merge( combined_DAU, DAU_total, on=common, how='outer' ).fillna( 0 )
            i += 1
            
        #sort the columns
        columns = sorted( [ int( c ) for c in combined_DAU.columns if c not in [ 'DAU', 'profile', 'cohort_date', 'age' ] ] )
        columns = [ str( c ) for c in columns ]
        if labels != None:
            columns += [ 'profile' ]
        #combined_DAU = combined_DAU.reindex( sorted( combined_DAU.columns, key=lambda x: float( combined_DAU.columns ) ), axis=1 )
        combined_DAU = combined_DAU[ columns ]
        combined_DAU.reset_index( )
        
        return combined_DAU.set_index( 'profile' )
    
    ######
    # Project Aged DAU
    # Will project out the number of people that are at least X days old on a given day
    ######
    def project_aged_DAU( self, profile, periods, cohorts, start_date = 1, ages = [ 1 ] ):
        if len( ages ) == 0:
            raise Exception( "Age values cannot be empty" )

        if any( x <= 0 for x in ages):
            raise Exception( "Age values cannot be less than 1" )
        
        #create a list of dates
        if start_date == 0:
            start_date = 1
        dates = list( range( start_date, ( start_date + periods ) ) )
        dates = [ str( x ) for x in dates ]
        #create the blank dataframe that will contain the forward_DAU
        aged_DAU = pd.DataFrame( columns = [ 'age' ] + dates ).set_index( 'age' )
        #remove any ages that are > the number of periods being projected out
        ages = [ age for age in ages if age <= periods ]
        for i, age in enumerate( ages ):
            this_age = pd.DataFrame( columns = [ 'age' ] + dates ).set_index( 'age' )
            this_age.loc[ age ] = [ 0 ] * len( dates ) 
            aged_DAU = aged_DAU.append( this_age )
            
        ###go through the cohorts and get the ages
        for i, cohort in enumerate( cohorts ):
            this_cohort = self.project_cohort( cohort, profile, periods )
            for j, age in enumerate( ages ):
                temp_cohort = this_cohort.copy()
                this_age = aged_DAU.loc[ [ age ] ]
                if age > 0:
                    #set 0s to the front of the cohort for each day that the cohort is less than age
                    temp_cohort[ 0: ( age - 1 ) ] = [ 0 ] * ( age - 1 )
                if i > 0:
                    #shift the cohort right by the number of cohorts this is
                    temp_cohort = [ 0 ] * i + temp_cohort[ : -i ]
                cohort_age = pd.DataFrame( columns = [ 'age' ] + dates ).set_index( 'age' )
                cohort_age.loc[ age ] = temp_cohort
                aged_DAU.loc[ [ age ] ] = this_age.add( cohort_age, fill_value=0 )
    
        return aged_DAU
    
    ######
    # Project Exact Aged DAU
    # Will project out the number of people that are exactly X days old on a given day
    ######
    def project_exact_aged_DAU( self, profile, periods, cohorts, start_date = 1, ages = [ 1 ] ):
        #create a list of dates
        if len( ages ) == 0:
            raise Exception( "Age values cannot be empty" )
            
        if start_date == 0:
            start_date = 1
            
        if any( x <= 0 for x in ages):
            raise Exception( "Age values cannot be less than 1" )
            
        dates = list( range( start_date, ( start_date + periods ) ) )
        dates = [ str( x ) for x in dates ]
        #create the blank dataframe that will contain the forward_DAU
        aged_DAU = pd.DataFrame( columns = [ 'age' ] + dates ).set_index( 'age' )
        #remove any ages that are > the number of periods being projected out
        ages = [ age for age in ages if age <= periods ]
        for i, age in enumerate( ages ):
            this_age = pd.DataFrame( columns = [ 'age' ] + dates ).set_index( 'age' )
            this_age.loc[ age ] = [ 0 ] * len( dates ) 
            aged_DAU = aged_DAU.append( this_age )
            
        ###go through the cohorts and get the ages
        for i, cohort in enumerate( cohorts ):
            this_cohort = self.project_cohort( cohort, profile, periods )
            for j, age in enumerate( ages ):
                temp_cohort = this_cohort.copy()
                this_age = aged_DAU.loc[ [ age ] ]
                if age > 0:
                    #set 0s to the front of the cohort for each day that the cohort is less than age
                    temp_cohort[ 0: ( age - 1 ) ] = [ 0 ] * ( age - 1 )
                    #set to 0 anything after the first day of the cohort
                    temp_cohort[ age: ] = [ 0 ] * ( len( temp_cohort ) - age )
                if i > 0:
                    #shift the cohort right by the number of cohorts this is
                    temp_cohort = [ 0 ] * i + temp_cohort[ : -i ]
                cohort_age = pd.DataFrame( columns = [ 'age' ] + dates ).set_index( 'age' )
                cohort_age.loc[ age ] = temp_cohort
                aged_DAU.loc[ [ age ] ] = this_age.add( cohort_age, fill_value=0 )
    
        return aged_DAU
    
    def project_cohorted_DAU( self, profile, periods, cohorts, DAU_target = None, 
        DAU_target_timeline = None, start_date = 1 ): ###
        
        if DAU_target is not None and DAU_target_timeline is not None and DAU_target_timeline > periods:
            raise Exception( "DAU target timeline is longer than the number of periods being projected" )
        
        if start_date == 0 or start_date == None:
            start_date = 1
            
        #create a list of dates
        if start_date == 1:
            dates = list( range( start_date, ( start_date + periods ) ) )
        else:
            dates = list( range( start_date, ( start_date + periods + 1 ) ) )

        dates = [ str( x ) for x in dates ]
        #create the blank dataframe that will contain the forward_DAU
        forward_DAU = pd.DataFrame( columns = [ 'cohort_date' ] + dates )
        ###build the initial forward DAU from the cohorts
        for cohort in cohorts:
            forward_DAU = self.build_forward_DAU( profile, forward_DAU, cohort, periods, start_date )
        
        # if DAU_target is set, it means we are trying to build to some target
        if DAU_target != None:
            
            if DAU_target_timeline == None:
                raise Exception( 'DAU Target Projections require a DAU Target Timeline' )
                
            tracker = len( cohorts ) + 1

            ###start projections
            start_DAU = forward_DAU.iloc[ :, tracker - 1 ].sum() #the current value of DAU
    
            ### this builds a list of DAU values needed to hit the DAU target over the timeline
            ### it uses a straight linear regression and just comes up with DAU values
            ### the reason it starts from tracker - 1 is that we want the model to project
            ### from the *current* value to target, not the day after the last cohort
            ### keep in mind that the entire timeline is projected out, which is why the
            ### tracker is needed in the first place (otherwise we could just use last column of df)
            model = self.build_DAU_trajecory( start_DAU, DAU_target, ( DAU_target_timeline + 1 - len( cohorts ) ) )

            ### get the DAU values that we need each day to linearly progress to the target DAU
            ### start from 2 because we want to exclude the first value, 
            ### which is the last value of the existing cohorts
            DAU_values = [ int( model[ 0 ] * i + model[ 1 ] ) for i in range( 1, ( DAU_target_timeline + 2 - len( cohorts ) ) ) ][ 1: ]
            
            for DAU_target in DAU_values:
                
                if len( forward_DAU ) > len( forward_DAU.columns.tolist() ):
                    forward_DAU[ str( int( forward_DAU.columns.tolist()[ -1 ] ) + 1 ) ] = [ 0 ] * ( len( forward_DAU ) )
                
                #the current value of DAU is the sum of the last column of forward_DAU
                start_DAU = forward_DAU.iloc[ :, tracker ].sum()
                DAU_needed = ( 0 if DAU_target - start_DAU < 0 else DAU_target - start_DAU )
                
                forward_DAU = self.build_forward_DAU( profile, forward_DAU, DAU_needed, periods, start_date )
                
                tracker += 1
                
        forward_DAU[ 'cohort_date' ] = forward_DAU[ 'cohort_date' ] + 1
        
        return forward_DAU.set_index( 'cohort_date' )
            
    ####
    # Graphing Functions
    ####
        
    def plot_retention( self, profile, show_average_values = True ):
        
        retention_projection = profile[ 'retention_projection' ]
        profile_label = profile[ 'retention_profile' ] + ' function'
            
        #
        fig, ax = plt.subplots( figsize = (25, 15) ) 
        plt.plot( profile[ 'x' ], profile[ 'y' ], 'ro', label="Original Data", markersize = 6)
        plt.plot( retention_projection[ 0 ], retention_projection[ 1 ], 'm--', label = profile_label, linewidth = 4 )
        
        if show_average_values:
            plt.plot( profile[ 'x_collapsed' ], profile[ 'y_collapsed' ], 'yo', 
                 label = 'Average Values', markersize = 12 )
        
        plt.xticks( fontsize=20 )
        plt.xticks( rotation=45 )
        plt.yticks( fontsize=20 )
        
        plt.axhline(y=0, color='r', linestyle='--')
        
        ax.get_yaxis().set_major_formatter(
            ticker.FuncFormatter(lambda y, _: '{:.0%}'.format( y / 100 ) )
        )

        plt.legend()
        plt.show()
        
    def stacked_bar( self, data, series_labels, category_labels=None, 
                    show_values=False, value_format="{}", y_label=None, 
                    grid=True, reverse=False, show_totals_values=False, totals = [] ):
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
        
        cmap = cm.get_cmap( 'tab20', 100 )    # PiYG, create a color map
        colors = [ pltcolors.rgb2hex( cmap( i )[ :3 ] ) for i in range( cmap.N ) ] 

        fig, ax = plt.subplots( figsize = (25, 15) ) 

        ny = len(data[0])
        ind = list( range(ny) )

        axes = []
        cum_size = np.zeros( ny )

        data = np.array( data )

        if reverse and category_labels != None:
            data = np.flip(data, axis=1)
            category_labels = reversed(category_labels)

        for i, row_data in enumerate( data ):
            if colors:
                axes.append( plt.bar( ind, row_data, bottom=cum_size, 
                                    label=series_labels[i], color = random.choice( colors ) ) )
            else:
                axes.append( plt.bar( ind, row_data, bottom=cum_size, 
                                    label=series_labels[i] ) )
            cum_size += row_data

        if category_labels:
            category_font_size = 20 if len( category_labels ) <= 15 else 16
            plt.xticks( ind, category_labels, fontsize=category_font_size )
            plt.xticks( rotation=45 )
            label_skip = 7  # Keeps every 7th label
            [ l.set_visible( False ) for ( i, l ) in enumerate( ax.xaxis.get_ticklabels() ) if i % label_skip != 0 ]
            
        if y_label:
            plt.ylabel( y_label, fontsize=20 )
            plt.yticks( fontsize=20 )
            ax.get_yaxis().set_major_formatter(
                ticker.FuncFormatter( lambda x, p: format(int(x), ',' ) )
            )

        plt.legend( fontsize = 'xx-large' )

        if grid:
            plt.grid()

        if show_values:
            for axis in axes:
                for bar in axis:
                    w, h = bar.get_width(), bar.get_height()
                    text_loc_x = bar.get_x() + w/2
                    text_loc_y = bar.get_y() + h/2
                    if h != 0:
                        plt.text( text_loc_x, text_loc_y, 
                                 h, ha="center", 
                                 va="center", fontsize=22 )

        if show_totals_values:
            #show the total for each stacked bar chart
            #eg. the sum of the values for any given category
            if totals:
                if len( totals ) == len( category_labels ):
                    count = 0
                    for index, total in enumerate( totals ):
                        totals_font = 26 if len( category_labels ) <= 15 else 18
                        totals_rotate = 0 if len( category_labels ) <= 15 else 45
                        totals_height = 3 if len( category_labels ) <= 15 else 10
                        totals_skip = 5 if len( category_labels ) >= 15 else 3
                        if count % totals_skip == 0 or count == 0:
                            plt.text( index, total + ( totals_height/100 * sum( totals ) / len( totals ) ), 
                                     '{:,}'.format( math.floor( total ) ), ha="center", 
                                     va="center", fontsize=totals_font, color="r", 
                                     weight = 'bold', rotation=totals_rotate )
                        count += 1
        
    def plot_forward_DAU_stacked( self, forward_DAU, forward_DAU_labels, forward_DAU_dates, show_values=False, 
        show_totals_values=False ):
        transformed = forward_DAU.values.tolist()

        #I dont remember what the purpose of this was, but it broke the transformed list when I 
        #re-indexed the forward_DAU df to start at 1
        #leaving it here just in case
        '''
        if len( forward_DAU.index ) > 1:
            for index, value in enumerate( transformed ):
                transformed[ index ] = value[ 1: ]
        '''

        totals = [ forward_DAU[ column ].sum() for column  
            in forward_DAU.loc[ :, forward_DAU.columns != 'cohort_date' ] ]

        self.stacked_bar( transformed, forward_DAU_labels, 
            category_labels=forward_DAU_dates, 
            show_values=show_values, value_format="{}", y_label='DAU', 
            grid=True, reverse=False, show_totals_values=show_totals_values, totals = totals )
        
    ####
    # Core Retention Profile Functions
    ####
    
    def generate_retention_profile( self, profile, profile_max ):        
        y_data_projected = self.project_retention( profile, profile_max = profile_max )
        #push 1 onto the front of the list because day 0 retention is always 100
        y_data_projected = np.insert( y_data_projected, 0, 100 )
        
        #get the occurances of all inf values
        inf_indices = [ i for i, x in enumerate( y_data_projected ) if x == float( "inf" ) ]
        #remove all inf values
        y_data_projected = [ y for y in y_data_projected if y != float( "inf" )][ :-1 ].copy()
        #add them back to the end
        to_add = [ self.project_retention( profile, start = len( y_data_projected ) + i, stop = len( y_data_projected ) + i + 1 ) for i, v in enumerate( inf_indices ) ]
        
        #test to see if to_add is a nested list
        #if it is, un-nest it
        if any( isinstance( i, list ) for i in to_add ):
            to_add = list( chain( *to_add ) )
        y_data_projected = y_data_projected + to_add
        x_data_projected = np.arange( start = 1, stop = len( y_data_projected ) + 1, step = 1 )

        return ( x_data_projected, y_data_projected )
    
    def project_retention( self, profile, profile_max = None, start = None, stop = None ):
        
        x2 = None
        
        if profile_max == None and start == None and stop == None:
            #no x2 x-axis values were passed
            #take the max x value from the profile and create a range from that
            x2 = np.arange( start = 1, stop = max( profile[ 'x' ] ) + 1, step = 1 )
        elif profile_max != None:
            #create a range from 0 to profile_max
            x2 = np.arange( start = 1, stop = profile_max + 1, step = 1 )
        elif start != None and stop != None:
            #a start and end date were provided, so that's x2
            x2 = np.arange( start = start, stop = stop, step = 1 )
        else:
            raise Exception( 'Incorrect parameter set sent. Must include either profile_max or start and end points.')
        
        this_process = profile[ 'retention_profile' ]
        
        #
        # we have a process equation for the function, so now use that to project
        # out DAU against x2
        #
        if this_process != 'interpolate':
            # if the process isn't simply to just interpolate the points
            if this_process == 'best_fit':
                this_process = profile[ 'best_fit' ]
            #get the retention projection for the appropriate process
            if this_process in self.processes:
                retention_projection = getattr( self, this_process + '_func' )( x2, *profile[ 'params' ][ this_process ] )
            else:
                raise Exception( 'Invalid retention function provided: ' + this_process )
        else:
            # create the retention projection for the interpolation
            if profile_max == None:
                # no profile max was selected, so x2 is just the max value from the profile X values
                # use the interpolation_f function which is the linear interpolation of the provided values
                retention_projection = [ profile[ 'interpolation_f' ]( z ) for z in range( min( profile[ 'x' ] ), max( profile[ 'x' ] ) + 1 ) ]
            else:
                # a profile_max was provided so we need to extrapolate the interpolation out
                # use the interpolation_s function
                retention_projection = [ profile[ 'interpolation_s' ]( z ) for z in range( min( profile[ 'x' ] ), max( x2 ) + 1 ) ]
        retention_projection = [ z if z > 0 else 0 for z in retention_projection ]
                
        #replace all negative y values with 0
        retention_projection[ 1 ] = np.where( retention_projection[ 1 ] < 0, 0, retention_projection[ 1 ] ) 
        
        return retention_projection
    
    def generate_curve_coefficients( self, profile, process_value ):
        if process_value in self.processes:
            x_data = profile[ 'x' ]
            y_data = profile[ 'y' ]
            this_func = process_value + '_func'
            try:
                popt, pcov = curve_fit( getattr( self, this_func ), x_data, y_data )
            except:
                raise Exception( 'Unable to process retention curve with ' + process_value + ' function' )
            popt, pcov = curve_fit( getattr( self, this_func ), x_data, y_data )
        elif process_value == 'interpolate':
            self.interpolate( profile )
            return None
        else:
            raise Exception( process_value + ' is not a valid retention curve function' )
        return popt

    
    def process_retention_profile_projection( self, profile ):
        curve_fit_values = {}
        process_list = self.processes.copy() + [ 'interpolate' ]

        for process_value in process_list:
            try:
                curve_fit_values[ process_value ] = self.generate_curve_coefficients( profile, process_value )
            except:
                pass
            curve_fit_values[ process_value ] = self.generate_curve_coefficients( profile, process_value )
        return curve_fit_values    

    def get_retention_projection_best_fit( self, profile, profile_max = None ):
        equations = {}
        errors = {}
        x_data = profile[ 'x' ]
        y_data = profile[ 'y' ]
        
        if profile_max == None:
            profile_max = max( x_data )
        
        x2 = np.arange( profile_max )
        
        if 'params' not in profile or not profile[ 'params' ]:
            profile[ 'params' ] = self.process_retention_profile_projection( profile )
        
        for process_value in self.processes:
            this_func = process_value + '_func'
            this_params = profile[ 'params' ][ process_value ]
            equations[ process_value ] = getattr( self, this_func )( x2, *this_params )
            #calculate the summed squared error for this model based on the X values
            #that exist for this retention profile
            these_summed_squares = 0

            for i, x_projection in enumerate( x2 ):
                x_projection = int( x_projection )
                #loop through x2 and get all the y values for that x
                #since there can be multiple points per x value
                #the indices in x_data are the same for those values in y_data
                x_indices = [ i for i, x in enumerate( x_data ) if x == x_projection ]
                y_values = [ y_data[ index ] for index in x_indices ]
                #get the projected value for this x value from equations
                projected_value = equations[ process_value ][ x_projection ]
                #sum up squared errors between all y values and the projected value
                this_ss = sum( [ abs( projected_value - this_value )**2 for this_value in y_values ] )
                #add the summed errors for the y values at this x value to the running total
                these_summed_squares += this_ss
            #assign the summed squares value to the errors for this process value
            errors[ process_value ] = these_summed_squares
            
        best_fit = str( min( errors, key=errors.get ) )
        profile[ 'errors' ] = errors
        profile[ 'best_fit' ] = best_fit

        return profile
    
    ##########################
    # OUTPUT
    ##########################
    
    def to_excel( self, df, file_name, sheet_name ):
        if not file_name:
            file_name = 'theseus_output.xlsx'
        if not sheet_name:
            sheet_name = 'sheet1'
            
        if not file_name.endswith( '.xlsx' ):
            file_name = file_name + '.xlsx'
        
        df.to_excel( file_name, sheet_name=sheet_name)
        
    def to_json( self, df, file_name = None ):
        if not file_name:
            file_name = 'theseus_output.json'
        
        if not file_name.endswith( '.json' ):
            file_name = file_name + '.json'
            
        df.to_json( path_or_buf = file_name, orient='index' )
