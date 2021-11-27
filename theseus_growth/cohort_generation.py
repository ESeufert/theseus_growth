import pandas as pd
import numpy as np
import datetime


class Cohort():
    """
    Generate cohorts from user data.

    If churn_date_column is provided, we assume each row is a user and that they were active throughout the period. Date field becomes cohort date.
    If identifer_column is provided, we assume rows are activity and that there may be many per user. We assign a cohort based on earliest activity. 
    """
    def __init__(self, data, date_column, churn_date_column=None, identifier_column=None,  interval=None, **kwargs):
        self.interval = interval
        self._df = pd.DataFrame(data) if not isinstance(data, pd.DataFrame) else data

        #Determine what format the data was given. We accept activity data or a list of users with churn date already given.
        if churn_date_column:
            self._df = self.add_cohort_fields(self._df, date_column, churn_date_column, interval)
            self._users = self._df
            self._cohort = self.users_to_cohorts(self._df)
        elif identifier_column:
            self._users, self._cohort = self.activity_to_cohorts(self._df, date_column, identifier_column)
        else:
            raise ValueError("Must provide either a churn_date_column or an identifier_column")

    @property
    def normalized(self):
        return self.normalize_cohort(self._cohort)

    @property
    def average(self):
        return self.average_cohort(self.normalized)

    @property
    def average_percent(self):
        return self.average_cohort(self.normalized) * 100

    @property
    def range(self):
        return np.arange(len(next(iter(self._cohort.values())))) + 1

    __repr__ = lambda self: self._cohort.__repr__()

    
    def users_to_cohorts(self, df):
        """
        Creates a cohort based on start and end date

        Each entry is considered a unique client and we assume they were active throughout the period.
        """
        cohorts = {}
        max_length = int(df['cohort_length'].max())
        for index, row in df.iterrows():
            if not row['cohort']: continue
            if row['cohort'] not in cohorts:
                cohorts[row['cohort']] = [0 for i in range(max_length)]
            cohort = cohorts[row['cohort']]
            
            for i in range(row['cohort_length']):
                cohort[i] += 1
        
        return dict(sorted(cohorts.items()))

    def activity_to_cohorts(self, df, date_column, id_column, interval="month"):
        """
        Creates a cohort based on usage activity.

        Activity is like a log entry. There can be many per unique client.
        """
        users = {}
        cohorts = {}
        df = df.sort_values(by=date_column)
        for index, row in df.iterrows():
            user_id = row[id_column]
            date_as_cohort = self.date_to_cohort(row[date_column])
            if user_id not in users:
                users[user_id] = {**row, 'cohort': date_as_cohort}
            user = users[user_id]

            if user.get('cohort_end') and user['cohort_end'] == date_as_cohort:
                continue
            user['cohort_end'] = date_as_cohort

            length = self.cohort_length(user, interval) + 1
            if user['cohort'] not in cohorts:
                cohorts[user['cohort']] = [0 for i in range(length)]
            if len (cohorts[user['cohort']]) < length:
                cohorts[user['cohort']].extend([0 for i in range(length-len(cohorts[user['cohort']]))])
            cohorts[user['cohort']][length-1] += 1
        
        return pd.DataFrame(users), dict(sorted(cohorts.items()))



    def add_cohort_fields(self, df, date_column, churn_date_column, interval=None):
        if date_column not in df: raise Exception('Cohort date column not found in dataframe: '+str(date_column))
        df['cohort'] = df.apply(self.cohort_start, axis=1, args=(date_column,)).astype(int, errors='ignore')
        df['cohort_end'] = df.apply(self.cohort_end, axis=1, args=(churn_date_column,)).astype(int, errors='ignore')
        df['cohort_length'] = df.apply(self.cohort_length, axis=1).astype(int)
        return df


    def date_to_cohort(self, date, interval='month'):
        if isinstance(date, str):
            date = pd.to_datetime(date)
        elif isinstance(date, datetime.date) or isinstance(date, datetime.datetime):
            date = pd.to_datetime(date)
        else:
            return 0
        return int(date.strftime('%Y%m'))

    def cohort_to_date(self, cohort, interval='month'):
        if not cohort: return None
        try: date = datetime.datetime.strptime(str(cohort)[0:6], '%Y%m')
        except: return None
        return date

    def cohort_start(self, row, column):
        date = None
        if row[column] and self.date_to_cohort(row[column]):
            date = row[column]
        return self.date_to_cohort(date)

    def cohort_end(self, row, column):
        date = None
        if row[column] and self.date_to_cohort(row[column]):
            date = row[column]
        return self.date_to_cohort(date)

    def cohort_length(self, row, interval='month'):
        if interval not in ['month', 'week', 'day']: raise Exception('Interval must be month, week, or day')

        cohort_date = self.cohort_to_date(row['cohort'])
        if not cohort_date: 
            return 0
        now = datetime.datetime.now()
        cohort_end_date = now if not self.cohort_to_date(row['cohort_end']) else self.cohort_to_date(row['cohort_end'])
        
        d1 = now if cohort_end_date > now else cohort_end_date
        d2 = cohort_date

        return int((d1.year - d2.year) * 12 + getattr(d1, interval) - getattr(d2, interval))


    def normalize_cohort(self, cohorts):
        cohorts_normalized = {}        
        for cohort in sorted(cohorts.keys()):
            starting_count =  max(cohorts[cohort])
            cohorts_normalized[cohort] = [float(x)/starting_count for x in cohorts[cohort]] if starting_count else 0

        return cohorts_normalized

    def average_cohort(self, cohorts_normalized):
        #Noramlize if they passed non normalized data
        if max(list(cohorts_normalized.values())[0]) > 1:
            cohorts_normalized = self.normalize_cohort(cohorts)

        df = pd.DataFrame(cohorts_normalized).replace(0, np.nan)

        return np.array(df.mean(axis=1).to_list())
