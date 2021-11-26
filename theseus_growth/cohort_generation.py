import pandas as pd
import numpy as np
import datetime

class Cohort():
    def __init__(self, data, cohort_date_column=None, churn_date_column=None,  interval=None, **kwargs):
        self.interval = interval
        self._df = pd.DataFrame(data) if not isinstance(data, pd.DataFrame) else data
        self._df = add_cohort_fields(self._df, cohort_date_column, churn_date_column, interval)
        self._cohort = df_to_cohorts(self._df)

    @property
    def normalized(self):
        return normalize_cohort(self._cohort)

    @property
    def average(self):
        return average_cohort(self.normalized)

    @property
    def average_percent(self):
        return average_cohort(self.normalized) * 100

    @property
    def range(self):
        return np.arange(len(next(iter(self._cohort.values())))) + 1

    __repr__ = lambda self: self._cohort.__repr__()

def create_cohort(data, cohort_date_column, churn_date_column, interval=None,  **kwargs):
    return Cohort(data, cohort_date_column=cohort_date_column, churn_date_column=churn_date_column, interval=interval, **kwargs)

def add_cohort_fields(df, cohort_date_column, churn_date_column, interval=None):
    if cohort_date_column not in df: raise Exception('Cohort date column not found in dataframe: '+str(cohort_date_column))
    df['cohort'] = df.apply(cohort_start, axis=1, args=(cohort_date_column,)).astype(int, errors='ignore')
    df['cohort_end'] = df.apply(cohort_end, axis=1, args=(churn_date_column,)).astype(int, errors='ignore')
    df['cohort_length'] = df.apply(cohort_length, axis=1).astype(int)
    return df

def get_data_type(data):
    if isinstance(data, pd.DataFrame):
        return 'dataframe'
    elif isinstance(data, list):
        return 'list'
    else:
        raise Exception('Data must be a list or dataframe')

def date_to_cohort(date, interval='month'):
    if isinstance(date, str):
        date = pd.to_datetime(date)
    elif isinstance(date, datetime.date) or isinstance(date, datetime.datetime):
        date = pd.to_datetime(date)
    else:
        return 0
    return int(date.strftime('%Y%m'))

def cohort_to_date(cohort, interval='month'):
    if not cohort: return None
    try: date = datetime.datetime.strptime(str(cohort)[0:6], '%Y%m')
    except: return None
    return date

def cohort_start(row, column):
    date = None
    if row[column] and date_to_cohort(row[column]):
        date = row[column]
    return date_to_cohort(date)

def cohort_end(row, column):
    date = None
    if row[column] and date_to_cohort(row[column]):
        date = row[column]
    return date_to_cohort(date)

def cohort_length(row, interval='month'):
    if interval not in ['month', 'week', 'day']: raise Exception('Interval must be month, week, or day')

    cohort_date = cohort_to_date(row['cohort'])
    if not cohort_date: 
        return 0
    now = datetime.datetime.now()
    cohort_end_date = now if not cohort_to_date(row['cohort_end']) else cohort_to_date(row['cohort_end'])
    
    d1 = now if cohort_end_date > now else cohort_end_date
    d2 = cohort_date

    return int((d1.year - d2.year) * 12 + getattr(d1, interval) - getattr(d2, interval))

def df_to_cohorts(df):
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

def list_to_cohorts(data, date_column, id_column, interval="month"):
    users = {}
    cohorts = {}
    data = sorted(data, key=lambda x: x[date_column])
    for row in data:
        user_id = row[id_column]
        date_as_cohort = date_to_cohort(row[date_column])
        if user_id not in users:
            users[user_id] = {**row, 'cohort': date_as_cohort}
        user = users[user_id]

        if user.get('cohort_end') and user['cohort_end'] == date_as_cohort:
            continue
        user['cohort_end'] = date_as_cohort

        length = cohort_length(user, interval) + 1
        if user['cohort'] not in cohorts:
            cohorts[user['cohort']] = [0 for i in range(length)]
        if len (cohorts[user['cohort']]) < length:
            cohorts[user['cohort']].extend([0 for i in range(length-len(cohorts[user['cohort']]))])
        cohorts[user['cohort']][length-1] += 1
    
    return cohorts


def normalize_cohort(cohorts):
    cohorts_normalized = {}        
    for cohort in sorted(cohorts.keys()):
        starting_count =  max(cohorts[cohort])
        cohorts_normalized[cohort] = [float(x)/starting_count for x in cohorts[cohort]] if starting_count else 0

    return cohorts_normalized

def average_cohort(cohorts_normalized):
    #Noramlize if they passed non normalized data
    if max(list(cohorts_normalized.values())[0]) > 1:
        cohorts_normalized = normalize_cohort(cohorts)

    df = pd.DataFrame(cohorts_normalized).replace(0, np.nan)

    return np.array(df.mean(axis=1).to_list())

if __name__ == '__main__':
    # data = pd.read_csv('/home/mike/projects/analytics/account_churn.csv')

    data = [
        {'date': '2019-01-01', 'name': "Johnny"},
        {'date': '2019-01-01', 'name': "Johnny"},
        {'date': '2019-02-01', 'name': "Mike"},
        {'date': '2019-03-01', 'name': "Mike"},
        {'date': '2019-02-01', 'name': "Mike"},
        {'date': '2019-01-01', 'name': "Johnny"},
        {'date': '2019-01-01', 'name': "Johnny"},
        {'date': '2019-03-01', 'name': "Kenny"},
        {'date': '2019-05-01', 'name': "Kenny"},
        {'date': '2019-02-01', 'name': "Kenny"},
        {'date': '2019-06-01', 'name': "BoB"},
        {'date': '2019-03-01', 'name': "BoB"},
        {'date': '2019-04-01', 'name': "BoB"},
        {'date': '2019-05-01', 'name': "BoB"},
    ]

    # c = create_cohort(data, 'Trial_End_Date__c', 'Cancellation_Date__c')
    # c = Cohort(data, 'date', 'name')
    d = list_to_cohorts(data, 'date', 'name')
    print(d)
    exit()
    # print(c._df)
    # print(c.average)
    # print(c._cohort)
    print(c.range)