
#  IATI Data Quality, tools for Data QA on IATI-formatted  publications
#  by Mark Brough, Martin Keegan, Ben Webb and Jennifer Smith
#
#  Copyright (C) 2013  Publish What You Fund
#
#  This programme is free software; you may redistribute and/or modify
#  it under the terms of the GNU Affero General Public License v3.0

from iatidq import db

from sqlalchemy import func

import summary

import models
import csv
import util
import unicodecsv

def checkCondition(row):
    if (('packagegroup_condition' in row) and (row['packagegroup_condition']!='')):
        return row['packagegroup_condition']
    else:
        return None

def importOrganisationPackagesFromFile(filename, organisation_c=None, organisation_n=None):
    with file(filename) as fh:
        return _importOrganisationPackages(organisation_c, organisation_n, fh, True)

def _importOrganisationPackages(organisation_c, organisation_n, fh, local):
    def get_checkp_code_name():
        if organisation_c is None:
            return (
                organisations(row['organisation_code']),
                row['organisation_code'],
                row['organisation_name']
                )
        return (
            organisations(organisation_c),
            organisation_c,
            organisation_n
            )

    def get_organisation(checkP):
        if checkP:
            return checkP
        return addOrganisation(
            {"organisation_name": organisation_name,
             "organisation_code": organisation_code
             })
    
    def get_packages(organisation_code):
        return models.Package.query.filter(
            models.PackageGroup.publisher_iati_id==organisation_code
            ).join(models.PackageGroup).all()

    def get_packagegroup(organisation_code):
        return models.PackageGroup.query.filter(
            models.PackageGroup.publisher_iati_id==organisation_code
            ).all()

    checkP, organisation_code, organisation_name = get_checkp_code_name()

    data = unicodecsv.DictReader(fh)

    for row in data:
        condition = checkCondition(row)
        organisation = get_organisation(checkP)

        print organisation_code
        for package in get_packages(organisation_code):
                        organisationpackage = addOrganisationPackage({
                                "organisation_id" : organisation.id,
                                "package_id" : package.id,
                                "condition": condition
                                })

        for packagegroup in get_packagegroup(organisation_code):
                organisationpackagegroup = addOrganisationPackageGroup({
                        "organisation_id" : organisation.id,
                        "packagegroup_id" : packagegroup.id,
                        "condition": condition
                        })
        if (('packagegroup_name' in row) and (row['packagegroup_name'] != "")):
            packagegroup = models.PackageGroup.query.filter(
                models.PackageGroup.name == row['packagegroup_name']
                ).first()
            data = {
                'packagegroup_id': packagegroup.id,
                'organisation_id': organisation.id,
                'condition': condition
                }
            addOrganisationPackageFromPackageGroup(data)
                
    print "Imported successfully"
    return True

def organisations(organisation_code=None):
    if organisation_code is None:
        return models.Organisation.query.all()
    else:
        return models.Organisation.query.filter_by(organisation_code=organisation_code).first()

def organisationPackages(organisation_code=None):
    if organisation_code is None:
        return False

    return db.session.query(models.Package,
                            models.OrganisationPackage
                        ).filter(
                        models.Organisation.organisation_code==organisation_code
                        ).join(models.OrganisationPackage
                        ).join(models.Organisation
                        ).all()

def organisationPackageGroups(organisation_code=None):
    if organisation_code is not None:
        organisationpackagegroups = db.session.query(models.PackageGroup,
                                             models.OrganisationPackageGroup
                        ).filter(models.Organisation.organisation_code==organisation_code
                        ).join(models.OrganisationPackageGroup
                        ).join(models.Organisation
                        ).all()
        return organisationpackagegroups
    else:
        return False

def addOrganisation(data):
    checkP = models.Organisation.query.filter_by(organisation_code=data["organisation_code"]).first()
    if not checkP:
        newP = models.Organisation()
        newP.setup(
            organisation_name = data["organisation_name"],
            organisation_code = data["organisation_code"]
        )
        db.session.add(newP)
        db.session.commit()
        return newP
    else:
        return False

def updateOrganisation(organisation_code, data):
    checkP = models.Organisation.query.filter_by(organisation_code=organisation_code).first()
    if (checkP is not None):
        checkP.organisation_code = data["organisation_code"]
        checkP.organisation_name = data["organisation_code"]
        db.session.add(checkP)
        db.session.commit()
        return checkP
    else:
        return False

def addOrganisationPackage(data):
    checkPP=models.OrganisationPackage.query.filter_by(organisation_id=data['organisation_id'], package_id=data['package_id']
                ).first()
    if (checkPP is None):
        newPP = models.OrganisationPackage()
        newPP.setup(
            organisation_id = data["organisation_id"],
            package_id = data["package_id"],
            condition = data["condition"]
        )
        db.session.add(newPP)
        db.session.commit()
        return newPP
    else:
        return False

