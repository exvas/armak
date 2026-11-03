# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WorkshopSettings(Document):
	def validate(self):
		seen = set()
		for row in self.branches:
			if row.branch in seen:
				frappe.throw(_("Row {0}: branch {1} is listed twice").format(row.idx, row.branch))
			seen.add(row.branch)
			for warehouse in (
				row.materials_warehouse,
				row.production_warehouse,
				row.finished_goods_warehouse,
			):
				if not warehouse:
					continue
				wh_company = frappe.db.get_value("Warehouse", warehouse, "company")
				if wh_company != row.company:
					frappe.throw(
						_("Row {0}: warehouse {1} belongs to {2}, not {3}").format(
							row.idx, warehouse, wh_company, row.company
						)
					)


def get_branch_settings(branch):
	"""The Workshop Branch row of `branch`, or None."""
	settings = frappe.get_cached_doc("Workshop Settings")
	return next((row for row in settings.branches if row.branch == branch), None)
