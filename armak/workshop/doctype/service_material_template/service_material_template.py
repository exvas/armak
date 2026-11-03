# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ServiceMaterialTemplate(Document):
	def validate(self):
		seen = set()
		for row in self.items:
			if row.item_code in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, row.item_code))
			seen.add(row.item_code)
			if frappe.db.get_value("Item", row.item_code, "is_stock_item") != 1:
				frappe.throw(_("Row {0}: {1} is not a stock item").format(row.idx, row.item_code))