def addOrganisationPackageGroup(data):
    checkPG=models.OrganisationPackageGroup.query.filter_by(organisation_id=data['organisation_id'], packagegroup_id=data['packagegroup_id']
                ).first()
    if (checkPG is None):
        newPG = models.OrganisationPackageGroup()
        newPG.setup(
            organisation_id = data["organisation_id"],
            packagegroup_id = data["packagegroup_id"],
            condition = data["condition"]
        )
        db.session.add(newPG)
        db.session.commit()
        return newPG
    else:
        # Confirm that it's already been added
        return checkPG

def addOrganisationPackageFromPackageGroup(data):
    packages = models.Package.query.filter_by(package_group=data['packagegroup_id']
            ).all()
    count_packages = 0
    for package in packages:
        packagedata = {
            'organisation_id': data['organisation_id'],
            'package_id': package.id,
            'condition': data["condition"]
        }
        if addOrganisationPackage(packagedata):
            count_packages+=1
    if count_packages >0:
        return count_packages
    else:
        return False

def deleteOrganisationPackage(organisation_code, package_name, organisationpackage_id):
    checkPP = models.OrganisationPackage.query.filter_by(id=organisationpackage_id).first()
    if checkPP:
        db.session.delete(checkPP)
        db.session.commit()
        return checkPP
    else:
        return False

def addFeedback(data):
    checkF=models.OrganisationConditionFeedback.query.filter_by(uses=data["uses"], element=data["element"], where=data["where"]
            ).first()
    if not checkF:
        feedback = models.OrganisationConditionFeedback()
        feedback.organisation_id=data["organisation_id"]
        feedback.uses=data["uses"]
        feedback.element=data["element"]
        feedback.where=data["where"]
        db.session.add(feedback)
        db.session.commit()
        return feedback
    else:
        return False

def _organisation_detail_ungrouped(organisation):
    return db.session.query(models.Indicator,
                                     models.Test,
                                     models.AggregateResult.results_data,
                                     models.AggregateResult.results_num,
                                     models.AggregateResult.result_hierarchy,
                                     models.AggregateResult.package_id,
                                     func.max(models.AggregateResult.runtime_id)
        ).filter(models.Organisation.id==organisation.id)

def _organisation_detail(organisation):
    aggregate_results = _organisation_detail_ungrouped(organisation)\
        .group_by(models.Indicator,
                   models.AggregateResult.result_hierarchy, 
                   models.Test, 
                   models.AggregateResult.package_id,
                   models.AggregateResult.results_data,
                   models.AggregateResult.results_num
        ).join(models.IndicatorTest
        ).join(models.Test
        ).join(models.AggregateResult
        ).join(models.Package
        ).join(models.OrganisationPackage
        ).join(models.Organisation
        ).all()

    pconditions = models.OrganisationCondition.query.filter_by(organisation_id=organisation.id
            ).all()

    db.session.commit()
    return summary.agr_results(aggregate_results, 
                                   conditions=pconditions, 
                                   mode="publisher")

def _organisation_indicators(organisation, aggregation_type=2):
    aggregate_results = db.session.query(models.Indicator,
                                     models.Test,
                                     models.AggregateResult.results_data,
                                     models.AggregateResult.results_num,
                                     models.AggregateResult.result_hierarchy,
                                     models.AggregateResult.package_id,
                                     func.max(models.AggregateResult.runtime_id)
        ).filter(models.Organisation.organisation_code==organisation.organisation_code
        ).filter(models.AggregateResult.aggregateresulttype_id == aggregation_type
        ).filter(models.AggregateResult.organisation_id == organisation.id
        ).group_by(models.AggregateResult.result_hierarchy, 
                   models.Test, 
                   models.AggregateResult.package_id,
                   models.Indicator,
                   models.AggregateResult.results_data,
                   models.AggregateResult.results_num,
                   models.AggregateResult.package_id
        ).join(models.IndicatorTest
        ).join(models.Test
        ).join(models.AggregateResult
        ).join(models.Package
        ).join(models.OrganisationPackage
        ).join(models.Organisation
        ).all()

    pconditions = models.OrganisationCondition.query.filter_by(organisation_id=organisation.id
            ).all()

    return summary.agr_results(aggregate_results, 
                                                conditions=pconditions, 
                                                mode="publisher_indicators")

def _organisation_indicators_split(organisation, aggregation_type=2):
    results = _organisation_indicators(organisation, aggregation_type)

    zero = lambda kv: not kv[1]["results_pct"]
    non_zero = lambda kv: kv[1]["results_pct"]

    zero_results = dict(filter(zero, results.iteritems()))
    non_zero_results = dict(filter(non_zero, results.iteritems()))

    return { "zero": zero_results,
             "non_zero": non_zero_results }
