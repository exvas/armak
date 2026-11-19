# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from armak.workshop.registration import normalize_gun_number


class Gun(Document):
	def before_insert(self):
		# gun numbers are typed from the gun itself; keep one spelling so search and history match.
		# before_insert runs before naming, so the name gets the same spelling
		self.gun_number = normalize_gun_number(self.gun_number)

	def validate(self):
		if self.customer and not frappe.db.get_value("Customer", self.customer, "mobile_no"):
			frappe.throw(
				_(
					"Customer {0} has no mobile number. The mobile number is the workshop's Customer ID."
				).format(self.customer),
				title=_("Mobile Number Required"),
			)
