
#  IATI Data Quality, tools for Data QA on IATI-formatted  publications
#  by Mark Brough, Martin Keegan, Ben Webb and Jennifer Smith
#
#  Copyright (C) 2013  Publish What You Fund
#
#  This programme is free software; you may redistribute and/or modify
#  it under the terms of the GNU Affero General Public License v3.0

from flask import flash, redirect, url_for

from iatidq import dqregistry


def registry_refresh():
    dqregistry.refresh_packages()
    return "Refreshed"


def registry_deleted():
    num_deleted = dqregistry.check_deleted_packages()
    if num_deleted > 0:
        msg = '%s packages were set to deleted' % num_deleted
    else:
        msg = "No packages were set to deleted"

    flash(msg, '')
    return redirect(url_for('packages_manage'))
