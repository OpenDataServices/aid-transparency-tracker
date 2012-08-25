from flask import Flask, render_template, flash, request, Markup, session, redirect, url_for, escape, Response
from flask.ext.celery import Celery
from celery.task.sets import TaskSet
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, UnicodeText, Date, DateTime, Float, Boolean, func
from iati_dq import activity_tests as IATIActivityTests
from iati_dq import file_tests as IATIFileTests
import models
import sys, os
from lxml import etree
from datetime import datetime

def create_app():
    return Flask("myapp")

app = create_app()
app.config.from_pyfile('config.py')
celery = Celery(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dataquality.sqlite'
db = SQLAlchemy(app)
db.create_all()

@celery.task(name="myapp.add", callback=None)
def add(x, y):
    return x + y
    return result

def aggregate_results(runtime):
    # get each of the test ids

    test_ids = result.query.filter_by(runtime_id=runtime).group_by('test_id').distinct()
    test_data = []

    for test in test_ids:
        # Get average
        #average = result.query(func.avg(result.result_data).label('average')).filter_by(runtime_id=runtime, test_id=test.test_id)

        # Get maximum for percentage
        score = '1'
        thistest = { 'test': test.test_id, 'score': score }
        test_data.append(thistest)
    return test_data

@app.route("/")
def index():
    runtimes = runtime.query.order_by('id DESC').first()
    #results = result.query.filter_by(runtime_id=runtimes.id).group_by('test_id')
    results = aggregate_results(runtimes.id)    
    return str(results)
    output = "Hi"
    return render_template('dashboard.html', results=results)

@app.route("/result/<task_id>")
def get_result(task_id):
    retval = load_file.AsyncResult(task_id).get(timeout=1.0)
    return retval

@app.route("/resultcheck/<task_id>")
def check_result(task_id):
    retval = load_file.AsyncResult(task_id).status
    return retval

def do_activity_tests(activity, context, file_name):
    # send XML file to tests
    # return results
    # do this for each file and commit to DB
    # but do it asynchronously
    # return a super-massive array

    tests = [ 'check_date', 'title', 'title_size' ]
    result_data = []
    for test in tests:
    	result = getattr(IATIActivityTests, 'test_' + test)(activity)
	result_data.append({'test': test, 'result': result})
    return result_data


def do_file_tests(filedata, context, file_name):
    tests = [ 'unique_identifiers' ]
    result_data = []
    for test in tests:
    	result = getattr(IATIFileTests, 'test_' + test)(filedata)
	result_data.append({'test': test, 'result': result})
    return result_data

@celery.task(name="myapp.load_file", callback=None)
def load_file(file_name, context=None, runtime=None):
    # Need to reference package ID in future, but for now, just fix it...
    package_id = file_name
    output = []
    doc = etree.parse(file_name)
    context = {}
    context['source_file'] = file_name

    output = str(runtime)

    # File-level tests
    output_data = []
    file_tests_data = do_file_tests(doc, context.copy(), file_name)
    
    for file_tests in file_tests_data:
        atest = ""
        aresult = ""

        atest = file_tests["test"]
        aresult = file_tests["result"]

        newresult = result(runtime, package_id, atest, aresult, "")
        db.session.add(newresult)

    # Activity-level tests
    for activity in doc.findall("iati-activity"):
        activity_tests_data = do_activity_tests(activity, context.copy(), file_name)
        for activity_tests in activity_tests_data:
            atest = ""
            aresult = ""

            atest = activity_tests["test"]
            aresult = activity_tests["result"]

            newresult = result(runtime, package_id, atest, aresult, "")
            db.session.add(newresult)


    output = output + "Writing to database..."

    db.session.commit()
    
    output = output + "Written to database."

    return output

def load_package(runtime):
    output = ""
    if (len(sys.argv) > 1):
        packagedir = sys.argv[1]
    else:
        packagedir = ""
    
    path = 'data/' + packagedir
    listing = os.listdir(path)
    totalfiles = len(listing)
    output = output + "Found" + str(totalfiles) + "files."
    filecount = 1
    for infile in listing:
        try:            
            output = output + ""
            output = output + "Loading file" + str(filecount) + "of" + str(totalfiles) + "(" + str(round(((float(filecount)/float(totalfiles))*100),2)) + "%)"
            filecount = filecount +1

            filename = path + '/' + infile
	        # run tests on file
            res = load_file.apply_async((filename, None, runtime))

            # res.task_id is the id of the task
            output = output + '<br />Task ID: <a href="/result/' + res.task_id + '">' + res.task_id + '</a> <a href="/resultcheck/' + res.task_id + '">(check)</a> <br />'
        except Exception, e:
            output = output + "Error in file: " + infile + " - " + str(e) + "\n"
	    pass
    return output

@app.route("/runtests/")
def runtests():

    newrun = runtime()
    db.session.add(newrun)
    db.session.commit()

    output = ""
    output = load_package(newrun.id)
    output = str(output) + "<br />Runtime is <br />" + str(newrun.id)
    return str(output)

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)
