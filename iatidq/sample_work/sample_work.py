#!/usr/bin/env python

import os
import random
import re
import uuid

import psycopg2
from psycopg2.extensions import adapt
import requests
import lxml.etree

from iatidataquality import app
from iatidq import models
from test_mapping import test_to_kind
import db


class NoIATIActivityFound(Exception):
    pass


def all_tests():
    sampling_tests = []
    all_tests = {test.description: test for test in models.Test.all()}
    for k in test_to_kind.keys():
        sampling_tests.append(all_tests[k])
    return sorted(sampling_tests, key=lambda x: x.description)


def all_orgs():
    all_orgs = models.Organisation.all()
    sample_org_ids = [x[0] for x in db.all_sample_orgs()]
    sample_orgs = filter(lambda x: x.id in sample_org_ids, all_orgs)
    return sorted(sample_orgs, key=lambda x: x.organisation_name)


def save_url(url, filename):
    resp = requests.get(url)
    with open(filename, 'w') as f:
        f.write(resp.content)


def query(*args, **kwargs):
    db_config = app.config['DATABASE_INFO']
    db = psycopg2.connect(**db_config)
    c = db.cursor()
    c.execute(*args)
    if kwargs.get("write"):
        db.commit()
    else:
        return c.fetchall()


class WorkItems(object):
    def __init__(self, org_ids, test_ids, create):
        self.org_ids = org_ids
        self.test_ids = test_ids

        query('''DROP TABLE IF EXISTS current_data_result;''', write=True)
        query('''DROP TABLE IF EXISTS sampling_current_result_tmp;''', write=True)
        query('''DROP TABLE IF EXISTS sampling_current_result;''', write=True)

        query('''CREATE TABLE current_data_result AS
                 SELECT * FROM result
                 WHERE test_id = 46
                 AND result_data > 0;''', write=True)

        query('''CREATE TABLE sampling_current_result_tmp AS
                   SELECT * FROM result
                   WHERE test_id = ANY(%s)
                   AND result_data > 0;''', (test_ids,), write=True)

        query('''CREATE TABLE sampling_current_result AS
                   SELECT sampling_current_result_tmp.* FROM sampling_current_result_tmp, current_data_result
                   WHERE sampling_current_result_tmp.result_identifier = current_data_result.result_identifier;''', write=True)

        self.update = not create

    def test_desc_of_test_id(self, test_id):
        results = query('''select description from test where id = %s;''', (test_id,));
        assert len(results) == 1
        return results[0][0]

    def kind_of_test(self, test_id):
        test_desc = self.test_desc_of_test_id(test_id)
        return test_to_kind[test_desc]

    def __iter__(self):
        total_samples = 20
        for org_id in self.org_ids:
            print("Org: {}".format(org_id))
            for test_id in self.test_ids:
                if self.update:
                    total_samples_done = db.count_samples(
                        org_id=org_id, test_id=test_id)
                    total_samples_todo = total_samples - total_samples_done
                else:
                    total_samples_todo = total_samples
                print("Test: {}".format(test_id))
                print('{} samples to add'.format(total_samples_todo))
                sot = SampleOrgTest(org_id, test_id)
                sample_ids = sot.sample_activity_ids(total_samples_todo)

                test_kind = self.kind_of_test(test_id)

                for act_id in sample_ids:
                    try:
                        act = sot.xml_of_activity(act_id)
                        parent_act = sot.xml_of_parent_activity(act_id)
                    except:
                        continue

                    u = str(uuid.uuid4())

                    args = {
                        "uuid": u,
                        "organisation_id": org_id,
                        "test_id": test_id,
                        "activity_id": act_id[0],
                        "package_id": act_id[1],
                        "xml_data": act,
                        "xml_parent_data": parent_act,
                        "test_kind": test_kind
                        }

                    yield args


