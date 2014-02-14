
#  IATI Data Quality, tools for Data QA on IATI-formatted  publications
#  by Mark Brough, Martin Keegan, Ben Webb and Jennifer Smith
#
#  Copyright (C) 2013  Publish What You Fund
#
#  This programme is free software; you may redistribute and/or modify
#  it under the terms of the GNU Affero General Public License v3.0

import operator
import itertools
import models # damn!

def reform_dict(d):
    def inner(k1):
        matches_first = lambda i: i[0] == k1
        return dict([ (k2, d[(k1, k2)]) for k2 in 
                      map(lambda i: i[1], filter(matches_first, d.keys())) ])

    return dict([ (k1, inner(k1))
                   for k1 in set( k1 for k1, k2 in d.keys() ) ])

def publisher_indicators(indicators, indicators_tests, simple_out):
    # get all tests which belong to a specific indicator
    # average the results for all tests in that indicator
    indicators_out = {}
    for indicator, indicatordata in indicators:
        indicators_out[indicator] = {}
        indicator_test_data = []
        results_pct = 0.0
        results_num = 0.0
        results_weighted_pct_average_numerator = 0.0
        for test, testdata in simple_out.items():
            try:
                testing = (indicator, test)
                if (testing in indicators_tests):
                    results_pct+= simple_out[test]["results_pct"]
                    results_num+= simple_out[test]["results_num"]
                    results_weighted_pct_average_numerator += (simple_out[test]["results_pct"]*simple_out[test]["results_num"])
                    oktest = test
                    indicator_test_data.append(simple_out[test])
            except KeyError:
                pass
        indicators_out[indicator] = {
            "indicator": {
                "id": indicator,
                "name": indicatordata[0],
                "description": indicatordata[1],
                "indicator_type": indicatordata[2],
                "indicator_category_name": indicatordata[3],
                "indicator_subcategory_name": indicatordata[4],
                "longdescription": indicatordata[5], 
                "indicator_noformat": indicatordata[6],
                "indicator_ordinal": indicatordata[7],
                "indicator_order": indicatordata[8],
                "indicator_weight": indicatordata[9]
                },
            "tests": indicator_test_data,
            "results_pct": (results_weighted_pct_average_numerator/results_num),
            "results_num": results_num
            }
    return indicators_out        
    #for test, testdata in simple_out.items():
    #    indicators_out[testdata["indicator"]["id"]] = testdata
    #return indicators_out

def make_summary(test_id, test_name, test_description, test_group, 
                 test_level, results_pct, results_num):
    return {
        "test": {
            "id": test_id,
            "name": test_name,
            "description": test_description,
            "test_group": test_group,
            "test_level": test_level
            },
        "results_pct": results_pct,
        "results_num": results_num
        }

def publisher_simple(out, cdtns):
    simple_out = {}
    hierarchies = set(out)
    tests = set()
    for h in hierarchies:
        tests.update(set(out[h]))
    for t in tests: 
        results_pct = 0.0
        results_num = 0.0
        results_weighted_pct_average_numerator = 0.0
        for hierarchy in hierarchies:
            try:
                key = (t,'activity hierarchy', str(hierarchy)) 
                try:
                    if ((cdtns) and (key in cdtns) and (cdtns[key][0]==0)):
                        continue
                except KeyError:
                    pass
                results_pct+= out[hierarchy][t]["results_pct"]
                results_num+= out[hierarchy][t]["results_num"]
                results_weighted_pct_average_numerator += (out[hierarchy][t]["results_pct"]*out[hierarchy][t]["results_num"])
                okhierarchy = hierarchy
            except KeyError:
                pass

        tmp = make_summary(
            out[okhierarchy][t]['test']["id"],
            out[okhierarchy][t]['test']["name"],
            out[okhierarchy][t]['test']["description"],
            out[okhierarchy][t]['test']["test_group"],
            out[okhierarchy][t]['test']["test_level"],
            (results_weighted_pct_average_numerator/results_num),
            results_num
            )
        tmp["indicator"] = out[okhierarchy][t]['indicator']
        simple_out[t] = tmp
    return simple_out

