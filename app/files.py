from app import db
from datetime import datetime, date
import pandas as pd
import os
from natsort import index_natsorted
import numpy as np
from io import TextIOWrapper
import csv
from .models import Schedule
import platform


def export():
    try:
        engine = db.create_engine(os.environ.get('DATABASE_URL')).connect()
    except:
        engine = db.create_engine('sqlite:///db.sqlite').connect()

    # pull the schedule information
    df = pd.read_sql('SELECT * FROM schedule;', engine)
    df = df.sort_values(by="startdate",
                        key=lambda x: np.argsort(index_natsorted(df["startdate"]))).reset_index(drop=True)

    csv_data = "Name,Amount,Type,Frequency,Next Date,First Date\n"
    for i in range(len(df.index)):
        # Create a CSV string from the data
        csv_data += (f"{df['name'][i]},{df['amount'][i]},{df['type'][i]},{df['frequency'][i]},{df['startdate'][i]}"
                     f",{df['firstdate'][i]}\n")

    return csv_data


def upload(csv_file):
    csv_file = TextIOWrapper(csv_file, encoding='utf-8')
    csv_reader = csv.reader(csv_file, delimiter=',')
    next(csv_reader)

    format = '%Y-%m-%d'
    for row in csv_reader:
        try:
            name = row[0]
            amount = float(row[1])
            type = row[2]
            frequency = row[3]
            next_date = row[4]
            next_date = datetime.strptime(next_date, format).date()
            first_date = row[5]
            first_date = datetime.strptime(first_date, format).date()

            existing = Schedule.query.filter_by(name=name).first()

            if (not existing and (type == "Income" or type == "Expense")
                    and (frequency == "Monthly" or frequency == "Quarterly" or frequency == "Yearly" or
                         frequency == "Weekly" or frequency == "BiWeekly" or frequency == "Onetime")):
                schedule = Schedule(name=name, amount=amount, type=type, frequency=frequency, startdate=next_date,
                                    firstdate=first_date)
                db.session.add(schedule)
                db.session.commit()
            elif (existing and (type == "Income" or type == "Expense")
                    and (frequency == "Monthly" or frequency == "Quarterly" or frequency == "Yearly" or
                         frequency == "Weekly" or frequency == "BiWeekly" or frequency == "Onetime")):
                existing.amount = amount
                existing.frequency = frequency
                existing.startdate = next_date
                existing.type = type
                existing.firstdate = first_date
                db.session.commit()
        except:
            pass

    return 0


def version():
    # get current python version
    pyversion = platform.python_version()
    # check for docker env variable
    try:
        app_version = os.environ['APP_VERSION']
        version = "pycashflow: " + app_version + " :: python: " + pyversion
    except KeyError:
        # read VERSION file and store string
        basedir = os.path.abspath(os.path.dirname(__file__))
        app_version = open(os.path.join(basedir, 'VERSION'), 'r').read()
        version = "pycashflow: " + app_version + " :: python: " + pyversion

    return version