class SampleOrgTest(object):
    def __init__(self, organisation_id, test_id):
        self.org_id = organisation_id
        self.test_id = test_id

        if self.qualifies():
            self.activities = self.activity_ids()
        else:
            self.activities = []

    def qualifies(self):
        rows = query('''select result_data from sampling_current_result
                          where organisation_id = %s
                            and test_id = %s
                            and result_data != 0''',
                     [self.org_id, self.test_id])
        return len(rows) >= 1

    def activity_ids(self):
        rows = query('''select result_identifier, package_name from sampling_current_result
                          left join package on sampling_current_result.package_id = package.id
                          where organisation_id = %s
                            and test_id = %s
                            and result_data = 1''',
                     [self.org_id, self.test_id])
        ids = [ i for i in rows ]
        return ids

    def sample_activity_ids(self, max):
        act_ids = [i for i in self.activities]
        random.shuffle(act_ids)
        return act_ids[:max]

    def xml_of_package(self, package_name):
        filename = package_name + '.xml'
        path = os.path.join(app.config['DATA_STORAGE_DIR'], filename)
        return lxml.etree.parse(path)

    def xml_of_activity(self, activity):
        activity_id, pkg = activity
        xml = self.xml_of_package(pkg)

        xpath_str = '//iati-activity[iati-identifier/text()="%s"]'

        activities = xml.xpath(xpath_str % activity_id)
        if 0 == len(activities):
            raise NoIATIActivityFound
        # Some publishers are re-using iati identifiers, so unfortunately
        # we can't rely on this assertion.
        # At least we know we have >0 though.
        # assert len(activities) == 1
        return lxml.etree.tostring(activities[0], pretty_print=True)

    def xml_of_parent_activity(self, activity):
        activity_id, pkg = activity
        xml = self.xml_of_package(pkg)

        xpath_str = '//iati-activity[iati-identifier/text()="%s"]'
        activities = xml.xpath(xpath_str % activity_id)

        # More than one IATI activity could be found (if a publisher re-using
        # iati-identifiers, but should be >0.
        assert len(activities) > 0
        activity_xml = activities[0]

        xpath_str = '''related-activity[@type='1']/@ref'''
        related_activity_ids = activity_xml.xpath(xpath_str)

        count_relateds = len(related_activity_ids)
        if 0 == count_relateds:
            return None

        assert 0 < count_relateds

        xpath_str = '''//iati-activity[iati-identifier/text()="%s"]'''

        parent_id = related_activity_ids[0]

        try:
            return lxml.etree.tostring(xml.xpath(xpath_str % parent_id)[0])
        except IndexError:
            return None


class DocumentLink(object):
    def __init__(self, url, title, elt, codelists):
        self.elt = elt
        self.title = title
        self.url = url
        self.codelists = codelists

    def __repr__(self):
        return '''<DocumentLink: %s>''' % self.url

    def to_dict(self):
        def getCategory(category, codelists):
            return {"category": codelists.get(category, 'ERROR'),
                    "category_code": category}

        def getCategories(categories, codelists):
            return [ getCategory(category, codelists) for category in categories ]

        data = {
            "name": self.title,
            "url": self.url,
            "categories": getCategories(self.elt.xpath('category/@code'),
                                       self.codelists)
            }
        return data


class DocumentLinks(object):
    def __init__(self, xml_string, codelists):
        root = lxml.etree.fromstring(xml_string)
        self.root = root
        self.codelists = codelists

    def get_elt_text(self, elt, key):
        # IATI 2.01
        res = elt.xpath(key + '/narrative/text()')
        if not res:
            # IATI 1.05
            res = elt.xpath(key + '/text()')
        return res

    def get_links(self):
        for i in self.root.iterfind('document-link'):
            url = i.attrib.get("url")
            title = self.get_elt_text(i, 'title')
            codelists = self.codelists
            yield DocumentLink(url, title, i, codelists)


class Location(object):
    def __init__(self, elt):
        self.elt = elt
        self.point_re = re.compile(r"\s*([^\s]+)\s+([^\s]+)")

    def __repr__(self):
        return '''<Location: %s>''' % self.elt

    def get_elt_text(self, elt, key):
        # IATI 2.01
        res = elt.xpath(key + '/narrative/text()')
        if not res:
            # IATI 1.05
            res = elt.xpath(key + '/text()')
        return res

    def get_point(self, elt):
        point = elt.xpath('point/pos/text()')
        if point:
            res = self.point_re.match(point[0])
            if res:
                return res.groups()
        return elt.xpath('coordinates/@latitude'), elt.xpath('coordinates/@longitude')

    def to_dict(self):
        lat, lng = self.get_point(self.elt)
        data = {
            "name": self.get_elt_text(self.elt, 'name'),
            "description": self.get_elt_text(self.elt, 'description'),
            "latitude": lat,
            "longitude": lng,
            }
        return data