def sum_for_publishers(packages, d, h, t):
    # aggregate data across multiple packages for a single publisher
        
    # for each package, add percentage for each
    total_pct = 0
    total_activities = 0

    # need below to only include packages that are in this hierarchy
    packages_in_hierarchy = 0

    relevant = lambda p: (h, t, p) in d
    relevant_data = map(lambda p: d[(h, t, p)], filter(relevant, packages))

    pct = lambda i: i[2]
    activities = lambda i: i[3]

    try:
        total_pct = reduce(operator.add, map(pct, relevant_data))
        total_activities = reduce(operator.add, map(activities, relevant_data))
    except Exception:
        total_pct = 0.0
        total_activities = 0
    packages_in_hierarchy = len(relevant_data)

    if total_activities <= 0:
        return {}

    ok_tdata = relevant_data[-1] ## FIXME: this is obviously wrong

    test_id = ok_tdata[1]
    test = models.Test.query.filter(models.Test.id == test_id).first()
         
    tmp = make_summary(
        test.id,
        test.name,
        test.description,
        test.test_group,
        test.test_level,
        int(float(total_pct/packages_in_hierarchy)),
        total_activities
        )
    tmp["indicator"] = ok_tdata[0]
    tmp["result_hierarchy"] = total_activities
    return tmp

def summarise_results(conditions, mode, hierarchies, 
                      tests, cdtns, indicators,
                      indicators_tests, packages, d, summary):

    def summaries(summary_f):
        for h, t in itertools.product(hierarchies, tests):
            yield h, t, summary_f(h, t)

    def add_condition(i):
        h, t, tdata = i
        if conditions:
            key = (t, 'activity hierarchy', str(h))
            if key in cdtns:
                tdata["condition"] = cdtns[key]
        return h, t, tdata


    summaries = (add_condition(i) for i in summaries(summary))

    tmp_out = dict([ ((h, t), tdata) for h, t, tdata in summaries ])
    out = reform_dict(tmp_out)

    has_keys = lambda kvp: len(kvp[1])
    out = dict([ 
            (K, dict(filter(has_keys, V.items()))) 
            for K, V in out.items() 
            ])

    if mode != "publisher_indicators":
        return out

    simple_out = publisher_simple(out, cdtns)
    return publisher_indicators(indicators, indicators_tests, simple_out)


class Summary(object):
    def __init__(self, data, conditions=None, manual=False):
        self.data = data
        self.conditions = conditions
        self.manual = manual
        self._summary = self.calculate()

    def calculate(self):
        mode = self.get_mode()

        if self.manual:
            return self.aggregate()

        def replace_first(tupl, newval):
            return tuple([newval] + list(tupl)[1:])
        switch_first = lambda t: replace_first(t, t[0].as_dict())
        self.data = map(switch_first, self.data)

        return self.aggregate()

    def summary(self):
        return self._summary

    def get_mode(self):
        raise

    def gen_hierarchies(self):
        for i in set(map(lambda x: (x[4]), self.data)):
            yield i

    def gen_tests(self):
        for i in set(map(lambda x: (x[1]), self.data)):
            yield i

    def get_conditions(self):
        if not self.conditions:
            return None

        return dict(map(lambda x: (
                    (x.test_id, x.condition, x.condition_value),
                    (x.operation, x.description)
                    ), self.conditions))

    def restructure_data(self):
        # (h, t, p) -> _
        # h: hierarchy
        # t: test
        # p: ???
        return lambda x: ((x[4], x[1], x[5]), (x))

    def setmap(self, lam):
        return set(map(lam, self.data))

    def aggregate(self):
        hierarchies = self.gen_hierarchies()
        tests = self.gen_tests()
        cdtns = self.get_conditions()
    
        d_f = self.restructure_data()

        d = dict(map(d_f, self.data))

        ind_f = lambda x: (
            x[0]["id"], (
                x[0]["name"], 
                x[0]["description"], 
                x[0]["indicator_type"], 
                x[0]["indicator_category_name"], 
                x[0]["indicator_subcategory_name"], 
                x[0]["longdescription"], 
                x[0]["indicator_noformat"], 
                x[0]["indicator_ordinal"], 
                x[0]["indicator_order"], 
                x[0]["indicator_weight"]
                )
            )
        indicators = self.setmap(ind_f)

        ind_test_f = lambda x: (x[0]["id"], x[1])
        indicators_tests = list(self.setmap(ind_test_f))

        pkg_f = lambda x: x[5]
        packages = self.setmap(pkg_f)

        summary = lambda h, t: sum_for_publishers(packages, d, h, t)

        return summarise_results(self.conditions, self.get_mode(), hierarchies, 
                                 tests, cdtns, indicators,
                                 indicators_tests, packages, d, summary)


class PublisherSummary(Summary):
    def get_mode(self):
        return "publisher"


class PublisherIndicatorsSummary(PublisherSummary):
    def get_mode(self):
        return "publisher_indicators"