class Locations(object):
    def __init__(self,xml_string):
        root = lxml.etree.fromstring(xml_string)
        self.root = root

    def get_locations(self):
        for i in self.root.iterfind('location'):
            yield Location(i)


class Period(object):
    def __init__(self, elt):
        self.elt = elt

    def to_dict(self):
        def format_pct(value):
            return '<div class="progress"><div class="progress-bar" style="width: ' + str(round(value,2)) + '%;"></div></div>'

        def calc_pct(target, actual):
            if (target and actual):
                try:
                    target = re.sub(",", "", target[0])
                    target = re.sub("%", "", target)
                    actual = re.sub(",", "", actual[0])
                    actual = re.sub("%", "", actual)
                    return format_pct((float(actual) / float(target)) * 100.00)
                except Exception, e:
                    return ""

        data = {
            'start_date': self.elt.xpath('period-start/@iso-date'),
            'end_date': self.elt.xpath('period-end/@iso-date'),
            'target': self.elt.xpath('target/@value'),
            'actual': self.elt.xpath('actual/@value'),
            'pct': calc_pct(self.elt.xpath('target/@value'),
                            self.elt.xpath('actual/@value'))
        }
        return data


class Indicator(object):
    def __init__(self,elt):
        self.elt = elt

    def elt_text_or_BLANK(self, key):
        elt = self.elt.find(key)
        if elt is not None and elt.find("narrative") is not None:
            elt = elt.find("narrative")
        return getattr(elt, "text", "")

    def to_dict(self):
        def get_period(period):
            return Period(period).to_dict()

        def get_periods(periods):
            return [ get_period(period)
                        for period in periods ]
        data = {
            "title": self.elt_text_or_BLANK("title"),
            "description": self.elt_text_or_BLANK("description"),
            "periods": get_periods(self.elt.xpath('period')),
        }
        return data


class Result(object):
    def __init__(self, elt):
        self.elt = elt

    def __repr__(self):
        return '''<Result: %s>''' % self.elt

    def elt_text_or_BLANK(self, key):
        elt = self.elt.find(key)
        if elt is not None and elt.find("narrative") is not None:
            elt = elt.find("narrative")
        return getattr(elt, "text", "")

    def to_dict(self):
        def get_indicator(indicator):
            return Indicator(indicator).to_dict()

        def get_indicators(indicators):
            return [ get_indicator(indicator)
                        for indicator in indicators ]

        data = {
            "title": self.elt_text_or_BLANK("title"),
            "description": self.elt_text_or_BLANK("description"),
            "indicators": get_indicators(self.elt.xpath('indicator')),
            }
        return data


class Results(object):
    def __init__(self, xml_string):
        root = lxml.etree.fromstring(xml_string)
        self.root = root

    def get_results(self):
        for i in self.root.iterfind('result'):
            yield Result(i)


class Condition(object):
    def __init__(self, elt):
        self.elt = elt

    def __repr__(self):
        return '''<Condition: %s>''' % self.elt

    def to_dict(self):
        texts = [{'text': x} for x in self.elt.xpath('narrative/text()')]
        if len(texts) == 0:
            texts = [{'text': self.elt.text}]
        data = {
            "type": self.elt.xpath("@type"),
            "texts": texts,
            }
        return data


class Conditions(object):
    def __init__(self, xml_string):
        root = lxml.etree.fromstring(xml_string)
        self.root = root

    def get_conditions(self):
        return {
            'attached': self.root.xpath("conditions/@attached"),
            'conditions': [Condition(condition).to_dict() for condition in self.root.xpath('conditions/condition')]}


class ActivityInfo(object):
    def __init__(self, xml_string):
        self.root = lxml.etree.fromstring(xml_string)
        self.titles = self.elt_text_or_MISSING("title")
        self.descriptions = self.elt_text_or_MISSING("description")

    def elt_text_or_MISSING(self, key):
        elt = self.root.xpath('{}/narrative/text()'.format(key))
        if len(elt) > 0:
            return [{'text': x} for x in elt]
        elt = self.root.xpath('{}/text()'.format(key))
        if len(elt) > 0:
            return [{'text': x} for x in elt]
        return [{'text': 'MISSING'}]
